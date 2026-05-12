"""Curriculum generation routes: generate, skeleton, expand, save."""

import json
import os
import re
from flask import Blueprint, request, Response, stream_with_context, jsonify

from config import AI_PROVIDER
from extensions import openai_client
from db import save_curriculum

from services.prompt_builder import (
    build_generate_prompt,
    build_skeleton_prompt,
    build_expand_prompt,
)

# =========================================================

curriculum_bp = Blueprint("curriculum", __name__)


# =========================================================
# SAFE JSON EXTRACTION (ROBUST)
# =========================================================
def extract_json(text: str):
    """
    Safely extracts first valid JSON object from LLM output.
    """
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None

        cleaned = match.group(0)

        # remove markdown artifacts
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        return json.loads(cleaned)

    except Exception as e:
        print("JSON extraction error:", e)
        print("RAW OUTPUT:", text[:1000])
        return None


# =========================================================
# GENERATE FULL CURRICULUM
# =========================================================
@curriculum_bp.route("/api/curriculum/generate", methods=["POST"])
def generate_curriculum():

    data = request.get_json()

    topic = data.get("topic", "")
    level = data.get("level", "")
    audience = data.get("audience", "")

    if not all([topic, level, audience]):
        return jsonify({"error": "Missing required fields"}), 400

    prompt = build_generate_prompt(
        topic=topic,
        level=level,
        audience=audience,
        accreditation_context=data.get("accreditation_context", ""),
        course_code=data.get("course_code", ""),
        course_type=data.get("course_type", "mixed"),
        module_count=int(data.get("module_count", 6)),
        session_duration=int(data.get("session_duration", 90)),
        design_approach=data.get("design_approach", "addie"),
        real_sources=[],
        required_sources=[],
        optional_sources=[],
    )

    try:

        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )

        full_text = response.choices[0].message.content
        #print(full_text)

        parsed = extract_json(full_text)

        if not parsed:
            return jsonify({
                "error": "Invalid curriculum JSON",
                "raw": full_text[:1000]
            }), 500

        return jsonify(parsed)

    except Exception as e:
        print("Generate error:", e)
        return jsonify({"error": str(e)}), 500


# =========================================================
# SAVE CURRICULUM
# =========================================================
@curriculum_bp.route("/api/curriculum/save", methods=["POST"])
def save_curriculum_endpoint():

    data = request.get_json()

    try:
        parsed = {
            "modules": data.get("modules", []),
            "sources": data.get("sources", []),
            "course_narrative": data.get("course_narrative", ""),
        }

        new_id = save_curriculum(
            data.get("topic", ""),
            data.get("level", ""),
            data.get("audience", ""),
            data.get("course_code", ""),
            data.get("course_type", "mixed"),
            data.get("module_count", 0),
            parsed,
            data.get("design_approach", "addie"),
            semester=data.get("semester", ""),
        )

        return jsonify({
            "status": "saved",
            "course_id": new_id
        })

    except Exception as e:
        print("Save error:", e)
        return jsonify({"error": str(e)}), 500


# =========================================================
# GENERATE SKELETON (FIXED - MOST IMPORTANT)
# =========================================================
@curriculum_bp.route("/api/curriculum/skeleton", methods=["POST"])
def generate_skeleton():

    data = request.get_json()

    topic = data.get("topic", "")
    level = data.get("level", "")
    audience = data.get("audience", "")

    if not all([topic, level, audience]):
        return jsonify({"error": "Missing required fields"}), 400

    module_count = int(data.get("module_count", 6))

    prompt = build_skeleton_prompt(
        topic=topic,
        level=level,
        audience=audience,
        accreditation_context=data.get("accreditation_context", ""),
        course_code=data.get("course_code", ""),
        course_type=data.get("course_type", "mixed"),
        module_count=module_count,
        design_approach=data.get("design_approach", "addie"),
    )

    try:

        response = openai_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )
        full_text = response.choices[0].message.content

        #print(full_text)

        parsed = extract_json(full_text)

        if not parsed:
            return jsonify({
                "error": "Invalid skeleton response",
                "raw": full_text[:1000]
            }), 500

        return jsonify(parsed)

    except Exception as e:
        print("Skeleton error:", e)
        return jsonify({"error": str(e)}), 500


# =========================================================
# EXPAND MODULE
# =========================================================
@curriculum_bp.route("/api/curriculum/expand", methods=["POST"])
def expand_module():

    data = request.get_json()

    skeleton = data.get("skeleton", [])
    module_index = data.get("module_index", 0)

    if not skeleton:
        return jsonify({"error": "No skeleton provided"}), 400

    module = skeleton[module_index]

    prompt = build_expand_prompt(
        topic=data.get("topic", ""),
        level=data.get("level", ""),
        audience=data.get("audience", ""),
        accreditation_context=data.get("accreditation_context", ""),
        course_code=data.get("course_code", ""),
        course_type=data.get("course_type", "mixed"),
        design_approach=data.get("design_approach", "addie"),
        session_duration=int(data.get("session_duration", 90)),
        module_title=module.get("title", ""),
        module_number=module.get("module_number", 1),
        complexity_level=module.get("complexity_level", 1),
        learning_objectives=module.get("learning_objectives", []),
        total_modules=len(skeleton),
        approved_sources=[],
    )

    def event_stream():

        yield f"data: {json.dumps({'status': 'expanding'})}\n\n"

        full_text = ""

        try:

            response = openai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
            )

            full_text = response.choices[0].message.content

            #print("\n========== EXPAND RESPONSE ==========\n")
            #print(full_text)
            print("\n=====================================\n")

            yield f"data: {json.dumps({'text': full_text})}\n\n"

        except Exception as e:
            print("Expand error:", e)

        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
    )