# app/db_init.py

import os
import pymysql
from flask import current_app
from sqlalchemy.engine.url import make_url

def inicializar_db_si_esta_vacia():
    try:
        # Obtener la URI desde la configuración de Flask
        uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
        db_url = make_url(uri)

        # Conexión a la base de datos usando los datos parseados
        connection = pymysql.connect(
            host=db_url.host,
            user=db_url.username,
            password=db_url.password,
            database=db_url.database,
            port=db_url.port or 3306,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        with connection.cursor() as cursor:
            # Verifica si hay tablas
            cursor.execute("SHOW TABLES;")
            tablas = cursor.fetchall()

            if len(tablas) == 0:
                print("✅ Base de datos vacía. Cargando sistema_tickets.sql...")

                sql_path = os.path.join(os.path.dirname(__file__), "data", "sistema_tickets.sql")
                with open(sql_path, 'r', encoding='utf-8') as f:
                    sql_script = f.read()

                for statement in sql_script.split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)

                connection.commit()
                print("✅ Base de datos cargada correctamente.")
            else:
                print("📦 La base de datos ya tiene contenido. No se realizó carga.")

        connection.close()

    except Exception as e:
        print("❌ Error al verificar o cargar la base de datos:", str(e))
