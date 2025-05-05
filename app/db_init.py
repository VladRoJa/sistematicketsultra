# app/db_init.py

import os
import pymysql
from flask import current_app

def inicializar_db_si_esta_vacia():
    try:
        # Conexión a la base de datos (usa tus variables de entorno)
        connection = pymysql.connect(
            host=os.environ.get("DB_HOST"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME"),
            port=int(os.environ.get("DB_PORT", 3306)),
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
