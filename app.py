from flask import Flask, request, send_file, render_template, jsonify, Response
import yt_dlp
import os
import shutil
import subprocess
import logging
from threading import Lock

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к файлу cookies
COOKIES_FILE = 'youtube_cookies.txt'

# Переменная для хранения прогресса
progress = {'percentage': 0, 'status': 'waiting'}
progress_lock = Lock()

@app.route('/')
def index():
    return render_template('index.html')

def progress_hook(d):
    """Обратный вызов для отслеживания прогресса"""
    with progress_lock:
        if d['status'] == 'downloading':
            progress['percentage'] = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100
            progress['status'] = 'downloading'
        elif d['status'] == 'finished':
            progress['percentage'] = 100
            progress['status'] = 'finished'
        logger.info(f"Прогресс: {progress['percentage']:.2f}%")

@app.route('/progress')
def progress_stream():
    """Поток событий для прогресса"""
    def generate():
        while True:
            with progress_lock:
                yield f"data: {progress['percentage']}\n\n"
            if progress['status'] == 'finished':
                break
            import time
            time.sleep(0.5)  # Обновление каждые 0.5 секунды
    return Response(generate(), mimetype='text/event-stream')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format = data.get('format')

    if not url or not format:
        return jsonify({'error': 'URL или формат не указаны'}), 400

    # Проверка FFmpeg
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info(f"FFmpeg version: {result.stdout.decode().splitlines()[0]}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("FFmpeg не найден")
        return jsonify({'error': 'FFmpeg не установлен или не найден'}), 500

    # Сброс прогресса
    with progress_lock:
        progress['percentage'] = 0
        progress['status'] = 'downloading'

    download_dir = 'downloads'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    output_template = f'{download_dir}/%(title)s.%(ext)s'

    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',  # Явный путь для Docker
        'cookiefile': COOKIES_FILE,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        },
        'progress_hooks': [progress_hook],  # Отслеживание прогресса
    }

    if format == 'mp4':
        ydl_opts.update({
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'postprocessor_args': ['-c:v', 'libx264', '-c:a', 'aac'],  # Принудительное перекодирование для совместимости
        })
    elif format == 'mp3':
        ydl_opts.update({
            'format': 'bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        return jsonify({'error': 'Неподдерживаемый формат'}), 400

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'unknown')
            logger.info(f"Скачан файл: {title}.{format}")

        file_path = f'{download_dir}/{title}.{format}'
        if not os.path.exists(file_path):
            for f in os.listdir(download_dir):
                if f.endswith(f'.{format}'):
                    file_path = f'{download_dir}/{f}'
                    title = f[:-4]
                    break
            else:
                raise FileNotFoundError(f"Файл с расширением .{format} не найден")

        if os.name == 'nt':
            os.system(f'attrib -h "{file_path}"')

        response = send_file(file_path, as_attachment=True, download_name=f'{title}.{format}')
        shutil.rmtree(download_dir, ignore_errors=True)
        return response

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        shutil.rmtree(download_dir, ignore_errors=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
