# app\Dockerfile


# Utiliza una imagen oficial de Python
FROM python:3.11-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia solo los requirements primero para aprovechar la cache de Docker
COPY requirements.txt .


# Instala dependencias del sistema (psycopg2 necesita gcc y libpq-dev para compilar)
RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    apt-get clean

# Copia el código de la app al contenedor (TODO el folder actual, porque lo ocupan los imports)
COPY . .

# Expone el puerto en el que corre Flask
EXPOSE 5000

# Usa Gunicorn para correr Flask en producción (mejor que flask run)
CMD ["gunicorn", "-b", "0.0.0.0:5000", "wsgi:app"]

