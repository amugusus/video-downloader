from flask import Flask, request, send_file, render_template, jsonify
import yt_dlp
import os
import shutil
import subprocess

app = Flask(__name__)

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
    ffmpeg_path = shutil.which('ffmpeg')  # Ищем FFmpeg в PATH
    if not ffmpeg_path:
        return jsonify({'error': 'FFmpeg не установлен или не найден в PATH'}), 500

    download_dir = 'downloads'
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # Динамическое имя файла на основе названия видео
    output_template = f'{download_dir}/%(title)s.%(ext)s'

    ydl_opts = {
        'outtmpl': output_template,
        'noplaylist': True,
        'ffmpeg_location': ffmpeg_path,  # Явно указываем путь к FFmpeg
    }

    if format == 'mp4':
        ydl_opts.update({
            'format': 'bestvideo+bestaudio/best',  # Лучшее видео + аудио
            'merge_output_format': 'mp4',  # Слияние в MP4
            'postprocessors': [{  # Явное слияние через FFmpeg
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
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
        shutil.rmtree(download_dir, ignore_errors=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # debug=True для локальной отладки