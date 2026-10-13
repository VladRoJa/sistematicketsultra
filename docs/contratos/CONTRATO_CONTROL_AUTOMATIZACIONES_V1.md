# Suite Ultra — Contrato funcional y técnico: Control de Automatizaciones V1

**Estado:** PROPUESTA PARA REVISIÓN — documental, sin autorización de implementación, despliegue ni ejecución manual.
**Fecha:** 2026-10-13
**Módulo:** Sistemas → Control de Automatizaciones
**Alcance:** schedulers, jobs, ejecuciones, salud, datos y solicitudes manuales.
**Arquitectura:** Angular + Flask + PostgreSQL + workers independientes (Docker Compose).

## 1. Antecedente y objetivo

Este contrato formaliza la propuesta conversada el 2026-10-08: una vista administrativa unificada para conocer qué procesos automáticos tiene Suite Ultra, cuándo deben correr, qué hicieron realmente, si fallaron, si los datos están al día y —cuando sea seguro— solicitar su ejecución manual.

No pretende sustituir los schedulers actuales por un proceso central ni iniciar trabajos largos en Flask. Debe respetar los módulos de Track, Warehouse, Marketing, Rutinas y mantenimiento, sin crear una segunda fuente de verdad para sus resultados.

**Principio rector:** distinguir 1) salud del worker, 2) resultado de cada ejecución, 3) frescura/completitud del dato de negocio. Un worker activo no implica un dato actualizado; una ejecución terminada no implica un corte funcional completo.

## 2. Inventario de partida verificado en main (no es prueba de estado en producción)

Servicios independientes presentes en docker-compose.yml:

| Worker | Jobs / responsabilidades detectadas | Programación de referencia |
|---|---|---|
| track-scheduler | previews Track; base nocturna; retry; solicitudes de cierre canónico; integración/exportación de agregadoras; retención Warehouse | previews en HH:00 (05–23); base 23:30; retry 00:30; retención 01:10; otras reglas dependientes del estado |
| marketing-scheduler | sincronización iVentas y Meta; captura opcional de estadísticas de Campaign V2 | 08:20, 12:20, 16:20, 20:20; retry 15 min; Campaign V2 opcional/deshabilitada por defecto |
| reports-scheduler | captura asistencia; fuentes de reactivación; resultados de reactivación; cobranza rechazada; Dirección; reportes comerciales diarios | asistencia 06:20; reactivaciones fuentes 09:00 y resultados 09:15 (defaults del código); cobranza 08:40 (Compose); reportes comerciales 01:20; Dirección según reglas específicas de su job |
| routine-control-scheduler | pipeline de Control de Rutinas por slots diarios | 09:20, 13:20, 17:20, 21:20 |
| ticket-attachment-cleanup | limpieza de adjuntos conforme a retención | 02:20, perfil maintenance |

Los horarios son **configuración del repositorio y valores por defecto**, no evidencia de que cada contenedor esté iniciado ni de que las variables de producción coincidan. El módulo mostrará configuración efectiva y estado observado, no únicamente literales de este contrato.

Cada job será una fila individual aunque comparta worker; p. ej., iVentas y Meta muestran estados diferenciados. Un worker puede estar sano mientras uno de sus jobs falle. Google Ads importado al Warehouse no debe presentarse como scheduler automático hasta que exista un job realmente configurado para ello. Los procesos no habilitados aparecerán DESHABILITADOS; no se ocultarán del inventario.

## 3. Alcance de producto

### 3.1 Resumen

Pantalla principal con conteos de jobs registrados, correctos, ejecutando, atrasados/incompletos, en error, deshabilitados y con estado desconocido; última actualización del propio panel y zona horaria America/Tijuana.

Tabla/tarjetas compactas por dominio: nombre, worker, próxima ejecución esperada, última ejecución real, duración, resultado, última fecha de negocio completa, estado de salud, dependencia o bloqueo y acciones disponibles. Filtros por dominio, worker, estado, fecha y búsqueda por nombre.

