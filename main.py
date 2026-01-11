from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import re
from urllib.parse import urlparse, parse_qs
import logging
import time
import requests

app = Flask(__name__)
CORS(app)

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_DOMAINS = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com']
RATE_LIMIT = {}
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')

def extract_youtube_id(url):
    """Extrait l'ID YouTube depuis une URL"""
    try:
        parsed = urlparse(url)
        
        # Format: youtube.com/watch?v=VIDEO_ID
        if 'youtube.com' in parsed.netloc:
            query_params = parse_qs(parsed.query)
            if 'v' in query_params:
                return query_params['v'][0]
        
        # Format: youtu.be/VIDEO_ID
        if 'youtu.be' in parsed.netloc:
            return parsed.path.lstrip('/')
        
        return None
    except:
        return None

def get_video_info_from_youtube_api(video_id):
    """Obtient les infos vidéo via l'API YouTube officielle"""
    if not YOUTUBE_API_KEY:
        logger.warning("Clé API YouTube non configurée")
        return None
    
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            'part': 'snippet,contentDetails',
            'id': video_id,
            'key': YOUTUBE_API_KEY
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Erreur API YouTube: {response.status_code}")
            return None
        
        data = response.json()
        
        if not data.get('items'):
            logger.warning(f"Aucune vidéo trouvée pour ID: {video_id}")
            return None
        
        item = data['items'][0]
        snippet = item['snippet']
        content_details = item['contentDetails']
        
        # Convertir la durée ISO 8601 en secondes
        duration_str = content_details.get('duration', 'PT0S')
        duration_seconds = parse_iso8601_duration(duration_str)
        
        # Obtenir la meilleure thumbnail
        thumbnails = snippet.get('thumbnails', {})
        thumbnail_url = (
            thumbnails.get('maxres', {}).get('url') or
            thumbnails.get('standard', {}).get('url') or
            thumbnails.get('high', {}).get('url') or
            thumbnails.get('medium', {}).get('url') or
            thumbnails.get('default', {}).get('url') or
            ''
        )
        
        return {
            'id': video_id,
            'title': snippet.get('title', 'Sans titre'),
            'thumbnail': thumbnail_url,
            'duration': duration_seconds,
            'from_api': True
        }
    
    except Exception as e:
        logger.error(f"Erreur lors de l'appel à l'API YouTube: {str(e)}")
        return None

def parse_iso8601_duration(duration_str):
    """Convertit une durée ISO 8601 (ex: PT3M34S) en secondes"""
    try:
        import re
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds
    except:
        return 0

def validate_url(url):
    """Valide l'URL de la vidéo"""
    try:
        parsed = urlparse(url)
        if not parsed.scheme in ['http', 'https']:
            return False, "Protocole non autorisé"
        
        domain = parsed.netloc.replace('www.', '').replace('m.', '')
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
    
    RATE_LIMIT[ip_address] = [
        req_time for req_time in RATE_LIMIT[ip_address]
        if current_time - req_time < 60
    ]
    
    if len(RATE_LIMIT[ip_address]) >= 10:
        return False
    
    RATE_LIMIT[ip_address].append(current_time)
    return True

