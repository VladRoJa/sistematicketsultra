# Issue #856 — Fase A: configuración local de plantillas y canales iVentas

## Alcance

Permite administración desde **Campañas V2 → Configuración · plantillas y canales**, solo si el backend retorna `scope.can_manage_dispatch_config=true`, correspondiente a capacidad global. Este indicador es exclusivamente UX: POST/PUT/GET administrativos requieren de nuevo `_resolve_campaign_v2_dispatch_config_request` con JWT, capacidad y alcance global.

- Consultar plantillas activas e inactivas mediante `GET /api/marketing/campaigns-v2/dispatch/templates/admin`. El GET anterior sin `/admin` conserva su contrato para selección de templates de preflight (solo activos y opcionalmente por purpose).
- Crear/editar/desactivar plantillas con nombre exacto previamente aprobado en iVentas, etiqueta local, propósito, variables posicionales y selección explícita de `provider_channel_id` de bindings existentes y activos. La interfaz impide guardar con cero canales; backend lo revalida y exige fuentes de variable conocidas y posiciones consecutivas.
- Consultar y administrar bindings (sucursal del catálogo activo, ID exacto de canal, activo y predeterminado). El catálogo de sucursales sale del Track interno bajo permiso de configuración; **no** proviene de iVentas.
- Protección de historial: para plantillas ya referenciadas por provider children, no alterar nombre, propósito, variables, compatibilidad, metadata o proveedor. Es posible cambiar etiqueta; desactivar solo cuando no haya children pendientes, HELD, ambiguos ni en reconciliación. Para bindings referenciados tampoco puede modificarse identidad y no puede inactivarse si hay children no finalizados; no puede sustituirse un default con children pendientes.
- `[]` del modelo legacy conserva su semántica histórica de **todos los canales** para entradas existentes y scripts internos. Las rutas administrativas de fase A requieren canales no vacíos; no se realiza migración silenciosa de las plantillas heredadas.
- La pantalla informa que registro local ≠ existencia/aprobación por canal en iVentas.

## Exclusiones / no cambios

No hay GET de catálogo de plantillas a iVentas, POST al proveedor, importación de secretos, envíos, ajustes de kill switch, cambios a campañas congeladas ni modificaciones en la infraestructura de scheduler. **No se necesita Alembic**: las tablas actuales guardan el contrato.

No se proporciona cotización/precio, deduplicación automática, resolución de ambigüedades o segmentación por cuota en esta fase: corresponden a B, C y D dentro del mismo #856.

## Validación

- Tests backend de configuración y rutas, incluyendo 403, allowed provider, canales explícitos/inactivos, variables con gaps, conflictos con provider children.
- Tests puros Node del contrato Angular, typecheck TS y build de producción.
- Reutilizar CI `winback-oct-2026-ci.yml`; no emitir WhatsApps durante las pruebas.
- Verificar manualmente con credenciales admin en entorno de QA: listado inactivo, plantilla con canal seleccionado, confirmación de desactivar, 403 para usuario sin capacidad; abrir detalle de una campaña REACTIVATION y comprobar que plantilla activa guardada aparece en selector de preflight sin reinicio.
