# backend/app/utils/local_upload.py

import os
from uuid import uuid4
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

def _get_cfg(key: str, default: str):
    """Lee primero de current_app.config, luego de os.getenv, y si no, usa default."""
    # Ojo: current_app solo existe dentro de contexto Flask; aquí estamos dentro de request.
    value = None
    try:
        value = current_app.config.get(key)
    except Exception:
        value = None
    if value is None:
        value = os.getenv(key, default)
    return value

def upload_image_to_local(image_file) -> str:
    """
    Guarda la imagen en el filesystem local y regresa una URL pública.
    Claves que puede leer de config/env (con fallback seguro):
      - LOCAL_UPLOAD_DIR (default: /home/adminrdp/sistematicketsultra/uploads/reportes)
      - PUBLIC_BASE_URL   (default: http://184.107.165.75)
      - UPLOADS_PUBLIC_PATH (default: /uploads/reportes)
      - MAX_UPLOAD_SIZE_MB (default: 10)
    """
    if not image_file or not getattr(image_file, "filename", ""):
        raise ValueError("Archivo de imagen inválido")

    ext = Path(image_file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"Extensión no permitida: {ext}")

    # Config con fallback: config -> env -> default
    try:
        max_mb = int(_get_cfg('MAX_UPLOAD_SIZE_MB', '10'))
    except ValueError:
        max_mb = 10

    # Obtener tamaño sin cargar todo a memoria
    image_file.stream.seek(0, os.SEEK_END)
    size_bytes = image_file.stream.tell()
    image_file.stream.seek(0)
    if size_bytes > max_mb * 1024 * 1024:
        raise ValueError(f"Archivo demasiado grande (> {max_mb} MB)")

    upload_dir = _get_cfg('LOCAL_UPLOAD_DIR', '/home/adminrdp/sistematicketsultra/uploads/reportes')
    public_base = _get_cfg('PUBLIC_BASE_URL', 'http://184.107.165.75').rstrip('/')
    public_path = _get_cfg('UPLOADS_PUBLIC_PATH', '/uploads/reportes').strip('/')

    os.makedirs(upload_dir, exist_ok=True)

    filename = secure_filename(f"{uuid4().hex}{ext}")
    dest = os.path.join(upload_dir, filename)
    image_file.save(dest)

    # URL pública final (luego Nginx servirá /uploads/ apuntando a la carpeta real)
    url = f"{public_base}/{public_path}/{filename}"
    return url
