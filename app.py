from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import shutil
import subprocess
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Путь к файлу cookies
COOKIES_FILE = 'youtube_cookies.txt'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format = data.get('format')

    if not url or not format:
        return jsonify({'error': 'URL или формат не указаны'}), 400

    # Проверка FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        logger.info("FFmpeg успешно проверен")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("FFmpeg не найден")
        return jsonify({'error': 'FFmpeg не установлен или не найден'}), 500

    download_dir = 'downloads'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    output_template = f'{download_dir}/%(title)s.%(ext)s'

    # Базовые настройки для yt-dlp
    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',
        'cookiefile': COOKIES_FILE,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        },
        'verbose': True,  # Для отладки в логах
    }

    if format == 'mp4':
        ydl_opts.update({
            'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best',
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': {
                'FFmpegVideoConvertor': [
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                ]
            },
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
            title = info.get('title', 'unknown').replace('/', '_').replace('\\', '_')
            logger.info(f"Скачан файл с названием: {title}")

        file_path = f'{download_dir}/{title}.{format}'
        if not os.path.exists(file_path):
            for f in os.listdir(download_dir):
                if f.endswith(f'.{format}'):
                    file_path = f'{download_dir}/{f}'
                    title = f[:-4]
                    break
            else:
                raise FileNotFoundError(f"Файл с расширением .{format} не найден")

        logger.info(f"Подготовка к отправке файла: {file_path}")

        # Отправляем файл клиенту
        response = send_file(file_path, as_attachment=True, download_name=f'{title}.{format}')
        
        # Очистка после успешной отправки
        shutil.rmtree(download_dir, ignore_errors=True)
        logger.info("Директория downloads очищена")
        return response

    except Exception as e:
        logger.error(f"Ошибка при скачивании: {str(e)}")
        shutil.rmtree(download_dir, ignore_errors=True)
        return jsonify({'error': f'Ошибка при скачивании: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
