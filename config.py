"""Configuração Flask."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'data' / 'dragagem.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")

    # Senhas de acesso (obrigatórias via .env)
    SENHA_GERENTE = os.environ.get("SENHA_GERENTE")
    SENHA_COMANDANTE = os.environ.get("SENHA_COMANDANTE")

    @staticmethod
    def validate():
        missing = []
        for var in ("SECRET_KEY", "SENHA_GERENTE", "SENHA_COMANDANTE"):
            if not os.environ.get(var):
                missing.append(var)
        if missing:
            raise RuntimeError(
                f"Variáveis obrigatórias não definidas no .env: {', '.join(missing)}"
            )
