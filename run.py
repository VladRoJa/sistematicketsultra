# C:\Users\Vladimir\Documents\Sistema tickets\run.py

# -------------------------------------------------------------------------------
# SCRIPT PRINCIPAL: Arranque de la aplicación Flask
# -------------------------------------------------------------------------------

from app import create_app, db
from app.db_init import inicializar_db_si_esta_vacia  # 🔁 Nueva función

# -------------------------------------------------------------------------------
# Crear la instancia de la app
# -------------------------------------------------------------------------------
app = create_app()

# -------------------------------------------------------------------------------
# Crear las tablas y cargar la base si está vacía
# -------------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    inicializar_db_si_esta_vacia()  # 🔁 Llama a la función que carga el .sql

# -------------------------------------------------------------------------------
# Ejecutar el servidor
# -------------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
