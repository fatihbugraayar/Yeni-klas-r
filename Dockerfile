FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && useradd --create-home --uid 10001 bot \
    && mkdir -p /app/data/jobs \
    && chown -R bot:bot /app/data
COPY telegram_bot ./telegram_bot
USER bot
CMD ["python", "-m", "telegram_bot.main"]
