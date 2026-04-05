"""Entry point – python run.py"""

import os
from pathlib import Path

from app import create_app

# Criar pastas de dados se não existirem
os.makedirs('data', exist_ok=True)

app = create_app()

# ✅ INICIALIZAR BANCO DE DADOS
with app.app_context():
    from app.models import db
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, port=5000)