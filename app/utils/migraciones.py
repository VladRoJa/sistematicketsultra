# C:\Users\Vladimir\Documents\Sistema tickets\app\utils\migraciones.py

from sqlalchemy import text
from app.db_init import db

class MigracionAplicada(db.Model):
    __tablename__ = 'migraciones_aplicadas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    aplicada_en = db.Column(db.DateTime, server_default=db.func.now())

def aplicar_migraciones():
    columnas_necesarias = {
        'fecha_en_progreso': "ALTER TABLE tickets ADD COLUMN fecha_en_progreso DATETIME;",
        'fecha_solucion': "ALTER TABLE tickets ADD COLUMN fecha_solucion DATETIME;",
        'subcategoria': "ALTER TABLE tickets ADD COLUMN subcategoria VARCHAR(255);",
        'subsubcategoria': "ALTER TABLE tickets ADD COLUMN subsubcategoria VARCHAR(255);"
    }

    with db.engine.connect() as connection:
        for nombre, sql in columnas_necesarias.items():
            # ¿Ya se aplicó esta migración?
            ya_aplicada = MigracionAplicada.query.filter_by(nombre=nombre).first()
            if ya_aplicada:
                print(f"⚠️ Ya aplicada: {nombre}")
                continue

            # ¿Existe la columna?
            resultado = connection.execute(text(f"""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'tickets' AND COLUMN_NAME = :columna
            """), {'columna': nombre})

            existe = resultado.fetchone()[0]
            if not existe:
                print(f"➕ Agregando columna '{nombre}'...")
                connection.execute(text(sql))
            else:
                print(f"✅ Ya existe la columna '{nombre}', pero la registraremos como aplicada.")

            # Registrar la migración
            nueva = MigracionAplicada(nombre=nombre)
            db.session.add(nueva)
            db.session.commit()
