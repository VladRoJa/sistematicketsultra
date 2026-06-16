# Contrato técnico-funcional

# Automatizaciones de reportes para Warehouse/Nube — Suite Ultra

## 1. Objetivo general

Crear una arquitectura separada para automatizaciones de reportes dentro de Suite Ultra, independiente del scheduler de Track, iniciando con el flujo automático de **Cobranza recurrente rechazados**.

El objetivo es que ciertos reportes externos, principalmente provenientes de Gasca u otras plataformas, puedan descargarse, procesarse, almacenarse y publicarse automáticamente en la Nube interna de Suite Ultra sin intervención manual.

---

## 2. Principio rector

Este módulo debe respetar el principio actual del Warehouse:

```text
Raw first, structured later
```

Todo reporte automático debe conservar:

* Archivo original descargado.
* Fecha de negocio.
* Fecha/hora de ejecución.
* Origen del reporte.
* Resultado procesado.
* Archivos generados.
* Trazabilidad de ejecución.
* Estado final: OK / ERROR.

La Nube debe mostrar el resultado final de forma simple para el usuario operativo.

---

## 3. Decisión arquitectónica

Se creará un scheduler nuevo e independiente:

```text
reports-scheduler
```

Este scheduler será diferente a:

```text
track-scheduler
```

### Responsabilidad de `track-scheduler`

```text
- Track Daily Mart
- Integraciones Track
- Cierres canónicos
- Snapshots operativos
- Procesos BI propios del Track
```

### Responsabilidad de `reports-scheduler`

```text
- Automatizaciones de reportes externos
- Descargas con Playwright
- Reportes Gasca
- Procesamiento de archivos descargados
- Publicación de resultados en Nube
- Registro de corridas automáticas
```

Motivo de la separación:

Si una automatización de reportes falla por login, descarga, cambio visual de Gasca o Playwright, no debe afectar el scheduler crítico de Track.

---

## 4. Primer flujo a implementar

## Cobranza recurrente rechazados

### Nombre funcional

```text
Cobranza recurrente / Rechazados
```

### Llave técnica

```text
report_type_key = cobranza_recurrente_rechazados
source_kind = gasca_auto
job_key = cobranza_recurrente_rechazados
```

### Comportamiento esperado

El flujo debe correr automáticamente todos los días en horario definido.

Proceso:

```text
reports-scheduler
→ ejecuta job de cobranza recurrente
→ entra a Gasca con Playwright
→ genera reporte del día
→ descarga XLSX original
→ guarda raw en Warehouse/Nube
→ filtra registros rechazados
→ elimina columna definida por negocio
→ separa archivos XLSX por sucursal
→ publica archivos en Nube
→ registra corrida
→ registra resumen
```

---

## 5. Alcance incluido

### 5.1 Scheduler nuevo

Crear un nuevo servicio Docker:

```text
reports-scheduler
```

Este servicio debe ejecutar:

```bash
python -m app.warehouse.scheduler.reports_scheduler_worker
```

Debe tener ciclo propio, logs propios y no depender de `track-scheduler`.

---

### 5.2 Job automático de cobranza recurrente

Crear job:

```text
backend/app/warehouse/jobs/cobranza_recurrente_rechazados_job.py
```

Responsabilidad:

```text
- Abrir Playwright.
- Iniciar sesión en Gasca.
- Navegar al reporte correcto.
- Configurar fecha.
- Descargar archivo XLSX.
- Guardar archivo raw.
- Procesar rechazados.
- Generar XLSX por sucursal.
- Registrar resultados.
- Publicar en Nube.
```

---

### 5.3 Publicación en Nube

Los archivos generados deberán ser visibles en la Nube interna.

Estructura visual esperada:

```text
Nube
└── Cobranza recurrente
    └── Rechazados
        └── 2026-06-16
            ├── RAW - Cobranza recurrente 2026-06-16.xlsx
            ├── JUSTO SIERRA.xlsx
            ├── VILLA VERDE.xlsx
            ├── SENDERO.xlsx
            └── ...
```

El usuario final no debe ver conceptos técnicos como:

