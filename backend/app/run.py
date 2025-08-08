# run.py

from dotenv import load_dotenv
import os
import logging

from backend.app.utils.migraciones import aplicar_migraciones




# -------------------------------------------------------------------------------
# Configurar logging básico
# -------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------------
# Detectar entorno automáticamente (evita input en producción)
# -------------------------------------------------------------------------------
app_env = os.getenv("APP_ENV", "prod" if os.getenv("RENDER") else "local")
os.environ["APP_ENV"] = app_env
env_file = ".env.local" if app_env == "local" else ".env.prod"
load_dotenv(env_file)
logger.info(f"✅ Entorno '{app_env}' cargado desde {env_file}.")

# -------------------------------------------------------------------------------
# Inicializar Flask y mostrar configuración
# -------------------------------------------------------------------------------
from backend.app import create_app, db
from flask_migrate import Migrate

app = create_app()
migrate = Migrate(app, db)

# Nunca muestres la URI completa en logs
from sqlalchemy.engine.url import make_url
try:
    db_url = make_url(app.config.get('SQLALCHEMY_DATABASE_URI'))
    logger.info(f"🔄 Conectando a base de datos: {db_url.database} en host {db_url.host}")
except Exception:
    logger.info("🔄 Conectando a base de datos (no se pudo obtener detalles).")

# -------------------------------------------------------------------------------
# Crear tablas, aplicar migraciones y cargar base de datos si está vacía
# Esto se ejecuta siempre, incluso en producción (Render, Railway)
# -------------------------------------------------------------------------------
with app.app_context():
    try:
        db.create_all()
        aplicar_migraciones()
        logger.info("🧩 Migraciones aplicadas correctamente.")
    except Exception as e:
        logger.error(f"❌ Error al verificar o cargar la base de datos: {e}")

# -------------------------------------------------------------------------------
# Solo en desarrollo: levantar el servidor local
# -------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=(app_env == "local"), host="0.0.0.0", port=5000)
