"""Entry point — python run.py"""
import os
from pathlib import Path

from app import create_app

# Criar pasta de dados se não existir
os.makedirs('instance', exist_ok=True)
os.makedirs('app/dados', exist_ok=True)  # ou onde seu DB está

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
