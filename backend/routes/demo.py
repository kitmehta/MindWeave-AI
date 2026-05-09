"""Demo seed route — one-click load of sample data for first-time users.

POST /api/demo/seed  (SSE)
  1. Seed curriculum demo data
  2. Seed xAPI mock data
  3. Seed feedback data
  4. Run curriculum analysis

GET /api/demo/status
  Returns { has_data: bool }
"""

import json
from flask import Blueprint, Response, stream_with_context, jsonify
from db import get_db

demo_bp = Blueprint("demo", __name__)


def _has_courses() -> bool:
    conn = get_db()

    if not conn:
        return False

    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM curricula")
        count = cur.fetchone()[0]

        cur.close()
        conn.close()

        return count > 0

    except Exception:
        try:
            conn.close()
        except Exception:
            pass

        return False


def _sse(message: str, status: str = "progress"):
    return f"data: {json.dumps({'status': status, 'message': message})}\n\n"


@demo_bp.route("/api/demo/status", methods=["GET"])
def demo_status():
    return jsonify({
        "has_data": _has_courses()
    })


@demo_bp.route("/api/demo/seed", methods=["POST"])
def seed_demo():

    def event_stream():

        # ---------------------------------------------------
        # STEP 1 — Seed demo curriculum
        # ---------------------------------------------------
        yield _sse("Creating demo curriculum data...")

        try:
            from seed_curriculum_demo import seed as run_seed

            run_seed()

            yield _sse("Demo curriculum seeded successfully.")

        except Exception as e:
            print(f"[DEMO SEED ERROR] {e}")

            yield _sse(f"Curriculum seed failed: {str(e)}", "error")
            return

        # ---------------------------------------------------
        # STEP 2 — Fetch course IDs
        # ---------------------------------------------------
        course_ids = []

        try:
            conn = get_db()

            if conn:
                cur = conn.cursor()

                cur.execute("SELECT id FROM curricula ORDER BY id")

                rows = cur.fetchall()

                course_ids = [row[0] for row in rows]

                cur.close()
                conn.close()

        except Exception as e:
            print(f"[COURSE FETCH ERROR] {e}")

        # ---------------------------------------------------
        # STEP 3 — Seed xAPI data
        # ---------------------------------------------------
        yield _sse(
            f"Generating learner analytics for {len(course_ids)} courses..."
        )

        try:
            from services.xapi_generator import (
                generate_all_courses,
                seed_all_feedback
            )

            generate_all_courses(noise_ratio=0.08)

            seed_all_feedback(noise_ratio=0.08)

            yield _sse("Learner analytics generated successfully.")

        except Exception as e:
            print(f"[XAPI ERROR] {e}")

            yield _sse(f"xAPI generation failed: {str(e)}", "error")

        # ---------------------------------------------------
        # STEP 4 — Run curriculum analysis
        # ---------------------------------------------------
        yield _sse("Running curriculum analysis...")

        errors = 0

        try:
            from routes.curriculum_agent_routes import (
                _run_structural_analysis
            )

            for course_id in course_ids:
                try:
                    _run_structural_analysis(course_id)

                except Exception as course_err:
                    errors += 1

                    print(
                        f"[ANALYSIS ERROR] Course {course_id}: {course_err}"
                    )

        except Exception as e:
            print(f"[ANALYSIS IMPORT ERROR] {e}")

            yield _sse(f"Analysis failed: {str(e)}", "error")
            return

        if errors > 0:
            yield _sse(
                f"Analysis completed with {errors} skipped courses."
            )
        else:
            yield _sse("Curriculum analysis completed successfully.")

        # ---------------------------------------------------
        # DONE
        # ---------------------------------------------------
        yield _sse(
            "Demo environment ready successfully!",
            "done"
        )

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )