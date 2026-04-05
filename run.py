"""Entry point – python run.py"""

import os

from app import create_app

# Criar pastas de dados se não existirem
os.makedirs('data', exist_ok=True)

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)