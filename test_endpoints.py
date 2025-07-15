#test_endpoints.py

import requests
import random
import string

BASE_URL = "http://localhost:5000"

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

def obtener_primer_inventario_id(token):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/api/inventario/", headers=headers, timeout=7)
        if r.ok and r.json():
            inventario_id = r.json()[0]['id']
            print(f"🟢 Usando inventario_id real: {inventario_id}")
            return inventario_id
        else:
            print("⚠️ No hay inventario registrado, creando uno nuevo para pruebas.")
            # Crear uno si no existe
            data = {
                "tipo": "producto",
                "nombre": nombre_random(),
                "descripcion": "producto prueba",
                "marca": "Generico",
                "proveedor": "Proveedor Test",
                "categoria": "TEST",
                "unidad": "PIEZAS",
                "sucursal_id": 1,
                "stock_actual": 10
            }
            res = requests.post(f"{BASE_URL}/api/inventario/", headers=headers, json=data, timeout=7)
            if res.ok:
                inventario_id = res.json().get('extra', {}).get('inventario_id')
                print(f"🟢 Inventario creado para test: {inventario_id}")
                return inventario_id
            return None
    except Exception as e:
        print(f"❌ Error al obtener primer inventario_id: {e}")
    return None

def construir_endpoints(token, inventario_id):
    sucursal_id = 1

    return [
        # --- AUTH ---
        {"name": "Login", "method": "POST", "url": f"{BASE_URL}/api/auth/login", "auth": False, "data": {"username": "admicorp", "password": "123"}},
        {"name": "Session Info", "method": "GET", "url": f"{BASE_URL}/api/auth/session-info", "auth": True},

        # --- TICKETS ---
        {"name": "Crear Ticket", "method": "POST", "url": f"{BASE_URL}/api/tickets/create", "auth": True, "data": {}},
        {"name": "Listar Todos los Tickets", "method": "GET", "url": f"{BASE_URL}/api/tickets/all", "auth": True},
        {"name": "Listar Tickets (Filtro)", "method": "GET", "url": f"{BASE_URL}/api/tickets/list", "auth": True},
        {"name": "Exportar Tickets Excel", "method": "GET", "url": f"{BASE_URL}/api/tickets/export-excel", "auth": True},
        {"name": "Migrar Historial Local", "method": "POST", "url": f"{BASE_URL}/api/tickets/migrar-historial-local", "auth": True},
        {"name": "Migrar Historial Railway", "method": "POST", "url": f"{BASE_URL}/api/tickets/migrar-historial-railway", "auth": True},
        {"name": "Eliminar Todos los Tickets", "method": "DELETE", "url": f"{BASE_URL}/api/tickets/eliminar-todos", "auth": True},

        # --- MAIN ---
        {"name": "Ping Main", "method": "GET", "url": f"{BASE_URL}/api/", "auth": False},

        # --- INVENTARIO ---
        {"name": "Ping Inventario", "method": "GET", "url": f"{BASE_URL}/api/inventario/ping", "auth": False},
        {"name": "Crear Inventario", "method": "POST", "url": f"{BASE_URL}/api/inventario/", "auth": True,
            "data": {
                "tipo": "producto",
                "nombre": nombre_random(),
                "descripcion": "producto prueba",
                "marca": "Generico",
                "proveedor": "Proveedor Test",
                "categoria": "TEST",
                "unidad": "PIEZAS",
                "sucursal_id": sucursal_id,
                "stock_actual": 10,
                "codigo_interno": "COD123",
                "no_equipo": "NEQ1",
                "gasto_sem": 1,
                "gasto_mes": 2,
                "pedido_mes": 3,
                "semana_pedido": "2024-27",
                "fecha_inventario": "2024-07-01"
            }},
        {"name": "Obtener Inventario", "method": "GET", "url": f"{BASE_URL}/api/inventario/", "auth": True},
        {"name": "Obtener Inventario por ID", "method": "GET", "url": f"{BASE_URL}/api/inventario/{inventario_id}", "auth": True},
        {"name": "Buscar Inventario", "method": "GET", "url": f"{BASE_URL}/api/inventario/buscar?nombre=TEST", "auth": True},
        {"name": "Editar Inventario", "method": "PUT", "url": f"{BASE_URL}/api/inventario/{inventario_id}", "auth": True,
            "data": {
                "nombre": "EDITADO_" + nombre_random(),
                "categoria": "EDITADO"
            }},
        {"name": "Registrar Movimiento", "method": "POST", "url": f"{BASE_URL}/api/inventario/movimientos", "auth": True,
            "data": {
                "tipo_movimiento": "entrada",
                "sucursal_id": sucursal_id,
                "usuario_id": 1,
                "inventarios": [
                    {
                        "inventario_id": inventario_id,
                        "cantidad": 5,
                        "unidad_medida": "PIEZAS"
                    }
                ],
                "observaciones": "Prueba de entrada"
            }
        },
        {"name": "Eliminar Inventario", "method": "DELETE", "url": f"{BASE_URL}/api/inventario/{inventario_id}", "auth": True},
        {"name": "Listar Sucursales (Inventario)", "method": "GET", "url": f"{BASE_URL}/api/inventario/sucursales", "auth": True},
        {"name": "Ver Existencias", "method": "GET", "url": f"{BASE_URL}/api/inventario/existencias", "auth": True},
        {"name": "Historial Movimientos", "method": "GET", "url": f"{BASE_URL}/api/inventario/movimientos", "auth": True},

        # --- PERMISOS / DEPARTAMENTOS ---
        {"name": "Asignar Permiso", "method": "POST", "url": f"{BASE_URL}/api/permisos/asignar", "auth": True, "data": {}},
        {"name": "Eliminar Permiso", "method": "DELETE", "url": f"{BASE_URL}/api/permisos/eliminar", "auth": True},
        {"name": "Listar Todos los Permisos", "method": "GET", "url": f"{BASE_URL}/api/permisos/listar", "auth": True},
        {"name": "Listar Departamentos", "method": "GET", "url": f"{BASE_URL}/api/departamentos/listar", "auth": True},

        # --- REPORTES ---
        {"name": "Exportar Inventario Excel", "method": "GET", "url": f"{BASE_URL}/api/reportes/exportar-inventario", "auth": True},
        {"name": "Exportar Movimientos Excel", "method": "GET", "url": f"{BASE_URL}/api/reportes/exportar-movimientos", "auth": True},
        {"name": "Reportar Error", "method": "POST", "url": f"{BASE_URL}/api/reportes/reportar-error", "auth": True, "data": {}},

        # --- SUCURSALES ---
        {"name": "Listar Sucursales", "method": "GET", "url": f"{BASE_URL}/api/sucursales/listar", "auth": True},

        # --- IMPORTAR ---
        {"name": "Importar Catálogo", "method": "POST", "url": f"{BASE_URL}/api/importar/catalogo", "auth": True, "file": "catalogo_ejemplo.xlsx"},
        {"name": "Importar Existencias", "method": "POST", "url": f"{BASE_URL}/api/importar/existencias", "auth": True, "file": "existencias_ejemplo.xlsx"},
        {"name": "Descargar Layout Catálogo", "method": "GET", "url": f"{BASE_URL}/api/importar/layout/catalogo", "auth": True},
        {"name": "Descargar Layout Existencias", "method": "GET", "url": f"{BASE_URL}/api/importar/layout/existencias", "auth": True},

        # --- ASISTENCIA ---
        {"name": "Registrar Asistencia", "method": "POST", "url": f"{BASE_URL}/api/asistencia/registrar", "auth": True, "data": {"usuario_id": 1, "sucursal_id": 1}},

        # --- HORARIOS ---
        {"name": "Listar Horarios", "method": "GET", "url": f"{BASE_URL}/api/horarios/", "auth": True},
        {"name": "Crear Horario", "method": "POST", "url": f"{BASE_URL}/api/horarios/", "auth": True, "data": {"nombre": nombre_random(), "ciclo": 1}},
    ]

