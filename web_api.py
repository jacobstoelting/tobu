"""
web_api.py — Tobu rating system API layer.

These functions are the bridge between the web UI and the database.
Each one maps to a logical HTTP endpoint (noted in the docstring) and
returns JSON-serializable data. Wire these directly into your web
framework routes (Flask, FastAPI, etc.).
"""

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
