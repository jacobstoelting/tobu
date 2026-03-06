import sys
import tty
import termios
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from garmin import get_last_run, get_recent_runs
from db import save_run

load_dotenv()

console = Console()

FEEL_OPTIONS = {
    "comparison": [
        ("1", "EASIER", "green"),
        ("2", "SAME",   "yellow"),
        ("3", "HARDER", "red"),
    ],
    "general": [
        ("1", "EASY",   "green"),
        ("2", "MEDIUM", "yellow"),
        ("3", "HARD",   "red"),
    ],
}


def prompt_feel(mode="comparison"):
    options = FEEL_OPTIONS[mode]

    console.print()
    if mode == "comparison":
        console.print("  How did this run feel [dim]compared to your recent runs?[/dim]  [dim](press 1, 2, or 3)[/dim]")
    else:
        console.print("  How hard was this run overall?  [dim](press 1, 2, or 3)[/dim]")
    console.print()

    for key, label, color in options:
        console.print(f"    [{color} bold]({key})[/{color} bold]  [{color}]{label}[/{color}]")

    console.print()
    valid = {k for k, _, _ in options}
    while True:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if ch in valid:
            label, color = next((label, color) for k, label, color in options if k == ch)
            console.print(f"  [{color} bold]{label}[/{color} bold]")
            return label.lower()


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
        recent = get_recent_runs(days=14)

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

        feel = prompt_feel("comparison")
    else:
        console.print("  [dim]No runs in the past 2 weeks — rating on general feel.[/dim]")
        feel = prompt_feel("general")

    console.print()
    notes_raw = console.input("  [dim]Any notes? (press Enter to skip) →[/dim] ").strip()
    notes = notes_raw or None

    current_run["feel"] = feel
    current_run["notes"] = notes
    save_run(current_run)

    feel_color = {"easier": "green", "easy": "green",
                  "same": "yellow", "medium": "yellow",
                  "harder": "red", "hard": "red"}.get(feel, "white")

    console.print()
    console.rule()
    console.print(f"\n  Saved  [{feel_color} bold]{feel.upper()}[/{feel_color} bold]"
                  + (f"  [dim]— \"{notes}\"[/dim]" if notes else ""))

    return current_run, feel, notes


if __name__ == "__main__":
    run_checkin()