```text
job
processor
scheduler
Playwright
raw storage
```

Solo debe ver los archivos listos para consulta o descarga.

---

### 5.4 Registro de corridas

Cada ejecución debe guardar trazabilidad.

Información mínima:

```text
- job_key
- report_type_key
- source_kind
- business_date
- started_at
- finished_at
- status
- raw_filename
- raw_storage_path
- total_rows
- total_files
- error_message
- metadata_json
```

---

### 5.5 Registro de archivos generados

Cada archivo por sucursal debe quedar registrado con:

```text
- run_id
- business_date
- sucursal_raw
- sucursal_canon
- filename
- storage_path
- rows_count
- mime_type
- created_at
```

---

## 6. Fuera de alcance

No se implementará en esta fase:

```text
- Botón manual para subir archivo.
- Pantalla para procesar archivo manualmente.
- Endpoint público para ejecutar el job desde frontend.
- Uso del .bat en producción.
- Playwright dentro de Gunicorn/backend web.
- Edición manual de archivos en servidor.
- Ejecución manual diaria por usuario.
```

Este flujo debe ser 100% automático.

---

## 7. Diseño backend

### 7.1 Archivos nuevos

```text
backend/app/warehouse/scheduler/reports_scheduler_worker.py
backend/app/warehouse/jobs/cobranza_recurrente_rechazados_job.py
```

Posibles archivos auxiliares:

```text
backend/app/warehouse/services/reports_scheduler_state_service.py
backend/app/warehouse/services/warehouse_report_artifacts_service.py
backend/app/models/warehouse_report_automation.py
```

---

### 7.2 Archivo: `reports_scheduler_worker.py`

Objetivo:

Crear el loop principal de automatizaciones de reportes.

Responsabilidades:

```text
- Crear app context.
- Leer variables de entorno.
- Verificar jobs habilitados.
- Verificar horario de ejecución.
- Evitar ejecuciones duplicadas del mismo día.
- Ejecutar jobs programados.
- Registrar errores.
- Limpiar sesión SQLAlchemy por ciclo.
```

Debe mantener al final de cada ciclo:

```python
db.session.remove()
```

Motivo:

Evitar conexiones colgadas en PostgreSQL, especialmente en procesos infinitos.

---

### 7.3 Archivo: `cobranza_recurrente_rechazados_job.py`

Objetivo:

Adaptar el script actual de cobranza recurrente para ejecución productiva dentro de Suite Ultra.

Debe incluir:

```text
- Login Gasca.
- Descarga automática.
- Lectura tolerante del XLSX.
- Filtro de estatus rechazado.
- Agrupación por sucursal.
- Exportación XLSX por sucursal.
- Publicación en Nube.
- Registro de corrida.
```

No debe incluir:

```text
- argparse como flujo principal.
- pause.
- winget.
- instalación de Python.
- instalación de dependencias.
- rutas locales fijas tipo salida/.
- credenciales hardcodeadas.
```

---

## 8. Diseño de base de datos

Se requiere migración Alembic.

### 8.1 Tabla propuesta: `warehouse_report_runs`

Registra cada ejecución automática.

Campos sugeridos:

```text
id
job_key
report_type_key
source_kind
business_date
status
raw_filename
raw_storage_path
total_rows
total_files
started_at
finished_at
error_message
metadata_json
created_at
updated_at
```

Estados posibles:

```text
RUNNING
OK
ERROR
SKIPPED
```

---

### 8.2 Tabla propuesta: `warehouse_report_artifacts`

Registra archivos generados por cada corrida.

Campos sugeridos:

```text
id
run_id
business_date
artifact_kind
sucursal_raw
sucursal_canon
filename
storage_path
mime_type
rows_count
metadata_json
created_at
```

`artifact_kind` para este flujo:

```text
cobranza_recurrente_rechazados_sucursal
```

---

## 9. Idempotencia

El job no debe generar duplicados si corre dos veces el mismo día.

Regla:

```text
job_key + business_date + status OK
```

Si ya existe una corrida OK del mismo día, el scheduler debe omitir la ejecución salvo que exista una bandera explícita de forzado.

En esta fase no se implementará forzado desde frontend.

