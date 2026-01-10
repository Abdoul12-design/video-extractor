#!/bin/bash
# Script de build pour Render.com
# Met à jour pip et installe les dépendances

echo "🔧 Mise à jour de pip..."
pip install --upgrade pip

echo "📦 Installation des dépendances..."
pip install -r requirements.txt

echo "✅ Build terminé avec succès!"
