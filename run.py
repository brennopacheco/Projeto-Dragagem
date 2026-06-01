"""Entry point – python run.py"""

import os

from app import create_app

# Criar pastas de dados se não existirem
os.makedirs('data', exist_ok=True)

app = create_app()

print("DATABASE_URL encontrada:", bool(os.environ.get("DATABASE_URL")))
print("URI sendo usada:", app.config.get("SQLALCHEMY_DATABASE_URI", "")[:30])

if __name__ == "__main__":
    app.run(debug=True, port=5000)