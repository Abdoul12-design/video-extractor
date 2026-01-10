from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import re
from urllib.parse import urlparse
import logging
from functools import wraps
import time

app = Flask(__name__)
CORS(app)

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_DOMAINS = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com']
RATE_LIMIT = {}  # Simple rate limiting in memory

def validate_url(url):
    """Valide l'URL de la vidéo"""
    try:
        parsed = urlparse(url)
        if not parsed.scheme in ['http', 'https']:
            return False, "Protocole non autorisé"
        
        domain = parsed.netloc.replace('www.', '')
        if not any(allowed in domain for allowed in ALLOWED_DOMAINS):
            return False, f"Domaine non autorisé. Domaines acceptés: {', '.join(ALLOWED_DOMAINS)}"
        
        return True, None
    except Exception as e:
        return False, f"URL invalide: {str(e)}"

def rate_limit_check(ip_address):
    """Vérifie le rate limiting (10 requêtes par minute)"""
    current_time = time.time()
    
    if ip_address not in RATE_LIMIT:
        RATE_LIMIT[ip_address] = []
    
    # Nettoyer les anciennes requêtes (plus de 60 secondes)
    RATE_LIMIT[ip_address] = [
        req_time for req_time in RATE_LIMIT[ip_address]
        if current_time - req_time < 60
    ]
    
    if len(RATE_LIMIT[ip_address]) >= 10:
        return False
    
    RATE_LIMIT[ip_address].append(current_time)
    return True

def extract_video_info(url):
    """Extrait les informations vidéo d'une URL"""
    try:
        ydl_opts = {
            'quiet': False,  # Changé pour voir les erreurs
            'no_warnings': False,  # Changé pour voir les warnings
            'extract_flat': False,
            'force_generic_extractor': False,
            'socket_timeout': 30,
            'format': 'best',  # Forcer le format "best"
            'nocheckcertificate': True,  # Ignorer les erreurs SSL
            'ignoreerrors': False,
            'no_color': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Tentative d'extraction: {url}")
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("Aucune information extraite")
            
            videos = []
            
            # Si c'est une playlist
            if 'entries' in info:
                logger.info(f"Playlist détectée avec {len(info['entries'])} entrées")
                for entry in info['entries']:
                    if entry:
                        video = format_video_info(entry)
                        if video:
                            videos.append(video)
            else:
                # Vidéo unique
                logger.info(f"Vidéo unique détectée: {info.get('title', 'Sans titre')}")
                video = format_video_info(info)
                if video:
                    videos.append(video)
            
            logger.info(f"Extraction réussie: {len(videos)} vidéo(s)")
            return videos
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"Erreur yt-dlp DownloadError: {error_msg}")
        
        # Messages d'erreur plus spécifiques
        if "Video unavailable" in error_msg or "This video is unavailable" in error_msg:
            raise Exception("Cette vidéo n'est pas disponible (privée ou supprimée)")
        elif "age" in error_msg.lower() or "Sign in to confirm your age" in error_msg:
            raise Exception("Cette vidéo est protégée par âge et ne peut pas être extraite")
        elif "copyright" in error_msg.lower():
            raise Exception("Cette vidéo est protégée par des droits d'auteur")
        elif "Private video" in error_msg:
            raise Exception("Cette vidéo est privée")
        else:
            raise Exception(f"Impossible d'extraire cette vidéo: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Erreur extraction générale: {error_msg}")
        
        # Ne pas exposer les détails techniques au client
        if "Aucune information extraite" in error_msg:
            raise Exception("Impossible d'extraire cette vidéo. Vérifiez l'URL.")
        else:
            raise Exception(f"Erreur lors de l'extraction: {error_msg}")

