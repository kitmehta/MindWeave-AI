"""Database operations: connection, initialization, and curriculum persistence."""

import json
import time
import psycopg2
import psycopg2.pool

from config import DATABASE_URL

# ---------------------------------------------------------------------------
# Connection Pool
# ---------------------------------------------------------------------------
_pool = None


def _ensure_pool():
    """Initialize the PostgreSQL connection pool."""
    global _pool

    if _pool is None:
        try:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=DATABASE_URL,
            )
            print("PostgreSQL connection pool initialized.")
        except Exception as e:
            print(f"Failed to initialize DB pool: {e}")
            _pool = None


# ---------------------------------------------------------------------------
# Pooled Connection Wrapper
# ---------------------------------------------------------------------------
class PooledConnection:
    """Wrapper that returns connection back to pool on close()."""

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    @property
    def autocommit(self):
        return self._conn.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._conn.autocommit = value

    def close(self):
        if self._conn and self._pool:
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def __bool__(self):
        return self._conn is not None


# ---------------------------------------------------------------------------
# DB Connection Helpers
# ---------------------------------------------------------------------------
def get_db():
    """Return pooled DB connection."""
    _ensure_pool()

    if _pool is None:
        return None

    try:
        conn = _pool.getconn()
        return PooledConnection(conn, _pool)
    except Exception as e:
        print(f"DB pool connection error: {e}")
        return None


