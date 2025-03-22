# run.py

from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from app.routes import auth_bp, ticket_bp
from app.routes.permisos_routes import permisos_bp
from app.routes.departamentos_routes import departamentos_bp

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar JWT
jwt = JWTManager(app)

# Configuración de CORS
"""CORS(app, resources={r"/*": {"origins": "http://localhost:4200"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])"""

"""CORS(app)"""

# Configuración de CORS correcta
CORS(app, supports_credentials=True)

# Habilitar preflight en todas las rutas
@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return '', 204  # ✅ Responde correctamente a preflight requests


# Registrar rutas
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(ticket_bp, url_prefix="/api/tickets")
app.register_blueprint(permisos_bp)
app.register_blueprint(departamentos_bp, url_prefix="/api/departamentos")

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
