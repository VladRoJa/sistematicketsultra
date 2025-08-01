# app\__init__.py

from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

load_dotenv()
from config import Config
from app.extensions import db, migrate
from app.routes import auth_bp, ticket_bp, main_bp
from app.routes.inventarios import inventario_bp
from app.routes.permisos_routes import permisos_bp
from app.routes.departamentos_routes import departamentos_bp
from app.routes.reportes import reportes_bp
from app.routes.sucursales import sucursales_bp
from app.routes.importar_inventario import bp_importar
from app.routes.asistencia_routes import asistencia_bp
from app.routes.horarios_routes import horarios_bp
from app.routes.bloques_routes import bloques_bp
from app.routes.asignacion_horario_routes import asignacion_bp
from app.routes.catalogos_routes import catalogos_bp
from app.routes.usuarios_routes import usuarios_bp
from app.routes.formulario_ticket_routes import formulario_ticket_bp


def create_app():
    """Inicializa la aplicación principal Flask."""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    @app.before_request
    def skip_jwt_for_options():
        # Permite todas las preflight sin JWT
        if request.method == 'OPTIONS':
            return '', 204

    # ──────────────────────────────────────
    # Inicializar Extensiones
    # ──────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    JWTManager(app)

    # ──────────────────────────────────────
    # Configuración de CORS
    # ──────────────────────────────────────
    CORS(
        app,
        origins=app.config['CORS_ORIGINS'],
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
    

    
    print("✅ CORS configurado con:", app.config['CORS_ORIGINS'])

    # ──────────────────────────────────────
    # Registrar Blueprints (todas bajo /api/)
    # ──────────────────────────────────────
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(ticket_bp, url_prefix='/api/tickets')
    app.register_blueprint(main_bp, url_prefix='/api')
    app.register_blueprint(inventario_bp, url_prefix='/api/inventario')
    app.register_blueprint(permisos_bp, url_prefix='/api/permisos')
    app.register_blueprint(departamentos_bp, url_prefix='/api/departamentos')
    app.register_blueprint(reportes_bp, url_prefix='/api/reportes')
    app.register_blueprint(sucursales_bp, url_prefix='/api/sucursales')
    app.register_blueprint(bp_importar, url_prefix='/api/importar')
    app.register_blueprint(asistencia_bp, url_prefix='/api/asistencia')
    app.register_blueprint(horarios_bp, url_prefix='/api/horarios')
    app.register_blueprint(bloques_bp, url_prefix='/api/bloques')
    app.register_blueprint(asignacion_bp, url_prefix='/api/asignaciones')
    app.register_blueprint(catalogos_bp, url_prefix='/api/catalogos')
    app.register_blueprint(usuarios_bp, url_prefix='/api/usuarios')
    app.register_blueprint(formulario_ticket_bp, url_prefix='/api/formulario_ticket')
    
    app.config['DEBUG'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True

    return app
