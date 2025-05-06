# C:\Users\Vladimir\Documents\Sistema tickets\run.py

from dotenv import load_dotenv
import os
import pymysql
pymysql.install_as_MySQLdb()


# -------------------------------------------------------------------------------
# Seleccionar entorno dinámicamente (solo si es proceso principal)
# -------------------------------------------------------------------------------
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    print("🌐 ¿En qué entorno deseas trabajar?")
    print("1. Local")
    print("2. Producción (Railway)")
    opcion = input("Selecciona 1 o 2: ").strip()

    if opcion == "1":
        os.environ["APP_ENV"] = "local"
        load_dotenv(".env.local")
        print("✅ Entorno local cargado.")
    elif opcion == "2":
        os.environ["APP_ENV"] = "prod"
        load_dotenv(".env.prod")
        print("✅ Entorno de producción cargado.")
    else:
        print("⚠️ Opción inválida. Usando entorno local por defecto.")
        os.environ["APP_ENV"] = "local"
        load_dotenv(".env.local")

# -------------------------------------------------------------------------------
# Inicializar Flask y mostrar configuración
# -------------------------------------------------------------------------------
from app import create_app, db

print(f"🧪 ENV SQLALCHEMY_DATABASE_URI = {os.environ.get('SQLALCHEMY_DATABASE_URI')}")

app = create_app()

print(f"🔄 App config URI = {app.config.get('SQLALCHEMY_DATABASE_URI')}")

# -------------------------------------------------------------------------------
# Crear tablas y cargar base de datos solo al ejecutar directamente
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

    app.run(debug=True, host="0.0.0.0", port=5000)
