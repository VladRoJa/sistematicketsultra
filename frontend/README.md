# Frontend – Sistema de Tickets UltraGym (Angular 19)

## 📌 Visión general
La interfaz está desarrollada con **Angular** usando un enfoque **modular y standalone**.  

- El punto de entrada es `app.component.ts`, que delega la navegación al `RouterOutlet`.  
- Las rutas principales están en `app.routes.ts`:  
  - `/login` → pantalla de autenticación.  
  - `/admin` → panel de administración (protegido).  
  - Usuarios autenticados → `LayoutComponent` con rutas hijas para tickets, inventario, permisos, etc.  

---

## 🏗️ Estructura de carpetas

| Carpeta | Propósito |
|---------|-----------|
| `main/` | Layout principal (sidebar + vistas de tickets). |
| `pantalla-login/` | Login de usuario (credenciales). |
| `pantalla-ver-tickets/` | Lista de tickets con filtros (usuario, estado, depto., etc.). |
| `pantalla-crear-ticket/` | Formulario de creación de tickets dinámicos por departamento. |
| `inventario/` | Inventario y catálogos (proveedores, marcas, categorías, etc.). |
| `admin-panel/` y `admin-permisos/` | Vistas exclusivas de administradores (dashboard + permisos). |
| `services/` | Servicios HTTP al backend (auth, tickets, inventario, catálogos, permisos, usuarios, etc.). |
| `guards/` | Guardias de rutas para autenticación y roles. |
| `interceptors/` | Interceptores HTTP (token y manejo de errores 401). |
| `helpers/` y `utils/` | Funciones auxiliares para filtros, sucursales, inventario por código, etc. |

---

## 🔌 Servicios principales

| Servicio | Métodos clave | Descripción |
|----------|---------------|-------------|
| **AuthService** (`services/auth.service.ts`) | `login(username, password)`, `logout()`, `setSession(token, user, redirigir?)`, `getToken()`, `getUser()`, `isLoggedIn()`, `obtenerUsuarioAutenticado()`, `esAdmin()` | Gestiona autenticación; persiste sesión en `localStorage`; redirige según rol/sucursal. |
| **TicketService** (`services/ticket.service.ts`) | `getTickets(limit, offset)`, `getTicketsConFiltros(filters)`, `getAllTicketsFiltered(filtros)`, `exportarTickets(filtros)` | Centraliza solicitudes de tickets, con soporte de filtros y exportación a Excel. |
| **CatalogoService** | `listarElemento`, `crearElemento`, `editarElemento`, `eliminarElemento`, `buscarElemento`, `importarArchivo`, `exportarArchivo`, `getClasificacionesArbol`, `getClasificacionesPlanas` | CRUD genérico de catálogos y métodos específicos para clasificaciones jerárquicas. |
| **PermisoService** | `getPermisosUsuario(userId)` | Consulta y asignación de permisos en el panel administrativo. |
| **Otros servicios** | `DepartamentoService`, `UsuarioService`, `InventarioService`, `FormularioTicketService`, `SucursalService`, etc. | Operaciones CRUD auxiliares. |

---

## 🛡️ Guards e Interceptors

### Guards
- **AuthGuard**: restringe acceso si no hay sesión → redirige a `/login`.  
- **AdminGuard**: permite acceso solo a roles `admin` o `super_admin`, en caso contrario redirige a `/ver-tickets`.  

### Interceptors
- **TokenInterceptor** (`auth.interceptor.ts`):  
  Adjunta token JWT a cada petición, maneja **401**, abre `ReauthModalComponent` y reintenta petición.  
- **JwtInterceptor** (`jwt.interceptor.ts`):  
  Comprueba expiración del token con `JwtHelperService` y lo añade a headers.  
  > ⚠️ Puede ser redundante con `TokenInterceptor`; revisar configuración.  

---

## 🧰 Helpers y Utils

| Archivo | Funciones | Descripción |
|---------|-----------|-------------|
| `helpers/inventario/buscar-por-codigo.helper.ts` | `buscarEquipoPorCodigo()` | Consulta GET a `inventario/buscar-por-codigo` con token en headers. |
| `helpers/sucursales/obtener-sucursales.helper.ts` | `obtenerSucursales()` | GET a `sucursales/listar` con token en headers. |
| `utils/ticket-utils.ts` | `FiltroString`, `FiltroNumero`, `generarOpcionesDepartamentosDesdeTickets`, `generarOpcionesDisponiblesDesdeTickets`, `getFiltrosActivosFrom`, `filtrarTicketsConFiltros`, `regenerarFiltrosFiltradosDesdeTickets` | Tipos y funciones para construir filtros dinámicos, aplicar filtros en cliente y recalcular opciones disponibles. |

> **Estándar Angular:** toda la lógica está en `.ts`, nunca en `.html`.  

---

## ⭐ Componentes destacados

### AdminPermisosComponent
- Variables: usuarios, departamentos, usuario seleccionado y permisos.  
- `ngOnInit`: carga usuarios y departamentos (`UsuarioService`, `DepartamentoService`).  
- `cargarPermisos()`: obtiene permisos actuales de un usuario.  
- `tienePermiso()` / `togglePermiso()`: gestionan permisos en UI.  
- `guardarPermisos()`: pendiente → actualmente solo imprime en consola.  

### Pantalla **Ver Tickets**
- Usa `TicketService` para consultar tickets.  
- Usa `utils/ticket-utils.ts` para:
  - Generar opciones de filtros (usuarios, estados, categorías, inventario, etc.).  
  - Obtener filtros activos.  
  - Filtrar en cliente sin llamar al backend.  
- Métodos clave:  
  - `getTickets()` → acepta `limit/offset`.  
  - `getTicketsConFiltros()` y `getAllTicketsFiltered()` → aplican filtros según paginación.  
  - `exportarTickets()` → descarga Excel con tickets filtrados.  

---

## 🔁 Flujo de navegación

1. **Login** (`/login`) → `AuthService.login()` guarda sesión y redirige según rol/sucursal.  
2. **LayoutComponent** (AuthGuard) → sidebar con rutas hijas.  
3. **Tickets**: ver/filtrar/exportar; crear tickets dinámicos.  
4. **Administración** (AdminGuard): panel y permisos.  
5. **Inventario/Catálogos**: CRUD genérico y clasificaciones jerárquicas.  

---

## ⚙️ Configuración

### Variables de entorno
En `src/environments/`:

- `environment.ts` y `environment.prod.ts`:  
  ```ts
  export const environment = {
    production: false,
    apiBaseUrl: 'http://localhost:5000/api'
  };
