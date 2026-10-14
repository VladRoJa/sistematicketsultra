# M1-F6 — Etapa 3: vigencia efectiva del universo Track

## Dictamen de fuentes (auditoría 14/10/2026)

- `sucursales.operational_status` describe el estado operativo actual, no
  desde qué fecha una sucursal era analíticamente elegible para Track.
- `openings.actual_opening_date` acredita fecha de apertura **operativa**,
  no inclusión, exclusión o cambio de `track_branch_catalog.is_track_active`.
- `track_branch_catalog` no tiene vigencias históricas. La captura de
  M1-F6/2 solo demuestra qué universo vio el builder al generar una
  determinada versión, no cuál debió estar activo para un D histórico.
- **No es lícito reconstruir retrospectivamente el universo Track con esas
  fuentes.** Los historiales 13/10 y anteriores siguen UNKNOWN.

## Propuesta de fuente autoritativa

El universo Track **por día** se ratifica mediante una decisión corporativa
del propietario del dato (BI + Operaciones). Queda separada de la operación
del catálogo y de `openings`; no se deriva de ellas sin aprobación.

`track_roster_effective_epochs`:
- `effective_from`: inicio de vigencia del universo, **fecha local futura**
  (mínimo mañana `America/Tijuana` respecto de cuándo se acredita).
- `attested_by_user_id`: usuario corporativo responsable, FK RESTRICT.
- `source_reference`: referencia al acta/autorización **real**, no generada.
- `expected_branch_count`, `roster_sha256`, `attested_at_utc`,
  `sealed_at_utc`. Hash de pares canónicos (codigo, ID) ordenados.
- Un único evento por fecha y solo fechas crecientes; se puede ratificar
  un reemplazo futuro, nunca modificar uno antiguo.

`track_roster_effective_members`:
- PK (`epoch_id`, `sucursal_canon`), ID operativo histórico escalar.
- Los triggers PostgreSQL prohíben UPDATE/DELETE, recapturas y cambios del
  evento después de sellar. La transacción no se sella si el conteo difiere.
- `pg_advisory_xact_lock` serializa autorizaciones concurrentes para impedir
  fechas insertadas fuera de secuencia.
- No se crean entradas, no se ejecutan seeds ni backfills en la migración.
  El downgrade rechaza destruir una decisión registrada.

## Flujo de autorización propuesto (no activo)

Servicio interno `attest_future_track_roster`: exige identidad ADMICORP,
fecha futura, referencia documental explícita y lectura única del catálogo
Track real no-demo; graba evidencia y sello **sin commit** propio. El caller
aprobado será responsable de confirmar, auditar y consolidar transacción.

**Aún NO se conecta a endpoint, botón, scheduler ni CLI.** Antes de
habilitarlo, el responsable debe ratificar:
1. Que ADMICORP/BI, con acta aprobada por Operaciones, es el custodio de
   la vigencia Track y la fuente es `CORPORATE_ROSTER_ATTESTATION`.
2. Que las altas/bajas/cambios efectivos nunca pueden fecharse antes del
   día siguiente a su autorización en `America/Tijuana`.
3. Dónde se conservará la referencia al acta y quién la aprueba.
4. Cómo se sincroniza una decisión aprobada con `track_branch_catalog`
   y cómo se alerta ante diferencias; **el scheduler no debe cambiar por
   su cuenta la membresía**.

Si no se ratifica ese gobierno, el nuevo registro permanece vacío;
no se inventan eventos ni se reinterpreta la fecha de apertura como
inclusión histórica.

## Enlace con la futura etapa 4

La lectura `read_effective_roster_for_date(D)` devuelve `verified=false`
sin evento sellado y verifica `hash + cardinalidad + códigos/IDs` de
los miembros para fechas cubiertas. Que este registro sea correcto es
**necesario pero insuficiente** para SLA: se deben comprobar además
versión base vigente y `success`, fecha D exacta, filas mart reales,
snapshot de miembros capturado para esa versión, hash de ese snapshot,
timestamp de publicación (diferente del corte canónico), y plazo
de Tijuana. Un cambio retroactivo de criterio debe ser una nueva
política explícita, nunca edición de hechos ya cerrados.

No se cambia `freshness_service.py` ni los indicadores en esta etapa.

## Despliegue

Requiere `f6roster1014` + la migración nueva `f6roster1410b`
para cualquier backend que invoque el servicio. PR y pruebas son
separados del despliegue. En producción las tablas se crean vacías;
ninguna nueva habilita certificado o modifica cronograma.
