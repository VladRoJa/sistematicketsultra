# app\extensions.py

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# ─────────────────────────────────────────────────────────────
# EXTENSIONES GLOBALMENTE DISPONIBLES
# ─────────────────────────────────────────────────────────────

# Base de datos (ORM)
db = SQLAlchemy()

# Migraciones automáticas (flask db init/migrate/upgrade)
migrate = Migrate()

