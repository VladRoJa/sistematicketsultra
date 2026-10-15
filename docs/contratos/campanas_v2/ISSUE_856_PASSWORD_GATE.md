# Campañas V2 — autorización por contraseña del operador

## Comportamiento

El endpoint de envío gobernado `POST /api/marketing/campaigns-v2/:campaign_id/dispatch/execute` exige `operator_password` (contraseña de inicio de sesión de Suite Ultra) **en cada solicitud de envío**.

Primero valida JWT, permisos `can_manage_dispatch_config` y `can_send_campaigns`, alcance global y **ambos kill switches**, después verifica la contraseña del **mismo usuario JWT** contra el hash ya existente. No hay una contraseña compartida, un interruptor de desbloqueo en sesión, ni credenciales persistidas, copiadas a otros servicios o registradas en logs. Un error rechaza la solicitud antes de construir el cliente iVentas.

El frontend requiere casilla y confirmación explícita `ENVIAR LOTE {id}`, y una contraseña no vacía. Borra el campo antes del POST y en cada actualización de la consola. El backend no acepta identidad de usuario o activación de switches desde el navegador.

Se conservan `manifest_digest`, aprobación de hasta 15 minutos, reservas, locks PostgreSQL, verificación del contacto, claim durable `IN_FLIGHT/SUBMITTING`, idempotencia, `READY/HELD`, y ausencia de reintentos automáticos. Un error ambiguo requiere conciliación manual, nunca reenvío automático.

## Activación inicial y parada de emergencia

Por diseño, **la contraseña no evita los kill switches globales**. Tras merge y despliegue aprobados, activar **una sola vez** en el entorno del backend `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true` y `CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=true`, y recrear el servicio backend para que Gunicorn lea ambos valores. Mientras ambos estén activos, las rutas de submit/retry legado web quedan bloqueadas por el modo gobernado. En adelante cada lote gobernado necesita un POST explícito con contraseña del operador autenticado y autorización vigente.

Para parar todos los envíos: poner `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=false` (preferentemente los dos switches en false) y recrear backend. Este kill switch no reemplaza permisos ni el control de sesión. No debe activarse sin una ventana operativa controlada.

**No habilitar flags en un despliegue inicial de código sin haber terminado CI, revisión y respaldo.** El cambio de código es sin migración; la activación global de runtime es una acción operativa independiente. No se modifica la aprobación vencida de la campaña #16 ni se renuevan automáticamente las de la #17. En caso de vencimiento, usar el flujo QA_MANUAL existente con una campaña nueva.

## Pruebas

En CI (sin llamadas iVentas reales): JWT ausente, permisos insuficientes, ambos switches OFF, contraseña faltante/incorrecta/ajena, contraseña válida con hash real y mocks de envío, errores inciertos, ejecución de un solo lote, Angular build y regresiones de Campañas V2.
