#run.py

from flask import Flask
from flask_cors import CORS
from app.routes.auth_routes import auth_bp
from app.routes.main_routes import main_bp
from app.routes.ticket_routes import ticket_bp
from config import Config
from flask_jwt_extended import JWTManager

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config.from_object(Config)

# 🔥 Depuración: Imprimir la clave JWT para verificar si Flask la reconoce
print(f"🔑 JWT_SECRET_KEY Cargado: {app.config.get('JWT_SECRET_KEY')}")
print(f"🔹 JWT_TOKEN_LOCATION: {app.config.get('JWT_TOKEN_LOCATION')}")
print(f"🔹 JWT_HEADER_NAME: {app.config.get('JWT_HEADER_NAME')}")
print(f"🔹 JWT_HEADER_TYPE: {app.config.get('JWT_HEADER_TYPE')}")

# 🔹 Inicializar JWT
jwt = JWTManager(app)

# ✅ Habilitar CORS correctamente
CORS(app, resources={r"/*": {"origins": "http://localhost:4200"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])


# 🔹 Registrar los Blueprints
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(main_bp, url_prefix="/api/main")
app.register_blueprint(ticket_bp, url_prefix="/api/tickets")

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