def get_db_raw():
    """Direct raw PostgreSQL connection."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Raw DB connection error: {e}")
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_semester(raw: str) -> str:
    """Normalize semester formatting."""
    if not raw:
        return ""

    parts = raw.strip().split()

    if len(parts) == 2:
        return f"{parts[0].capitalize()} {parts[1]}"

    return raw.strip().title()


# ---------------------------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------------------------
def init_db():
    """Initialize all required database tables."""
    for attempt in range(10):
        conn = get_db_raw()

        if conn:
            try:
                cur = conn.cursor()

                # -------------------------------------------------------------------
                # curricula
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS curricula (
                        id SERIAL PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT NOW(),
                        topic TEXT NOT NULL,
                        level TEXT,
                        audience TEXT,
                        course_code TEXT,
                        course_type TEXT,
                        module_count INTEGER,
                        modules JSONB,
                        sources JSONB,
                        semester TEXT DEFAULT '',
                        is_favorite BOOLEAN DEFAULT FALSE
                    )
                """)

                # -------------------------------------------------------------------
                # xapi_statements
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS xapi_statements (
                        id SERIAL PRIMARY KEY,
                        actor_email TEXT NOT NULL,
                        actor_name TEXT NOT NULL,
                        verb TEXT NOT NULL,
                        object_id TEXT NOT NULL,
                        object_name TEXT NOT NULL,
                        response TEXT,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        curriculum_topic TEXT,
                        course_id INTEGER
                    )
                """)

                # -------------------------------------------------------------------
                # student_feedback
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS student_feedback (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        module_index INTEGER NOT NULL,
                        module_title TEXT,
                        sentiment TEXT NOT NULL,
                        comment TEXT DEFAULT '',
                        student_id TEXT DEFAULT 'anonymous',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                # -------------------------------------------------------------------
                # course_analysis_snapshots
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS course_analysis_snapshots (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        noise_label TEXT DEFAULT 'unknown',
                        risk_distribution JSONB,
                        total_students INTEGER,
                        at_risk_count INTEGER,
                        high_risk_count INTEGER,
                        top_signals JSONB,
                        module_engagement_summary JSONB,
                        verb_distribution JSONB,
                        cohort_groups JSONB,
                        is_favorite BOOLEAN DEFAULT FALSE
                    )
                """)

                # -------------------------------------------------------------------
                # change_log
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS change_log (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        module_id VARCHAR NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        flag_reason TEXT[],
                        recommendation TEXT,
                        agent VARCHAR DEFAULT 'curriculum_agent',
                        status VARCHAR DEFAULT 'pending',
                        backup_data TEXT,
                        change_type VARCHAR DEFAULT 'objective_update'
                    )
                """)

                # -------------------------------------------------------------------
                # module_flags
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS module_flags (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        module_id VARCHAR NOT NULL,
                        flag_level VARCHAR NOT NULL,
                        signals JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        dismissed BOOLEAN DEFAULT FALSE
                    )
                """)

                # -------------------------------------------------------------------
                # cohort_concept_mastery
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cohort_concept_mastery (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        semester TEXT NOT NULL DEFAULT '',
                        module_id TEXT NOT NULL,
                        concept_id TEXT NOT NULL,
                        concept_label TEXT,
                        mastery_level TEXT NOT NULL DEFAULT 'not_started',
                        completed_count INTEGER DEFAULT 0,
                        passed_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        struggled_count INTEGER DEFAULT 0,
                        fb_got_it INTEGER DEFAULT 0,
                        fb_mostly INTEGER DEFAULT 0,
                        fb_confused INTEGER DEFAULT 0,
                        fb_not_read INTEGER DEFAULT 0,
                        valid_from TIMESTAMP DEFAULT NOW(),
                        valid_to TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(course_id, semester, module_id, concept_id, valid_from)
                    )
                """)

                # -------------------------------------------------------------------
                # concept_annotations
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS concept_annotations (
                        id SERIAL PRIMARY KEY,
                        course_id INTEGER NOT NULL,
                        concept_id TEXT NOT NULL,
                        student_id TEXT DEFAULT 'anonymous',
                        annotation_type TEXT NOT NULL DEFAULT 'confused',
                        content TEXT DEFAULT '',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # -------------------------------------------------------------------
                # student_profiles
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS student_profiles (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        display_name TEXT DEFAULT '',
                        preferred_style TEXT DEFAULT '',
                        persona_sets JSONB DEFAULT '[]',
                        avatar_url TEXT DEFAULT '',
                        discipline TEXT DEFAULT 'humanities',
                        custom_prompt TEXT DEFAULT '',
                        model_config JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # -------------------------------------------------------------------
                # prompt_templates
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS prompt_templates (
                        id SERIAL PRIMARY KEY,
                        template_key TEXT UNIQUE NOT NULL,
                        custom_instructions TEXT DEFAULT '',
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # -------------------------------------------------------------------
                # Indexes
                # -------------------------------------------------------------------
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_course
                    ON student_feedback(course_id)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_snapshots_course
                    ON course_analysis_snapshots(course_id, run_at DESC)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_changelog_course
                    ON change_log(course_id, timestamp DESC)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_module_flags_course
                    ON module_flags(course_id, dismissed)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mastery_course
                    ON cohort_concept_mastery(course_id, semester)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_xapi_actor
                    ON xapi_statements(actor_email)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_xapi_verb
                    ON xapi_statements(verb)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_xapi_object
                    ON xapi_statements(object_id)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_xapi_topic
                    ON xapi_statements(curriculum_topic)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_xapi_timestamp
                    ON xapi_statements(timestamp)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_annotations_course
                    ON concept_annotations(course_id)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_student_profiles_email
                    ON student_profiles(email)
                """)

                conn.commit()
                cur.close()
                conn.close()

                _ensure_pool()

                print("Database initialized successfully.")
                return

            except Exception as e:
                print(f"Database init error: {e}")

                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass

                return

        print(f"Database not ready. Retry {attempt + 1}/10...")
        time.sleep(3)

    print("Could not connect to database after retries.")


# ---------------------------------------------------------------------------
# Curriculum Save
# ---------------------------------------------------------------------------
def save_curriculum(
    topic,
    level,
    audience,
    course_code,
    course_type,
    module_count,
    data,
    design_approach="addie",
    semester="",
):
    """Save curriculum and return inserted course ID."""

    with get_db() as conn:
        if not conn:
            return None

        try:
            normalized_semester = (
                normalize_semester(semester) if semester else ""
            )

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO curricula (
                    topic,
                    level,
                    audience,
                    course_code,
                    course_type,
                    module_count,
                    modules,
                    sources,
                    semester
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    topic,
                    level,
                    audience,
                    course_code,
                    course_type,
                    module_count,
                    json.dumps(data.get("modules", [])),
                    json.dumps(data.get("sources", [])),
                    normalized_semester,
                ),
            )

            new_id = cur.fetchone()[0]

            conn.commit()
            cur.close()

            return new_id

        except Exception as e:
            print(f"Curriculum save error: {e}")
            return None