### 3.2 Detalle de un job

Ficha con descripción, propósito, fuente de datos, habilitación efectiva, horario en TZ local, prioridad, dependencias, últimos intentos y última ejecución exitosa, cronología de reintentos, fechas cubiertas y evidencia producida (run_id, snapshot_id, referencias de Warehouse/Track, contadores permitidos). No mostrar credenciales, tokens, teléfonos, archivos sensibles o trazas sin sanear.

### 3.3 Historial auditable

Separar cada solicitud de ejecución de sus intentos. Mostrar origen PROGRAMADO / MANUAL / REINTENTO / RECUPERACIÓN; persona solicitante si aplica; actor worker; parámetros tipados; corte/alcance; timestamps UTC con representación Tijuana; duración; resultado; errores sanitizados; decisiones de bloqueo; correlación con tablas existentes y enlaces internos a evidencias.

Histórico paginado, filtros por rango, estado y job. Los resultados de los jobs existentes se consultarán desde sus tablas reales; está prohibido inventar SUCCESS retrospectivos cuando solo haya logs parciales.

### 3.4 Botones de acción

- **Ejecutar ahora:** solicitar un job declarado manualmente habilitado e idempotente. No equivale a ejecutar inmediatamente: valida reglas y encola para el worker dueño.
- **Reintentar fallo:** conserva corte, parámetros y contexto verificable del intento fallido; genera nuevo intento ligado a la misma operación lógica.
- **Reprocesar:** operación distinta y más sensible; oculta/deshabilitada hasta certificarse por job una política de sustitución, snapshots y canonicalidad. Nunca reaplicar por defecto.

Cada botón muestra confirmación con job, business_date, alcance, dependencias, efectos y posibilidad de reutilizar un resultado. El estado inicial visible tras aceptar es SOLICITADO/EN_COLA; solo el worker puede marcar ÉXITO.

## 4. Semántica de estados (tres ejes obligatorios)

**Worker:** HEALTHY, DEGRADED, UNREACHABLE, DISABLED, UNKNOWN. Se calcula con latido persistido y plazo configurado; no depende de que el navegador vea un contenedor Docker. Sin instrumentación no se puede afirmar HEALTHY: usar UNKNOWN.

**Ejecución/solicitud:** QUEUED, WAITING_WINDOW, WAITING_DEPENDENCY, CLAIMED, RUNNING, SUCCEEDED, PARTIAL, FAILED, SKIPPED_ALREADY_DONE, REJECTED, CANCELLED_BEFORE_START, TIMED_OUT y UNKNOWN_LEGACY. No convertir PARTIAL en éxito; reintentos y recuperaciones quedan correlacionados.

**Frescura de datos:** UP_TO_DATE, INCOMPLETE, LATE, NOT_DUE, DISABLED, UNKNOWN. Cada adaptador define calendario de negocio, corte esperado y criterios de completitud. La evaluación considera la hora local y margen permitido; no señalar atraso antes del vencimiento del SLA del job.

Ejemplo obligatorio: Funnel Venta Nueva solo es completo en un día con intersección de cinco fuentes —iVentas, Meta, Venta Total, Ventas Nuevos Socios y KPI Desempeño—. Si cuatro alcanzan el 13/oct y una el 12/oct, mostrar último corte completo 12/oct, fuente faltante y NO marcar verde por tener el worker Marketing activo.

## 5. Política de priorización y seguridad de ejecución

