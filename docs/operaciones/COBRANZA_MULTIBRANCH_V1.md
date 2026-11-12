# Cobranza rechazada por sucursal — operación independiente V1

## Estado inicial y controles

**OFF por defecto.** Este paquete NO habilita envíos a nuevas sucursales, no cambia el piloto fijo del 12/11/2026 y no toca datos de producción. Para activar posteriormente se requiere aprobación de alcance, roster de sucursales, verificación técnica, merge y despliegue.

Se mantiene Gasca → Excel separado por sucursal → Warehouse/Nube, y luego:

1. Se comprueba fecha, identidad técnica global, cuatro flags de envío gobernado y límites explícitos.
2. Se lee la lista de sucursales autorizadas; se indexan los Excel de **todas las sucursales** para identificar teléfonos presentes en distintas sucursales. Los teléfonos ambiguos se excluyen de todas las campañas del corte, no se selecciona una sucursal arbitraria.
3. Por sucursal configurada: si falta Excel, estructura, teléfonos o excede el límite, se registra `SKIPPED` y continúa con las demás.
4. Una campaña por sucursal: `COBRANZA RECURRENTE RECHAZADOS - AAAA-MM-DD - SUCURSAL_CANON`. Conservar el **mismo corte** permite un conjunto lógico para reporte. Mantener nombre estable y metadata `isolated_branch_key` impide mezclarla con la campaña general o el piloto.
5. Cada campaña conserva preflight, presupuesto/cuota, aprobación gobernada, manifiesto, job único e idempotencia del worker. NO se realizan llamadas iVentas desde el scheduler.
6. Un job `REVIEW_REQUIRED` o una respuesta incierta afecta **únicamente esa sucursal**. El worker sigue procesando trabajos independientes en su siguiente ciclo. No se amplía la lista de rechazos confirmados ni se reintentan automáticamente.
7. Se escribe `warehouse_audit_logs.action='COBRANZA_BRANCH_AUTO'` con fecha, sucursal, motivo, campaña y job. Los jobs y children se consultan separadamente para estado final de proveedor.

## Variables (solo cuando se autorice activación posterior)

Conservar los cuatro flags de Campaign V2 y `COBRANZA_IVENTAS_TEMPLATE_ID=14` después de verificar bindings por sucursal. En `.env.docker`:

```dotenv
COBRANZA_IVENTAS_MULTI_BRANCH_ENABLED=false
COBRANZA_IVENTAS_MULTI_BRANCH_START_DATE=2026-11-13
COBRANZA_IVENTAS_MULTI_BRANCH_KEYS=VILLAS_DEL_REY,VILLA_VERDE,SAN_LUIS
COBRANZA_IVENTAS_MULTI_BRANCH_OPERATOR_ID=47
COBRANZA_IVENTAS_MULTI_BRANCH_MAX_RECIPIENTS_PER_BRANCH=1000
COBRANZA_IVENTAS_MULTI_BRANCH_MAX_DAILY_RECIPIENTS=10000
```

Estos valores son **solo un ejemplo**. No copiarlos como configuración final sin cotejar roster/canales, población/costos reales y permisos; nunca asumir que todas las sucursales de Ultra Gym están en esa lista. El flag debe permanecer `false` hasta nueva autorización. Fecha de inicio es incluyente y no puede ser el día del piloto ni anterior.

**Límites técnicos:** 1–30 sucursales explícitas sin repetidos; 1–10,000 destinatarios por sucursal; 1–100,000 diarios; el tope diario debe ser al menos igual al tope por sucursal. Si un tope falla, no se truncan listas.

## Seguimiento de faltantes (consulta sin enviar)

Auditoría de todas las sucursales, incluidas las omitidas antes de crear campaña:

```sql
SELECT created_at, details->>'business_date' AS dia,
       details->>'branch' AS sucursal, details->>'status' AS etapa,
       details->>'reason' AS motivo,
       details->>'campaign_id' AS campana,
       details->>'dispatch_job_id' AS job
FROM warehouse_audit_logs
WHERE action = 'COBRANZA_BRANCH_AUTO'
  AND details->>'business_date' = '2026-11-13'
ORDER BY created_at DESC;
```

Estado de trabajo y aceptación real (no confundir con entrega/lectura):

```sql
SELECT c.id AS campana, c.name, j.id AS job,
       j.status AS estado_job, j.stop_reason_code AS motivo,
       p.sucursal_canon, p.recipient_count, p.status AS estado_iventas,
       p.provider_campaign_id
FROM marketing_campaign_v2_campaigns c
LEFT JOIN marketing_campaign_v2_background_jobs j ON j.campaign_v2_id = c.id
LEFT JOIN marketing_campaign_v2_provider_campaigns p ON p.campaign_v2_id = c.id
WHERE c.name LIKE 'COBRANZA RECURRENTE RECHAZADOS - 2026-11-13 - %'
ORDER BY p.sucursal_canon;
```

La preparación/fila de auditoría `QUEUED` no acredita entrega. `SUBMITTED` acredita aceptación del lote por iVentas. Las estadísticas de entrega/lectura se consultan después mediante snapshots.

## Recuperación sin duplicados

- **Error anterior a enviar:** revisar archivo, plantilla, canal, cuota o permiso y preparar nueva operación gobernada, sin omitir gate ni forzar reintento ciego.
- **`PROVIDER_ERROR` con rechazo definitivo verificable:** usar vista previa + congelamiento de cohorte fallida de Campaign V2, autorización nueva y único envío autorizado. El origen no se reenvía.
- **`RECONCILIATION_REQUIRED` o job `REVIEW_REQUIRED`:** investigación manual en iVentas antes de cualquier intento; nunca crear automáticamente una segunda campaña para los mismos teléfonos.
- **`SUBMITTED`:** no reenviar. Capturar estadísticas separadamente.
- El scheduler marca el corte Gasca como completado aunque alguna sucursal quede pendiente. La operación manual de recuperación es distinta del job diario.

## QA requerido previo a despliegue

- Tests sintéticos: configuración OFF, fecha, operador, lista/límites, problemas por sucursal, duplicados entre sucursales, idempotencia por nombre y flujo de envío solo con preflight válido.
- CI focal de Cobranza, checks de seguridad, permisos y frontend.
- Revisión manual de roster real, capacidades y canales de iVentas.
- Despliegue en servidor con `git pull --ff-only`, `docker compose --profile scheduler up -d --build reports-scheduler`. No requiere nueva migración. El worker existente conserva su comportamiento y no se reconstruye por este paquete.
