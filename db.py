import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "tobu.db")

ELO_K = 32
ELO_DEFAULT = 1000


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT,
                distance_mi      REAL,
                duration_min     REAL,
                avg_pace         TEXT,
                avg_hr           REAL,
                max_hr           REAL,
                avg_cadence      REAL,
                elevation_gain_ft REAL,
                training_effect  REAL,
                training_load    REAL,
                vo2max           REAL,
                feel             TEXT,
                notes            TEXT,
                recorded_at      TEXT,
                elo_score        REAL DEFAULT 1000
            )
        """)
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN elo_score REAL DEFAULT 1000")
        except Exception:
            pass  # column already exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_comparisons (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                today_date   TEXT,
                other_date   TEXT,
                result       TEXT,
                recorded_at  TEXT
            )
        """)


def save_run(run_data: dict):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO runs (
                date, distance_mi, duration_min, avg_pace,
                avg_hr, max_hr, avg_cadence, elevation_gain_ft,
                training_effect, training_load, vo2max,
                feel, notes, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_data.get("date"),
            run_data.get("distance_mi"),
            run_data.get("duration_min"),
            run_data.get("avg_pace_min_mi"),
            run_data.get("avg_hr"),
            run_data.get("max_hr"),
            run_data.get("avg_cadence"),
            run_data.get("elevation_gain_ft"),
            run_data.get("aerobic_training_effect"),
            run_data.get("training_load"),
            run_data.get("vo2max"),
            run_data.get("feel"),
            run_data.get("notes"),
            datetime.now().isoformat(),
        ))


def get_runs_last_n_days(n=14):
    init_db()
    cutoff = (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM runs WHERE date >= ? ORDER BY date DESC", (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_comparisons(today_date: str, comparisons: list):
    init_db()
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany("""
            INSERT INTO run_comparisons (today_date, other_date, result, recorded_at)
            VALUES (?, ?, ?, ?)
        """, [(today_date, c["other_date"], c["result"], now) for c in comparisons])


def compute_and_save_elo():
    """Replay all stored comparisons to compute ELO scores for every run."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        # Load all run dates and seed scores
        rows = conn.execute("SELECT date FROM runs").fetchall()
        scores = {r[0][:10]: ELO_DEFAULT for r in rows}

        # Replay comparisons in chronological order
        comps = conn.execute(
            "SELECT today_date, other_date, result FROM run_comparisons ORDER BY recorded_at"
        ).fetchall()

        for today_date, other_date, result in comps:
            td = today_date[:10]
            od = other_date[:10]
            if td not in scores:
                scores[td] = ELO_DEFAULT
            if od not in scores:
                scores[od] = ELO_DEFAULT

            r_today = scores[td]
            r_other = scores[od]
            expected_today = 1 / (1 + 10 ** ((r_other - r_today) / 400))

            if result == "harder":      # today won
                actual = 1.0
            elif result == "easier":    # today lost
                actual = 0.0
            else:                       # same = draw
                actual = 0.5

            scores[td] = r_today + ELO_K * (actual - expected_today)
            scores[od] = r_other + ELO_K * ((1 - actual) - (1 - expected_today))

        # Write scores back
        for date_key, score in scores.items():
            conn.execute(
                "UPDATE runs SET elo_score = ? WHERE date LIKE ?",
                (round(score, 1), f"{date_key}%")
            )


def get_run_elo_ranking(days=14):
    """Returns recent runs sorted by elo_score descending."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT date, distance_mi, avg_pace, elo_score FROM runs "
            "WHERE date >= ? ORDER BY elo_score DESC",
            (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]
