# app/__init__.py
from flask import Flask
from flask_cors import CORS
from config import Config
from app.routes import auth_bp, ticket_bp, main_bp, aparatos_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Configuración de CORS
    CORS(app, origins=["http://localhost:8080"], supports_credentials=True)

    # Registrar blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(ticket_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(aparatos_bp, url_prefix='/api/aparatos')


    return app