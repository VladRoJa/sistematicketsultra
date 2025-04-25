# C:\Users\Vladimir\Documents\Sistema tickets\setup_db.py

# -------------------------------------------------------------------------------
# SCRIPT: Inicialización de la base de datos (creación de tablas si no existen)
# -------------------------------------------------------------------------------

from setup_db_connection import get_setup_db_connection


# -------------------------------------------------------------------------------
# FUNCIÓN: Crear todas las tablas necesarias
# -------------------------------------------------------------------------------
def inicializar_base_de_datos():
    conn = get_setup_db_connection()
    cursor = conn.cursor()

    # -------------------------------------------------------------------------------
    # CREACIÓN DE TABLAS
    # -------------------------------------------------------------------------------

    cursor.execute("""CREATE TABLE IF NOT EXISTS detalle_movimiento (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS inventario_sucursal (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS movimientos_inventario (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS productos (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS sucursales (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tickets (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tickets_mantenimiento_aparatos (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tickets_mantenimiento_edificio (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS usuarios_permisos (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS aparatos_gimnasio (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS departamentos (...);""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS historial_eliminaciones_movimientos (...);""")

    # -------------------------------------------------------------------------------
    # FINALIZAR
    # -------------------------------------------------------------------------------
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Todas las tablas han sido creadas correctamente (si no existían).")

# -------------------------------------------------------------------------------
# EJECUCIÓN DIRECTA DEL SCRIPT
# -------------------------------------------------------------------------------
if __name__ == "__main__":
    inicializar_base_de_datos()