1. Track conserva prioridad. Ningún botón manual puede evadir scheduler_priority_service.py.
2. Los jobs secundarios sujetos a prioridad solamente arrancan en ventanas seguras definidas por el servicio (actualmente HH:20–HH:44, horas 05–22), si no existe Track activo. Jobs nocturnos o con ventanas especiales usan su política específica; no reinterpretar arbitrariamente estos horarios.
3. Si un usuario solicita un job fuera de ventana, registrar WAITING_WINDOW con motivo/fecha estimada si puede calcularse; **no ejecutar a la fuerza**. Ante Track pending/running, WAITING_DEPENDENCY.
4. Un mismo job + corte de negocio + scope no puede correr concurrentemente. Locks transaccionales PostgreSQL, claim atómico y restricciones/índices de idempotencia; no bastan diccionarios en memoria.
5. La elegibilidad es por job/adaptador, no un endpoint que acepte nombre de función, shell command, ruta o argumentos arbitrarios.
6. Todos los jobs manuales deben soportar reintento seguro, idempotencia, comprobación del resultado existente, control de tiempo, límites de recursos y recuperación tras reinicio.
7. Los jobs que envían WhatsApp/SMS/campañas, cobran a terceros, eliminan datos, publican o sustituyen cierres canónicos o disparan otros efectos irreversibles son **solo observables por defecto**. No habilitarles ejecución manual con un switch genérico; requieren contrato específico y aprobación explícita.
8. Un endpoint manual ya existente en Track u otro módulo no constituye autorización automática para integrarlo: primero reconciliar su lock, autorización y semántica con la cola nueva.
9. Flask únicamente valida, persiste solicitud y devuelve 202 + request_id; jamás hace trabajo pesado en request Gunicorn. Los workers consumen mediante un adaptador explícito, con límites de concurrencia y conexión SQLAlchemy saneada con db.session.remove().
10. No se dará acceso al socket de Docker al backend ni posibilidad de reiniciar/activar/desactivar contenedores desde esta pantalla en V1.

## 6. Seguridad y permisos (política propuesta)

- Visualización: usuarios de ADMICORP y SISTEMAS mediante autorización explícita validada en backend. Ocultar menú a otros roles no es control suficiente.
- Solicitar ejecución manual: solo ADMICORP con permiso específico AUTOMATIONS_RUN; no derivarlo del rol genérico ADMINISTRADOR. Permiso distinto AUTOMATIONS_REPROCESS para reproceso futuro.
- Autorizar cada solicitud por acción, job y scope; resolver identidad del JWT en servidor, sin aceptar triggered_by del cliente.
- Registrar aceptación, denegación, duplicado, cambios de estado, intentos y decisiones de prioridad. Errores técnicos sanitizados al frontend; logs detallados solo en backend.
- Confirmación obligatoria en acciones manuales; límites/rate-limit, protección CSRF/Origin según esquema de autenticación realmente utilizado y validación estricta de entrada.
- Catálogo de acciones manuales permitido por defecto: vacío. La primera habilitación depende de auditoría y pruebas de cada adaptador.

Esta asignación de roles se presenta como **política inicial del contrato** y se ratifica antes de implementar M2.

## 7. Diseño técnico y persistencia

No crear un scheduler monolítico. Agregar una capa común de observabilidad/control, con registro estático versionado de job_key, worker_key, dominio, descripción, schedule_resolver, health_adapter, result_adapter, data_freshness_adapter, priority_policy y capacidades autorizadas. Una configuración no conocida no es inferida por nombre.

Nuevos recursos PostgreSQL, exclusivamente con migraciones Alembic:
- system_worker_heartbeats: worker_key, instance_id, last_seen_at, started_at, release_sha, metadata sanitizada. Debe soportar múltiples instancias y reportar ambigüedad en vez de falsear normalidad.
- system_job_runs: id, job_key, worker_key, business_date, scope_key, slot_key, trigger_source, request_id nullable, started_at, finished_at, status, attempt_number, duration_ms, upstream_run_ref, output_ref, counters_json, error_code, sanitized_error, created_at.
- system_job_requests: id, job_key, action, business_date, scope_key, typed_parameters_json, requested_by_user_id, idempotency_key, status, queued_at, claimed_at, finished_at, worker_key, denial_or_block_reason, last_run_id. Correlación y unicidad defensiva por operación lógica; no deduplicar solicitudes de distintos usuarios sin una respuesta explícita.
- system_job_audit_events: event_id, request_id nullable, run_id nullable, actor_user_id nullable, event_type, decision, reason_code, created_at, metadata_json sanitizada.

