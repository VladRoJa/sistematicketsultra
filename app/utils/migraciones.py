# C:\Users\Vladimir\Documents\Sistema tickets\app\utils\migraciones.py

from sqlalchemy import text
from sqlalchemy.engine import Engine
from app import db

class MigracionAplicada(db.Model):
    __tablename__ = 'migraciones_aplicadas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    aplicada_en = db.Column(db.DateTime, server_default=db.func.now())


def aplicar_migraciones():
    engine: Engine = db.engine
    dialect = engine.dialect.name.lower()

    def columna_existe(nombre_columna: str) -> bool:
        if dialect == 'postgresql':
            query = """
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name = 'tickets' AND column_name = :columna
            """
        elif dialect == 'mysql':
            query = """
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'tickets' AND COLUMN_NAME = :columna
            """
        else:
            print(f"❌ Dialecto no soportado: {dialect}")
            return False

        with engine.connect() as conn:
            result = conn.execute(text(query), {'columna': nombre_columna})
            return result.fetchone()[0] > 0

    columnas_necesarias = {
        'fecha_en_progreso': "ALTER TABLE tickets ADD COLUMN fecha_en_progreso TIMESTAMP;",
        'fecha_solucion': "ALTER TABLE tickets ADD COLUMN fecha_solucion TIMESTAMP;",
        'subcategoria': "ALTER TABLE tickets ADD COLUMN subcategoria VARCHAR(255);",
        'subsubcategoria': "ALTER TABLE tickets ADD COLUMN subsubcategoria VARCHAR(255);"
    }

    if dialect == 'mysql':
        # Corrige tipo para MySQL
        columnas_necesarias = {
            k: v.replace("TIMESTAMP", "DATETIME") for k, v in columnas_necesarias.items()
        }

    with engine.connect() as connection:
        for nombre, sql in columnas_necesarias.items():
            if MigracionAplicada.query.filter_by(nombre=nombre).first():
                print(f"⚠️ Ya aplicada: {nombre}")
                continue

            if not columna_existe(nombre):
                print(f"➕ Agregando columna '{nombre}'...")
                connection.execute(text(sql))
            else:
                print(f"✅ Ya existe la columna '{nombre}', se registrará como aplicada.")

            nueva = MigracionAplicada(nombre=nombre)
            db.session.add(nueva)
            db.session.commit()
