FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV DB_PATH=/bot/app/data/bot.db
WORKDIR /bot

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY nexora ./nexora

RUN mkdir -p /bot/app/data
CMD ["python", "-m", "app.main"]
