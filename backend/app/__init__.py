from pathlib import Path

import click
from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .models import (
    User,
    UserAccount,
    backfill_practice_evaluation_versions,
    configure_sqlite,
    db,
)
from .schema import upgrade_schema


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
        upgrade_schema()
        backfill_practice_evaluation_versions()

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "service": "interploop"})

    @app.cli.command("create-admin")
    @click.option("--login-id", prompt="管理员账号")
    @click.option("--name", prompt="管理员姓名")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(login_id, name, password):
        """Create the first administrator account."""
        if len(password) < app.config["PASSWORD_MIN_LENGTH"]:
            raise click.ClickException(
                f"密码至少需要 {app.config['PASSWORD_MIN_LENGTH']} 位"
            )
        if UserAccount.query.filter_by(login_id=login_id.strip()).first():
            raise click.ClickException("管理员账号已存在")
        user = User(name=name.strip(), role="admin")
        db.session.add(user)
        db.session.flush()
        account = UserAccount(user_id=user.id, login_id=login_id.strip())
        account.set_password(password, must_change=False)
        db.session.add(account)
        db.session.commit()
        click.echo(f"管理员账号 {login_id.strip()} 已创建")

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