Definir CHECK constraints, FKs, índices por job/status/date y estrategia de retención de metadatos sin borrar auditorías críticas ni evidencias de Warehouse. Los registros nuevos no reemplazan ni reescriben las tablas del dominio; guardan referencias a ellas.

Estrategia de instrumentación incremental:
1. M1: adaptadores de lectura para datos reales existentes + indicadores UNKNOWN cuando no se pueda verificar; sin alterar ejecución de los workers.
2. M2: heartbeat y registro duradero de los jobs habilitados manualmente; cola en PostgreSQL, claim con FOR UPDATE SKIP LOCKED o mecanismo transaccional equivalente; leases/timeout, desbloqueo con reconciliación y no con simple reejecución automática ciega.
3. M3: alertas, escalamiento, métricas de cumplimiento y recuperación controlada.

Asegurar UTC en timestamps persistidos y business_date/calendarios en America/Tijuana. No exponer secretos de .env.docker ni credenciales del proveedor.

## 8. API propuesta (bajo /api, autenticación JWT y guards backend)

- GET /api/automation-control/summary → resumen de salud/frescura.
- GET /api/automation-control/jobs → catálogo, permisos/capacidades efectivas, filtros y paginación.
- GET /api/automation-control/jobs/<job_key> → configuración efectiva, dependencias y detalle.
- GET /api/automation-control/jobs/<job_key>/runs → historial paginado, errores saneados y evidencias.
- GET /api/automation-control/requests/<request_id> → avance de una solicitud manual.
- POST /api/automation-control/jobs/<job_key>/requests → body tipado: action, business_date, scope permitido, idempotency_key, confirmación. Responde 202 con request_id y estado, o 409 para conflicto real, o 403 ante denegación. No despacha trabajo pesado en HTTP.

Sin API genérica de comandos, docker exec, SQL arbitrario, reinicio de contenedores o modificaciones de horarios en V1. Las rutas no se registran ni publican hasta la fase que las implemente.

## 9. Frontend propuesto

Nueva ruta de administración protegida; entrada **Sistemas → Control de Automatizaciones**, separada de dashboards de negocio.

Angular standalone en archivos separados .ts / .html / .css. Reglas, acciones, permisos derivados, composición de estados, formateo y confirmaciones en TypeScript; HTML solo plantilla y bindings simples.

Resumen compacto y adaptable a 26+ sucursales sin tarjetas gigantes; lista agrupada por worker/dominio y detalle con tabs Estado, Ejecuciones, Fuentes y Auditoría. Los botones se deshabilitan mostrando el motivo concreto, no desaparecen sin explicación para perfiles autorizados de lectura. Refresh controlado con backoff para no saturar Flask/PostgreSQL.

## 10. Fases e hitos independientes

### M1 — Observabilidad (solo lectura)
- Auditoría del inventario: jobs reales, propiedad, schedules efectivos, tablas de evidencia, dependencias, salud y cobertura.
- Registro/catálogo, API GET, Angular resumen/detalle/historial y lectura de fuentes.
- Sin POST de ejecución ni cambios de comportamiento en schedulers productivos.
- PASS requiere demostrar NO false-green: worker sano + fuente incompleta = INCOMPLETE.

### M2 — Ejecución manual segura
- Migraciones y modelo duradero de solicitudes/intentos/locks/latidos.
- Cola consumida por worker dueño y adaptadores por job habilitados uno por uno.
- Autorización ADMICORP/acción/corte, confirmación, auditoría, ventanas y deduplicación bajo concurrencia.
- Piloto recomendado: un job no destructivo con prueba de idempotencia; no se habilita todo el catálogo por defecto.
- Probar crash/restart, dos peticiones concurrentes, reintento, Track activo, fuera de ventana, permiso denegado, resultado ya existente, timeout y falla parcial.

### M3 — Alertas y recuperación
- Alertas de worker caído, job fallido, corte atrasado, dependencia y SLA.
- Umbrales por job, notificación configurable, acuse e historial; sin reinicio automático ni reproceso destructivo implícitos.