---

## 10. Variables de entorno

Agregar variables:

```env
REPORTS_SCHEDULER_ENABLED=true
REPORTS_SCHEDULER_TZ=America/Tijuana
REPORTS_SCHEDULER_SLEEP_SECONDS=60

COBRANZA_RECURRENTE_ENABLED=true
COBRANZA_RECURRENTE_RUN_HOUR=07
COBRANZA_RECURRENTE_RUN_MINUTE=10

GASCA_USER=...
GASCA_PASS=...
GASCA_LOGIN_URL=...
GASCA_REPORTES_URL=...
```

Las credenciales deben vivir en `.env` del servidor, no en código.

---

## 11. Docker / producción

### 11.1 Nuevo servicio en `docker-compose.yml`

Agregar servicio:

```yaml
reports-scheduler:
  build:
    context: ./backend
  command: python -m app.warehouse.scheduler.reports_scheduler_worker
  env_file:
    - .env
  depends_on:
    - db
  profiles:
    - scheduler
  restart: unless-stopped
```

---

### 11.2 Dependencias backend

Agregar o validar en `backend/requirements.txt`:

```text
playwright
openpyxl
python-dotenv
tzdata
```

---

### 11.3 Playwright en Dockerfile

Agregar instalación de Chromium en el build del backend.

Posible instrucción:

```dockerfile
RUN python -m playwright install chromium
```

Si el contenedor requiere dependencias del sistema:

```dockerfile
RUN python -m playwright install --with-deps chromium
```

Esto debe validarse contra el Dockerfile real antes de aplicar.

---

## 12. Comandos operativos

### Levantar scheduler de reportes

```bash
docker compose --profile scheduler up -d reports-scheduler
```

### Ver logs

```bash
docker compose --profile scheduler logs -f reports-scheduler
```

### Reconstruir

```bash
docker compose --profile scheduler up -d --build reports-scheduler
```

### Detener

```bash
docker compose --profile scheduler stop reports-scheduler
```

---

## 13. Nube / frontend

### Alcance frontend inicial

No se creará una pantalla especial para procesar.

La Nube debe mostrar los documentos generados como archivos disponibles.

Vista esperada:

```text
Nube / Cobranza recurrente / Rechazados / Fecha
```

El usuario debe poder:

```text
- Ver archivos generados.
- Descargar archivo raw si tiene permiso.
- Descargar archivo por sucursal.
- Buscar por fecha.
- Buscar por sucursal.
```

---

## 14. Permisos

El backend debe ser la fuente real de permisos.

Este flujo debe respetar permisos de Warehouse/Nube.

Regla mínima:

```text
Solo usuarios con permiso Warehouse/Nube autorizado pueden ver archivos de cobranza recurrente.
```

Regla futura:

```text
Usuarios por sucursal solo deberían ver archivos de su sucursal.
Usuarios globales pueden ver todas las sucursales.
```

En esta fase, si Nube todavía no tiene permisos granulares por sucursal, se usará el permiso global existente de Warehouse/Nube.

---

## 15. Manejo de errores

Aunque el script actual sea estable, producción debe registrar errores de forma clara.

Errores esperados:

```text
- Login fallido.
- Gasca no disponible.
- Reporte no encontrado.
- Descarga no generada.
- XLSX vacío.
- Estructura inesperada.
- No hay filas rechazadas.
- Error al guardar archivo.
- Error al publicar en Nube.
```

Cada error debe marcar la corrida como:

```text
ERROR
```

Y guardar:

```text
error_message
finished_at
metadata_json
```

---

## 16. Logs

El scheduler debe escribir logs a salida estándar para Docker.

Ejemplo esperado:

```text
[reports-scheduler] iniciado
[cobranza_recurrente_rechazados] evaluando ejecución 2026-06-16
[cobranza_recurrente_rechazados] iniciando job
[cobranza_recurrente_rechazados] login Gasca OK
[cobranza_recurrente_rechazados] archivo descargado
[cobranza_recurrente_rechazados] archivos generados: 22
[cobranza_recurrente_rechazados] publicado en Nube
[cobranza_recurrente_rechazados] finalizado OK
```

