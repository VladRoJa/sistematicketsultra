import requests
import random
import string
import os

BASE_URL = "http://localhost:5000"

def nombre_random(prefix='TEST'):
    return f"{prefix}_{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"

def login():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admicorp", "password": "123"})
    if resp.ok:
        return resp.json()["token"]
    else:
        raise Exception(f"Login failed: {resp.status_code} {resp.text}")

def print_result(ok, label, url, resp=None):
    emoji = "✅" if ok else "❌"
    msg = f"{emoji} {label} [{url}]"
    if not ok and resp is not None:
        msg += f"\n     {resp.text[:180]}"
    print(msg)

def create_dummy_file(filename):
    with open(filename, "wb") as f:
        f.write(b"Dummy,Archivo,Para,Test\n1,2,3,4")
    return filename

def cleanup_dummy_file(filename):
    if os.path.exists(filename):
        os.remove(filename)

def main():
    # --- RESUMEN ---
    PASADOS, FALLIDOS = 0, 0
    recursos_creados = {"catalogos": {}, "inventario": [], "movimientos": [], "tickets": [], "permisos": []}
    archivos_dummy = []

    token = login()
    HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ---------- CATALOGOS CRUD ----------
    catalogos = ["proveedores", "marcas", "categorias", "unidades_medida", "grupos_musculares"]
    for cat in catalogos:
        # Crear
        nombre = nombre_random(cat)
        resp = requests.post(f"{BASE_URL}/api/catalogos/{cat}", json={"nombre": nombre}, headers=HEADERS)
        ok = resp.ok
        print_result(ok, f"Crear {cat}", resp.request.url, resp)
        if ok:
            id_ = resp.json().get("id") or resp.json().get("elemento", {}).get("id")
            recursos_creados["catalogos"].setdefault(cat, []).append(id_)
            PASADOS += 1
            # Editar
            resp = requests.put(f"{BASE_URL}/api/catalogos/{cat}/{id_}", json={"nombre": nombre+"_EDIT"}, headers=HEADERS)
            print_result(resp.ok, f"Editar {cat}", resp.request.url, resp)
            PASADOS += int(resp.ok)
            FALLIDOS += int(not resp.ok)
            # Buscar
            resp = requests.get(f"{BASE_URL}/api/catalogos/{cat}/buscar?q={nombre}", headers=HEADERS)
            print_result(resp.ok, f"Buscar {cat}", resp.request.url, resp)
            PASADOS += int(resp.ok)
            FALLIDOS += int(not resp.ok)
        else:
            FALLIDOS += 1

    # ---------- INVENTARIO CRUD ----------
    inventario_payload = {
        "tipo": "producto",
        "nombre": nombre_random("PROD"),
        "descripcion": "producto prueba",
        "marca": "Generico",
        "proveedor": "Proveedor Test",
        "categoria": "TEST",
        "unidad": "PIEZAS",
        "sucursal_id": 1,
    }
    resp = requests.post(f"{BASE_URL}/api/inventario/", json=inventario_payload, headers=HEADERS)
    ok = resp.ok
    print_result(ok, "Crear Inventario", resp.request.url, resp)
    if ok:
        inventario_id = resp.json().get('extra', {}).get('inventario_id') or resp.json().get("inventario_id") or resp.json().get("id")
        recursos_creados["inventario"].append(inventario_id)
        PASADOS += 1
        # Obtener
        resp = requests.get(f"{BASE_URL}/api/inventario/{inventario_id}", headers=HEADERS)
        print_result(resp.ok, "Obtener Inventario por ID", resp.request.url, resp)
        PASADOS += int(resp.ok)
        FALLIDOS += int(not resp.ok)
        # Editar
        resp = requests.put(f"{BASE_URL}/api/inventario/{inventario_id}", json={"nombre": nombre_random("EDITADO"), "categoria": "EDITADO"}, headers=HEADERS)
        print_result(resp.ok, "Editar Inventario", resp.request.url, resp)
        PASADOS += int(resp.ok)
        FALLIDOS += int(not resp.ok)
    else:
        FALLIDOS += 1

    # ---------- MOVIMIENTOS ----------
    if recursos_creados["inventario"]:
        movimiento_payload = {
            "tipo_movimiento": "entrada",
            "sucursal_id": 1,
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
        resp = requests.post(f"{BASE_URL}/api/inventario/movimientos", json=movimiento_payload, headers=HEADERS)
        ok = resp.ok
        print_result(ok, "Registrar Movimiento", resp.request.url, resp)
        PASADOS += int(ok)
        FALLIDOS += int(not ok)
        if ok:
            recursos_creados["movimientos"].append(True)

    # ---------- TICKETS ----------
    ticket_payload = {
        "descripcion": "Ticket de prueba",
        "departamento_id": 1,
        "criticidad": 1,
        "categoria": "PRUEBA",
    }
    resp = requests.post(f"{BASE_URL}/api/tickets/create", json=ticket_payload, headers=HEADERS)
    ok = resp.ok
    print_result(ok, "Crear Ticket", resp.request.url, resp)
    if ok:
        ticket_id = resp.json().get("ticket_id")
        recursos_creados["tickets"].append(ticket_id)
        PASADOS += 1

    # ---------- PERMISOS / DEPARTAMENTOS ----------
    permiso_payload = {"user_id": 1, "permiso": "TEST"}
    resp = requests.post(f"{BASE_URL}/api/permisos/asignar", json=permiso_payload, headers=HEADERS)
    print_result(resp.ok, "Asignar Permiso", resp.request.url, resp)
    PASADOS += int(resp.ok)
    FALLIDOS += int(not resp.ok)

    # ---------- SUCURSALES / REPORTES ----------
    resp = requests.get(f"{BASE_URL}/api/sucursales/listar", headers=HEADERS)
    print_result(resp.ok, "Listar Sucursales", resp.request.url, resp)
    PASADOS += int(resp.ok)
    FALLIDOS += int(not resp.ok)
    resp = requests.get(f"{BASE_URL}/api/reportes/exportar-inventario", headers=HEADERS)
    print_result(resp.ok, "Exportar Inventario Excel", resp.request.url, resp)
    PASADOS += int(resp.ok)
    FALLIDOS += int(not resp.ok)

    # ---------- IMPORTAR / EXPORTAR ----------
    archivo = create_dummy_file("catalogo_ejemplo.xlsx")
    archivos_dummy.append(archivo)
    resp = requests.post(f"{BASE_URL}/api/importar/catalogo", files={"archivo": open(archivo, "rb")}, headers={"Authorization": f"Bearer {token}"})
    print_result(resp.ok, "Importar Catálogo", resp.request.url, resp)
    PASADOS += int(resp.ok)
    FALLIDOS += int(not resp.ok)
    cleanup_dummy_file(archivo)

    # ---------- CLEANUP ----------
    # Borrar recursos de prueba al final
    for cat, ids in recursos_creados["catalogos"].items():
        for id_ in ids:
            resp = requests.delete(f"{BASE_URL}/api/catalogos/{cat}/{id_}", headers=HEADERS)
            print_result(resp.ok, f"Borrar {cat}", resp.request.url, resp)
    for inventario_id in recursos_creados["inventario"]:
        resp = requests.delete(f"{BASE_URL}/api/inventario/{inventario_id}", headers=HEADERS)
        print_result(resp.ok, "Borrar Inventario", resp.request.url, resp)
    for ticket_id in recursos_creados["tickets"]:
        resp = requests.delete(f"{BASE_URL}/api/tickets/delete/{ticket_id}", headers=HEADERS)
        print_result(resp.ok, "Borrar Ticket", resp.request.url, resp)
    # Si quieres, puedes borrar permisos o movimientos dummy aquí también...

    print("\n----- RESUMEN FINAL -----")
    print(f"✔️ Pruebas PASADAS: {PASADOS}")
    print(f"❌ Pruebas FALLIDAS: {FALLIDOS}")

if __name__ == "__main__":
    main()
