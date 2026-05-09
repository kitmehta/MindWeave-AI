"""Source preview route."""

import json
from flask import Blueprint, request, jsonify

from extensions import redis_client
from services.research import (
    research_sources,
    score_credibility,
)

sources_bp = Blueprint("sources", __name__)


@sources_bp.route("/api/sources/preview", methods=["POST"])
def preview_sources():
    """
    Return researched sources for curriculum generation.
    """

    try:
        data = request.get_json()

        topic = data.get("topic", "").strip()
        level = data.get("level", "").strip()
        audience = data.get("audience", "").strip()

        # ---------------------------------------------------
        # VALIDATION
        # ---------------------------------------------------
        if not topic or not level or not audience:
            return jsonify({
                "error": "Missing required fields: topic, level, audience"
            }), 400

        # ---------------------------------------------------
        # REDIS CACHE CHECK
        # ---------------------------------------------------
        cache_key = f"sources_preview:{topic}:{level}:{audience}"

        if redis_client is not None:
            try:
                cached = redis_client.get(cache_key)

                if cached:
                    print(f"Redis cache hit: {cache_key}")

                    return json.loads(cached)

            except Exception as redis_err:
                print(f"Redis GET error: {redis_err}")

        # ---------------------------------------------------
        # FETCH SOURCES
        # ---------------------------------------------------
        raw_sources = research_sources(
            topic=topic,
            level=level,
            audience=audience
        )

        sources = []

        for source in raw_sources:

            source_data = {
                "url": source.get("url", ""),
                "title": source.get("title", ""),
                "type": source.get("type", "other"),
                "snippet": source.get("content", ""),
                "credibility": score_credibility(
                    source.get("url", ""),
                    source.get("type", "")
                ),

                # Static tags (safe fallback)
                "tags": [
                    "AI",
                    "Research",
                ],
            }

            sources.append(source_data)

        print(
            f"Prepared {len(sources)} preview sources for topic: {topic}"
        )

        response_data = {
            "sources": sources
        }

        # ---------------------------------------------------
        # STORE CACHE
        # ---------------------------------------------------
        if redis_client is not None:
            try:
                redis_client.setex(
                    cache_key,
                    604800,
                    json.dumps(response_data)
                )

            except Exception as redis_err:
                print(f"Redis SET error: {redis_err}")

        return jsonify(response_data)

    except Exception as e:
        print(f"[SOURCES PREVIEW ERROR] {e}")

        return jsonify({
            "error": str(e)
        }), 500