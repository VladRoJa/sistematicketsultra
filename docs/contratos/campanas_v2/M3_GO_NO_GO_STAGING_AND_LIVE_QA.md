# M3 — Gate GO/NO-GO para QA controlada

**Estado: procedimiento preparado; NO hay autorización para enviar mensajes.**
Aplica a Campaign V2 M3. No reemplaza los contratos, el preflight backend ni el kill switch.

## 1. Separación de entornos

El repositorio no identifica un staging permanente independiente. Para uno nuevo es obligatorio:

- Servidor/instancia o proyecto Docker Compose independiente de producción.
- Base PostgreSQL **nueva y sin datos de socios reales**, credenciales propias, volúmenes, redes y puertos propios.
- Sin reutilizar `.env.docker`, JWT secrets, cookies, claves iVentas/Meta, ni directorios de archivos del servidor productivo.
- `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=false`; autocaptura de estadísticas provider desactivada hasta aprobar su uso aislado.
- Solo identidades de QA, CORS específico, acceso restringido y logs sin teléfonos/tokens.
- Las migraciones Alembic se aplican únicamente al esquema aislado, nunca a la base de producción.
- Antes de levantar servicios: comprobar host, DB, URLs de conexiones, volumen, entorno y kill switch; cualquier ambigüedad detiene el proceso.

La CI existente valida Flask/HTTP, PostgreSQL, el scheduler en contenedores independientes y su bucle en Compose temporal. **No es un staging permanente** ni avala conexiones a iVentas.

## 2. Prepara los dos archivos de QA

Conservar la cohorte congelada original y la lista enviable actual (supresiones incluidas). Revisarlas manualmente para confirmar que:

1. Los números pertenecen a personas/cuentas de QA que autorizaron recibir la prueba, nunca a socios reales de campañas masivas.
2. No hay duplicados ni sorpresas por sucursal, clasificación, tarifa o variables.
3. La cantidad y sucursal de cada batch coinciden con el preflight.
4. El canal iVentas y el template son los correctos para **cada sucursal**.
5. Los hashes SHA-256 corresponden a los archivos realmente revisados. Si se vuelven a generar, repetir toda la revisión.
6. Fecha y hora local, timezone y fingerprint son los del último preflight (si es programado).

No cargar a GitHub los XLSX, números, tokens ni el JSON privado de la revisión.

## 3. Revisión offline antes de pedir autorización

Archivo local (fuera del repositorio), con `preflight` de la API y `manifest` confirmado manualmente:

```json
{
  "preflight": {
    "campaign_id": 77,
    "provider": "IVENTAS",
    "mode": "IMMEDIATE",
    "schedule": null,
    "frozen_count": 3,
    "suppressed": {"blacklist": 1},
    "sendable_count": 2,
    "template": {"id": 10},
    "batches": [
      {"sucursal_id": 1, "sucursal_canon": "QA_A", "provider_channel_id": "qa-channel-a", "template_id": 10, "recipient_count": 1, "blocked_reasons": [], "ready": true},
      {"sucursal_id": 2, "sucursal_canon": "QA_B", "provider_channel_id": "qa-channel-b", "template_id": 10, "recipient_count": 1, "blocked_reasons": [], "ready": true}
    ],
    "blocked": {"missing_branch": 0, "missing_channel": 0, "missing_required_variable": 0, "invalid_phone": 0, "template_channel_mismatch": 0},
    "provider_campaign_count": 2,
    "dispatch_fingerprint_version": "campaign-v2-dispatch-v3",
    "dispatch_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "ready": true
  },
  "manifest": {
    "expected_campaign_id": 77,
    "expected_mode": "IMMEDIATE",
    "expected_sendable_count": 2,
    "max_qa_recipients": 2,
    "expected_provider_channels": {"QA_A": "qa-channel-a", "QA_B": "qa-channel-b"},
    "expected_template_id": 10,
    "reviewed_dispatch_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "frozen_export_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "sendable_export_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "frozen_export_reviewed": true,
    "sendable_export_reviewed": true,
    "qa_only_recipients_verified": true,
    "template_content_reviewed": true,
    "channel_ownership_reviewed": true,
    "fingerprint_reviewed": true
  }
}
```

**Estos valores son un ejemplo ficticio, no una evidencia real.** Para una campaña programada agregar `expected_timezone`, `expected_local_datetime` y respetar `schedule` serializado por backend.

Hashes locales, sin compartir el contenido del XLSX:

- PowerShell: `Get-FileHash -Algorithm SHA256 'ruta-del-archivo.xlsx'`
- Linux: `sha256sum ruta-del-archivo.xlsx`

Validar el archivo privado localmente desde `backend`:

```text
python tests/marketing/m3_qa_readiness_gate.py --input ruta-a-revision-privada.json
```

Salida permitida: `BLOCKED` con códigos o `READY_FOR_HUMAN_APPROVAL` con `send_authorized: false`. Se excluyen teléfonos, variables personales y tokens del resultado; si el archivo está corrupto, se bloquea.

## 4. No confundir revisión con autorización

**READY_FOR_HUMAN_APPROVAL no autoriza la llamada al proveedor.** Falta un visto bueno explícito para una campaña QA y una cohorte identificada, con fecha, sucursales, cantidades, canales y template. Después del visto bueno, Suite debe volver a realizar el preflight. Si blacklist, sendable, variables, channel, template, fecha o fingerprint cambian, anular aprobación anterior y detener todo.

Orden de pruebas live (solo tras autorización específica y kill switch controlado):

1. Una sucursal, 1 provider child, números de QA controlados; verificar idempotencia y que no existan reenvíos.
2. Dos sucursales, 2 provider children, cantidades pequeñas; revisar éxito parcial, reconciliación, snapshots, cost status y consolidado.
3. Ante timeout o estado ambiguo: `RECONCILIATION_REQUIRED`, **no crear de nuevo**.

Nunca usar campaña masiva como prueba inicial. Conservar siempre ambas exportaciones manuales.

## 5. Stop conditions (NO-GO)

Bloquear ante cualquier permiso incompleto, cohortes con destinatarios no verificados, fingerprints incompatibles, diferencias entre archivos y batches, estadísticas no confiables, channels o templates dudosos, costos asumidos como cero, secret leakage, cambios de fecha/hora, o falta de autorización.

**M3 permanece NO ACCEPTED** hasta completar el staging persistente y las pruebas live documentadas. Cualquier paso productivo requiere aprobación separada de merge/deploy.
