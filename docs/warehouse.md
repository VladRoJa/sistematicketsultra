Visión horizontal del flujo
1. Disparo

El flujo empieza en un endpoint interno de Suite.

Archivo: backend/app/routes/warehouse_internal_jobs.py
Función: create_gasca_report_job()

Qué hace

Recibe:

report_type_key
run_mode

Valida combinaciones permitidas y resuelve:

snapshot_kind

Ejemplos:

reporte_direccion + scheduled_daily → daily
reporte_direccion + scheduled_month_end_close → month_end_close
KPIs → siempre daily
2. Orquestación central

Ese endpoint llama al orquestador.

Archivo: backend/app/warehouse/services/gasca_job_orchestrator.py
Función: run_gasca_report_job()

Qué hace

Coordina todo el flujo:

valida inputs
llama al extractor de Gasca
crea el upload documental en Warehouse
si aplica, dispara la ingesta estructurada
Regla actual
reporte_direccion → sí intenta ingesta estructurada
kpi_desempeno y kpi_ventas_nuevos_socios → por ahora solo upload documental
3. Extracción desde Gasca

El orquestador no habla directo con el script.
Pasa por una cadena de adaptadores.

3.1 Adaptador de extractor

Archivo: backend/app/warehouse/services/gasca_extractor_adapter.py
Función: extract_gasca_report()

Hace dispatch por report_type_key y normaliza la salida a un artifact.

3.2 Bridge del script

Archivo: backend/app/warehouse/services/gasca_script_bridge.py
Función: extract_with_gasca_script()

Este archivo conecta Suite con el script real.
Puede trabajar así:

si el runner devuelve ruta/archivo, la usa
si no, busca el .xlsx reciente por carpeta + prefijo
3.3 Runner del script

Archivo: backend/app/warehouse/services/gasca_script_runner.py
Función: run_gasca_script_report()

Decide estrategia:

single_report
legacy_main
3.4 Implementación real actual

Archivo: backend/app/warehouse/services/gasca_legacy_main_runner_impl.py
Función: run_gasca_legacy_main()

Aquí el sistema ejecuta el main legado completo.

3.5 Script legado real

Archivo: backend/scripts/gasca_legacy_main.py
Función: main()

Este script:

hace login
baja los 3 reportes
guarda los archivos en carpetas conocidas

Y ya lo ajustamos para que cargue:

primero .env.local
luego .env
4. Upload documental a Warehouse

Cuando el extractor ya produjo el archivo, el orquestador intenta crear el upload documental.

4.1 Adaptador genérico

Archivo: backend/app/warehouse/services/warehouse_upload_creator.py
Función: create_warehouse_upload_from_artifact()

Este archivo no persiste por sí mismo.
Solo adapta el artifact a un contrato interno y delega.

4.2 Bridge hacia el servicio existente

Archivo: backend/app/warehouse/services/warehouse_upload_creator_existing_service.py
Función: create_warehouse_upload_via_existing_service()

Este puente está pensado para reusar Warehouse F1, no duplicarlo.

4.3 Estado real aquí

Aquí encontramos un hallazgo importante:

El upload F1 actual en warehouse_routes.py no es reusable todavía porque depende de:

request.files
request.form
JWT
periodo documental calculado en el route

Por eso definimos el siguiente paso limpio:
extraer esa lógica a un servicio reusable.

Archivo pendiente clave

Archivo nuevo propuesto: backend/app/warehouse/services/warehouse_document_upload_service.py
Función: create_warehouse_document_upload()

Este es el siguiente gran puente real que falta consolidar.

5. Lectura del upload documental

Para que la ingesta estructurada funcione, primero debe poder leer el upload creado en Warehouse.

5.1 Adaptador genérico

Archivo: backend/app/warehouse/services/warehouse_upload_loader.py
Función: load_warehouse_upload()

5.2 Implementación real SQL

Archivo: backend/app/warehouse/services/warehouse_upload_loader_sql.py
Función: load_warehouse_upload_from_db()

Este ya es un puente real a warehouse_uploads.

Qué hace
lee el registro por ID
detecta columnas reales compatibles
resuelve storage_path
devuelve:
report_type_key
original_filename
storage_path
captured_at

