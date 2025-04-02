FROM python:3.11-slim

# Устанавливаем FFmpeg и зависимости для Playwright
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && apt-get clean

# Устанавливаем Playwright
RUN pip install playwright && playwright install chromium

# Копируем проект
WORKDIR /app
COPY . .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Указываем порт
EXPOSE 5000

# Запускаем приложение
CMD ["gunicorn", "app:app", "--timeout", "1200", "--bind", "0.0.0.0:5000"]
