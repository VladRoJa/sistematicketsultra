# M1-F6 — Etapa 4: evaluación del SLA Track sin falsos verdes

## Alcance implementado

Servicio de solo lectura:
`backend/app/services/automation_control/track_sla_certification_evidence_service.py`

Valida **independientemente** para un día de negocio D:
1. Exactamente una versión `base_nocturna_canonica`,
   `is_current=true`, `status=success`, con fecha D exacta.
2. Existencia de una vigencia Track prospectivamente ratificada por
   empresa con **atestación Y sello antes de comenzar D**; fecha `effective_from <= D`; miembros
   íntegros, cardinalidad y hash canónico.
3. Snapshot inmutable de la versión concreta creado mientras se
   procesaba; captura y sello con timestamps coherentes dentro de su
   ejecución; mismos pares código/ID de sucursal que el evento autorizado.
4. El mart enlazado a la **misma versión**, fecha D, modo
   `official_closed_day`, sin faltantes, sobrantes ni duplicados.
5. Versión completada con `finished_at_utc` real, después del
   inicio/sello y **antes de la consulta**.
6. Publicación dentro o fuera del plazo ratificado de base:
   **02:00 D+1** America/Tijuana, con `base_sla_window` y política de
   cambio de horario. Reporta `published_on_time` real (True/False)
   y dos razones separadas para cumplimiento o publicación tardía.

El resultado distingue evidencia histórica técnicamente verificable de
la autorización de cambiar el estado visible. Se retienen campos
`green_activation_authorized=False` y `sla_status=UNKNOWN` en todos los
casos. En el servicio es imposible habilitar un verde mediante mera
coincidencia con catálogo actual.

## Gate de negocio pendiente

No está ratificado ni desplegado un procedimiento para emitir el primer
`CORPORATE_ROSTER_ATTESTATION` prospectivo, ni un endpoint/flujo para
emitirlo. El PR de etapa 3 solo crea la base y el servicio interno.

Antes de conectar este evaluador a `read_track_base_sla`, endpoint o
indicador, requieren autorización explícita del custodio del dato:
- autoridad corporativa del roster Track y su documento aprobatorio;
- tratamiento de omisiones, cambios efectivos posteriores y exclusiones;
- semántica de publicación tardía: si una base se publicó a las 02:35,
  debe indicar cumplió cobertura pero incumplió plazo; el semáforo no
  debe confundir ausencia con disponibilidad tardía;
- política de visualización global/permisos backend y UX de indicadores;
- staging PostgreSQL con versiones sintéticas y cronología ficticia:
  éxito puntual, tardío, incompleto, fecha incorrecta, versión sustituida,
  duplicidad, horario de verano, falta de vigencia corporativa.

## Integración y aislamiento

Este PR es **stacked sobre M1-F6 etapa 3** y no será mergeado a main
antes de su aprobación. No modifica Angular, base nocturna, scheduler,
canonización, permisos, cifras Track, Funnel o Warehouse.

Al ser diagnóstico interno, `inspect_track_base_certification_evidence`
no está expuesto por endpoint y `read_freshness` no lo invoca. Para
históricos sin vigencia ratificada, incluido 2026-10-13, el estado visible
sigue `UNKNOWN` y el sistema nunca inventa fechas ni resultados.

Las migraciones `f6roster1014` + `f6roster1410b` están integradas en
el código (segunda todavía en PR), pero no aplicadas en producción.
