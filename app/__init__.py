"""Flask app factory."""

import sys

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app():
    from config import Config
    Config.validate()

    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401
        from app.routes import bp
        app.register_blueprint(bp)
        try:
            db.create_all()
            print("Tabelas criadas/verificadas com sucesso")
        except Exception as e:
            print(f"ERRO ao criar tabelas: {e}", file=sys.stderr)
            raise

    return app
