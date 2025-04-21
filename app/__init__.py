# C:\Users\Vladimir\Documents\Sistema tickets\app\__init__.py

from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from app.extensions import db
from app.routes import auth_bp, ticket_bp, main_bp, aparatos_bp
from app.routes.inventarios import inventario_bp
from app.routes.permisos_routes import permisos_bp
from app.routes.departamentos_routes import departamentos_bp
from app.routes.reportes import reportes_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inicializar extensiones
    db.init_app(app)
    JWTManager(app)
    CORS(app, supports_credentials=True)

    # Registrar blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(ticket_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(aparatos_bp, url_prefix='/api/aparatos')
    app.register_blueprint(inventario_bp, url_prefix='/api/inventario')
    app.register_blueprint(permisos_bp)
    app.register_blueprint(departamentos_bp, url_prefix='/api/departamentos')
    app.register_blueprint(reportes_bp, url_prefix='/api/reportes')

    return app
