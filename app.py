from flask import Flask
import importlib
import logging
import os

from config import get_config, MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE
from extensions import db
from utils.mysql import get_mysql_url, ensure_database_exists

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure the Flask application, initialize DB extensions and ensure tables exist."""
    cfg = get_config()
    proc_cfg = cfg.get("PROCESSING_CONFIG", {}) if isinstance(cfg, dict) else {}
    # Prefer MySQL credentials exported by top-level `config` module.
    # Fall back to environment variables when not present.
    user = MYSQL_USER or os.environ.get("MYSQL_USER")
    password = MYSQL_PASSWORD or os.environ.get("MYSQL_PASSWORD")
    host = MYSQL_HOST or os.environ.get("MYSQL_HOST")
    port = MYSQL_PORT or os.environ.get("MYSQL_PORT")
    database = MYSQL_DATABASE or os.environ.get("MYSQL_DATABASE")

    # ensure database exists on the server (pass credentials if available)
    try:
        # If credentials provided, ensure the DB exists using them; otherwise rely on env-derived defaults
        ensure_database_exists(user=user, password=password, host=host, port=port, db_name=database)
    except Exception as e:
        logger.warning(f"ensure_database_exists failed: {e}")

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = get_mysql_url(user=user, password=password, host=host, port=port, db=database)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Type"
        return response

    # initialize db extension
    db.init_app(app)

    # create tables within app context
    with app.app_context():
        # import models so SQLAlchemy can register them
        try:
            import schemas.file  # registers File
            import schemas.jobs  # registers Jobs
            import schemas.graph
            import schemas.filegraph
            import schemas.syllabus
            import schemas.syllabusgraph
            import schemas.user
            import schemas.user_syllabus
        except Exception:
            # models may already be imported elsewhere; ignore import errors here
            pass
        try:
            db.create_all()
        except Exception as e:
            logger.warning(f"db.create_all() failed: {e}")

    blueprint_targets = [
        ("blueprint.file_transmit_api", "bp"),
        ("blueprint.knowledge_build_api", "bp"),
        ("blueprint.learning_api", "bp"),
        ("blueprint.syllabus_material_api", "bp"),
        ("blueprint.user_api", "bp"),
    ]

    for module_name, attr_name in blueprint_targets:
        try:
            module = importlib.import_module(module_name)
            blueprint = getattr(module, attr_name)
            app.register_blueprint(blueprint)
        except Exception:
            logger.exception(f"register blueprint failed: {module_name}.{attr_name}")

    return app
