# Campaña #41: continuar sin PASEO_2000 (#255)

## Alcance autorizado

El operador solicitó omitir PASEO_2000 de la continuación y conservar los
7,994 destinatarios sin volver a intentar el envío rechazado por iVentas.
El rechazo es `TEMPLATE_NOT_FOUND`, HTTP 400, referencia
`bc-mw1c1why-phq041`, plantilla `promos_noviembre_v`, canal
`6a299740e83fa20008b59c9a`.

Esta es una recuperación excepcional y acotada a campaña #41. **No**
constituye una funcionalidad general de retry y no cambia el proceso
gobernado por defecto. No crea endpoints, muta aprobaciones, altera el
manifiesto ni cambia el estado del lote rechazado. Evita que cualquier
`SUBMITTED` vuelva a enviarse.

## Revisión técnica

- `backend/scripts/resume_campaign41_ready.py` lee el plan, la aprobación,
  el digest, la ejecución y, si existe, su mandato de background.
- Exige el error #255 y la aceptación de un prefijo continuo de lotes,
  seguida por un sufijo intacto `READY`, sin otros errores.
- Compara *todos* los lotes contra el manifiesto aprobado, los snapshots
  exactos y las claves de idempotencia con el servicio existente de
  continuación parcial. Verifica la identidad del canal.
- Verifica cuotas actuales de todos los pendientes en el dry-run y, durante
  `--apply`, en una transacción nueva para cada lote bajo los locks de
  contactos, campaña, aprobación, ejecución, job y cuotas. Registra
  `READY -> SUBMITTING` y confirma la transacción ANTES de contactar a iVentas.
- La continuación **gobernada** utiliza
  `marketing_campaign_v2_governed_recovery_service.py`; no utiliza la
  transición heredada `continue_ready_children()`, que el backend prohíbe
  correctamente para las campañas con aprobación gobernada.
- Se detiene ante cualquier error, cuota vencida, resultado ambiguo,
  divergencia de estado o de proveedor.
- No reautoriza ni reintenta el #255; la ejecución original continúa
  `REVIEW_REQUIRED`, precisamente porque el error original se conserva.
- Solo el proceso CLI de envío habilita sus switches; no habilitar flags
  en el backend web por este procedimiento.

## Pruebas focales en rama

```bash
cd backend
pytest -q tests/marketing/test_resume_campaign41_ready.py
# La prueba PostgreSQL sintética corre únicamente en CI (quota_ci).
```

CI integral antes de merge. No considerar una ejecución de CI como
evidencia de cambios aplicados en producción.

## Procedimiento controlado tras PR, CI, revisión y despliegue autorizados

**No ejecutar `--apply` hasta ver el dry-run y comprobar que todos los
READY son exactamente los lotes que se quiere enviar.**

```bash
cd /home/adminrdp/sistematicketsultra

# Solo lectura; no usa API de iVentas:
docker compose exec -T -e PYTHONPATH=/app backend \
  python scripts/resume_campaign41_ready.py
```

Salida esperada: `CAMPAÑA = 41`, `OMITIDO = PASEO_2000 | #255 | 7994 |
PROVIDER_ERROR`, `CUOTA_ACTUAL = VALIDADA`, listado de `READY`,
`ENVÍO_REAL = NO EJECUTADO`. Los conteos de lotes restantes se obtienen
de la base real, **no deben adivinarse**.

Tras validar el listado y obtener autorización operativa específica para
el envio real, ejecutar **una sola vez**:

```bash
docker compose exec -T \
  -e PYTHONPATH=/app \
  -e CAMPAIGN_V2_PROVIDER_SEND_ENABLED=true \
  -e CAMPAIGN_V2_GOVERNED_DISPATCH_ENABLED=true \
  backend python -u scripts/resume_campaign41_ready.py \
  --apply --confirm CONTINUAR_41_SIN_255
```

No interrumpir deliberadamente ni ejecutar en paralelo. Si cae el terminal,
hay timeout, o un lote devuelve error, **no repetir `--apply`**. Consultar
el estado persistido, los IDs externos aceptados y los logs; los siguientes
`READY` requieren un nuevo diagnóstico. El usuario debe comprobar en
iVentas la aceptación por canal; `SUBMITTED` no equivale a entregado.

## Criterios de aceptación

1. PASEO_2000 #255 conserva `PROVIDER_ERROR` y su evidencia intacta.
2. Los anteriores `SUBMITTED` conservan sus `provider_campaign_id`.
3. Solo los originales `READY` posteriores a #255 pueden salir.
4. Ningún POST ocurre con flags apagados, capacidad insuficiente o cambio
   de ejecución, aprobación, fingerprint o snapshot.
5. Cada aceptación y error conserva trazabilidad; en caso de resultado
   incierto, se suspende la continuación.
6. No hay cambios de esquema, merge ni despliegue implícitos.


## Incidente #1211 y corrección PR #1212