---

## 17. Criterios de aceptación

El flujo se considera correcto cuando:

```text
1. Existe servicio Docker reports-scheduler.
2. reports-scheduler corre independiente de track-scheduler.
3. El job entra a Gasca automáticamente.
4. Descarga el XLSX del día.
5. Guarda el archivo raw.
6. Genera archivos XLSX por sucursal.
7. Registra corrida OK.
8. Registra artifacts generados.
9. Los archivos aparecen en Nube.
10. Los archivos se pueden descargar.
11. Si el job corre dos veces el mismo día, no duplica resultados.
12. Si falla, registra ERROR y no tumba el scheduler.
13. Track sigue funcionando aunque reports-scheduler falle.
```

---

## 18. Orden de implementación

### Cambio 1 — Crear base del scheduler

Archivo:

```text
backend/app/warehouse/scheduler/reports_scheduler_worker.py
```

Objetivo:

Crear proceso independiente que arranque, haga loop, lea configuración y limpie sesión DB.

Prueba:

```bash
docker compose --profile scheduler up -d --build reports-scheduler
docker compose --profile scheduler logs -f reports-scheduler
```

---

### Cambio 2 — Crear modelos y migración

Archivos:

```text
backend/app/models/warehouse_report_automation.py
backend/migrations/versions/<revision>_add_warehouse_report_runs.py
```

Objetivo:

Guardar corridas y artifacts.

Prueba:

```bash
flask db upgrade
```

Validación SQL:

```sql
select * from warehouse_report_runs order by id desc limit 5;
select * from warehouse_report_artifacts order by id desc limit 5;
```

---

### Cambio 3 — Integrar job de cobranza recurrente

Archivo:

```text
backend/app/warehouse/jobs/cobranza_recurrente_rechazados_job.py
```

Objetivo:

Adaptar script actual a Suite Ultra.

Prueba manual dentro del contenedor:

```bash
docker compose --profile scheduler exec reports-scheduler \
  python -m app.warehouse.jobs.cobranza_recurrente_rechazados_job
```

---

### Cambio 4 — Publicar artifacts en Nube

Archivos a revisar/modificar:

```text
backend/app/routes/warehouse_routes.py
backend/app/models/warehouse.py
backend/app/warehouse/services/*
```

Objetivo:

Que los archivos generados aparezcan en Nube con categoría y metadata.

Prueba:

```text
Entrar a Nube
→ Cobranza recurrente
→ Rechazados
→ Fecha actual
→ Descargar archivo por sucursal
```

---

### Cambio 5 — Activar horario automático

Archivo:

```text
backend/app/warehouse/scheduler/reports_scheduler_worker.py
```

Objetivo:

Ejecutar automáticamente el job a la hora configurada.

Prueba:

```text
Cambiar temporalmente hora/minuto en .env
Levantar reports-scheduler
Confirmar ejecución automática en logs
Confirmar archivos en Nube
```

---

## 19. Roadmap futuro

Este scheduler permitirá agregar nuevos reportes automáticos sin tocar Track.

Ejemplos futuros:

```text
- Cobranza rechazada.
- Cobranza recuperada.
- Reportes de socios.
- Reportes de pagos.
- Reportes operativos Gasca.
- Exportaciones periódicas para dirección.
- Documentos automáticos para sucursal.
```

Cada nuevo reporte debe integrarse como job independiente:

```text
backend/app/warehouse/jobs/<nombre_reporte>_job.py
```

Y registrarse en:

```text
reports_scheduler_worker.py
```

---

## 20. Regla de trabajo

No se debe editar directamente en servidor.

Flujo correcto:

```text
repo local
→ branch
→ cambios paso a paso
→ prueba local/contenedor
→ commit
→ push
→ pull servidor
→ docker compose up -d --build reports-scheduler
→ migraciones si aplica
→ validar logs
→ validar Nube
```

---

## 21. Resumen ejecutivo

Se implementará un nuevo servicio `reports-scheduler` para automatizaciones de reportes, separado de Track.

El primer job será **Cobranza recurrente rechazados**, 100% automático, basado en el script actual de Gasca + Playwright.

