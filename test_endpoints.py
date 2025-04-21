#C:\Users\Vladimir\Documents\Sistema tickets\test_endpoints.py

import requests
import random
import string

BASE_URL = "http://localhost:5000"

def nombre_random():
    return 'TEST_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

# Si necesitas token, primero lo obtenemos
def obtener_token():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admicorp",
            "password": "123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print("❌ Error al obtener token:", response.text)
    except Exception as e:
        print("❌ Excepción al obtener token:", e)
    return None

# Lista de endpoints a validar
endpoints = [
    {"name": "Login", "method": "POST", "path": "/api/auth/login", "auth": False, "data": {"username": "admicorp", "password": "123"}},
    {"name": "Ping Inventario", "method": "GET", "path": "/api/inventario/ping", "auth": False},
    {"name": "Obtener Productos", "method": "GET", "path": "/api/inventario/productos", "auth": True},
    {
        "name": "Crear Producto",
        "method": "POST",
        "path": "/api/inventario/productos",
        "auth": True,
        "data": {
            "nombre": nombre_random(),  # ← genera un nombre único
            "descripcion": "producto test",
            "unidad_medida": "PIEZAS",
            "categoria": "PRUEBA",
            "subcategoria": "PRUEBA_SUB"
        }
    },
    {"name": "Editar Producto", "method": "PUT", "path": "/api/inventario/productos/{producto_id}", "auth": True,
     "data": {
        "nombre": "TEST EDITADO",
        "descripcion": "producto modificado",
        "unidad_medida": "CAJA",
        "categoria": "ACTUALIZADO",
        "subcategoria": "SECUNDARIA"
     }},
    {"name": "Eliminar Producto", "method": "DELETE", "path": "/api/inventario/productos/{producto_id}", "auth": True},
    {"name": "Historial de Movimientos", "method": "GET", "path": "/api/inventario/movimientos", "auth": True},
    {"name": "Resumen Stock Total", "method": "GET", "path": "/api/inventario/stock-total", "auth": True},
    {"name": "Resumen Movimientos por Producto", "method": "GET", "path": "/api/inventario/resumen-movimientos", "auth": True},
    {"name": "Exportar Inventario a Excel", "method": "GET", "path": "/api/reportes/exportar-inventario", "auth": True},
    {"name": "Exportar Movimientos a Excel", "method": "GET", "path": "/api/reportes/exportar-movimientos", "auth": True},

]

def validar_endpoints():
    token = obtener_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}" 

    producto_id_creado = None

    for ep in endpoints:
        url = f"{BASE_URL}{ep['path']}"
        try:
            h = headers if ep.get("auth") else {}
            method = ep["method"]
            data = ep.get("data", {})

            if method == "POST":
                response = requests.post(url, json=data, headers=h)
                # Guardar el ID del producto creado
                if ep["name"] == "Crear Producto" and response.status_code == 201:
                    producto_id_creado = response.json().get("producto_id")
            elif method == "PUT" and "{producto_id}" in ep["path"]:
                if producto_id_creado:
                    url = url.replace("{producto_id}", str(producto_id_creado))
                else:
                    print("❌ No se puede editar porque no se creó el producto.")
                    continue
                response = requests.put(url, json=data, headers=h)
            elif method == "DELETE" and "{producto_id}" in ep["path"]:
                if producto_id_creado:
                    url = url.replace("{producto_id}", str(producto_id_creado))
                else:
                    print("❌ No se puede eliminar porque no se creó el producto.")
                    continue
                response = requests.delete(url, headers=h)
            elif method == "GET":
                response = requests.get(url, headers=h)
            else:
                print(f"⚠️ Método {method} no implementado.")
                continue

            check = "✅" if response.status_code < 400 else "❌"
            print(f"{check} [{response.status_code}] {ep['name']} -> {url}")

        except Exception as e:
            print(f"❌ {ep['name']} -> Error: {e}")


if __name__ == "__main__":
    validar_endpoints()
