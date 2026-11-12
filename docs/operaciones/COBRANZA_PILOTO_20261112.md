# Cobranza iVentas — piloto desatendido 2026-11-12

## Alcance y seguridad

- **Solo** fecha de negocio 2026-11-12 (America/Tijuana) y sucursal canónica `VILLAS_DEL_REY`.
- **No envía** fuera de ese día, incluso si el flag permanece activado.
- El scheduler existente descarga el reporte Gasca, lo separa y publica Warehouse/Nube.
- Tras publicación correcta, crea la campaña V2 **solo de Villas del Rey** y solicita despacho a través de los servicios gobernados existentes: preflight, cuotas, manifiesto, autorización, worker.
- No llama al proveedor desde el scheduler. El worker aislado ejecuta el envío. No reintenta envíos de resultado incierto.
- Fallos de preparación o autorización no vuelven a intentar el reporte exitoso ni alteran los archivos de otras sucursales. Revisar logs y campaña; intervención manual con autorización propia.
- Un máximo de **30 teléfonos**; si la cohorte supera el máximo, bloquea envío sin truncarla. No inventar un subgrupo arbitrario.
- El evento de la UI es solo lectura, para ADMICORP, y se actualiza al consultar cada minuto mientras la Suite esté abierta. Los estados `COMPLETED`/`SUBMITTED` significan aceptado por iVentas, no entregado.
- La ventana normal de reporte es 08:40 America/Tijuana. Si el archivo no existe/no está listo, se aplican los reintentos existentes del reporte.

## Variables para despliegue **posterior a merge y aprobación**

Configurarlas en `.env.docker` del servidor; no exhibir el archivo ni secretos:

```dotenv
COBRANZA_IVENTAS_TEMPLATE_ID=14
COBRANZA_IVENTAS_AUTO_SEND_ENABLED=true
COBRANZA_IVENTAS_AUTO_SEND_DATE=2026-11-12
COBRANZA_IVENTAS_AUTO_SEND_BRANCH=VILLAS_DEL_REY
COBRANZA_IVENTAS_AUTO_SEND_MAX_RECIPIENTS=30
COBRANZA_IVENTAS_AUTO_SEND_OPERATOR_ID=<ID real de un usuario técnico autorizado>
```

Requisitos preexistentes: `WAREHOUSE_AUTOMATION_USER_ID` válido, cuenta técnica activa con privilegios globales de Campaign V2 (manage, preflight, dispatch config, send), permisos de cuota y template/canal `ACTIVE_MEMBERS`, los cuatro flags de despacho habilitados en scheduler/worker, y worker actualizado y activo.

**No usar** un ID aleatorio ni asumir que el ID del rol ADMICORP es un ID de usuario. Verificar explícitamente usuario y rol antes de activar.

## Verificación sin emitir mensajes

- Revisión de los flags, identidad técnica y vínculo plantilla/canal.
- QA sintético sobre fecha distinta, sucursal distinta, límite excedido, acceso no-global y flags desactivados.
- La API de aviso: `GET /api/automation-control/cobranza/pilot-event` con JWT ADMICORP, responde `event: null` antes de congelar. Después devuelve etapa y contadores, **sin teléfonos**.

## Criterios de producción del 12/11

1. Reporte Gasca completo y Warehouse publicado.
2. Solo una campaña congelada para Villas del Rey, sin otras sucursales.
3. Destinatarios entre 1 y 30; plantilla #14 y canales verificables.
4. Trabajo duradero en `QUEUED`, `RUNNING`, `COMPLETED` o `REVIEW_REQUIRED` con auditoría.
5. Notificación en sesión ADMICORP al detectar la campaña, con estado distinguible; refresco al cambiar estado.
6. Captura separada de estadísticas iVentas para entrega y lectura; no inferir de `SUBMITTED`.

## Desactivar inmediatamente la **siguiente** ejecución

Cambiar `COBRANZA_IVENTAS_AUTO_SEND_ENABLED=false` y reconstruir **solo reports-scheduler** después de validar que no hay un despacho ya encolado. Este flag no cancela mensajes previamente aceptados o iniciados por el worker. Requiere procedimiento de parada gobernada si ya existe un job.

## Estado
Código preparado en rama aislada, sin activación ni envío en producción. No ejecutar el rollout hasta revisión/aprobación explícita.