El intento de envío después del PR #1210 se detuvo en
`_transition_ready_to_submitting`, con el mensaje
`Transición heredada bloqueada para aprobación gobernada`.
Fue un rechazo local *antes de HTTP*; se consultó PostgreSQL y se verificó
que #256–#268 permanecieron READY, sin timestamps ni provider IDs.

La corrección usa un mecanismo de recuperación gobernada explícito con
permisos globales vigentes, kill switches activados **solo en el proceso
de envío**, controles de la ejecución y mandato originales en
`REVIEW_REQUIRED`, validación de snapshots y cupo actual bajo advisory
locks, claim durable antes del provider y rechazo de cualquier replay.

La ejecución #41 y el mandato background original permanecen
`REVIEW_REQUIRED` (se conserva el error #255). El progreso correcto
de recuperación se verifica por los provider children y sus
`provider_campaign_id`, no por la etiqueta de la ejecución original.

La recuperación se prueba con PostgreSQL sintético e iVentas simulado;
no es evidencia de entrega. Si un nuevo envío falla o se interrumpe,
**no repetir `--apply`**. Revisar primero el lote y conciliación externa.


## Segunda interrupción — 2026-11-04, SEND_CUL #261

El envío real con el paquete #1212 sí aceptó los lotes #256–#260:
PASEO_LA_PAZ (3,604), SANTA_FE (4,723), SAN_ISIDRO_CUL (3,152),
SAN_LUIS (3,238), SEND_CHIH (2,845); total 17,562 adicionales.
Su identidad externa está congelada en el script y debe coincidir con
la persistida. El lote #261 SEND_CUL (3,402) fue rechazado
`TEMPLATE_NOT_FOUND`, referencia `bc-mw2eakos-r7lxsj`.
La ejecución se detuvo deliberadamente sin intentar #262–#268.

La segunda continuación requiere aprobación operativa **expresa** para
omitir también SEND_CUL. No resetea/reintenta #261 ni #255. El nuevo
dry-run debe arrojar 12 lotes SUBMITTED / 43,266 destinatarios,
2 rechazados con evidencia íntegra, y 7 READY / 23,755 destinatarios.
Si cualquier fila, actor, external ID, snapshot, orden, flag o capacidad
cambia, la continuación se bloquea.

No ejecutar el anterior comando `--confirm CONTINUAR_41_SIN_255`.
Cuando se autorice el nuevo envío, debe utilizar el nuevo token de
confirmación `CONTINUAR_41_SIN_255_261` y mantenerse restringido a
la misma ruta controlada, una sola vez y con una revisión manual antes.
El preflight local no certifica existencia de plantilla en iVentas.


## Tercera interrupción — TEC_MXL #265, 2026-11-04

El segundo tramo aceptó #262 SEND_MXL (5,157; provider `6aeb742601d5f90009b03954`),
#263 SEND_SALTILLO (4,870; provider `6aeb746901d5f90009b03dbb`)
y #264 STA_CATARINA (2,964; provider `6aeb74abd85a8f00082012fa`).

#265 TEC_MXL: 3,135, canal `6a86010a24aa9a00076c9800`,
`RECONCILIATION_REQUIRED` / `TRANSPORT_CONNECTIONERROR`;
`submit_started_at = 2026-11-04 10:09:47.962 -0800`,
sin respuesta ni provider_campaign_id. El operador revisó manualmente el panel
de iVentas y no encontró la campaña `Winback ene 25 a oct 26 · TEC_MXL`.
**La ausencia en el panel NO es prueba suficiente de no creación.**

La tercera continuación es exclusivamente para los tres lotes no intentados:
#266 TLALNEPANTLA (1,511), #267 VILLAS_DEL_REY (3,731),
#268 VILLA_VERDE (2,387): 7,629 destinatarios. Verifica en cada claim
los quince aceptados, ambos rechazos deterministas, la cuarentena intacta de
#265 y los tres READY; no modifica ni reintenta #265. Se vuelven a evaluar
permisos, snapshots, cuota vigente y bloqueo de contacto.

**Estado esperado en dry-run**: 15/56,257 SUBMITTED; 2/11,396 rechazados;
1/3,135 en CUARENTENA; 3/7,629 READY; `CUOTA_ACTUAL = VALIDADA`.

No reutilizar tokens antiguos de confirmación.
La nueva confirmación (solo tras aprobación expresa de envío real y
verificación del dry-run) será `CONTINUAR_41_DESPUES_265_CUARENTENA`.
Si un lote nuevo termina en un resultado distinto de SUBMITTED, detener de
nuevo y NO volver a ejecutar `--apply` a ciegas.

La cuarentena #265 requiere evidencia definitiva del proveedor para
conciliación auditada posterior: campaña encontrada con identidad externa,
o confirmación documentada del proveedor de no creación.
Sin evidencia no registrar una resolución ni reenviar #265.
