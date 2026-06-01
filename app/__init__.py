"""Flask app factory."""

import sys

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app():
    from config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    Config.validate()

    db.init_app(app)

    with app.app_context():
        from app import models  # noqa: F401
        try:
            db.create_all()
            print("Tabelas criadas/verificadas com sucesso")
        except Exception as e:
            print(f"ERRO ao criar tabelas: {e}", file=sys.stderr)
            raise

    from app.routes import bp
    app.register_blueprint(bp)

    return app