def correr_tests():
    token = obtener_token()
    if not token:
        print("🚫 No se pudo autenticar. Abortando pruebas.")
        return

    inventario_id = obtener_primer_inventario_id(token)
    if not inventario_id:
        print("🚫 No se pudo crear ni obtener inventario_id. Abortando pruebas.")
        return

    endpoints = construir_endpoints(token, inventario_id)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

    print("\n📋 Ejecutando pruebas...\n")
    for ep in endpoints:
        method = ep["method"]
        url = ep["url"]
        auth_required = ep.get("auth", False)
        data = ep.get("data", None)
        file_path = ep.get("file", None)

        h = headers if auth_required else {"Content-Type": "application/json"}
        try:
            if method == "GET":
                response = requests.get(url, headers=h, timeout=10)
                if "layout" in url:
                    # Guardar el archivo de layout recibido
                    filename = url.split("/")[-1] + ".xlsx"
                    with open(filename, "wb") as f:
                        f.write(response.content)
                    print(f"✅ [Layout descargado] {ep['name']} → {filename}")
                    continue
            elif method == "POST" and file_path:
                with open(file_path, "rb") as f:
                    files = {"archivo": (file_path, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                    response = requests.post(url, files=files, headers={"Authorization": f"Bearer {token}"}, timeout=15)
            elif method == "POST":
                response = requests.post(url, json=data, headers=h, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=h, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=h, timeout=10)
            else:
                print(f"⚠️ Método {method} no implementado para {ep['name']}")
                continue

            status = "✅" if response.ok else "❌"
            print(f"{status} [{response.status_code}] {ep['name']} → {url}")
            if not response.ok and response.content:
                print("⛔️ ", response.text)
        except requests.exceptions.Timeout:
            print(f"⏳ Timeout en {ep['name']}")
        except Exception as e:
            print(f"❌ Error en {ep['name']}: {e}")


if __name__ == "__main__":
    correr_tests()
