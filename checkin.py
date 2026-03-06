import sys
import tty
import termios
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from garmin import get_last_run, get_recent_runs
from db import save_run, save_comparisons, compute_and_save_elo

load_dotenv()

console = Console()

COMPARISON_OPTIONS = [
    ("1", "EASIER", "green"),
    ("2", "SAME",   "yellow"),
    ("3", "HARDER", "red"),
]

GENERAL_OPTIONS = [
    ("1", "EASY",   "green"),
    ("2", "MEDIUM", "yellow"),
    ("3", "HARD",   "red"),
]


def _read_keypress(valid: set) -> tuple:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in valid:
                return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def prompt_feel_general():
    console.print()
    console.print("  How hard was this run overall?  [dim](press 1, 2, or 3)[/dim]")
    console.print()
    for key, label, color in GENERAL_OPTIONS:
        console.print(f"    [{color} bold]({key})[/{color} bold]  [{color}]{label}[/{color}]")
    console.print()
    ch = _read_keypress({"1", "2", "3"})
    label, color = next((lbl, col) for k, lbl, col in GENERAL_OPTIONS if k == ch)
    console.print(f"  [{color} bold]{label}[/{color} bold]")
    return label.lower()


def prompt_pairwise_comparisons(today_run, comparison_runs):
    """Ask the user to compare today's run against each past run individually.
    Returns a list of {other_date, result} dicts."""
    if not comparison_runs:
        return []

    console.print()
    console.rule("[dim]Run Comparisons[/dim]")
    console.print()
    console.print("  Compare today's run to each recent run. Was today [green]easier[/green], [yellow]same[/yellow], or [red]harder[/red]?")
    console.print()

    results = []
    for past_run in comparison_runs:
        date_str = past_run["date"][:10]
        dist = past_run["distance_mi"]
        pace = past_run.get("avg_pace_min_mi") or past_run.get("avg_pace", "?")
        hr_str = f"  HR {past_run['avg_hr']:.0f}" if past_run.get("avg_hr") else ""

        console.print(f"  [dim]{date_str}[/dim]  {dist} mi  {pace}{hr_str}")
        for key, label, color in COMPARISON_OPTIONS:
            console.print(f"    [{color} bold]({key})[/{color} bold]  [{color}]{label}[/{color}]")

        ch = _read_keypress({"1", "2", "3"})
        label, color = next((lbl, col) for k, lbl, col in COMPARISON_OPTIONS if k == ch)
        console.print(f"  → [{color} bold]{label}[/{color} bold]")
        console.print()

        results.append({"other_date": date_str, "result": label.lower()})

    return results


def run_checkin():
    console.print()
    console.rule("[bold]Tobu — Post-Run Check-In[/bold]")
    console.print()

    with console.status("[dim]Fetching your last run from Garmin...[/dim]", spinner="dots"):
        current_run = get_last_run()

    if not current_run:
        console.print("[red]No run found.[/red]")
        return

    # Today's run summary
    date_str = current_run["date"][:10]
    console.print(f"  [bold]Today's run[/bold]  [dim]{date_str}[/dim]")
    console.print()

    run_table = Table(box=None, show_header=False, padding=(0, 2))
    run_table.add_column(style="dim")
    run_table.add_column(style="bold")
    run_table.add_row("Distance",  f"{current_run['distance_mi']} mi")
    run_table.add_row("Pace",      str(current_run['avg_pace_min_mi']))
    run_table.add_row("Avg HR",    f"{current_run['avg_hr']:.0f} bpm")
    run_table.add_row("Duration",  f"{current_run['duration_min']} min")
    console.print(run_table)

    # Recent runs comparison
    with console.status("[dim]Fetching recent runs...[/dim]", spinner="dots"):
        recent = get_recent_runs(days=7)

    today_date = current_run["date"][:10]
    comparison_runs = [r for r in recent if not r["date"].startswith(today_date)]

    console.print()

    if comparison_runs:
        display_runs = comparison_runs[:3]
        console.print(f"  [bold]Your last {len(display_runs)} run(s)[/bold]  [dim]past 2 weeks[/dim]")
        console.print()

        hist_table = Table(box=None, show_header=False, padding=(0, 2))
        hist_table.add_column(style="dim")
        hist_table.add_column(style="dim")
        hist_table.add_column(style="dim")
        hist_table.add_column(style="dim")
        for r in display_runs:
            hr_str = f"HR {r['avg_hr']:.0f}" if r["avg_hr"] else ""
            hist_table.add_row(
                r["date"][:10],
                f"{r['distance_mi']} mi",
                str(r["avg_pace_min_mi"]),
                hr_str,
            )
        console.print(hist_table)

        feel = "compared"  # placeholder — actual feel comes from pairwise comparisons
        comparisons = prompt_pairwise_comparisons(current_run, comparison_runs)
    else:
        console.print("  [dim]No runs in the past 2 weeks — rating on general feel.[/dim]")
        feel = prompt_feel_general()
        comparisons = []

    console.print()
    notes_raw = console.input("  [dim]Any notes? (press Enter to skip) →[/dim] ").strip()
    notes = notes_raw or None

    current_run["feel"] = feel
    current_run["notes"] = notes
    save_run(current_run)

    if comparisons:
        today_date = current_run["date"][:10]
        save_comparisons(today_date, comparisons)
        compute_and_save_elo()
        harder = sum(1 for c in comparisons if c["result"] == "harder")
        easier = sum(1 for c in comparisons if c["result"] == "easier")
        same   = sum(1 for c in comparisons if c["result"] == "same")
        console.print()
        console.rule()
        console.print(
            f"\n  Saved  [red bold]{harder} harder[/red bold]  "
            f"[yellow bold]{same} same[/yellow bold]  "
            f"[green bold]{easier} easier[/green bold]"
            + (f"  [dim]— \"{notes}\"[/dim]" if notes else "")
        )
    else:
        feel_color = {"easy": "green", "medium": "yellow", "hard": "red"}.get(feel, "white")
        console.print()
        console.rule()
        console.print(f"\n  Saved  [{feel_color} bold]{feel.upper()}[/{feel_color} bold]"
                      + (f"  [dim]— \"{notes}\"[/dim]" if notes else ""))

    return current_run, feel, notes, comparisons


if __name__ == "__main__":
    run_checkin()
