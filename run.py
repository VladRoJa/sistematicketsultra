# run.py

from dotenv import load_dotenv
import os


from app.utils.migraciones import aplicar_migraciones

# -------------------------------------------------------------------------------
# Detectar entorno automáticamente (evita input en producción)
# -------------------------------------------------------------------------------
app_env = os.getenv("APP_ENV", "prod" if os.getenv("RENDER") else "local")
os.environ["APP_ENV"] = app_env
env_file = ".env.local" if app_env == "local" else ".env.prod"
load_dotenv(env_file)
print(f"✅ Entorno '{app_env}' cargado desde {env_file}.")

# -------------------------------------------------------------------------------
# Inicializar Flask y mostrar configuración
# -------------------------------------------------------------------------------
from app import create_app, db
from flask_migrate import Migrate

print(f"🧪 ENV SQLALCHEMY_DATABASE_URI = {os.environ.get('SQLALCHEMY_DATABASE_URI')}")

app = create_app()
migrate = Migrate(app, db)
print(f"🔄 App config URI = {app.config.get('SQLALCHEMY_DATABASE_URI')}")



# -------------------------------------------------------------------------------
# Crear tablas, aplicar migraciones y cargar base de datos si está vacía
# Esto se ejecuta siempre, incluso en producción (Render, Railway)
# -------------------------------------------------------------------------------
with app.app_context():
    try:
        print(f"🧩 Conectando a base de datos: {app.config['SQLALCHEMY_DATABASE_URI']}")
        db.create_all()
        aplicar_migraciones()
    except Exception as e:
        print(f"❌ Error al verificar o cargar la base de datos: {e}")

# -------------------------------------------------------------------------------
# Solo en desarrollo: levantar el servidor local
# -------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=(app_env == "local"), host="0.0.0.0", port=5000)
