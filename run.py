# run.py

from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from app.routes import auth_bp, ticket_bp

app = Flask(__name__)
app.config.from_object(Config)

# Inicializar JWT
jwt = JWTManager(app)

# Configuración de CORS
"""CORS(app, resources={r"/api/*": {"origins": "http://localhost:4200"}}, 
     supports_credentials=True, allow_headers=["Content-Type", "Authorization"], 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])"""

CORS(app)

# Registrar rutas
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(ticket_bp, url_prefix="/api/tickets")

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