Cada fase pasa por rama/PR, pruebas, revisión y merge por separado. Ninguna fase se considera desplegada por la existencia de este documento.

## 11. Criterios de aceptación contractuales

- AC01: inventario distingue worker de job y muestra config efectiva/sin dato; incluye jobs deshabilitados.
- AC02: salud worker, ejecución y frescura se evalúan por separado.
- AC03: Funnel presenta cinco fuentes y el último corte común, con causa de incompletitud.
- AC04: existe historial consultable y paginado con UTC/Tijuana, correlación, resultado y error sanitizado.
- AC05: sin evidencias el estado es UNKNOWN, nunca SUCCESS inferido de proceso vivo.
- AC06: rol no autorizado no consulta ni dispara acciones, incluso invocando API directa.
- AC07: POST de M2 devuelve 202 y request_id, no corre procesos en Gunicorn.
- AC08: dos peticiones concurrentes al mismo job/corte/scope no producen dos ejecuciones efectivas.
- AC09: solicitud secundaria fuera de ventana o con Track activo espera o se rechaza con motivo, sin saltarse prioridad.
- AC10: un FAILED puede reintentarse sin duplicar efectos ni alterar evidencia canónica indebidamente.
- AC11: reinicio del worker no pierde solicitud ni genera éxitos falsos; conserva auditoría.
- AC12: ningún job destructivo, de envío masivo o de publicación/cierre sensible expone acción manual sin adaptador y autorización propia.
- AC13: todos los cambios de esquema pasan Alembic; pruebas backend, Angular, permisos, migración y despliegue aislado.
- AC14: las pantallas y endpoints de este módulo no alteran el estado del Funnel por el mero hecho de consultarlo.

## 12. Exclusiones y decisiones pendientes

**Fuera de V1:** control del servicio Docker, cron editor, kill switch de terceros, reprocesamiento masivo, reconstrucción de Warehouse/Track por un clic, automatización genérica de campañas, orquestador único/Celery impuesto, editor de SQL, logs con PII y cambios a la programación productiva desde UI.

**Para ratificar al iniciar M2:** primer job habilitado manualmente; permisos definitivos por roles/custom; política y tiempo de retención; SLA/umbral por job; si ciertas tareas nocturnas no admiten jamás acción manual; cómo se reconcilian endpoints manuales existentes con el mismo lock. No bloquear M1 por estas decisiones.

## 13. Archivos objetivo estimados (no creados por el contrato)

- backend/app/routes/automation_control_routes.py: API segura y de solo lectura en M1; POST diferido a M2.
- backend/app/services/automation_control/: catálogo y adaptadores de salud/frescura; cola y dispatcher solo en M2.
- backend/app/models/automation_control.py y backend/migrations/versions/: persistencia nueva mediante Alembic (fase correspondiente).
- backend/app/warehouse/scheduler/track_scheduler_worker.py, backend/app/warehouse/scheduler/reports_scheduler_worker.py, backend/app/services/marketing_scheduler_worker.py, backend/app/routine_control/scheduler/routine_control_scheduler_worker.py y backend/app/services/ticket_attachment_cleanup_worker.py: instrumentación mínima progresiva, sin cambiar reglas en M1.
- frontend/src/app/automation-control/: componentes .ts/.html/.css y service separados.
- frontend/src/app/app.routes.ts y frontend/src/app/layout/layout.component.ts: ruta/menú protegidos por permisos reales.
- backend/tests/ y frontend tests: verificación de semántica, seguridad, idempotencia y no regresión.

## 14. Gobierno

Documento de **contrato propuesto**. No aprueba por sí solo habilitar jobs, endpoints POST, permisos productivos, migraciones, ejecuciones, modificaciones de workers ni despliegue. Implementación posterior requiere auditoría por job, revisiones, pruebas verdes y autorización operativa conforme a las reglas de Suite Ultra.
