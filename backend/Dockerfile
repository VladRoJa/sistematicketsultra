# app\Dockerfile

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        libglib2.0-0t64 \
        libnspr4 \
        libnss3 \
        libdbus-1-3 \
        libatk1.0-0t64 \
        libatk-bridge2.0-0t64 \
        libexpat1 \
        libatspi2.0-0t64 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libxcb1 \
        libxkbcommon0 \
        libcups2t64 \
        libasound2t64 && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    python -m playwright install chromium && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY app /app/app
COPY migrations /app/migrations
COPY scripts /app/scripts

EXPOSE 5000
CMD ["gunicorn", "--timeout", "300", "-b", "0.0.0.0:5000", "app.wsgi:app"]