# SMS Gasca — pulso sintético cada 2 horas

## Alcance

La verificación envía un **SMS real** al mismo teléfono que el usuario mantiene
vinculado con Google Messages. Se ejecuta dentro del único
`gasca-sms-worker` cuando no hay solicitudes comerciales pendientes.

- No agrega procesos de Chrome ni toca el flujo Gasca/PIN.
- `GASCA_SMS_PULSE_ENABLED` tiene valor predeterminado **deshabilitado**.
- El destino privado se define en `GASCA_SMS_PULSE_PHONE` (10–15 dígitos).
- El mensaje de control tiene un identificador de slot UTC fijo.
- La reserva `STARTED` se persiste **antes** del intento. La unicidad de
  `slot_id` evita repeticiones tras reinicios. Si el resultado quedó
  ambiguo, no se reintenta el mismo slot.
- Un pulso nuevo se programa cada 7200 segundos (slots fijos de UTC);
  durante una cola comercial ocupada se pospone, **sin bloquear SMS clientes**.
- Verde significa que Google Messages mostró un mensaje enviado. No equivale
  a acuse de recepción de la compañía telefónica.

## Configuración y operación (solo tras CI / PR y migración aprobados)

El número no debe escribirse en Git, en código, en comentarios ni en capturas.
En el archivo privado `.env.docker` del servidor, introducir
`GASCA_SMS_PULSE_ENABLED=true` y
`GASCA_SMS_PULSE_PHONE=<número reservado para control>`, sin registrar el
valor literal en terminales compartidas. **No activar durante desarrollo.**

Aplicar primero la migración Alembic
`f22c10202601_gasca_sms_health_pulses.py` con backend actualizado. Antes de
recrear el worker verificar que no haya SMS en vuelo; seguir la ventana de
mantenimiento habitual. Reconstruir `gasca-sms-worker` después de modificar
`.env.docker` (solo `docker compose start` no renueva las variables).

El primer envío ocurre al detectar el primer slot libre de dos horas
y cola disponible. Se enviarán **hasta 12 mensajes por día** si siempre
existe disponibilidad. Considerar tarifa SMS del operador.

## Monitoreo

`GET /api/automation-control/sms-gasca/pulse` usa JWT y los mismos permisos
ADMICORP que el panel de Control de Automatizaciones.

- `UNKNOWN`: no hay registros de envío (por ejemplo, antes de activar).
- `RUNNING`: intento reservado hace menos de 10 minutos.
- `HEALTHY`: último intento enviado y aún dentro del intervalo + gracia.
- `FAILED`: último intento falló o quedó sin confirmación 10 minutos.
- `LATE`: último éxito tiene más de 2 horas y 15 minutos.

El endpoint nunca devuelve el número, un PIN ni el cuerpo del SMS.
La ausencia del heartbeat sigue siendo independiente.

## Aceptación

1. Migración arriba, tablas y permisos correctos en base sintética.
2. Worker actual consume solicitudes normales sin cambios; flag apagada no
   llama a Google Messages para pulsos.
3. PostgreSQL impide dos intentos del mismo slot y conserva registros al
   reiniciar. Fallo incierto no provoca reenvío ciego.
4. Angular muestra rojo ante fallo, verde al confirmarse un envío y gris sin
   datos; sin exponer destinatario.
5. Activación real separada, con aprobación del propietario y con
   confirmación de recepción en su propio teléfono si se desea.
