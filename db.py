import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "tobu.db")


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
                recorded_at      TEXT
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
