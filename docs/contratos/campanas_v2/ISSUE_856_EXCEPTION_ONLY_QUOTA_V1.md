# Campaign V2 — reglas automáticas de límites (v1)

Decisión operativa 2026-10-15: **no pedir cuotas diarias internas para
sucursales normales**. La expectativa de volumen de Meta/iVentas de 100 mil
diarios no se registra como un saldo verificado ni se convierte en un nuevo
bloqueo de la Suite.

## Únicas excepciones

- `INDEPENDENCIA` — canal iVentas `6a29c8ffe83fa20008b5a789`.
- `INSURGENTES` — canal iVentas `6a2aff2d555186000912586d`.

**250 posibles intentos de envío por canal**, cada uno de forma independiente,
en **ventana móvil de 24 horas**, contados conservadoramente sobre intentos
persistidos y reservas activas visibles para Suite Ultra. No es un límite
compartido de 250 entre las dos sucursales. Un mensaje aceptado pero no
entregado sigue consumiendo cupo preventivo, por seguridad, aunque iVentas
cobre solamente entregas. No se infiere cuánto cupo queda en Meta.

Las referencias de canal provienen de la migración
`f3c8a1b2d4e6_seed_campaign_v2_iventas_channels.py`. Se aplican las
restricciones si coincide la sucursal canónica **o el ID de canal**, para evitar
que cambios en etiquetas eliminen accidentalmente un límite.

## Aprobación y compatibilidad

- Preflight usa `SUITE_BRANCH_EXCEPTION_CAPS_V1` para nuevas aprobaciones.
- Todas las ramas requieren identidades válidas y siguen con la auditoría
  de reservas y bloqueo transaccional de canal, aun sin cuota numérica.
- Excepción superada/resultado incierto => bloqueo de esa rama. El operador
  puede documentar `HELD` para el lote especial y aprobar los demás. No
  se libera HELD ni se reintenta automáticamente.
- Aprobaciones anteriores guardaron el `basis` de su manifiesto. La
  materialización y autorización las siguen evaluando bajo ese contrato,
  nunca se recalculan retroactivamente con la regla nueva.
- La restricción sólo evalúa actividad **registrada en Suite**. Envíos
  externos por iVentas u otros sistemas son desconocidos.
- Autorización independiente, permisos backend, listas negras,
  confirmación humana, idempotencia, revisión de resultado incierto
  y ambos interruptores de envío siguen obligatorios.
- No se requiere migración ni modificación de datos históricos;
  no se envían mensajes como parte de esta implementación.

## Entrega

Deploy normal: commit->main, servidor `git pull --ff-only`,
reconstrucción backend y frontend, sin upgrade Alembic para este cambio.
Validar ambos flags apagados, endpoint de preflight sólo lectura para
la campaña #16 y que la vista informe «Sin límite interno diario».
El despliegue no autoriza enviar a Insurgentes/Independencia ni liberar
los lotes retenidos de campañas anteriores.
