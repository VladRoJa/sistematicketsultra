# backend\app\run.py

from dotenv import load_dotenv
import os
import logging

# Detectar entorno automáticamente (evita input en producción)
app_env = os.getenv("APP_ENV", "prod" if os.getenv("RENDER") else "local")
os.environ["APP_ENV"] = app_env
env_file = ".env.local" if app_env == "local" else ".env.prod"

# Cargar variables de entorno ANTES de importar cualquier módulo que las use
load_dotenv(env_file)
print("SECRET_KEY =", os.getenv("SECRET_KEY"))

# Ahora importar módulos que dependen de las variables de entorno cargadas
from app.utils.migraciones import aplicar_migraciones
from app import create_app, db
from flask_migrate import Migrate
from sqlalchemy.engine.url import make_url

# Configurar logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"✅ Entorno '{app_env}' cargado desde {env_file}.")

# Inicializar Flask y mostrar configuración
app = create_app()
migrate = Migrate(app, db)

try:
    db_url = make_url(app.config.get('SQLALCHEMY_DATABASE_URI'))
    logger.info(f"🔄 Conectando a base de datos: {db_url.database} en host {db_url.host}")
except Exception:
    logger.info("🔄 Conectando a base de datos (no se pudo obtener detalles).")

# Crear tablas, aplicar migraciones y cargar base de datos si está vacía
with app.app_context():
    try:
        db.create_all()
        aplicar_migraciones()
        logger.info("🧩 Migraciones aplicadas correctamente.")
    except Exception as e:
        logger.error(f"❌ Error al verificar o cargar la base de datos: {e}")

# Solo en desarrollo: levantar el servidor local
if __name__ == '__main__':
    app.run(debug=(app_env == "local"), host="0.0.0.0", port=5000)