El flujo descargará el XLSX, conservará el raw, generará archivos por sucursal y los publicará en Nube, dejando trazabilidad completa en Warehouse.

No habrá carga manual ni botón de procesamiento.

La Suite ganará una nueva capa de automatización operativa sin contaminar el scheduler crítico de Track.





# Contrato técnico-funcional v1.1

# Automatizaciones de reportes para Warehouse/Nube — Suite Ultra

## Actualización posterior a revisión del repo

Después de revisar la estructura actual del repositorio, se confirma que la integración del nuevo `reports-scheduler` puede iniciar sin modificar dependencias ni Dockerfile.

El repo ya cuenta con:

```text
- Servicio backend con env_file: .env.docker
- Servicio track-scheduler con env_file: .env.docker
- Volumen compartido /uploads entre backend, frontend y scheduler
- Playwright instalado en requirements.txt
- Chromium instalado desde backend/Dockerfile
- openpyxl, python-dotenv y tzdata ya presentes en requirements.txt
```

Por lo tanto, la primera fase se reduce a crear el nuevo scheduler independiente y validar que arranque correctamente.

---

## 1. Ajuste sobre variables de entorno

En producción se reutilizará el archivo actual:

```text
.env.docker
```

No se creará un `.env` separado para `reports-scheduler`.

Los servicios quedarán alineados así:

```yaml
backend:
  env_file:
    - .env.docker

track-scheduler:
  env_file:
    - .env.docker

reports-scheduler:
  env_file:
    - .env.docker
```

Cada servicio leerá el mismo `.env.docker`, pero usará únicamente las variables que correspondan a su responsabilidad.

---

## 2. Variables nuevas para automatizaciones

Se agregarán variables con prefijo claro para evitar confusión con Track.

```env
REPORTS_SCHEDULER_ENABLED=true
REPORTS_SCHEDULER_TZ=America/Tijuana
REPORTS_SCHEDULER_SLEEP_SECONDS=60

COBRANZA_RECURRENTE_ENABLED=false
COBRANZA_RECURRENTE_RUN_HOUR=07
COBRANZA_RECURRENTE_RUN_MINUTE=10

GASCA_USER=...
GASCA_PASS=...
GASCA_LOGIN_URL=...
GASCA_REPORTES_URL=...
```

Durante la primera prueba, `COBRANZA_RECURRENTE_ENABLED` debe permanecer en:

```env
COBRANZA_RECURRENTE_ENABLED=false
```

Motivo:

Primero se validará que el nuevo scheduler levanta, mantiene ciclo, entra al app context y limpia sesión de base de datos sin ejecutar todavía el scraper de Gasca.

---

## 3. Docker / producción — ajuste confirmado

El archivo `backend/Dockerfile` ya incluye instalación de dependencias de sistema para Chromium y ejecuta la instalación del navegador de Playwright.

Por lo tanto, en la primera fase no se modificará:

```text
backend/Dockerfile
```

Tampoco se modificará inicialmente:

```text
backend/requirements.txt
```

porque ya contiene las dependencias necesarias para este flujo:

```text
playwright
openpyxl
python-dotenv
tzdata
```

---

## 4. Nuevo servicio Docker

Se agregará un nuevo servicio en:

```text
docker-compose.yml
```

Servicio:

```yaml
reports-scheduler:
  build:
    context: ./backend
  depends_on:
    - db
  env_file:
    - .env.docker
  environment:
    APP_ENV: "prod"

    REPORTS_SCHEDULER_ENABLED: "true"
    REPORTS_SCHEDULER_TZ: "America/Tijuana"
    REPORTS_SCHEDULER_SLEEP_SECONDS: "60"

    COBRANZA_RECURRENTE_ENABLED: "false"
    COBRANZA_RECURRENTE_RUN_HOUR: "7"
    COBRANZA_RECURRENTE_RUN_MINUTE: "10"

  command: python -m app.warehouse.scheduler.reports_scheduler_worker
  restart: unless-stopped
  init: true
  stop_grace_period: 120s
  networks:
    - backend-net
  volumes:
    - /home/adminrdp/sistematicketsultra/uploads:/uploads
  profiles:
    - scheduler
```

