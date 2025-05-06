# C:\Users\Vladimir\Documents\Sistema tickets\run.py

from dotenv import load_dotenv
import os
import pymysql
pymysql.install_as_MySQLdb()

# -------------------------------------------------------------------------------
# Detectar entorno automáticamente o pedirlo si se ejecuta localmente
# -------------------------------------------------------------------------------
app_env = os.getenv("APP_ENV")

# Si se ejecuta localmente (sin definir APP_ENV), preguntamos
if not app_env and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    print("🌐 ¿En qué entorno deseas trabajar?")
    print("1. Local")
    print("2. Producción (Railway)")
    opcion = input("Selecciona 1 o 2: ").strip()

    if opcion == "1":
        app_env = "local"
    elif opcion == "2":
        app_env = "prod"
    else:
        print("⚠️ Opción inválida. Usando entorno local por defecto.")
        app_env = "local"

# Forzar variable para todo el proceso
os.environ["APP_ENV"] = app_env or "local"
env_file = ".env.local" if app_env == "local" else ".env.prod"
load_dotenv(env_file)
print(f"✅ Entorno '{app_env}' cargado desde {env_file}.")

# -------------------------------------------------------------------------------
# Inicializar Flask y mostrar configuración
# -------------------------------------------------------------------------------
from app import create_app, db

print(f"🧪 ENV SQLALCHEMY_DATABASE_URI = {os.environ.get('SQLALCHEMY_DATABASE_URI')}")

app = create_app()

print(f"🔄 App config URI = {app.config.get('SQLALCHEMY_DATABASE_URI')}")

# -------------------------------------------------------------------------------
# Crear tablas y cargar base de datos solo si corre directamente
# -------------------------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        try:
            print(f"🧩 Conectando a base de datos: {app.config['SQLALCHEMY_DATABASE_URI']}")
            db.create_all()
            from app.db_init import inicializar_db_si_esta_vacia
            inicializar_db_si_esta_vacia()
        except Exception as e:
            print(f"❌ Error al verificar o cargar la base de datos: {e}")

    app.run(debug=(app_env == "local"), host="0.0.0.0", port=5000)
