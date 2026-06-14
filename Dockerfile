# Использовать официальный легковесный образ Python 3.11
FROM python:3.11-slim

# Установить Node.js, npm, curl и системные библиотеки для работы с документами
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Создать рабочую директорию внутри контейнера
WORKDIR /app

# Скопировать список зависимостей Python и установить их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать весь исходный код проекта в контейнер
COPY . .

# Применить патч библиотеки CrewAI для обхода ValidationError
RUN python patch_crewai.py

# Установить зависимости Node.js для прокси-сервера DeepSeek
RUN cd FreeDeepseekAPI && npm install --omit=dev

# Открыть необходимые порты (9655 для прокси, 8080 для вебхука при необходимости)
EXPOSE 9655 8080

# Установить переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1

# По умолчанию в облаке запускаем основного бота напрямую (он слушает Telegram)
CMD ["python", "-u", "bot.py"]
