# backend\app\run.py

from dotenv import load_dotenv
import os
import logging

# Detectar entorno automáticamente (evita input en producción)
app_env = os.getenv("APP_ENV", "prod" if os.getenv("RENDER") else "local")
os.environ["APP_ENV"] = app_env
env_file = ".env.local" if app_env == "local" else ".env.prod"

# Cargar variables de entorno ANTES de importar módulos que las usen
load_dotenv(env_file)

# Ahora importar módulos que dependen de las variables de entorno cargadas
from app import create_app, db
from flask_migrate import Migrate

# Configurar logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("✅ Entorno '%s' cargado desde %s.", app_env, env_file)

# Inicializar Flask
app = create_app()
migrate = Migrate(app, db)

logger.info("✅ Aplicación Flask inicializada correctamente.")

# Solo en desarrollo: levantar el servidor local
if __name__ == "__main__":
    logger.info(
        "🚀 Iniciando servidor Flask en modo %s.",
        "debug" if app_env == "local" else "producción",
    )
    app.run(
        debug=(app_env == "local"),
        host="0.0.0.0",
        port=5000,
    )