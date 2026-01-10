# 🎬 Video Extractor v2.0

Application Flutter moderne pour extraire et télécharger des vidéos depuis YouTube, Vimeo, Dailymotion et plus encore.

## ✨ Fonctionnalités

- ✅ Extraction de vidéos depuis plusieurs plateformes
- ✅ Support des playlists
- ✅ Sélection de la qualité vidéo
- ✅ Téléchargement optimisé en streaming
- ✅ Barre de progression en temps réel
- ✅ Sélection multiple de vidéos
- ✅ Support Android 11+ avec stockage scopé
- ✅ Interface moderne avec mode sombre
- ✅ Gestion robuste des erreurs
- ✅ Rate limiting côté serveur

## 🚀 Installation

### Backend (API Python/Flask)

1. **Installer les dépendances**
```bash
cd backend
pip install -r requirements.txt
```

2. **Lancer le serveur en local**
```bash
python main.py
```

Le serveur sera disponible sur `http://localhost:5000`

3. **Déployer sur Render.com** (recommandé)
   - Créez un compte sur [Render.com](https://render.com)
   - Créez un nouveau "Web Service"
   - Connectez votre repository Git
   - Utilisez les paramètres du fichier `api.yaml`
   - Déployez !

### Frontend (Application Flutter)

1. **Installer Flutter**
   - Suivez les instructions sur [flutter.dev](https://flutter.dev/docs/get-started/install)

2. **Installer les dépendances**
```bash
flutter pub get
```

3. **Configurer l'URL de l'API**
   - Copiez `.env.example` en `.env`
   - Modifiez `API_URL` selon votre environnement

4. **Lancer l'application**
```bash
# Pour Android
flutter run

# Pour iOS (nécessite un Mac)
flutter run -d ios

# Pour générer un APK
flutter build apk --release
```

## 📱 Configuration Android

### Permissions requises

Le fichier `AndroidManifest.xml` est pré-configuré avec les permissions suivantes:
- `INTERNET` - Pour la connexion à l'API
- `WRITE_EXTERNAL_STORAGE` - Pour Android ≤10
- `READ_EXTERNAL_STORAGE` - Pour Android ≤12
- `READ_MEDIA_VIDEO` - Pour Android 13+

### Stockage

- **Android 11+** : Utilise le stockage scopé (pas besoin de MANAGE_EXTERNAL_STORAGE)
- **Android ≤10** : Demande la permission de stockage classique
- Les fichiers sont sauvegardés dans le dossier Downloads de l'application

## 🔧 Architecture

### Backend
```
main.py              # API Flask
├── /api/extract     # Extraction des infos vidéo
├── /api/download    # Téléchargement en streaming
└── /api/health      # Health check
```

**Sécurité implémentée:**
- Validation d'URL
- Whitelist de domaines
- Rate limiting (10 req/min par IP)
- Limite de taille de fichier (500 MB)
- Streaming pour éviter la surcharge mémoire
- Timeout sur les requêtes

### Frontend
```
lib/
├── main.dart          # Point d'entrée
├── home_page.dart     # Page principale
└── models.dart        # Modèles de données
```

**Optimisations:**
- Téléchargement en streaming (chunks de 4KB)
- Barre de progression en temps réel
- Gestion des permissions Android 11+
- Gestion d'erreurs robuste
- Timeouts configurables

## 🔒 Sécurité

### Backend
- ✅ Validation stricte des URL
- ✅ Whitelist de domaines autorisés
- ✅ Rate limiting par IP
- ✅ Limite de taille de fichier
- ✅ Nettoyage automatique des fichiers temporaires
- ✅ Logs des erreurs

### Frontend
- ✅ Validation des entrées utilisateur
- ✅ Timeouts sur les requêtes
- ✅ Gestion des permissions Android
- ✅ Messages d'erreur clairs
- ✅ Pas de stockage de données sensibles

## 📊 Limites

- **Taille maximale par vidéo:** 500 MB
- **Rate limit:** 10 requêtes par minute par IP
- **Timeout extraction:** 30 secondes
- **Timeout téléchargement:** 10 minutes
- **Plateformes supportées:** YouTube, Vimeo, Dailymotion

## 🐛 Résolution de problèmes

### "Erreur de connexion"
- Vérifiez que l'API est démarrée
- Vérifiez l'URL de l'API dans le code
- Pour émulateur Android, utilisez `http://10.0.2.2:5000`
- Pour appareil physique, utilisez votre IP locale

### "Permission de stockage requise"
- Sur Android 11+, l'app utilise le stockage scopé (pas de permission nécessaire)
- Sur Android ≤10, acceptez la permission de stockage

### "Trop de requêtes"
- Attendez 1 minute avant de réessayer
- Le rate limit est de 10 requêtes par minute

### "Fichier trop volumineux"
- La limite est de 500 MB par vidéo
- Choisissez une qualité inférieure

### "Impossible d'extraire cette vidéo"
- Vérifiez que l'URL est correcte
- Assurez-vous que la vidéo n'est pas privée
- Certaines vidéos peuvent être protégées

## 🔄 Changelog

### Version 2.0.0
- ✅ Téléchargement en streaming (résout les problèmes de mémoire)
- ✅ Support Android 11+ avec stockage scopé
- ✅ Rate limiting côté serveur
- ✅ Validation et sécurité renforcées
- ✅ Barre de progression en temps réel
- ✅ Gestion d'erreurs améliorée
- ✅ UI/UX améliorée
- ✅ Configuration API flexible

### Version 1.0.0
- ✅ Extraction de vidéos
- ✅ Téléchargement de vidéos
- ✅ Interface de base

## 📝 Licence

MIT License - Libre d'utilisation et de modification

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
- Signaler des bugs
- Proposer des améliorations
- Soumettre des pull requests

## 👨‍💻 Développement

### Prérequis
- Python 3.9+
- Flutter 3.0+
- Android Studio (pour Android)
- Xcode (pour iOS, Mac uniquement)

### Tests
```bash
# Backend
python -m pytest

# Frontend
flutter test
```

## 📞 Support

Pour toute question ou problème :
1. Consultez d'abord la section "Résolution de problèmes"
2. Vérifiez les issues existantes
3. Créez une nouvelle issue si nécessaire

---

Fait avec ❤️ pour la communauté
