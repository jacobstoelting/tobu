import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ELO_K = 32
ELO_DEFAULT = 1000
_initialized = False


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
    global _initialized
    if _initialized:
        return
    _initialized = True

    with _db() as conn:
        cur = _cursor(conn)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                SERIAL PRIMARY KEY,
                user_id           TEXT DEFAULT '',
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
            CREATE TABLE IF NOT EXISTS run_comparisons (
                id           SERIAL PRIMARY KEY,
                user_id      TEXT DEFAULT '',
                today_date   TEXT,
                other_date   TEXT,
                result       TEXT,
                recorded_at  TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id              SERIAL PRIMARY KEY,
                user_id         TEXT DEFAULT '',
                run_date        TEXT,
                recommendation  TEXT,
                created_at      TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          SERIAL PRIMARY KEY,
                user_id     TEXT DEFAULT '',
                run_date    TEXT,
                role        TEXT,
                content     TEXT,
                created_at  TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id          SERIAL PRIMARY KEY,
                user_id     TEXT DEFAULT '',
                week_start  TEXT,
                summary     TEXT,
                created_at  TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS garmin_tokens (
                user_id     TEXT PRIMARY KEY,
                tokens      TEXT,
                updated_at  TEXT
            )
        """)

        # Column migrations for existing deployments
        for table in ["runs", "run_comparisons", "analyses", "chat_messages", "weekly_summaries"]:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT ''")
        cur.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS elo_score REAL DEFAULT 1000")

        # Migrate weekly_summaries unique constraint from (week_start) to (week_start, user_id)
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'weekly_summaries_week_start_user_id_key'
                ) THEN
                    ALTER TABLE weekly_summaries
                        DROP CONSTRAINT IF EXISTS weekly_summaries_week_start_key;
                    ALTER TABLE weekly_summaries
                        ADD CONSTRAINT weekly_summaries_week_start_user_id_key
                        UNIQUE (week_start, user_id);
                END IF;
            END $$;
        """)

        # One-time data migration: claim existing unowned rows for the server owner
        owner_email = os.environ.get("GARMIN_EMAIL", "")
        if owner_email:
            for table in ["runs", "run_comparisons", "analyses", "chat_messages", "weekly_summaries"]:
                cur.execute(f"UPDATE {table} SET user_id = %s WHERE user_id = ''", (owner_email,))


