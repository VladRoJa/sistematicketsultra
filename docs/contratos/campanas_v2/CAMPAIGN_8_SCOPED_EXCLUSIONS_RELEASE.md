# Campaña V2 #8 — excluir 3 conflictos solo de envío

**Cambio urgente de seguridad para la campaña «Socios activos/venta nueva invita y gana».**

## Alcance autorizado

- Campaña única: ID **8**; cohorte congelada **14,002**.
- Excluir únicamente del despacho los recipient IDs **59510, 59859, 60120**.
- Motivo: `AMBIGUOUS_BRANCH_EVIDENCE`; cada destinatario presenta dos sucursales distintas en sus evidencias.
- No modificar los 14,002 destinatarios congelados, ni evidencias, ni blacklist global.
- La lista enviable y el preflight tomarán las exclusiones desde una tabla separada con auditoría de operador, motivo y fecha.
- Cantidad esperada sin otras supresiones: **13,999**; debe confirmarse con preflight real.
- La exclusión no autoriza envíos ni habilita `CAMPAIGN_V2_PROVIDER_SEND_ENABLED`.

## Despliegue seguro (solo después de aprobar y mergear este PR)

1. Confirmar que el servidor está en el commit esperado, sin cambios locales ni trabajos paralelos en migrations.
2. Ejecutar procedimiento oficial: repo local -> commit/PR -> merge -> servidor `git pull` -> `docker compose up -d --build backend`.
3. Ejecutar `docker compose exec -T backend flask db upgrade` (migración `d8f1c3a9b204`).
4. Comprobar Alembic `flask db current`, la salud del backend y la tabla vacía.
5. Primero modo revisión:

```bash
docker compose exec -T backend python scripts/apply_campaign8_scoped_exclusions.py
```

6. Verificar `CAMPAIGN_ID=8`, `FROZEN=14002`, `EXPECTED_SCOPED_EXCLUSIONS=3`, `ACTION=DRY_RUN`, `ALREADY_EXCLUDED=0`. Si algo difiere, **NO continuar**.
7. Después ejecutar la aplicación auditada, previamente autorizada:

```bash
docker compose exec -T backend python scripts/apply_campaign8_scoped_exclusions.py --apply
```

8. El resultado esperado es `ADDED=3`, `EXCLUSIONS_AFTER=3`. Repetir la lectura en modo simulación debe mostrar `ALREADY_EXCLUDED=3`.
9. En Suite recargar campaña 8 y template `invita_y_gana_4800`; volver a **Revisar envío**.
10. Esperar cohorte congelada 14,002, blacklist 0 (si no cambió), exclusiones de campaña 3, enviables 13,999, 26 lotes listos y **cero bloqueos**. Descargar y revisar manualmente la lista enviable y el fingerprint nuevo.
11. No activar envío por UI o CLI sin una autorización **adicional y específica para el submit**.

## Precaución de migraciones paralelas

Este hotfix sale de `main` para no depender del PR M3 #812. Ambas ramas parten de la misma revisión Alembic `f3f1d4e6a7c9`. **Antes de mergear M3 posteriormente, se debe resolver el grafo de revisiones Alembic**: revisar sus migraciones y ajustar ancestry o crear revisión de merge; jamás llevar dos heads a producción sin reconciliar.

## Reversibilidad

No borrar la tabla para deshacer exclusiones en una campaña activa. La tabla contiene auditoría y el fingerprint depende del conjunto excluido. Una reversión, si fuese necesaria, requerirá decisión explícita, ninguna campaña enviada y migración revisada. Sin hacks ni borrados manuales.
