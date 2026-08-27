# Cartera histórica de Socios Vencidos

Socios Vencidos usa retención estructurada: el archivo fuente se elimina tras
una ingesta estructurada exitosa porque PostgreSQL constituye la fuente
histórica operativa del dominio.

Esta es una excepción exclusiva de `report_type_key=socios_vencidos`. Los
demás reportes Warehouse conservan la política general `raw first, structured
later`.

Cada fila de `socios_vencidos_cartera` representa un episodio identificado
por `(sucursal_key, pin, fecha_vencimiento_date)`. Un nuevo vencimiento del
mismo socio en otra fecha es otro episodio y no reemplaza el histórico.

El flujo operativo es:

1. Gasca descarga el XLSX temporal.
2. Warehouse conserva metadata y hash del upload.
3. El parser existente valida y normaliza las filas.
4. El repositorio crea el batch `SociosVencidosSnapshotORM` y hace upsert de
   cartera en una sola transacción.
5. Después del commit se elimina el XLSX y se registra
   `source_file_deleted_at`.

Un error de parsing o base de datos conserva el archivo. Un error de cleanup
no revierte datos committed y se reporta como `cleanup_warning`.

Los snapshots y filas snapshot anteriores permanecen para auditoría y
regresión. El seed `backend/scripts/seed_socios_vencidos_cartera.py` permite
poblar cartera de forma idempotente desde esas filas. El backfill mensual y
el sync diario reutilizan el orquestador, runner, upload, parser e ingestor
Gasca existentes; no implementan login ni scraper alternos.
