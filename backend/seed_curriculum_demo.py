"""Seed sample data into module_flags + change_log for ALL courses.

Automatically reads course IDs and module titles from the curricula table.
Seeds both 'pending' (professor notification) and 'applied' (student banner) entries.

Run:
    python seed_curriculum_demo.py
"""

import json
import os
import random

from db import get_db_raw


def seed():

    conn = get_db_raw()

    if not conn:
        print("ERROR: Could not connect to DB")
        return

    print("DB connection SUCCESS in seed")

    cur = conn.cursor()

    # ---------------------------------------------------------
    # LOAD COURSES
    # ---------------------------------------------------------

    cur.execute("""
        SELECT id, topic, modules
        FROM curricula
        ORDER BY id
    """)

    rows = cur.fetchall()

    if not rows:
        print("No courses found in curricula table.")
        cur.close()
        conn.close()
        return

    all_courses = {}

    for row in rows:

        course_id = row[0]
        topic = row[1]
        raw_modules = row[2]

        try:
            if isinstance(raw_modules, str):
                modules = json.loads(raw_modules)
            elif raw_modules is not None:
                modules = raw_modules
            else:
                modules = []
        except Exception:
            modules = []

        module_list = []

        for i, module in enumerate(modules):

            mod_id = f"module_{i + 1}"

            if isinstance(module, dict):
                mod_title = module.get("title", f"Module {i + 1}")
            else:
                mod_title = f"Module {i + 1}"

            module_list.append((mod_id, mod_title))

        if module_list:
            all_courses[course_id] = {
                "topic": topic,
                "modules": module_list,
            }

    print(f"Found {len(all_courses)} courses with modules.\n")

    # ---------------------------------------------------------
    # CLEAR OLD DATA
    # ---------------------------------------------------------

    cur.execute("DELETE FROM module_flags")
    cur.execute("DELETE FROM change_log")
    cur.execute("DELETE FROM cohort_concept_mastery")

    recommendation_templates = [
        "Consider reducing the complexity level of this module. Students are spending {time}x the expected time.",
        "Add introductory content. {pct}% of students are struggling with prerequisites.",
        "Break assessments into smaller checkpoints to improve completion.",
        "Add practical case studies to improve engagement.",
        "Add peer discussion activities before assignments.",
        "The current reading load is too high for this module.",
    ]

    # ---------------------------------------------------------
    # MODULE FLAGS + CHANGE LOG
    # ---------------------------------------------------------

    for course_id, info in all_courses.items():

        topic = info["topic"]
        modules = info["modules"]

        print(f"[Course {course_id}] {topic} ({len(modules)} modules)")

        if not modules:
            continue

        flag_count = min(random.randint(2, 3), len(modules))

        flagged_modules = random.sample(modules, flag_count)

        # ---------------------------------------------------------
        # MODULE FLAGS
        # ---------------------------------------------------------

        for mod_id, mod_name in flagged_modules:

            flag_level = random.choice(["yellow", "orange"])

            signals = []

            if random.random() > 0.35:
                signals.append({
                    "source": "content_optimizer",
                    "detail": f"{mod_name} has a high struggle rate.",
                    "metric": "struggle_rate",
                    "value": round(random.uniform(0.28, 0.52), 2),
                })

            if random.random() > 0.45:
                signals.append({
                    "source": "risk_detector",
                    "detail": f"Students are at-risk in {mod_name}.",
                    "metric": "at_risk_pct",
                    "value": round(random.uniform(0.25, 0.45), 2),
                })

            if random.random() > 0.55:
                signals.append({
                    "source": "behavior_analyst",
                    "detail": f"Low completion rate detected in {mod_name}.",
                    "metric": "completion_rate",
                    "value": round(random.uniform(0.35, 0.55), 2),
                })

            if not signals:
                signals.append({
                    "source": "content_optimizer",
                    "detail": f"Negative feedback signals detected in {mod_name}.",
                    "metric": "negative_feedback",
                    "value": random.randint(3, 7),
                })

            cur.execute("""
                INSERT INTO module_flags
                (
                    course_id,
                    module_id,
                    flag_level,
                    signals,
                    dismissed
                )
                VALUES (%s, %s, %s, %s, FALSE)
            """, (
                course_id,
                mod_id,
                flag_level,
                json.dumps(signals),
            ))

            print(
                f"  [FLAG] {mod_id} ({mod_name}) "
                f"level={flag_level} signals={len(signals)}"
            )

        # ---------------------------------------------------------
        # CHANGE LOG
        # ---------------------------------------------------------

        for idx, (mod_id, mod_name) in enumerate(flagged_modules[:3]):

            template = random.choice(recommendation_templates)

            recommendation = template.format(
                time=round(random.uniform(2.1, 3.8), 1),
                pct=random.randint(28, 48),
            )

            reasons_pool = [
                "high_struggle_rate",
                "at_risk_concentration",
                "low_completion_rate",
                "negative_feedback",
                "time_on_task_anomaly",
            ]

            flag_reasons = random.sample(
                reasons_pool,
                random.randint(1, 3),
            )

            status = "applied" if idx == 0 else "pending"

            backup_data = None

            if status == "applied":

                try:
                    mod_idx = int(mod_id.replace("module_", "")) - 1

                    cur.execute("""
                        SELECT modules
                        FROM curricula
                        WHERE id = %s
                    """, (course_id,))

                    row = cur.fetchone()

                    if row:

                        curr_modules = row[0]

                        if isinstance(curr_modules, str):
                            curr_modules = json.loads(curr_modules)

                        if (
                            curr_modules
                            and 0 <= mod_idx < len(curr_modules)
                        ):
                            backup_data = json.dumps(
                                curr_modules[mod_idx]
                            )

                except Exception as e:
                    print(f"Backup creation error: {e}")

            if status == "applied":
                change_type = "objective_update"
            elif idx == 1:
                change_type = "reference_suggestion"
            else:
                change_type = "assignment_alert"

            cur.execute("""
                INSERT INTO change_log
                (
                    course_id,
                    module_id,
                    flag_reason,
                    recommendation,
                    agent,
                    status,
                    backup_data,
                    change_type
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(course_id),
                mod_id,
                flag_reasons,
                recommendation,
                "curriculum_agent",
                status,
                backup_data,
                change_type,
            ))

            print(
                f"  [CHANGE_LOG] {mod_id} "
                f"status={status} "
                f"reasons={flag_reasons}"
                f"{' (with backup)' if backup_data else ''}"
            )

        print()

    # ---------------------------------------------------------
    # COHORT MASTERY
    # ---------------------------------------------------------

    print("\nSeeding cohort concept mastery...")

    seed_cohort_mastery(cur, all_courses)

    conn.commit()

    cur.close()
    conn.close()

    print("✅ Demo data seeded for ALL courses!")


def seed_cohort_mastery(cur, all_courses):

    MASTERY_POOL = (
        ["mastered"] * 30
        + ["learning"] * 35
        + ["struggling"] * 20
        + ["not_started"] * 15
    )

    SEMESTER = "Fall 2025"

    for course_id, info in all_courses.items():

        modules = info["modules"]

        for mod_id, mod_title in modules:

            base = next(
                (
                    word
                    for word in mod_title.split()
                    if len(word) > 3
                ),
                mod_title[:8],
            )

            concepts = [
                (f"{mod_id}_c1", f"{base} Principles"),
                (f"{mod_id}_c2", f"{base} Application"),
                (f"{mod_id}_c3", f"{base} Analysis"),
                (f"{mod_id}_c4", f"{base} Case Study"),
                (f"{mod_id}_c5", f"{base} Theory"),
            ]

            for concept_id, concept_label in concepts:

                mastery = random.choice(MASTERY_POOL)

                total = random.randint(18, 30)

                completed = total

                if mastery == "mastered":
                    passed = int(total * 0.85)
                    failed = int(total * 0.05)
                    struggled = total - passed - failed

                elif mastery == "learning":
                    passed = int(total * 0.55)
                    failed = int(total * 0.15)
                    struggled = total - passed - failed

                elif mastery == "struggling":
                    passed = int(total * 0.25)
                    failed = int(total * 0.35)
                    struggled = total - passed - failed

                else:
                    passed = 0
                    failed = 0
                    struggled = total

                cur.execute("""
                    INSERT INTO cohort_concept_mastery
                    (
                        course_id,
                        semester,
                        module_id,
                        concept_id,
                        concept_label,
                        mastery_level,
                        completed_count,
                        passed_count,
                        failed_count,
                        struggled_count
                    )
                    VALUES
                    (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                """, (
                    course_id,
                    SEMESTER,
                    mod_id,
                    concept_id,
                    concept_label,
                    mastery,
                    completed,
                    passed,
                    failed,
                    struggled,
                ))

        print(
            f"  [MASTERY] Course {course_id} "
            f"({info['topic']}): fallback module concepts seeded"
        )


if __name__ == "__main__":
    seed()