def format_video_info(info):
    """Formate les informations vidéo"""
    try:
        video_id = info.get('id', '')
        
        # Obtenir les formats disponibles
        formats = []
        if 'formats' in info:
            for fmt in info['formats']:
                # Accepter les formats vidéo et audio
                ext = fmt.get('ext', '')
                vcodec = fmt.get('vcodec', 'none')
                acodec = fmt.get('acodec', 'none')
                
                # Filtrer: doit avoir vidéo OU audio (pas "none")
                if vcodec == 'none' and acodec == 'none':
                    continue
                
                # Accepter plus d'extensions
                if ext not in ['mp4', 'webm', '3gp', 'm4a', 'mkv']:
                    continue
                
                filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                
                # Vérifier la taille maximale (seulement si connue)
                if filesize > MAX_VIDEO_SIZE:
                    continue
                
                # Déterminer la qualité
                quality = fmt.get('format_note', '')
                if not quality or quality == 'N/A':
                    # Essayer height (résolution verticale)
                    height = fmt.get('height')
                    if height:
                        quality = f"{height}p"
                    else:
                        # Essayer resolution complète
                        quality = fmt.get('resolution', 'unknown')
                
                format_info = {
                    'quality': quality,
                    'size': format_size(filesize) if filesize > 0 else 'Unknown',
                    'codec': ext.upper(),
                    'url': fmt.get('url', ''),
                    'format_id': fmt.get('format_id', ''),
                    'filesize': filesize
                }
                
                formats.append(format_info)
        
        # Si aucun format trouvé, logger pour debug
        if not formats:
            logger.warning(f"Aucun format trouvé pour la vidéo {video_id}")
            # Essayer d'obtenir le format "best" par défaut
            if 'url' in info:
                formats.append({
                    'quality': 'best',
                    'size': 'Unknown',
                    'codec': info.get('ext', 'MP4').upper(),
                    'url': info.get('url', ''),
                    'format_id': 'best',
                    'filesize': 0
                })
        
        # Filtrer les doublons et trier
        unique_formats = {}
        for fmt in formats:
            key = f"{fmt['quality']}-{fmt['codec']}"
            # Garder celui avec la plus grande taille (ou le premier si taille inconnue)
            if key not in unique_formats:
                unique_formats[key] = fmt
            elif fmt['filesize'] > 0 and (unique_formats[key]['filesize'] == 0 or fmt['filesize'] > unique_formats[key]['filesize']):
                unique_formats[key] = fmt
        
        # Limiter à 10 formats maximum et trier par taille
        sorted_formats = sorted(
            unique_formats.values(),
            key=lambda x: x['filesize'] if x['filesize'] > 0 else 0,
            reverse=True
        )[:10]
        
        return {
            'id': video_id,
            'title': info.get('title', 'Sans titre'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'formats': sorted_formats
        }
    except Exception as e:
        logger.error(f"Erreur formatage vidéo: {str(e)}")
        return None

def format_size(bytes_size):
    """Formate la taille en octets vers une chaîne lisible"""
    if bytes_size == 0:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

@app.route('/api/extract', methods=['POST'])
def extract():
    """Endpoint pour extraire les informations vidéo"""
    # Rate limiting
    client_ip = request.remote_addr
    if not rate_limit_check(client_ip):
        return jsonify({'error': 'Trop de requêtes. Veuillez patienter.'}), 429
    
    data = request.json
    if not data:
        return jsonify({'error': 'Corps de requête invalide'}), 400
    
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL requise'}), 400
    
    # Valider l'URL
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    try:
        videos = extract_video_info(url)
        
        if videos and len(videos) > 0:
            return jsonify({
                'success': True,
                'videos': videos,
                'count': len(videos)
            })
        else:
            return jsonify({'error': 'Aucune vidéo trouvée'}), 404
            
    except Exception as e:
        logger.error(f"Erreur API extract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Endpoint pour télécharger une vidéo avec streaming"""
    # Rate limiting
    client_ip = request.remote_addr
    if not rate_limit_check(client_ip):
        return jsonify({'error': 'Trop de requêtes. Veuillez patienter.'}), 429
    
    data = request.json
    if not data:
        return jsonify({'error': 'Corps de requête invalide'}), 400
    
    url = data.get('url')
    format_id = data.get('format_id')
    title = data.get('title', 'video')
    
    if not url:
        return jsonify({'error': 'URL requise'}), 400
    
    # Valider l'URL
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    try:
        # Nettoyer le titre pour le nom de fichier
        safe_title = re.sub(r'[^\w\s-]', '', title)
        safe_title = re.sub(r'[-\s]+', '_', safe_title)[:100]  # Limiter à 100 caractères
        
        # Options pour yt-dlp
        ydl_opts = {
            'format': format_id if format_id else 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }
        
        # Créer un répertoire temporaire
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts['outtmpl'] = os.path.join(tmpdir, f'{safe_title}.%(ext)s')
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    # Si le fichier a une extension différente, chercher le fichier téléchargé
                    if not os.path.exists(filename):
                        for file in os.listdir(tmpdir):
                            if file.startswith(safe_title):
                                filename = os.path.join(tmpdir, file)
                                break
                    
                    if not os.path.exists(filename):
                        return jsonify({'error': 'Fichier non trouvé après téléchargement'}), 404
                    
                    # Vérifier la taille du fichier
                    file_size = os.path.getsize(filename)
                    if file_size > MAX_VIDEO_SIZE:
                        return jsonify({'error': f'Fichier trop volumineux (max {MAX_VIDEO_SIZE // (1024*1024)} MB)'}), 413
                    
                    # Streaming du fichier
                    def generate():
                        with open(filename, 'rb') as f:
                            while True:
                                chunk = f.read(4096)  # Lire par chunks de 4KB
                                if not chunk:
                                    break
                                yield chunk
                    
                    # Déterminer le type MIME
                    ext = info.get('ext', 'mp4')
                    mime_types = {
                        'mp4': 'video/mp4',
                        'webm': 'video/webm',
                        '3gp': 'video/3gpp',
                        'm4a': 'audio/mp4'
                    }
                    mime_type = mime_types.get(ext, 'application/octet-stream')
                    
                    response = Response(
                        stream_with_context(generate()),
                        mimetype=mime_type,
                        headers={
                            'Content-Disposition': f'attachment; filename="{safe_title}.{ext}"',
                            'Content-Length': str(file_size)
                        }
                    )
                    
                    return response
                    
            except yt_dlp.utils.DownloadError as e:
                logger.error(f"Erreur yt-dlp download: {str(e)}")
                return jsonify({'error': 'Impossible de télécharger cette vidéo'}), 500
                    
    except Exception as e:
        logger.error(f"Erreur API download: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    """Page d'accueil de l'API"""
    return jsonify({
        'service': 'video-extractor-api',
        'version': '2.0.0',
        'status': 'running',
        'endpoints': {
            'health': '/api/health',
            'extract': '/api/extract (POST)',
            'download': '/api/download (POST)'
        },
        'documentation': 'https://github.com/votre-repo'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint de vérification de santé de l'API"""
    return jsonify({
        'status': 'healthy',
        'service': 'video-extractor-api',
        'version': '2.0.0',
        'max_video_size_mb': MAX_VIDEO_SIZE // (1024 * 1024)
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint non trouvé'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erreur serveur: {str(error)}")
    return jsonify({'error': 'Erreur interne du serveur'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
