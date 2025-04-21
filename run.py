# run.py

from app import create_app
from setup_db import inicializar_base_de_datos
inicializar_base_de_datos()

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
