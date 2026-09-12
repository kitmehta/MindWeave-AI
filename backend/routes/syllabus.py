"""Syllabus parse route."""

import os
import json

from flask import Blueprint, request, jsonify

from config import AI_PROVIDER
from extensions import openai_client
from services.file_parser import extract_text_from_bytes

# ---------------------------------------------------
# GEMINI CLIENT
# ---------------------------------------------------
client = None

if AI_PROVIDER == "gemini":
    try:
        from google import genai

        client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY")
        )

        print("Gemini client initialized successfully.")

    except Exception as e:
        print(f"Gemini initialization failed: {e}")

# ---------------------------------------------------
# BLUEPRINT
# ---------------------------------------------------
syllabus_bp = Blueprint("syllabus", __name__)


@syllabus_bp.route("/api/syllabus/parse", methods=["POST"])
def parse_syllabus():
    """
    Parse uploaded syllabus PDF/DOCX using AI.
    """

    # ---------------------------------------------------
    # VALIDATE FILE
    # ---------------------------------------------------
    if "file" not in request.files:
        return jsonify({
            "error": "No file field in request"
        }), 400

    uploaded = request.files["file"]

    if not uploaded or not uploaded.filename:
        return jsonify({
            "error": "No file uploaded"
        }), 400

    filename = uploaded.filename

    ext = os.path.splitext(filename.lower())[1]

    if ext not in [".pdf", ".docx"]:
        return jsonify({
            "error": "Only PDF and DOCX files are supported"
        }), 400

    # ---------------------------------------------------
    # READ FILE
    # ---------------------------------------------------
    content = uploaded.read()

    if len(content) > 10 * 1024 * 1024:
        return jsonify({
            "error": "File too large (max 10MB)"
        }), 400

    # ---------------------------------------------------
    # EXTRACT TEXT
    # ---------------------------------------------------
    try:
        text = extract_text_from_bytes(
            filename,
            content
        )

    except Exception as e:
        print(f"Syllabus extraction error: {e}")

        return jsonify({
            "error": f"Failed to extract text: {str(e)}"
        }), 500

    if not text.strip():
        return jsonify({
            "error": "No readable text found in syllabus"
        }), 400

    # ---------------------------------------------------
    # LIMIT TOKENS
    # ---------------------------------------------------
    truncated = text[:6000]

    # ---------------------------------------------------
    # PROMPT
    # ---------------------------------------------------
    prompt = f"""
You are a syllabus parser.

Return ONLY valid JSON.

Structure:

{{
  "fields": {{
    "topic": "",
    "course_code": "",
    "level": "",
    "audience": "",
    "accreditation_context": "",
    "course_type": ""
  }},
  "modules": [],
  "references": [],
  "assignments": []
}}

Rules:
- Extract only information explicitly written
- Do not hallucinate
- Return valid JSON only

Syllabus text:

{truncated}
"""

    # ---------------------------------------------------
    # AI GENERATION
    # ---------------------------------------------------
    try:

        # -----------------------------------------------
        # GEMINI
        # -----------------------------------------------
        if AI_PROVIDER == "gemini":

            if client is None:
                return jsonify({
                    "error": "Gemini client not initialized"
                }), 500

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )

            raw = response.text.strip()

        # -----------------------------------------------
        # OPENAI
        # -----------------------------------------------
        else:

            if openai_client is None:
                return jsonify({
                    "error": "OpenAI client not initialized"
                }), 500

            response = openai_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.2,
                max_tokens=2000,
            )

            raw = response.choices[0].message.content.strip()

        # ---------------------------------------------------
        # CLEAN JSON
        # ---------------------------------------------------
        raw = (
            raw
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        parsed = json.loads(raw)

        return jsonify({
            "fields": parsed.get("fields", {}),
            "modules": parsed.get("modules", []),
            "references": parsed.get("references", []),
            "assignments": parsed.get("assignments", []),
        })

    # ---------------------------------------------------
    # JSON ERROR
    # ---------------------------------------------------
    except json.JSONDecodeError as e:

        print(f"JSON parse error: {e}")

        print(f"RAW RESPONSE:\n{raw[:500]}")

        return jsonify({
            "error": "AI returned invalid JSON"
        }), 500

    # ---------------------------------------------------
    # GENERAL ERROR
    # ---------------------------------------------------
    except Exception as e:

        print(f"Syllabus AI error: {e}")

        return jsonify({
            "error": str(e)
        }), 500