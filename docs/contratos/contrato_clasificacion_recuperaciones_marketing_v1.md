# Suite Ultra — Clasificación de recuperaciones de Marketing V1

## Objetivo

Separar el resultado técnico de una campaña de la clasificación comercial utilizada por UltraGym.

Una campaña puede recuperar a un socio vencido. Esa recuperación se clasifica después como **Renovación** o **Reactivación** según el mes calendario del vencimiento y del pago que produjo su regreso.

## Términos

### Recuperación atribuida

Socio incluido en una campaña `SENT` que posteriormente cumple la atribución definida en el contrato de Reactivaciones V1.

El estado técnico persistido continúa siendo `REACTIVATED` por compatibilidad del motor de atribución. En UI y métricas de negocio se muestra como **Recuperado**.

### Renovación

Una recuperación es `RENOVACION` cuando la fecha de vencimiento y la fecha del pago que recuperó al socio pertenecen al mismo mes calendario.

Ejemplo:

- vencimiento: 2026-09-05
- pago: 2026-09-18
- resultado: `RENOVACION`

### Reactivación

Una recuperación es `REACTIVACION` cuando la fecha de vencimiento es anterior al primer día del mes calendario en el que ocurrió el pago.

Ejemplo:

- vencimiento: 2026-08-31
- pago: 2026-09-18
- resultado: `REACTIVACION`

La misma regla aplica al cambio de año:

- vencimiento: 2026-12-31
- pago: 2027-01-02
- resultado: `REACTIVACION`

## Datos inconsistentes

Si falta la fecha de vencimiento, falta la fecha del pago o el vencimiento resulta posterior al pago, la recuperación se conserva como atribuida pero queda **sin clasificar**.

No se fuerza Renovación ni Reactivación cuando la evidencia no es suficiente.

## Persistencia

La clasificación no se guarda en una columna adicional.

Se deriva de:

- `MarketingReactivationCampaignRecipientORM.fecha_vencimiento_date`
- `MarketingReactivationCampaignRecipientOutcomeORM.reactivated_at_local`

Esto evita duplicar información derivada y permite corregir la clasificación automáticamente si se corrige la evidencia fuente.

## Winback

La clasificación no modifica las reglas ni segmentos de `WINBACK`.

Winback sigue siendo una estrategia de campaña. Renovación y Reactivación son clasificaciones del resultado obtenido.

## Métricas de resultados

El panel de resultados muestra:

- Enviados
- Recuperados
- Renovaciones
- Reactivaciones
- Conversión
- En seguimiento

La conversión se mantiene como:

`Recuperados / Enviados`

`reactivated` se conserva en la respuesta API como alias técnico compatible del total recuperado; las nuevas interfaces utilizan `recovered` para el lenguaje de negocio.