def get_formats_from_ytdlp(url, video_info):
    """Essaie d'obtenir les formats via yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 15,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                return []
            
            formats = []
            if 'formats' in info:
                for fmt in info['formats']:
                    ext = fmt.get('ext', '')
                    vcodec = fmt.get('vcodec', 'none')
                    acodec = fmt.get('acodec', 'none')
                    
                    if vcodec == 'none' and acodec == 'none':
                        continue
                    
                    if ext not in ['mp4', 'webm', '3gp', 'm4a', 'mkv']:
                        continue
                    
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                    
                    if filesize > MAX_VIDEO_SIZE:
                        continue
                    
                    height = fmt.get('height')
                    quality = f"{height}p" if height else fmt.get('format_note', 'unknown')
                    
                    formats.append({
                        'quality': quality,
                        'size': format_size(filesize) if filesize > 0 else 'Unknown',
                        'codec': ext.upper(),
                        'url': fmt.get('url', ''),
                        'format_id': fmt.get('format_id', ''),
                        'filesize': filesize
                    })
            
            # Dédupliquer et trier
            unique_formats = {}
            for fmt in formats:
                key = f"{fmt['quality']}-{fmt['codec']}"
                if key not in unique_formats:
                    unique_formats[key] = fmt
                elif fmt['filesize'] > 0 and (unique_formats[key]['filesize'] == 0 or fmt['filesize'] > unique_formats[key]['filesize']):
                    unique_formats[key] = fmt
            
            return sorted(
                unique_formats.values(),
                key=lambda x: x['filesize'] if x['filesize'] > 0 else 0,
                reverse=True
            )[:10]
    
    except Exception as e:
        logger.warning(f"yt-dlp a échoué pour les formats: {str(e)}")
        return []

def extract_video_info(url):
    """Extrait les informations vidéo - Mode hybride API YouTube + yt-dlp"""
    try:
        # Vérifier si c'est une URL YouTube
        video_id = extract_youtube_id(url)
        
        # Méthode 1: Essayer l'API YouTube d'abord (plus fiable)
        if video_id and YOUTUBE_API_KEY:
            logger.info(f"Utilisation de l'API YouTube pour: {video_id}")
            video_info = get_video_info_from_youtube_api(video_id)
            
            if video_info:
                # Essayer d'obtenir les formats avec yt-dlp
                formats = get_formats_from_ytdlp(url, video_info)
                
                if not formats:
                    # Si pas de formats, créer un format générique
                    formats = [{
                        'quality': 'best',
                        'size': 'Unknown',
                        'codec': 'MP4',
                        'url': '',
                        'format_id': 'best',
                        'filesize': 0
                    }]
                
                video_info['formats'] = formats
                return [video_info]
        
        # Méthode 2: Fallback sur yt-dlp pur (pour non-YouTube ou si API échoue)
        logger.info(f"Utilisation de yt-dlp pour: {url}")
        return extract_video_info_ytdlp(url)
    
    except Exception as e:
        logger.error(f"Erreur extraction: {str(e)}")
        raise Exception(f"Impossible d'extraire cette vidéo: {str(e)[:100]}")

def extract_video_info_ytdlp(url):
    """Extraction pure yt-dlp (fallback)"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("Aucune information extraite")
            
            videos = []
            
            if 'entries' in info:
                for entry in info['entries']:
                    if entry:
                        video = format_video_info_ytdlp(entry)
                        if video:
                            videos.append(video)
            else:
                video = format_video_info_ytdlp(info)
                if video:
                    videos.append(video)
            
            return videos
    
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "bot" in error_msg.lower() or "Sign in" in error_msg:
            raise Exception("YouTube a bloqué la requête. Utilisez des vidéos populaires et anciennes, ou réessayez dans quelques minutes.")
        else:
            raise Exception(f"Erreur d'extraction: {error_msg[:200]}")