def save_run(run_data: dict, user_id: str):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO runs (
                user_id, date, distance_mi, duration_min, avg_pace,
                avg_hr, max_hr, avg_cadence, elevation_gain_ft,
                training_effect, training_load, vo2max,
                feel, notes, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
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


def get_runs_last_n_days(n=14, user_id: str = ""):
    init_db()
    cutoff = (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM runs WHERE user_id = %s AND date >= %s ORDER BY date DESC",
            (user_id, cutoff),
        )
        return [dict(r) for r in cur.fetchall()]


def save_comparisons(today_date: str, comparisons: list, user_id: str):
    init_db()
    now = datetime.now().isoformat()
    with _db() as conn:
        cur = _cursor(conn)
        cur.executemany("""
            INSERT INTO run_comparisons (user_id, today_date, other_date, result, recorded_at)
            VALUES (%s, %s, %s, %s, %s)
        """, [(user_id, today_date, c["other_date"], c["result"], now) for c in comparisons])


def compute_and_save_elo(user_id: str):
    """Replay all stored comparisons to compute ELO scores for every run."""
    init_db()
    with _db() as conn:
        cur = _cursor(conn)

        cur.execute("SELECT date FROM runs WHERE user_id = %s", (user_id,))
        scores = {r["date"][:10]: ELO_DEFAULT for r in cur.fetchall()}

        cur.execute(
            "SELECT today_date, other_date, result FROM run_comparisons "
            "WHERE user_id = %s ORDER BY recorded_at",
            (user_id,),
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

        for date_key, score in scores.items():
            cur.execute(
                "UPDATE runs SET elo_score = %s WHERE user_id = %s AND date LIKE %s",
                (round(score, 1), user_id, f"{date_key}%"),
            )


def get_run_elo_ranking(days=14, user_id: str = ""):
    """Returns recent runs sorted by elo_score descending."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT date, distance_mi, avg_pace, elo_score FROM runs "
            "WHERE user_id = %s AND date >= %s ORDER BY elo_score DESC",
            (user_id, cutoff),
        )
        return [dict(r) for r in cur.fetchall()]


def get_run_by_date(date: str, user_id: str = ""):
    """Returns the saved run for a given date, or None."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM runs WHERE user_id = %s AND date LIKE %s "
            "ORDER BY recorded_at DESC LIMIT 1",
            (user_id, f"{date_key}%"),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def has_comparisons(date: str, user_id: str = "") -> bool:
    """Returns True if the run on this date has pairwise comparisons stored."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT COUNT(*) AS count FROM run_comparisons "
            "WHERE user_id = %s AND today_date LIKE %s",
            (user_id, f"{date_key}%"),
        )
        return cur.fetchone()["count"] > 0


def get_comparisons_for_run(date: str, user_id: str = "") -> list:
    """Returns all pairwise comparisons for a given run date."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT today_date, other_date, result FROM run_comparisons "
            "WHERE user_id = %s AND today_date LIKE %s ORDER BY recorded_at",
            (user_id, f"{date_key}%"),
        )
        return [dict(r) for r in cur.fetchall()]


def update_comparison(today_date: str, other_date: str, new_result: str, user_id: str = ""):
    """Update a single pairwise comparison result and recompute ELO."""
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "UPDATE run_comparisons SET result = %s, recorded_at = %s "
            "WHERE user_id = %s AND today_date LIKE %s AND other_date LIKE %s",
            (new_result, datetime.now().isoformat(), user_id,
             f"{today_date[:10]}%", f"{other_date[:10]}%"),
        )
    compute_and_save_elo(user_id)


def delete_comparisons_for_run(date: str, user_id: str = ""):
    """Delete all comparisons for a run and recompute ELO."""
    init_db()
    date_key = date[:10]
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "DELETE FROM run_comparisons WHERE user_id = %s AND today_date LIKE %s",
            (user_id, f"{date_key}%"),
        )
    compute_and_save_elo(user_id)


def save_analysis(run_date: str, recommendation: str, user_id: str = ""):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO analyses (user_id, run_date, recommendation, created_at)
            VALUES (%s, %s, %s, %s)
        """, (user_id, run_date, recommendation, datetime.now().isoformat()))


def get_latest_analysis(user_id: str = ""):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM analyses WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def save_chat_message(run_date: str, role: str, content: str, user_id: str = ""):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO chat_messages (user_id, run_date, role, content, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, run_date, role, content, datetime.now().isoformat()))


def get_chat_messages(run_date: str, user_id: str = "") -> list:
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT role, content FROM chat_messages "
            "WHERE user_id = %s AND run_date = %s ORDER BY created_at",
            (user_id, run_date),
        )
        return [dict(r) for r in cur.fetchall()]


def save_weekly_summary(week_start: str, summary: str, user_id: str = ""):
    init_db()
    now = datetime.now().isoformat()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO weekly_summaries (user_id, week_start, summary, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (week_start, user_id) DO UPDATE SET summary = %s, created_at = %s
        """, (user_id, week_start, summary, now, summary, now))


def get_weekly_summary(week_start: str, user_id: str = ""):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute(
            "SELECT * FROM weekly_summaries WHERE user_id = %s AND week_start = %s",
            (user_id, week_start),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def save_garmin_tokens(user_id: str, tokens: str):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("""
            INSERT INTO garmin_tokens (user_id, tokens, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET tokens = %s, updated_at = %s
        """, (user_id, tokens, datetime.now().isoformat(), tokens, datetime.now().isoformat()))


def get_garmin_tokens(user_id: str):
    init_db()
    with _db() as conn:
        cur = _cursor(conn)
        cur.execute("SELECT tokens FROM garmin_tokens WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    return row["tokens"] if row else None