O sea: la lectura real del upload ya quedó aterrizada.

6. Ingesta estructurada de Reporte Dirección

Si el upload corresponde a reporte_direccion, el orquestador dispara la ingesta estructurada.

6.1 Servicio de ingesta

Archivo: backend/app/warehouse/services/reporte_direccion_ingestion_service.py
Función: ingest_reporte_direccion_upload()

Qué hace
carga el upload documental
valida que sea reporte_direccion
llama al parser
persiste snapshot + rows
resuelve canonicalidad
7. Parser puro de Reporte Dirección
Archivo

backend/app/warehouse/services/reporte_direccion_parser.py

Función

parse_reporte_direccion_snapshot()

Qué hace
abre el xlsx
valida layout por posición
saca business_date desde el header
ignora filas resumen T: y P:
devuelve:
cabecera parseada
rows
counts
issues
Qué no hace
no toca BD
no decide canonicalidad
no sabe nada de month_end_close
8. Persistencia estructurada
Archivo

backend/app/warehouse/services/reporte_direccion_repository.py

Función

persist_reporte_direccion_snapshot()

Qué hace
idempotencia por warehouse_upload_id
insert en reporte_direccion_snapshots
insert en reporte_direccion_snapshot_rows
consulta snapshot canónico actual del día
aplica switch de is_canonical
todo en una sola transacción
9. Regla de canonicalidad

Esta ya quedó cerrada a nivel de diseño y backend.

Regla actual

Para reporte_direccion:

puede haber múltiples capturas del mismo business_date
pero solo una queda con is_canonical = true
Casos
primer snapshot del día → puede quedar canónico
entra otro daily → no reemplaza automáticamente
entra month_end_close y el canónico actual es daily → lo reemplaza lógicamente
entra segundo month_end_close → no reemplaza automáticamente
Resultado

No duplicas Track en fin de mes, pero tampoco borras historia documental.

10. Tablas nuevas

La estructura ya fue diseñada y migrada.

Tabla cabecera

reporte_direccion_snapshots

Tabla detalle

reporte_direccion_snapshot_rows

Con qué objetivo

Separar:

metadata del snapshot
detalle por sucursal

Eso evita repetir is_canonical en cada fila.

11. Wiring runtime

Todo esto ya lo fuimos registrando en:

Archivo: backend/app/warehouse/__init__.py
Función: register_warehouse_runtime_hooks(app)

Y además lo conectamos en:

Archivo: backend/app/__init__.py
Función: create_app()

12. Flujo completo ideal, ya en una sola línea
Flujo horizontal final

POST /api/warehouse/internal/gasca-report-jobs
→ create_gasca_report_job()
→ run_gasca_report_job()
→ extract_gasca_report()
→ run_gasca_script_report()
→ run_gasca_legacy_main()
→ scripts.gasca_legacy_main.main()
→ bridge localiza archivo correcto
→ create_warehouse_upload_from_artifact()
→ bridge al servicio real de Warehouse F1
→ se crea warehouse_upload
→ load_warehouse_upload()
→ ingest_reporte_direccion_upload()
→ parse_reporte_direccion_snapshot()
→ persist_reporte_direccion_snapshot()
→ snapshot/rows en PostgreSQL
→ canonicalidad aplicada
→ Track puede leer solo el snapshot canónico

Dónde estamos exactamente ahorita

Estamos aquí:

Ya quedó armado
endpoint interno
orquestador
extractor/bridge/runner
integración con script legado
loader real de warehouse_uploads
parser
ingestor
repository
migración/tablas
wiring runtime
El siguiente cuello real

Todavía falta consolidar el puente de escritura al upload documental real de Warehouse F1.

O sea:

ya sabemos cómo leer warehouse_uploads
pero todavía no hemos extraído formalmente la lógica de creación documental del route actual a un servicio reusable
En una frase

Ya construimos casi todo el pipeline nuevo de punta a punta, y el punto más importante que falta para cerrar el circuito real es convertir el upload documental de Warehouse F1 en un servicio reusable que pueda usar tanto el route manual como el flujo interno de Gasca.