def format_video_info_ytdlp(info):
    """Formate les infos vidéo depuis yt-dlp"""
    try:
        formats = get_formats_from_ytdlp_info(info)
        
        return {
            'id': info.get('id', ''),
            'title': info.get('title', 'Sans titre'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'formats': formats,
            'from_api': False
        }
    except Exception as e:
        logger.error(f"Erreur formatage: {str(e)}")
        return None

def get_formats_from_ytdlp_info(info):
    """Extrait les formats depuis l'info yt-dlp"""
    formats = []
    
    if 'formats' in info:
        for fmt in info['formats']:
            ext = fmt.get('ext', '')
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            
            if vcodec == 'none' and acodec == 'none':
                continue
            
            if ext not in ['mp4', 'webm', '3gp', 'm4a', 'mkv']:
                continue
            
            filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
            
            if filesize > MAX_VIDEO_SIZE:
                continue
            
            height = fmt.get('height')
            quality = f"{height}p" if height else fmt.get('format_note', 'unknown')
            
            formats.append({
                'quality': quality,
                'size': format_size(filesize) if filesize > 0 else 'Unknown',
                'codec': ext.upper(),
                'url': fmt.get('url', ''),
                'format_id': fmt.get('format_id', ''),
                'filesize': filesize
            })
    
    # Dédupliquer et trier
    unique_formats = {}
    for fmt in formats:
        key = f"{fmt['quality']}-{fmt['codec']}"
        if key not in unique_formats:
            unique_formats[key] = fmt
        elif fmt['filesize'] > 0 and (unique_formats[key]['filesize'] == 0 or fmt['filesize'] > unique_formats[key]['filesize']):
            unique_formats[key] = fmt
    
    sorted_formats = sorted(
        unique_formats.values(),
        key=lambda x: x['filesize'] if x['filesize'] > 0 else 0,
        reverse=True
    )[:10]
    
    if not sorted_formats:
        sorted_formats = [{
            'quality': 'best',
            'size': 'Unknown',
            'codec': 'MP4',
            'url': info.get('url', ''),
            'format_id': 'best',
            'filesize': 0
        }]
    
    return sorted_formats

def format_size(bytes_size):
    """Formate la taille en octets"""
    if bytes_size == 0:
        return "N/A"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

@app.route('/', methods=['GET'])
def index():
    """Page d'accueil de l'API"""
    api_status = "✅ Configurée" if YOUTUBE_API_KEY else "❌ Non configurée"
    
    return jsonify({
        'service': 'video-extractor-api',
        'version': '3.0.0',
        'status': 'running',
        'youtube_api': api_status,
        'endpoints': {
            'health': '/api/health',
            'extract': '/api/extract (POST)',
            'download': '/api/download (POST)'
        },
        'features': [
            'API YouTube officielle pour métadonnées (fiable)',
            'yt-dlp pour liens de téléchargement',
            'Mode hybride intelligent',
            '10,000 vidéos/jour avec API YouTube'
        ]
    })

@app.route('/api/extract', methods=['POST'])
def extract():
    """Endpoint pour extraire les informations vidéo"""
    client_ip = request.remote_addr
    if not rate_limit_check(client_ip):
        return jsonify({'error': 'Trop de requêtes. Veuillez patienter.'}), 429
    
    data = request.json
    if not data:
        return jsonify({'error': 'Corps de requête invalide'}), 400
    
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL requise'}), 400
    
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    try:
        videos = extract_video_info(url)
        
        if videos and len(videos) > 0:
            return jsonify({
                'success': True,
                'videos': videos,
                'count': len(videos),
                'method': 'youtube_api' if videos[0].get('from_api') else 'yt-dlp'
            })
        else:
            return jsonify({'error': 'Aucune vidéo trouvée'}), 404
            
    except Exception as e:
        logger.error(f"Erreur API extract: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    """Endpoint pour télécharger une vidéo"""
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
    
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    try:
        safe_title = re.sub(r'[^\w\s-]', '', title)
        safe_title = re.sub(r'[-\s]+', '_', safe_title)[:100]
        
        ydl_opts = {
            'format': format_id if format_id else 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts['outtmpl'] = os.path.join(tmpdir, f'{safe_title}.%(ext)s')
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    if not os.path.exists(filename):
                        for file in os.listdir(tmpdir):
                            if file.startswith(safe_title):
                                filename = os.path.join(tmpdir, file)
                                break
                    
                    if not os.path.exists(filename):
                        return jsonify({'error': 'Fichier non trouvé'}), 404
                    
                    file_size = os.path.getsize(filename)
                    if file_size > MAX_VIDEO_SIZE:
                        return jsonify({'error': f'Fichier trop volumineux (max {MAX_VIDEO_SIZE // (1024*1024)} MB)'}), 413
                    
                    def generate():
                        with open(filename, 'rb') as f:
                            while True:
                                chunk = f.read(4096)
                                if not chunk:
                                    break
                                yield chunk
                    
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

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint de vérification de santé"""
    return jsonify({
        'status': 'healthy',
        'service': 'video-extractor-api',
        'version': '3.0.0',
        'youtube_api_configured': bool(YOUTUBE_API_KEY),
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
    if not YOUTUBE_API_KEY:
        logger.warning("⚠️ YOUTUBE_API_KEY non configurée. Fonctionnement en mode yt-dlp uniquement.")
    else:
        logger.info("✅ YouTube API configurée et prête")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
