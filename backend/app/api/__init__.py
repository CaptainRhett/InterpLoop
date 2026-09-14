def register_blueprints(api):
    from .admin import admin_bp
    from .system import system_bp
    from .auth import auth_bp
    from .feedback import feedback_bp
    from .practice import practice_bp
    from .prompt import prompt_bp
    from .stats import stats_bp
    from .chat import bp as llm_bp

    api.register_blueprint(system_bp, url_prefix="/api/admin/system")
    api.register_blueprint(auth_bp, url_prefix="/api/auth")
    api.register_blueprint(practice_bp, url_prefix="/api")
    api.register_blueprint(feedback_bp, url_prefix="/api")
    api.register_blueprint(prompt_bp, url_prefix="/api")
    api.register_blueprint(stats_bp, url_prefix="/api")
    api.register_blueprint(admin_bp, url_prefix="/api/admin")
    api.register_blueprint(llm_bp, url_prefix="/api/llm")
