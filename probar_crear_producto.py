# probar_crear_producto.py
import requests

url = "http://localhost:5000/api/inventario/productos"

payload = {
    "nombre": "CLORO",
    "descripcion": "cloro galón",
    "unidad_medida": "GALON",
    "categoria": "LIMPIEZA"
}

try:
    response = requests.post(url, json=payload)
    print("✅ Código de estado:", response.status_code)
    print("📦 Respuesta:", response.json())
except requests.exceptions.RequestException as e:
    print("❌ Error en la petición:", e)
