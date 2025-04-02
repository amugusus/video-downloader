from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import shutil
import subprocess
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright
import time
from dotenv import load_dotenv

app = Flask(__name__)

# Загружаем переменные из файла .env
load_dotenv('/etc/secrets/.env')  # Путь, где Render монтирует Secret Files

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Путь к файлу cookies
COOKIES_FILE = 'youtube_cookies.txt'

# Учетные данные из файла .env
GOOGLE_USERNAME = os.getenv('GOOGLE_USERNAME')
GOOGLE_PASSWORD = os.getenv('GOOGLE_PASSWORD')
PROXY = os.getenv('PROXY')  # Опционально, если нужен прокси

# Проверка наличия учетных данных
if not GOOGLE_USERNAME or not GOOGLE_PASSWORD:
    logger.error("GOOGLE_USERNAME или GOOGLE_PASSWORD не заданы в файле .env")
    raise ValueError("GOOGLE_USERNAME и GOOGLE_PASSWORD должны быть заданы в файле .env")

# Функция для обновления cookies с авторизацией
def update_youtube_cookies():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                proxy={'server': PROXY} if PROXY else None
            )
            page = context.new_page()

            # Переходим на страницу входа Google
            page.goto('https://accounts.google.com/signin', wait_until='domcontentloaded')
            page.wait_for_timeout(2000)

            # Вводим логин
            page.fill('input[type="email"]', GOOGLE_USERNAME)
            page.click('#identifierNext')
            page.wait_for_timeout(2000)

            # Вводим пароль
            page.fill('input[type="password"]', GOOGLE_PASSWORD)
            page.click('#passwordNext')
            page.wait_for_timeout(5000)  # Ждем завершения входа

            # Переходим на YouTube для получения cookies
            page.goto('https://www.youtube.com', wait_until='domcontentloaded')
            page.wait_for_timeout(5000)

            # Сохраняем cookies
            cookies = context.cookies()
            with open(COOKIES_FILE, 'w') as f:
                f.write('# Netscape HTTP Cookie File\n')
                for cookie in cookies:
                    f.write(f"{cookie['domain']}\tTRUE\t{cookie['path']}\t{'TRUE' if cookie['secure'] else 'FALSE'}\t{cookie['expires'] if cookie['expires'] else 0}\t{cookie['name']}\t{cookie['value']}\n")

            logger.info("Cookies успешно обновлены с авторизацией")
            browser.close()
    except Exception as e:
        logger.error(f"Ошибка при обновлении cookies: {str(e)}")

# Инициализация планировщика
scheduler = BackgroundScheduler()
scheduler.add_job(update_youtube_cookies, 'interval', hours=1)  # Обновление раз в час
scheduler.start()

# Выполняем обновление cookies при старте приложения
update_youtube_cookies()

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

    # Настройки для yt-dlp
    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
        'ffmpeg_location': '/usr/bin/ffmpeg',
        'cookiefile': COOKIES_FILE,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/',
        },
        'proxy': PROXY,
        'verbose': True,
        'retries': 10,
        'sleep_interval': 5,
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
