"""Entry point – python run.py"""

import sys
import os

from app import create_app

os.makedirs('data', exist_ok=True)

print("DATABASE_URL encontrada:", bool(os.environ.get("DATABASE_URL")))

try:
    app = create_app()
    print("App criado com sucesso")
except Exception as e:
    print(f"ERRO ao criar app: {e}", file=sys.stderr)
    raise

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)