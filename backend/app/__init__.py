from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .extensions import db
from .models import configure_sqlite


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    CORS(
        app,
        supports_credentials=True,
        origins=app.config["CORS_ORIGINS"],
    )
    db.init_app(app)
    configure_sqlite(db)

    from .api import register_blueprints

    register_blueprints(app)

    with app.app_context():
        db.create_all()

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "service": "interploop"})

    @app.errorhandler(400)
    def bad_request(err):
        return jsonify({"error": getattr(err, "description", "Bad request")}), 400

    @app.errorhandler(401)
    def unauthorized(err):
        return jsonify({"error": getattr(err, "description", "Unauthorized")}), 401

    @app.errorhandler(403)
    def forbidden(err):
        return jsonify({"error": getattr(err, "description", "Forbidden")}), 403

    @app.errorhandler(404)
    def not_found(err):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(err):
        return jsonify({"error": "Internal server error"}), 500

    return app
