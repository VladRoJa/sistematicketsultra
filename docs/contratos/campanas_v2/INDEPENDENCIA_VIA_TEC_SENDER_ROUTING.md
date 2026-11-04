# Campañas V2 — INDEPENDENCIA como origen, TEC_MXL como canal emisor

## Contrato de negocio

La sucursal comercial de los contactos y sus KPIs permanece **INDEPENDENCIA**.
Solo cambia la cuenta/canal por la que iVentas realiza el despacho, a
**TEC_MXL**. El canal original de Independencia
`6a29c8ffe83fa20008b5a789` tiene la excepción interna de 250 posibles
intentos en 24 h. TEC_MXL usa el canal `6a86010a24aa9a00076c9800`.

No convertir ni reclasificar destinatarios a TEC_MXL. El envío por TEC no
implica acreditar ingresos, conversiones, citas, resultados ni sucursal a TEC.

## Operación

1. **No se activa con el merge.** Desde **Campañas V2 → Configuración →
   Plantillas y canales → Administrar canales**, editar el binding activo
   predeterminado de **INDEPENDENCIA** y elegir **Emisor: TEC_MXL**.
   El servidor solo permite la ruta explícita Independencia → TEC_MXL.
2. Antes de activar la ruta verificar externamente que el canal TEC existe,
   pertenece a la cuenta correcta y tiene acceso a la plantilla con
   variables/idioma aprobados y capacidad real suficiente. El inventario
   local de Suite **no es verificación online**. La incertidumbre de
   TEC_MXL #265 en campaña #41 sigue pendiente de conciliación: no se debe
   inferir que hay cupo ni que su campaña no existió.
3. Congelar una **nueva** campaña (estándar, Excel o derivada de HELD).
   En ese instante se guarda `audience_definition_json.dispatch_channel_routing`
   con IDs del binding de origen y del emisor, sucursal emisora y canal.
   Las campañas previamente congeladas siguen sin ruta alterna.
4. El preflight muestra **Sucursal de origen = INDEPENDENCIA** y
   **Emisor = TEC_MXL**. El lote conserva `sucursal_id` y
   `sucursal_canon` originales. `channel_binding_id` y
   `provider_channel_id` representan el canal real TEC. La solicitud y el
   nombre externo incluyen la identidad de origen y el emisor.
5. La aprobación habitual de presupuesto, capacidad, plantilla, alcance,
   cuotas, fingerprint y autorización de envío sigue siendo obligatoria.
   El cap local 250 se aplica al **canal realmente emisor** solo en una ruta
   congelada y verificada; una sustitución de provider_channel_id sin
   snapshot NO elimina el cap de Independencia. No se supone una nueva cuota
   real para TEC_MXL a partir de la política local.
6. Si se desactiva o altera cualquiera de los bindings, se revoca la ruta,
   o cambia el canal/plantilla, el preflight falla cerrado. No modificar
   historia ni mandar nuevamente sin revisar el nuevo estado.

## Auditoría

El detalle de campaña, el preflight, el snapshot de envío y el estado de
provider children conservan ambas dimensiones:
- **origen comercial:** `sucursal_canon=INDEPENDENCIA`;
- **emisor real:** `send_via_sucursal_canon=TEC_MXL`,
  `provider_channel_id=6a86010a24aa9a00076c9800`.

## Pruebas de aceptación

- Sin configuración, el flujo y huella de los envíos actuales no cambian.
- Nueva cohorte de Independencia: el child sigue atribuido a Independencia,
  transportado por TEC con binding distinto y sin cap Suite de 250 de
  Independencia. No se afirma capacidad real de Meta/iVentas.
- Coexistencia de destinatarios TEC_MXL propios en la misma campaña: se
  mantiene cada origen sin mezclar cohortes y las reservas se agrupan por
  proveedor/channel ID real.
- Cambio/revocación de binding, ausencia de emisor o intento de usar
  Insurgentes: bloqueo antes del POST.
- Roles sin configuración global: 403 por endpoint actual.
- Sin cambios de esquema, sin Alembic, sin WhatsApps desde las pruebas.
