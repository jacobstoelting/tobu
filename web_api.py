"""
web_api.py — Tobu rating system API layer.

These functions are the bridge between the web UI and the database.
Each one maps to a logical HTTP endpoint (noted in the docstring) and
returns JSON-serializable data. Wire these directly into your web
framework routes (Flask, FastAPI, etc.).
"""

from datetime import datetime, timedelta
import coach
from db import (
    get_runs_last_n_days,
    get_run_by_date,
    has_comparisons,
    get_comparisons_for_run,
    save_comparisons,
    update_comparison,
    delete_comparisons_for_run,
    compute_and_save_elo,
    get_run_elo_ranking,
    save_analysis as save_analysis_db,
    get_latest_analysis as get_latest_analysis_db,
    save_chat_message as save_chat_message_db,
    get_chat_messages as get_chat_messages_db,
    save_weekly_summary as save_weekly_summary_db,
    get_weekly_summary as get_weekly_summary_db,
)


def get_all_runs(days=90):
    """
    Returns all runs with their rating status and comparisons.
    Web route: GET /api/runs
    """
    runs = get_runs_last_n_days(days)
    for run in runs:
        run["comparisons"] = get_comparisons_for_run(run["date"])
        run["is_rated"] = bool(run.get("feel")) or has_comparisons(run["date"])
    return runs


def get_pending_ratings(days=30):
    """
    Returns runs that haven't been rated yet.
    Web route: GET /api/ratings/pending
    """
    runs = get_runs_last_n_days(days)
    return [r for r in runs if not r.get("feel") and not has_comparisons(r["date"])]


def get_run_ratings(date: str):
    """
    Returns a run and all its existing ratings.
    Web route: GET /api/ratings/<date>
    Response: {"run": {...}, "comparisons": [...]}
    """
    return {
        "run": get_run_by_date(date),
        "comparisons": get_comparisons_for_run(date),
    }


def submit_ratings(today_date: str, comparisons: list):
    """
    Save pairwise comparisons for a run and recompute ELO.
    Use this for first-time rating of a run.
    Web route: POST /api/ratings/<date>
    Body: [{"other_date": "YYYY-MM-DD", "result": "harder"|"easier"|"same"}, ...]
    Raises ValueError if run is already rated.
    """
    if has_comparisons(today_date):
        raise ValueError(f"Run on {today_date} already has ratings. Use rerate_run() to replace them.")
    _validate_comparisons(comparisons)
    save_comparisons(today_date, comparisons)
    compute_and_save_elo()


def update_rating(today_date: str, other_date: str, new_result: str):
    """
    Edit a single comparison result and recompute ELO.
    Use this for targeted edits without wiping all ratings.
    Web route: PATCH /api/ratings/<date>/<other_date>
    Body: {"result": "harder"|"easier"|"same"}
    """
    _validate_result(new_result)
    update_comparison(today_date, other_date, new_result)


def rerate_run(today_date: str, comparisons: list):
    """
    Wipe and resubmit all ratings for a run.
    Use this when the user wants to redo the full comparison set.
    Web route: PUT /api/ratings/<date>
    Body: [{"other_date": "YYYY-MM-DD", "result": "harder"|"easier"|"same"}, ...]
    """
    _validate_comparisons(comparisons)
    delete_comparisons_for_run(today_date)
    save_comparisons(today_date, comparisons)
    compute_and_save_elo()


def get_elo_leaderboard(days=14):
    """
    Returns recent runs ranked by ELO score (hardest first).
    Web route: GET /api/elo?days=<days>
    """
    return get_run_elo_ranking(days=days)


# --- Validation helpers ---

def _validate_result(result: str):
    valid = {"harder", "easier", "same"}
    if result not in valid:
        raise ValueError(f"result must be one of {valid}, got '{result}'")


def _validate_comparisons(comparisons: list):
    for c in comparisons:
        if "other_date" not in c or "result" not in c:
            raise ValueError("Each comparison must have 'other_date' and 'result'")
        _validate_result(c["result"])


def get_latest_analysis():
    """
    Returns the most recent Claude analysis.
    Web route: GET /api/analysis/latest
    """
    return get_latest_analysis_db()


def generate_analysis():
    """
    Generate a new analysis for the most recent run and save it.
    Web route: POST /api/analysis/generate
    """
    runs = get_runs_last_n_days(30)
    if not runs:
        raise ValueError("No runs found")
    current_run = runs[0]
    run_date = current_run["date"][:10]
    recent_runs = runs[1:]
    comparisons = get_comparisons_for_run(run_date)
    elo_ranking = get_run_elo_ranking(days=14)
    feel = current_run.get("feel", "unknown")
    notes = current_run.get("notes")
    recommendation = coach.get_recommendation(
        current_run, recent_runs, None, feel, notes,
        comparisons, elo_ranking, None, None
    )
    save_analysis_db(run_date, recommendation)
    return {"run_date": run_date, "recommendation": recommendation}


def send_chat_message(run_date: str, message: str):
    """
    Send a follow-up chat message about a run.
    Web route: POST /api/analysis/{date}/chat
    """
    analysis = get_latest_analysis_db()
    analysis_text = analysis["recommendation"] if analysis else "No previous analysis available."
    history = get_chat_messages_db(run_date)
    save_chat_message_db(run_date, "user", message)
    response = coach.chat_followup(run_date, analysis_text, history, message)
    save_chat_message_db(run_date, "assistant", response)
    return {"response": response}


def get_or_generate_weekly_summary():
    """
    Returns this week's summary, generating it if needed.
    Web route: GET /api/summary/weekly
    """
    today = datetime.now()
    week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    runs = get_runs_last_n_days(7)
    existing = get_weekly_summary_db(week_start)
    if existing and runs:
        return existing
    summary = coach.get_weekly_summary(runs)
    if runs:
        save_weekly_summary_db(week_start, summary)
    return {"week_start": week_start, "summary": summary}
