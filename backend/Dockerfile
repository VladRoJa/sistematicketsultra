# app\Dockerfile


FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    apt-get clean

COPY backend/app /app/app
COPY migrations /app/migrations


EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app.wsgi:app"]
