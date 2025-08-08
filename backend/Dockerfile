# app\Dockerfile


# Usa una imagen oficial de Python
FROM python:3.11-slim

# Establece el directorio de trabajo en /app
WORKDIR /app

# Copia el archivo de requirements
COPY requirements.txt .

# Instala dependencias del sistema (psycopg2 necesita gcc y libpq-dev para compilar)
RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    apt-get clean

# Copia TODO el código de la carpeta app/ dentro del contenedor en /app/app
COPY app/ .

# Expón el puerto 5000
EXPOSE 5000

# Ejecuta Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app.wsgi:app"]
