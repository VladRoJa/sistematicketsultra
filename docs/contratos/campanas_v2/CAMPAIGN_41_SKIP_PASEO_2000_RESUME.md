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
- Verifica cuotas actuales de todos los pendientes y después de cada lote
  antes de cualquier POST, y reutiliza el claim durable
  `READY -> SUBMITTING`, gate de contactos y persistencia de resultados.
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
