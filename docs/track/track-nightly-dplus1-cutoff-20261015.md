# Track — captura completa del día D en D+1

## Decisión operativa propuesta
- Zona horaria: `America/Tijuana`.
- El periodo de venta del día D termina a las **23:59:59 de D**.
- La base nocturna de D se solicita **D+1 a las 00:15**.
- Si falla y no existe base `success/current`, reintento condicionado **D+1 a las 00:45**.
- Duración observada en 10 cierres del 05 al 14 de octubre de 2026: 1.5 a 3.6 minutos; el máximo observado no es garantía.
- SLA de disponibilidad de la base D ratificado por separado: D+1 a las **02:00** (sin alterar `track_base_sla_service.py`).
- El cierre definitivo con agregadoras sigue siendo **independiente y condicionado**, sin horario fijo.

## Cambio de fecha
El scheduler resuelve `track_date = fecha_local - 1 día` **al lanzar la base a las 00:15**. La misma fecha D se pasa al pipeline y a los extractores. Venta Total permite seleccionar mes D y fecha final D. KPI Desempeño y KPI Ventas Nuevos Socios reciben `GASCA_TARGET_BUSINESS_DATE=D`.

Ejemplos:
- 2026-10-16 00:15 captura el 2026-10-15.
- 2026-11-01 00:15 captura el 2026-10-31.
- 2027-01-01 00:15 captura el 2026-12-31.

La nueva programación NO vuelve a generar automáticamente bases históricas incompletas ni recierra versiones existentes. No altera canonicalidad del cierre con agregadoras.

## Despliegue y vigilancia
1. Mergear con CI verde; desplegar mediante `git pull` y `docker compose --profile scheduler up -d --build track-scheduler` **durante el día**, fuera del corte.
2. Revisar el heartbeat/schedule reportado por `track-scheduler`: `00:15` y `00:45`.
3. En la primera madrugada, verificar `track_daily_versions` (`version_type='base_nocturna_canonica'`, `track_date=D`, `status='success'`) y hora local de inicio después de medianoche.
4. Comparar Venta Total y nuevos domiciliados de D con el corte de finanzas; si hay diferencias revisar `source_snapshot_id` y registro concreto sin forzar sumas.
5. Evitar desplegar entre las 23:30 y las 00:45 para no solapar la transición con una ejecución en curso.

## Limitaciones
El scheduler consulta la hora por minuto y ejecuta tareas secuencialmente. Si queda ocupado o detenido durante la ventana exacta de 00:15, puede perder el disparo; el reintento de 00:45 solo aplica si existe base fallida, no a una base ausente. Fortalecer la recuperación de slots perdidos requiere una misión posterior con persistencia/idempotencia por `track_date`.

Los reportes del proveedor pueden tener demora de publicación. 15 minutos es margen operativo inicial, sujeto a observación de ventas de última hora en los próximos cierres.
