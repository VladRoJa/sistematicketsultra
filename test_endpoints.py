# C:\Users\Vladimir\Documents\Sistema tickets\test_endpoints.py

import requests
import random
import string

BASE_URL = "http://localhost:5000"

# Funciones auxiliares
def nombre_random():
    return 'TEST_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

def obtener_token():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admicorp",
            "password": "123"
        }, timeout=5)
        if response.status_code == 200:
            return response.json().get("token")
        else:
            print(f"❌ Error al obtener token: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ Excepción al obtener token: {e}")
    return None

# Endpoints a probar
def construir_endpoints(token, producto_id=None):
    headers_auth = {"Authorization": f"Bearer {token}"} if token else {}

    return [
        # --- AUTH ---
        {"name": "Login", "method": "POST", "url": f"{BASE_URL}/api/auth/login", "auth": False, "data": {"username": "admicorp", "password": "123"}},

        # --- INVENTARIO ---
        {"name": "Ping Inventario", "method": "GET", "url": f"{BASE_URL}/api/inventario/ping", "auth": False},
        {"name": "Obtener Productos", "method": "GET", "url": f"{BASE_URL}/api/inventario/productos", "auth": True},
        {"name": "Crear Producto", "method": "POST", "url": f"{BASE_URL}/api/inventario/productos", "auth": True,
         "data": {"nombre": nombre_random(), "descripcion": "producto prueba", "unidad_medida": "PIEZAS", "categoria": "TEST", "subcategoria": "SUBTEST"}},

        {"name": "Obtener Sucursales", "method": "GET", "url": f"{BASE_URL}/api/inventario/sucursales", "auth": True},

        {"name": "Ver Existencias", "method": "GET", "url": f"{BASE_URL}/api/inventario/existencias", "auth": True},
        {"name": "Historial Movimientos", "method": "GET", "url": f"{BASE_URL}/api/inventario/movimientos", "auth": True},

        # --- TICKETS ---
        {"name": "Listar Tickets (All)", "method": "GET", "url": f"{BASE_URL}/api/tickets/all", "auth": True},
        {"name": "Listar Tickets (Filtro)", "method": "GET", "url": f"{BASE_URL}/api/tickets/list", "auth": True},
        {"name": "Exportar Tickets Excel", "method": "GET", "url": f"{BASE_URL}/api/tickets/export-excel", "auth": True},

        # --- REPORTES ---
        {"name": "Exportar Inventario Excel", "method": "GET", "url": f"{BASE_URL}/api/reportes/exportar-inventario", "auth": True},
        {"name": "Exportar Movimientos Excel", "method": "GET", "url": f"{BASE_URL}/api/reportes/exportar-movimientos", "auth": True},

        # --- PERMISOS / DEPARTAMENTOS ---
        {"name": "Listar Departamentos", "method": "GET", "url": f"{BASE_URL}/api/departamentos/listar", "auth": True},
        {"name": "Listar Permisos Global", "method": "GET", "url": f"{BASE_URL}/api/permisos/listar", "auth": True},

        # --- SUCURSALES ---
        {"name": "Listar Sucursales (módulo)", "method": "GET", "url": f"{BASE_URL}/api/sucursales/listar", "auth": True},
    ]

def correr_tests():
    token = obtener_token()
    if not token:
        print("🚫 No se pudo autenticar. Abortando pruebas.")
        return

    endpoints = construir_endpoints(token)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    print("\n📋 Ejecutando pruebas...\n")
    for ep in endpoints:
        method = ep["method"]
        url = ep["url"]
        auth_required = ep.get("auth", False)
        data = ep.get("data", None)

        h = headers if auth_required else {"Content-Type": "application/json"}

        try:
            if method == "GET":
                response = requests.get(url, headers=h, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=data, headers=h, timeout=5)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=h, timeout=5)
            elif method == "DELETE":
                response = requests.delete(url, headers=h, timeout=5)
            else:
                print(f"⚠️ Método {method} no implementado para {ep['name']}")
                continue

            status = "✅" if response.ok else "❌"
            print(f"{status} [{response.status_code}] {ep['name']} → {url}")

        except requests.exceptions.Timeout:
            print(f"⏳ Timeout en {ep['name']}")
        except Exception as e:
            print(f"❌ Error en {ep['name']}: {e}")

if __name__ == "__main__":
    correr_tests()
