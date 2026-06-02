"""Configuração Flask."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # SQLAlchemy moderno exige postgresql:// (não postgres://)
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'data' / 'dragagem.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    # Keepalives mantêm a conexão TCP viva em transações longas (ex.: importação
    # da tábua) e evitam que o Supabase derrube o socket ocioso. São parâmetros
    # do libpq/psycopg2: só se aplicam ao Postgres — passá-los ao SQLite quebra
    # a conexão (sqlite3.connect não aceita esses kwargs).
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    # Cookies de sessão. SECURE exige HTTPS (ok em produção/Render e em
    # localhost, que os navegadores tratam como contexto seguro).
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

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
        # Em produção (ENV=production) exigir banco persistente: SQLite em disco
        # efêmero (Heroku/Railway) perde todos os dados a cada restart.
        if os.environ.get("ENV", "").lower() == "production" and not os.environ.get("DATABASE_URL"):
            raise RuntimeError(
                "ENV=production exige DATABASE_URL (Postgres). "
                "Sem ela o app usaria SQLite em disco efêmero e perderia "
                "todos os dados a cada restart."
            )
