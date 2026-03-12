import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ELO_K = 32
ELO_DEFAULT = 1000


@contextmanager
def _db():
    """Context manager that yields a connection and auto-commits or rolls back."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _cursor(conn):
    """Returns a cursor that produces dicts."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                SERIAL PRIMARY KEY,
                date              TEXT,
                distance_mi       REAL,
                duration_min      REAL,
                avg_pace          TEXT,
                avg_hr            REAL,
                max_hr            REAL,
                avg_cadence       REAL,
                elevation_gain_ft REAL,
                training_effect   REAL,
                training_load     REAL,
                vo2max            REAL,
                feel              TEXT,
                notes             TEXT,
                recorded_at       TEXT,
                elo_score         REAL DEFAULT 1000
            )
        """)
        cur.execute("""
            ALTER TABLE runs ADD COLUMN IF NOT EXISTS elo_score REAL DEFAULT 1000
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS run_comparisons (
                id           SERIAL PRIMARY KEY,
                today_date   TEXT,
                other_date   TEXT,
                result       TEXT,
                recorded_at  TEXT
            )
        """)


def save_run(run_data: dict):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO runs (
                date, distance_mi, duration_min, avg_pace,
                avg_hr, max_hr, avg_cadence, elevation_gain_ft,
                training_effect, training_load, vo2max,
                feel, notes, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM runs WHERE date >= %s ORDER BY date DESC", (cutoff,)
        )
        return [dict(r) for r in cur.fetchall()]


def save_comparisons(today_date: str, comparisons: list):
    init_db()
    now = datetime.now().isoformat()
    with _db() as conn:
        cur = _cursor(conn)
        cur.executemany("""
            INSERT INTO run_comparisons (today_date, other_date, result, recorded_at)
            VALUES (%s, %s, %s, %s)
        """, [(today_date, c["other_date"], c["result"], now) for c in comparisons])


def compute_and_save_elo():
    """Replay all stored comparisons to compute ELO scores for every run."""
    init_db()
    with _db() as conn:
        cur = _cursor(conn)

        # Load all run dates and seed scores
        cur.execute("SELECT date FROM runs")
        scores = {r["date"][:10]: ELO_DEFAULT for r in cur.fetchall()}

        # Replay comparisons in chronological order
        cur.execute(
            "SELECT today_date, other_date, result FROM run_comparisons ORDER BY recorded_at"
        )
        comps = cur.fetchall()

        for row in comps:
            td = row["today_date"][:10]
            od = row["other_date"][:10]
            result = row["result"]
            if td not in scores:
                scores[td] = ELO_DEFAULT
            if od not in scores:
                scores[od] = ELO_DEFAULT

            r_today = scores[td]
            r_other = scores[od]
            expected_today = 1 / (1 + 10 ** ((r_other - r_today) / 400))

            if result == "harder":
                actual = 1.0
            elif result == "easier":
                actual = 0.0
            else:
                actual = 0.5

            scores[td] = r_today + ELO_K * (actual - expected_today)
            scores[od] = r_other + ELO_K * ((1 - actual) - (1 - expected_today))

        # Write scores back
        for date_key, score in scores.items():
            cur.execute(
                "UPDATE runs SET elo_score = %s WHERE date LIKE %s",
                (round(score, 1), f"{date_key}%")
            )


def get_run_elo_ranking(days=14):
    """Returns recent runs sorted by elo_score descending."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT date, distance_mi, avg_pace, elo_score FROM runs "
            "WHERE date >= %s ORDER BY elo_score DESC",
            (cutoff,)
        )
        return [dict(r) for r in cur.fetchall()]


def get_run_by_date(date: str):
    """Returns the saved run for a given date, or None."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM runs WHERE date LIKE %s ORDER BY recorded_at DESC LIMIT 1",
            (f"{date_key}%",)
        )
        row = cur.fetchone()
    return dict(row) if row else None


def has_comparisons(date: str) -> bool:
    """Returns True if the run on this date has pairwise comparisons stored."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT COUNT(*) AS count FROM run_comparisons WHERE today_date LIKE %s",
            (f"{date_key}%",)
        )
        return cur.fetchone()["count"] > 0


def get_comparisons_for_run(date: str) -> list:
    """Returns all pairwise comparisons for a given run date."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT today_date, other_date, result FROM run_comparisons "
            "WHERE today_date LIKE %s ORDER BY recorded_at",
            (f"{date_key}%",)
        )
        return [dict(r) for r in cur.fetchall()]


def update_comparison(today_date: str, other_date: str, new_result: str):
    """Update a single pairwise comparison result and recompute ELO."""
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "UPDATE run_comparisons SET result = %s, recorded_at = %s "
            "WHERE today_date LIKE %s AND other_date LIKE %s",
            (new_result, datetime.now().isoformat(),
             f"{today_date[:10]}%", f"{other_date[:10]}%")
        )
    compute_and_save_elo()


def delete_comparisons_for_run(date: str):
    """Delete all comparisons for a run and recompute ELO."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "DELETE FROM run_comparisons WHERE today_date LIKE %s",
            (f"{date_key}%",)
        )
    compute_and_save_elo()
