# Campañas V2 — Inventario masivo de plantillas iVentas

## Alcance

La Suite puede recibir **un único arreglo JSON de inventario** y revisar todas
las vinculaciones activas/predeterminadas del catálogo, sin solicitar 26 cargas
por separado. En «Plantillas, canales y tarifas», seleccionar una plantilla,
pulsar «Inventario masivo», pegar/importar el JSON, y «Revisar todos los canales».

La matriz distingue aceptada, sin evidencia, estado distinto e incompatible.
Un registro de estado distinto de `accepted` jamás se acredita. Una captura
parcial registra los canales aceptados y deja pendientes los demás.

## Reutilización y seguridad

- Un solo evento de operador con referencia, captura UTC y hash de inventario
  produce filas auditadas por **versión de plantilla y binding emisor exacto**.
- Evidencia válida 24 horas; requiere captura de menos de una hora.
- Se reutiliza entre campañas y no depende de la campaña original.
- Modificaciones de nombre/variables/media o identidad del emisor revocan el pase.
- Para campañas de recuperación fallida, se une a pruebas QA aceptadas y
  evidencia manual antigua. No elimina ninguno de esos controles.
- No habilita envíos ni reservas; el preflight, cuota y aprobación siguen intactos.
- No se guarda el inventario completo ni destinatarios, solo su SHA-256.
- El registro y vista previa exigen JWT, administración global y permiso de envío.
- API propia: POST `/api/marketing/campaigns-v2/dispatch/templates/{id}/inventory/preview`
  y POST `/api/marketing/campaigns-v2/dispatch/templates/{id}/inventory/register`.
- Alembic `m1232bulk110926` crea tabla de evidencia por canal; **despliegue
  requiere migración explícita**. No editar SQL en producción.
- Sin API autenticada de lectura de plantillas de iVentas confirmada. La vía
  de importación requiere un archivo o arreglo **real** observado en iVentas,
  no estados creados por el usuario. El botón revisa el inventario aportado,
  no consulta automáticamente 26 cuentas en iVentas.

## Aceptación

- Una carga muestra todos los emisores y distingue pendientes.
- Carga sin aceptación o con inventario contradictorio no concede permiso.
- Evidencia conservada tras reapertura de la Suite, reutilizable por otras campañas.
- Expiración, deriva de plantilla/canal, permisos y ausencia de huella bloquean.
- Ningún POST al proveedor desde esta funcionalidad.
