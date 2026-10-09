# Campaign V2 #8 — continuación parcial sin duplicados

**Incidente:** en el submit inmediato de 13,999 destinatarios y 26 sucursales,
iVentas aceptó 11 children (5,850 contactos), devolvió `TEMPLATE_NOT_FOUND`
en `PASEO_LA_PAZ` (170 contactos, soporte
`bc-mv09582n-ly0gq0`) y dejó otros 14 children `READY` (7,979 contactos).

**Autorización:** el operador autorizó omitir Paseo La Paz y continuar los
14 children pendientes. No se autoriza reenvío de los 11 `SUBMITTED`.

## Alcance del hotfix

- Script especializado: `backend/scripts/resume_campaign8_pending.py`.
- Servicio: `backend/app/services/marketing_campaign_v2_partial_resume_service.py`.
- Sin API pública, sin cambios ORM o migraciones y sin ediciones manuales en servidor.
- Conserva los 11 IDs aceptados en iVentas. Valida el **ID exacto** de cada uno.
- Conserva el error original en Paseo La Paz: permanece en `PROVIDER_ERROR`,
  con `error_code=TEMPLATE_NOT_FOUND`, sin modificar el historial ni marcarla
  falsamente como aceptada. **Omitida de esta continuación** no significa un
  nuevo estado persistido `SKIPPED`.
- Reconstruye preflight en la misma ejecución, valida fingerprint
  `30881c47615db3b227eeea9a5d10ee079b798914657a95e744c6b852b1d1c25d`,
  template 1 y manifest exacto de 26 sucursales, conteos, provider IDs, canal,
  snapshot original, claves de idempotencia y estados.
- La primera discrepancia cancela el intento ANTES de cualquier HTTP.
- Cada READY -> SUBMITTING se confirma en DB antes de contactar proveedor;
  el resultado se confirma inmediatamente. Ante error 4xx, ambiguity o
  excepción, se detiene y se impide reejecutar con el mismo manifiesto.
- El kill switch global del backend web permanece en `false`; solo el
  proceso aislado de ejecución recibe `CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true`.

## Secuencia operativa (solo tras revisión, CI y merge)

1. Desplegar según procedimiento habitual (git pull + rebuild backend),
   sin cambiar env de docker compose ni activar el interruptor web.
2. Revisar migración y salud del backend; no hay migración nueva.
3. Dry-run **de solo lectura**:
   ```bash
   cd /home/adminrdp/sistematicketsultra
   docker compose exec -T backend python scripts/resume_campaign8_pending.py
   ```
   Esperado: `VALIDACION_REANUDACION = OK`,
   `YA_ACEPTADOS = 11 / 5850`, `PASEO_LA_PAZ_OMITIDO = 1 / 170`,
   `PENDIENTES_A_ENVIAR = 14 / 7979`, `OPERACION = DRY_RUN`.
4. Verificar desde operación que los 11 provider campaigns están registrados,
   y que los 14 canales pendientes tienen aprobada la plantilla; NO asumirlo
   solo por la allowlist local.
5. Con autorización existente y tras validación inmediata, un único submit real:
   ```bash
   docker compose exec -T -e CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true backend \
     python -u scripts/resume_campaign8_pending.py --apply
   ```
   NO repetir, aunque el terminal se desconecte.
6. Leer tabla de children / log de resultados. No reintentar un resultado
   `SUBMITTING`, `RECONCILIATION_REQUIRED` o `PROVIDER_ERROR`
   sin reconciliar evidencia contra iVentas.

## Resultado esperado si los 14 son aceptados

- `SUBMITTED`: 25 branches, 13,829 destinatarios **aceptados por proveedor**
  (entrega real individual aún pendiente de analytics).
- `PROVIDER_ERROR`: solo Paseo La Paz, 170 destinatarios no enviados.
- `READY`: 0.
- Agregado legacy `get_campaign_v2_submit_state().status` seguirá
  `PROVIDER_ERROR` por la fila omitida; esto NO indica que las 25 aceptadas
  hayan fallado. Se deben revisar children individualmente.
- El interruptor del backend web debe mantenerse apagado.


## Actualización: Paseo La Paz con plantilla ya cargada

El operador confirmó posteriormente que `invita_y_gana_4800` ya está
cargada en el canal iVentas de Paseo La Paz y solicitó incluir los 170
destinatarios originales. **No se modifica ni borra el error registrado.**

Por seguridad hay dos etapas distintas, con verificaciones y autorizaciones
operativas separadas antes de cada POST:

- **Etapa A**: ejecutar el hotfix existente `resume_campaign8_pending.py`
  para los **14 READY / 7,979**. Conservar el estado
  `PASEO_LA_PAZ = PROVIDER_ERROR` durante esta etapa.
- **Etapa B**: después de confirmar **25 SUBMITTED / 13,829** y que
  Paseo La Paz es el único `PROVIDER_ERROR`, ejecutar
  `retry_campaign8_la_paz.py` para **un único intento de 170**.
  La etapa B rechaza cualquier variación en los 26 children, en el
  fingerprint, los 11 provider IDs originales o los conteos.
  El rechazo determinístico previo (`TEMPLATE_NOT_FOUND`, supportRef
  `bc-mv09582n-ly0gq0`) se preserva en `retry_history_json`
  **antes de llamar a iVentas**. Se usa la infraestructura de auditoría
  de retry ya existente, sin nueva migración ni endpoint.
  Si no hay éxito verificable, no repetir la ejecución.

Importante: **ambos scripts son DRY_RUN por defecto**; no llamar nunca
`--apply` antes de revisar el dry-run correspondiente.

### Ejecutar dry-run por separado, siempre con PYTHONPATH

```bash
cd /home/adminrdp/sistematicketsultra

# Antes de iniciar etapa A
docker compose exec -T -e PYTHONPATH=/app backend \
  python scripts/resume_campaign8_pending.py

# Después de terminar etapa A y confirmar 25 SUBMITTED, antes de etapa B
docker compose exec -T -e PYTHONPATH=/app backend \
  python scripts/retry_campaign8_la_paz.py
```

Para el comando `--apply`, el interruptor se habilita solo en el
proceso aislado, con `-e CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true`,
además de `-e PYTHONPATH=/app`. Nunca alterar el .env del backend web.

Si la primera etapa falla o queda inconclusa, **NO intentar la segunda**.
La segunda etapa está programada para fallar cerrada si una sola de las
otras 25 campañas no está aceptada.

Resultado esperado si ambas etapas son aceptadas: **26 SUBMITTED / 13,999
aceptados por proveedor**. No equivale a entrega de 13,999 mensajes.
