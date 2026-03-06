from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from garmin import get_health_snapshot
from checkin import run_checkin
from db import get_runs_last_n_days, get_run_elo_ranking
from coach import get_recommendation
from weather import get_run_weather, get_forecast

load_dotenv()

console = Console()


def main():
    # Step 1: Check-in (fetches run, prompts user, saves to DB)
    result = run_checkin()
    if not result:
        return
    current_run, feel, notes, comparisons = result

    # Step 2: Fetch supporting context for Claude
    today_date = current_run["date"][:10]
    with console.status("[dim]Fetching health data...[/dim]", spinner="dots"):
        recent_runs = get_runs_last_n_days(14)
        recent_runs = [r for r in recent_runs if not r.get("date", "").startswith(today_date)]
        health = get_health_snapshot(today_date)
        elo_ranking = get_run_elo_ranking(days=14)

    with console.status("[dim]Fetching weather...[/dim]", spinner="dots"):
        weather = get_run_weather(
            current_run.get("start_lat"),
            current_run.get("start_lon"),
            current_run.get("date"),
            current_run.get("duration_min"),
        )
        forecast = get_forecast(current_run.get("start_lat"), current_run.get("start_lon"))

    # Step 3: Get Claude's recommendation
    with console.status("[dim]Generating your next run recommendation...[/dim]", spinner="dots"):
        recommendation = get_recommendation(current_run, recent_runs, health, feel, notes, comparisons, elo_ranking, weather, forecast)

    console.print()
    console.print(Panel(
        f"[white]{recommendation}[/white]",
        title="[bold]Next Run[/bold]",
        border_style="dim",
        padding=(1, 2),
    ))
    console.print()


if __name__ == "__main__":
    main()