Este servicio reutiliza el mismo patrón operativo del `track-scheduler`, pero con responsabilidad separada.

---

## 5. Volumen de archivos

El nuevo `reports-scheduler` reutilizará el volumen actual:

```text
/home/adminrdp/sistematicketsultra/uploads:/uploads
```

Motivo:

Los archivos descargados desde Gasca y los archivos generados por sucursal deben quedar disponibles para backend y frontend/Nube.

La publicación final de archivos deberá quedar dentro de rutas controladas bajo `/uploads`, respetando la lógica existente del Warehouse/Nube.

---

## 6. Primer cambio real de implementación

La primera fase de implementación tendrá alcance mínimo.

Archivos a modificar/crear:

```text
docker-compose.yml
backend/app/warehouse/scheduler/reports_scheduler_worker.py
```

No se tocarán todavía:

```text
backend/Dockerfile
backend/requirements.txt
backend/app/models/warehouse.py
backend/app/routes/warehouse_routes.py
frontend/*
```

Objetivo de la primera fase:

```text
Crear reports-scheduler vacío
Levantarlo con Docker Compose
Validar app context
Validar loop
Validar logs
Validar db.session.remove()
Confirmar que no afecta track-scheduler
```

---

## 7. Worker inicial

Archivo nuevo:

```text
backend/app/warehouse/scheduler/reports_scheduler_worker.py
```

Responsabilidad inicial:

```text
- Crear app Flask con create_app()
- Abrir app_context()
- Leer variables REPORTS_SCHEDULER_*
- Ejecutar loop infinito
- Escribir logs a stdout
- Limpiar db.session.remove() en cada ciclo
- Responder correctamente a SIGTERM/SIGINT
```

En esta fase no ejecutará todavía el job de cobranza recurrente.

---

## 8. Prueba de aceptación de la primera fase

Comando:

```bash
docker compose --profile scheduler up -d --build reports-scheduler
```

Logs:

```bash
docker compose --profile scheduler logs -f reports-scheduler
```

Resultado esperado:

```text
[reports-scheduler] reports-scheduler iniciado
[reports-scheduler] Ciclo activo
```

Validación adicional:

```bash
docker compose --profile scheduler ps
```

Resultado esperado:

```text
track-scheduler     running
reports-scheduler   running
```

El nuevo scheduler debe poder detenerse sin afectar backend ni Track:

```bash
docker compose --profile scheduler stop reports-scheduler
```

---

## 9. Segunda fase posterior

Solo después de validar que `reports-scheduler` funciona correctamente, se implementará:

```text
backend/app/warehouse/jobs/cobranza_recurrente_rechazados_job.py
```

Esta segunda fase incluirá:

```text
- Adaptar script Playwright de Gasca
- Descargar XLSX del día
- Guardar raw en /uploads
- Generar XLSX por sucursal
- Registrar corrida
- Publicar archivos en Nube
```

---

## 10. Regla actualizada de implementación

El flujo queda dividido en fases obligatorias:

### Fase 1

```text
Crear reports-scheduler vacío y probar Docker.
```

### Fase 2

```text
Integrar job de cobranza recurrente sin programarlo automáticamente.
```

### Fase 3

```text
Activar ejecución automática por horario.
```

### Fase 4

```text
Publicar resultados en Nube con trazabilidad.
```

No se avanza a la siguiente fase si la anterior no está validada.

---

## 11. Resumen ejecutivo actualizado

El nuevo `reports-scheduler` se implementará como servicio independiente en Docker Compose, reutilizando `.env.docker`, la imagen del backend y el volumen `/uploads`.

La revisión del repo confirma que no es necesario modificar inicialmente `Dockerfile` ni `requirements.txt`, porque Playwright, Chromium y las dependencias de Excel ya están contempladas.

El primer cambio será controlado y no ejecutará todavía Gasca. Solo validará que el nuevo scheduler corre correctamente, limpia sesión de DB y no interfiere con Track.

Una vez validado, se integrará el job automático de Cobranza recurrente rechazados.
