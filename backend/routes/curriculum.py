"""Curriculum generation routes: generate, skeleton, expand, save."""

import json
import os
from flask import Blueprint, request, Response, stream_with_context, jsonify

from config import AI_PROVIDER
from extensions import openai_client, redis_client
from db import save_curriculum

from google import genai

from services.research import research_sources
from services.prompt_builder import (
    build_generate_prompt,
    build_skeleton_prompt,
    build_expand_prompt,
)

# GEMINI CLIENT
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

curriculum_bp = Blueprint("curriculum", __name__)


def _sanitize_json(text: str) -> str:
    result = []
    in_string = False
    escaped = False

    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue

        if ch == "\\":
            result.append(ch)
            escaped = True
            continue

        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue

        if in_string and ord(ch) < 0x20:
            _ESC = {
                "\n": "\\n",
                "\r": "\\r",
                "\t": "\\t",
                "\x0b": "\\u000b",
                "\x0c": "\\f",
                "\x08": "\\b",
            }
            result.append(_ESC.get(ch, f"\\u{ord(ch):04x}"))
        else:
            result.append(ch)

    return "".join(result)


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
        return {"error": "Missing required fields"}, 400

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

        # GEMINI
        if AI_PROVIDER == "gemini":

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )

            full_text = response.text

        # OPENAI
        else:

            response = openai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
            )

            full_text = response.choices[0].message.content

        clean = (
            full_text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

        first = clean.index("{")
        last = clean.rindex("}")

        parsed = json.loads(
            _sanitize_json(clean[first:last + 1])
        )

        return jsonify(parsed)

    except Exception as e:
        print(f"Skeleton error: {e}")
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
        print(f"Save endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


# =========================================================
# GENERATE SKELETON
# =========================================================

@curriculum_bp.route("/api/curriculum/skeleton", methods=["POST"])
def generate_skeleton():

    data = request.get_json()

    topic = data.get("topic", "")
    level = data.get("level", "")
    audience = data.get("audience", "")

    if not all([topic, level, audience]):
        return {"error": "Missing required fields"}, 400

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

    def event_stream():

        yield f"data: {json.dumps({'status': 'generating', 'message': 'Generating skeleton...'})}\n\n"

        try:

            # GEMINI
            if AI_PROVIDER == "gemini":

                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                )

                full_text = response.text

                yield f"data: {json.dumps({'text': full_text})}\n\n"

            # OPENAI
            else:

                response = openai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                )

                full_text = response.choices[0].message.content

                yield f"data: {json.dumps({'text': full_text})}\n\n"

        except Exception as e:
            print(f"Skeleton stream error: {e}")

        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
    )


# =========================================================
# EXPAND MODULE
# =========================================================

@curriculum_bp.route("/api/curriculum/expand", methods=["POST"])
def expand_module():

    data = request.get_json()

    skeleton = data.get("skeleton", [])
    module_index = data.get("module_index", 0)

    if not skeleton:
        return {"error": "No skeleton provided"}, 400

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

        yield f"data: {json.dumps({'status': 'expanding', 'message': 'Expanding module...'})}\n\n"

        try:

            # GEMINI
            if AI_PROVIDER == "gemini":

                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                )

                full_text = response.text

                yield f"data: {json.dumps({'text': full_text})}\n\n"

            # OPENAI
            else:

                response = openai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                )

                full_text = response.choices[0].message.content

                yield f"data: {json.dumps({'text': full_text})}\n\n"

        except Exception as e:
            print(f"Expand module error: {e}")

        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
    )