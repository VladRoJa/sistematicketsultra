# Backend – Sistema de Tickets UltraGym

## 📌 Visión general
El backend está construido con **Flask** y organiza su código en una **estructura modular**.

- La aplicación se crea en `backend/app/__init__.py`, donde se inicializan:
  - Extensiones (`db`, `migrate`)
  - Configuración de **CORS** y **JWT**
  - Registro de **blueprints** con las rutas de la API

- La configuración central está en `backend/app/config.py`:
  - Carga de variables de entorno
  - Definición de claves secretas y expiración de tokens
  - Orígenes permitidos para CORS

---

## ⚙️ Extensiones

- **`backend/app/extensions.py`**  
  Instancias globales de **SQLAlchemy** y **Migrate**.

- **`backend/app/config.py`**  
  - Lee el entorno (`APP_ENV`) para cargar el `.env` correspondiente.  
  - Valida `SECRET_KEY` y `JWT_SECRET_KEY`.  
  - Configura la conexión a la base de datos y CORS.  

---

## 🗂️ Estructura de módulos

- **Rutas (Blueprints):** `backend/app/routes/` – cada módulo define un Blueprint con prefijo de URL y endpoints.  
- **Modelos (ORM):** `backend/app/models/` – clases SQLAlchemy que representan tablas.  
- **Controladores:** `backend/app/controllers/` – lógica de negocio.  
- **Utilidades:** `backend/app/utils/` – funciones auxiliares (fechas, errores, filtros, etc.).  

---

## 📑 Modelos principales

| Archivo / Clase | Descripción | Campos y relaciones |
|-----------------|-------------|----------------------|
| `user_model.py` – **UserORM** | Usuarios del sistema | `id`, `username`, `password`, `rol`, `sucursal_id`, `department_id`. <br> Relaciones: movimientos, asistencias. <br> Métodos: `verify_password`, `get_by_username`, `get_by_id`. |
| `permiso_model.py` – **Permiso** | Usuarios ↔ departamentos (flag admin) | `id`, `user_id`, `departamento_id`, `es_admin`. <br> Relaciones con `UserORM` y `Departamento`. |
| `ticket_model.py` – **Ticket** | Entidad de tickets | `descripcion`, `username`, `asignado_a`, `sucursal_id`, `estado`, fechas de creación/progreso/finalización, `historial_fechas` (JSON). <br> Relaciones: `Departamento`, `InventarioGeneral`, `Sucursal`, `CatalogoClasificacion`. |
| `sucursal_model.py` – **Sucursal** | Sucursales físicas | `sucursal_id`, `serie`, `sucursal`, `estado`, `municipio`, `direccion`. <br> Relaciones con inventarios y movimientos. |
| `departamento_model.py` – **Departamento** | Catálogo de departamentos | `id`, `nombre`. |
| `catalogos.py` – (varias) | Catálogos del sistema | Proveedores, marcas, unidades, tipos de inventario, clasificaciones. <br> `CatalogoClasificacion` implementa jerarquía padre/hijos. |
| `inventario.py` – **InventarioGeneral**, **InventarioSucursal** | Inventario y existencias | `InventarioGeneral`: tipo, nombre, descripción, marca, proveedor, categoría, unidad, códigos internos. <br> `InventarioSucursal`: asocia inventario a sucursal y maneja stock. |

> 🔎 Nota: algunos modelos tienen métodos `__repr__` vacíos (`return f" "`). Se recomienda completarlos o eliminarlos si no se usan.

---

## 🛠️ Utilidades

| Archivo | Funciones | Uso |
|---------|-----------|-----|
| `datetime_utils.py` | `format_datetime(dt)`, `format_datetime_iso(dt)` | Formatea `datetime` a legible o ISO (zona Tijuana). |
| `ticket_filters.py` | `filtrar_tickets_por_usuario(user, query=None)` | Aplica reglas por rol para queries de tickets. |
| `error_handler.py` | `manejar_error(e, contexto="")` | Manejo uniforme de excepciones y respuesta JSON. |

---

## 🎛️ Controladores

| Archivo | Clase / Métodos | Uso |
|---------|----------------|-----|
| `auth_controller.py` – **AuthController** | `login(data)` (genera JWT), `logout()` | `login()` se usa en rutas. `logout()` no está expuesto → posible código muerto. |
| `ticket_controller.py` – **TicketController** | `create_ticket`, `update_ticket`, `list_tickets`, … | Invocados desde las rutas de tickets. |

---

## 🌐 Rutas (Blueprints)

| Archivo | Blueprint | Endpoints principales | Descripción |
|---------|-----------|----------------------|-------------|
| `auth_routes.py` | `auth_bp` | `login()`, `session_info()` | Autenticación e info de sesión. No hay logout expuesto. |
| `ticket_routes.py` | `ticket_bp` | `create_ticket()`, `list_tickets()`, `update_ticket_status()`, exportar Excel, … | Núcleo CRUD de tickets y exportaciones. |
| `formulario_ticket_routes.py` | `formulario_ticket_bp` | Campos dinámicos de formularios | Construcción de formularios por departamento/clasificación. |
| `reportes.py` | `reportes_bp` | Exportar inventario, reportes por sucursal, … | Genera archivos con pandas + openpyxl. |
| `sucursales.py` | `sucursales_bp` | CRUD sucursales | Usa el modelo `Sucursal`. |
| `departamentos_routes.py` | `departamentos_bp` | CRUD departamentos | Usa `Departamento`. |
| `permisos_routes.py` | `permisos_bp` | `asignar_permiso()`, `listar_permisos()` | Gestiona permisos usuario/departamento. |
| `catalogos_routes.py` | `catalogos_bp` | `listar_catalogo()`, `crear_catalogo()` | Manejo dinámico de catálogos. |
| **Otros** | — | — | Inventarios, asistencia, horarios, usuarios, importación, etc. Siguen el mismo patrón (Blueprint + CRUD). |
