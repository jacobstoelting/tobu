"""
web_api.py — Tobu rating system API layer.

These functions are the bridge between the web UI and the database.
Each one maps to a logical HTTP endpoint (noted in the docstring) and
returns JSON-serializable data. Wire these directly into your web
framework routes (Flask, FastAPI, etc.).
"""

from datetime import datetime, timedelta
from typing import NamedTuple
import coach
from db import (
    get_runs_last_n_days,
    get_run_by_date,
    save_run,
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


class UserContext(NamedTuple):
    user_id: str
    garmin_email: str
    garmin_password: str
    anthropic_key: str


def get_all_runs(ctx: UserContext, days=90):
    """
    Returns all runs with their rating status and comparisons.
    Web route: GET /api/runs
    """
    runs = get_runs_last_n_days(days, user_id=ctx.user_id)
    for run in runs:
        run["comparisons"] = get_comparisons_for_run(run["date"], user_id=ctx.user_id)
        run["is_rated"] = bool(run.get("feel")) or has_comparisons(run["date"], user_id=ctx.user_id)
    return runs


def get_pending_ratings(ctx: UserContext, days=30):
    """
    Returns runs that haven't been rated yet.
    Web route: GET /api/ratings/pending
    """
    runs = get_runs_last_n_days(days, user_id=ctx.user_id)
    return [r for r in runs if not r.get("feel") and not has_comparisons(r["date"], user_id=ctx.user_id)]


def get_run_ratings(date: str, ctx: UserContext):
    """
    Returns a run and all its existing ratings.
    Web route: GET /api/ratings/<date>
    Response: {"run": {...}, "comparisons": [...]}
    """
    return {
        "run": get_run_by_date(date, user_id=ctx.user_id),
        "comparisons": get_comparisons_for_run(date, user_id=ctx.user_id),
    }


def submit_ratings(today_date: str, comparisons: list, ctx: UserContext):
    """
    Save pairwise comparisons for a run and recompute ELO.
    Use this for first-time rating of a run.
    Web route: POST /api/ratings/<date>
    Body: [{"other_date": "YYYY-MM-DD", "result": "harder"|"easier"|"same"}, ...]
    Raises ValueError if run is already rated.
    """
    if has_comparisons(today_date, user_id=ctx.user_id):
        raise ValueError(f"Run on {today_date} already has ratings. Use rerate_run() to replace them.")
    _validate_comparisons(comparisons)
    save_comparisons(today_date, comparisons, user_id=ctx.user_id)
    compute_and_save_elo(user_id=ctx.user_id)


def update_rating(today_date: str, other_date: str, new_result: str, ctx: UserContext):
    """
    Edit a single comparison result and recompute ELO.
    Web route: PATCH /api/ratings/<date>/<other_date>
    Body: {"result": "harder"|"easier"|"same"}
    """
    _validate_result(new_result)
    update_comparison(today_date, other_date, new_result, user_id=ctx.user_id)


def rerate_run(today_date: str, comparisons: list, ctx: UserContext):
    """
    Wipe and resubmit all ratings for a run.
    Web route: PUT /api/ratings/<date>
    Body: [{"other_date": "YYYY-MM-DD", "result": "harder"|"easier"|"same"}, ...]
    """
    _validate_comparisons(comparisons)
    delete_comparisons_for_run(today_date, user_id=ctx.user_id)
    save_comparisons(today_date, comparisons, user_id=ctx.user_id)
    compute_and_save_elo(user_id=ctx.user_id)


def get_elo_leaderboard(ctx: UserContext, days=14):
    """
    Returns recent runs ranked by ELO score (hardest first).
    Web route: GET /api/elo?days=<days>
    """
    return get_run_elo_ranking(days=days, user_id=ctx.user_id)


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


def get_latest_analysis(ctx: UserContext):
    """
    Returns the most recent Claude analysis.
    Web route: GET /api/analysis/latest
    """
    return get_latest_analysis_db(user_id=ctx.user_id)


def generate_analysis(ctx: UserContext):
    """
    Generate a new analysis for the most recent run and save it.
    Web route: POST /api/analysis/generate
    """
    runs = get_runs_last_n_days(30, user_id=ctx.user_id)
    if not runs:
        raise ValueError("No runs found")
    current_run = runs[0]
    run_date = current_run["date"][:10]
    recent_runs = runs[1:]
    comparisons = get_comparisons_for_run(run_date, user_id=ctx.user_id)
    elo_ranking = get_run_elo_ranking(days=14, user_id=ctx.user_id)
    feel = current_run.get("feel", "unknown")
    notes = current_run.get("notes")
    recommendation = coach.get_recommendation(
        current_run, recent_runs, {}, feel, notes,
        comparisons, elo_ranking, None, None,
        api_key=ctx.anthropic_key,
    )
    save_analysis_db(run_date, recommendation, user_id=ctx.user_id)
    return {"run_date": run_date, "recommendation": recommendation}


def send_chat_message(run_date: str, message: str, ctx: UserContext):
    """
    Send a follow-up chat message about a run.
    Web route: POST /api/analysis/{date}/chat
    """
    analysis = get_latest_analysis_db(user_id=ctx.user_id)
    analysis_text = analysis["recommendation"] if analysis else "No previous analysis available."
    history = get_chat_messages_db(run_date, user_id=ctx.user_id)
    save_chat_message_db(run_date, "user", message, user_id=ctx.user_id)
    response = coach.chat_followup(run_date, analysis_text, history, message, api_key=ctx.anthropic_key)
    save_chat_message_db(run_date, "assistant", response, user_id=ctx.user_id)
    return {"response": response}


def get_or_generate_weekly_summary(ctx: UserContext):
    """
    Returns this week's summary, generating it if needed.
    Web route: GET /api/summary/weekly
    """
    today = datetime.now()
    week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    runs = get_runs_last_n_days(7, user_id=ctx.user_id)
    if not runs:
        return {"week_start": week_start, "summary": "No runs this week yet."}
    existing = get_weekly_summary_db(week_start, user_id=ctx.user_id)
    if existing and existing.get("summary") != "No runs this week yet.":
        return existing
    summary = coach.get_weekly_summary(runs, api_key=ctx.anthropic_key)
    save_weekly_summary_db(week_start, summary, user_id=ctx.user_id)
    return {"week_start": week_start, "summary": summary}


def sync_from_garmin(ctx: UserContext, days=30):
    """
    Pull recent runs from Garmin and save any that aren't already in the DB.
    Web route: POST /api/sync
    Returns: {"synced": int, "total": int}
    """
    from garmin import get_recent_runs as garmin_get_recent_runs
    runs = garmin_get_recent_runs(days=days, email=ctx.garmin_email, password=ctx.garmin_password)
    new_count = 0
    for run in runs:
        date_key = run["date"][:10]
        if not get_run_by_date(date_key, user_id=ctx.user_id):
            save_run(run, user_id=ctx.user_id)
            new_count += 1
    if new_count > 0:
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        save_weekly_summary_db(week_start, "No runs this week yet.", user_id=ctx.user_id)
    return {"synced": new_count, "total": len(runs)}
