"""Plot-Ark backend entry point."""

import os
from dotenv import load_dotenv

load_dotenv()
print("DATABASE_URL =", os.getenv("DATABASE_URL"))

from extensions import app
from db import init_db

# ---------------------------------------------------------------------------
# Route Blueprints
# ---------------------------------------------------------------------------
from routes.curriculum import curriculum_bp
from routes.curriculum_agent_routes import curriculum_agent_bp
from routes.history import history_bp
from routes.sources import sources_bp
from routes.graph import graph_bp
from routes.xapi import xapi_bp, seed_mock_xapi
from routes.syllabus import syllabus_bp
from routes.materials import materials_bp
from routes.feedback import feedback_bp
from routes.analytics import analytics_bp
from routes.settings import settings_bp
from routes.demo import demo_bp
from routes.mastery import mastery_bp
from routes.annotations import annotations_bp
from routes.profile import profile_bp
from routes.prompts import prompts_bp

# ---------------------------------------------------------------------------
# Register Blueprints
# ---------------------------------------------------------------------------
app.register_blueprint(curriculum_bp, url_prefix="/api/curriculum")
app.register_blueprint(curriculum_agent_bp)
app.register_blueprint(history_bp)
app.register_blueprint(sources_bp)
app.register_blueprint(graph_bp)
app.register_blueprint(xapi_bp)
app.register_blueprint(syllabus_bp)
app.register_blueprint(materials_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(demo_bp)
app.register_blueprint(mastery_bp)
app.register_blueprint(annotations_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(prompts_bp)

# ---------------------------------------------------------------------------
# Health Check Route
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def health_check():
    return {
        "status": "ok",
        "message": "Plot-Ark backend running successfully"
    }, 200


# ---------------------------------------------------------------------------
# Startup Initialization
# ---------------------------------------------------------------------------
try:
    init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"Database initialization failed: {e}")

try:
    seed_mock_xapi()
    print("Mock xAPI seeded successfully.")
except Exception as e:
    print(f"Mock xAPI seed failed: {e}")


# ---------------------------------------------------------------------------
# Run Flask App
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
        threaded=True
    )