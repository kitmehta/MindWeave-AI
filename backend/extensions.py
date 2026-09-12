"""
Flask app, AI clients, Redis, and third-party service initialization.
Groq-first architecture with backward compatibility for old OpenAI imports.
"""

import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
from groq import Groq
from tavily import TavilyClient

# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)

# ---------------------------------------------------------------------------
# Redis (optional)
# ---------------------------------------------------------------------------
redis_client = None

try:
    import redis

    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=0,
        decode_responses=True,
    )

    redis_client.ping()
    print("✅ Redis connected")

except Exception as e:
    print(f"⚠️ Redis unavailable: {e}")
    redis_client = None

# ---------------------------------------------------------------------------
# Redis helper
# ---------------------------------------------------------------------------
_REDIS_PREFIX = "plotark:settings:"


def _resolve(redis_key: str, env_value: str | None = None) -> str | None:
    """
    Resolve values from Redis first, fallback to environment.
    """

    try:
        if redis_client:
            stored = redis_client.get(_REDIS_PREFIX + redis_key)

            if stored:
                return stored

    except Exception as e:
        print(f"Redis resolve error ({redis_key}): {e}")

    return env_value


# ---------------------------------------------------------------------------
# GROQ CLIENT
# ---------------------------------------------------------------------------
groq_client = None

try:
    resolved_groq_key = _resolve(
        "groq_key",
        os.getenv("GROQ_API_KEY")
    )

    if resolved_groq_key:
        groq_client = Groq(api_key=resolved_groq_key)
        print("✅ Groq client initialized")

    else:
        print("⚠️ GROQ_API_KEY missing")

except Exception as e:
    print(f"❌ Groq initialization failed: {e}")
    groq_client = None


# ---------------------------------------------------------------------------
# BACKWARD COMPATIBILITY
# IMPORTANT:
# Old files still import openai_client
# We alias Groq client to avoid rewriting whole project
# ---------------------------------------------------------------------------
openai_client = groq_client


# ---------------------------------------------------------------------------
# TAVILY CLIENT
# ---------------------------------------------------------------------------
tavily_client = None

try:
    resolved_tavily_key = _resolve(
        "tavily_key",
        os.getenv("TAVILY_API_KEY")
    )

    if resolved_tavily_key:
        tavily_client = TavilyClient(api_key=resolved_tavily_key)
        print("✅ Tavily client initialized")

    else:
        print("⚠️ TAVILY_API_KEY missing")

except Exception as e:
    print(f"❌ Tavily initialization failed: {e}")
    tavily_client = None


# ---------------------------------------------------------------------------
# GENERATE FUNCTION
# ---------------------------------------------------------------------------
def generate_with_groq(
    prompt: str,
    model: str = "openai/gpt-oss-120b"
):
    """
    Safe Groq generation wrapper.
    """

    if not groq_client:
        return "Groq client not initialized"

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=4000,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Groq generation error: {e}")
        return f"Groq error: {str(e)}"


# ---------------------------------------------------------------------------
# RELOAD CLIENTS
# ---------------------------------------------------------------------------
def reload_clients() -> None:
    """
    Reload AI clients dynamically.
    """

    global groq_client
    global openai_client
    global tavily_client

    # ---------------- GROQ ----------------
    try:
        groq_key = _resolve(
            "groq_key",
            os.getenv("GROQ_API_KEY")
        )

        if groq_key:
            groq_client = Groq(api_key=groq_key)

            # backward compatibility
            openai_client = groq_client

            print("✅ Groq client reloaded")

        else:
            groq_client = None
            openai_client = None

            print("⚠️ Groq key missing during reload")

    except Exception as e:
        print(f"❌ Groq reload failed: {e}")

        groq_client = None
        openai_client = None

    # ---------------- TAVILY ----------------
    try:
        tavily_key = _resolve(
            "tavily_key",
            os.getenv("TAVILY_API_KEY")
        )

        if tavily_key:
            tavily_client = TavilyClient(api_key=tavily_key)
            print("✅ Tavily client reloaded")

        else:
            tavily_client = None
            print("⚠️ Tavily key missing during reload")

    except Exception as e:
        print(f"❌ Tavily reload failed: {e}")
        tavily_client = None

    print("✅ AI clients reload complete")