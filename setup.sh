#!/bin/bash

echo "🚀 Iniciando setup del proyecto Sistema de Tickets..."

echo "📦 Backend..."
cd app
python -m venv ../.venv
source ../.venv/Scripts/activate
pip install -r ../requirements.txt
deactivate
cd ..

echo "🌐 Frontend..."
cd frontend-angular
npm install
cd ..

echo "✅ Todo listo. Puedes correr el backend y el frontend."
