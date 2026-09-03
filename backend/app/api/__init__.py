def register_blueprints(app):
    from .admin import admin_bp
    from .auth import auth_bp
    from .feedback import feedback_bp
    from .practice import practice_bp
    from .prompt import prompt_bp
    from .stats import stats_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(practice_bp, url_prefix="/api")
    app.register_blueprint(feedback_bp, url_prefix="/api")
    app.register_blueprint(prompt_bp, url_prefix="/api")
    app.register_blueprint(stats_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
