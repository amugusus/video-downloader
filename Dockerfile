FROM python:3.9-slim

# Устанавливаем FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Копируем проект
WORKDIR /app
COPY . .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Открываем порт (Render использует PORT из окружения)
EXPOSE 5000

# Запускаем приложение с привязкой к динамическому порту
CMD ["gunicorn", "app:app", "--timeout", "600", "--bind", "0.0.0.0:5000"]
