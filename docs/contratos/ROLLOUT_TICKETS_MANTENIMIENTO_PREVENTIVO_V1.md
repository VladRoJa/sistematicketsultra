# Rollout — Tickets Preventive Maintenance V1

**PR:** #655  
**Feature flag:** `TICKETS_PREVENTIVE_V1_ENABLED`

## Principio

El despliegue se realiza en dos pasos para evitar un corte irreversible:

1. desplegar código y migraciones con el flag en `false`;
2. validar el flujo nuevo;
3. activar el flag en `true` para convertir Tickets en la fuente operativa oficial y dejar PM legacy en modo histórico.

El flag solo afecta la transición del PM legacy. La información histórica no se elimina.

## 1. Actualizar código

Seguir el flujo normal de Suite Ultra:

```bash
git pull
```

No editar código manualmente en el servidor.

## 2. Mantener cutover apagado durante la primera subida

En el entorno del backend:

```env
TICKETS_PREVENTIVE_V1_ENABLED=false
```

El `docker-compose.yml` usa `false` por defecto si la variable no existe.

## 3. Reconstruir backend y frontend

```bash
docker compose up -d --build backend frontend
```

## 4. Ejecutar migraciones Alembic

```bash
docker compose exec backend flask db upgrade
```

La cadena V1 agrega, en orden:

- semántica preventiva/correctiva en Tickets;
- lotes de programación;
- cuadrillas y personal;
- vínculo Ticket ↔ bitácora;
- checklists;
- snapshot de checklist;
- catálogo de motivos de reprogramación.
- recurrencia preventiva y ocurrencias auditables;
- objetivos preventivos de Edificio reutilizando `catalogo_clasificacion`.

## 5. Smoke test con cutover apagado

Validar respuesta rápida del backend:

```bash
curl -i --max-time 5 http://127.0.0.1:5000/
```

Un 404 rápido es sano si Flask respondió.

Validar workers:

```bash
docker compose top backend
```

Debe existir 1 master + 3 workers con la configuración actual de Gunicorn.

## 6. Validar el flujo nuevo antes del corte

Con `TICKETS_PREVENTIVE_V1_ENABLED=false`:

1. abrir **Tickets → Programación preventiva**;
2. crear lote manual pequeño de prueba;
3. validar borrador;
4. publicar;
5. confirmar ticket `PREVENTIVO`;
6. abrir **Mi programa** con el técnico asignado;
7. guardar bitácora;
8. subir evidencia;
9. marcar realizado;
10. entrar como gerente a Tickets;
11. abrir **Revisar preventivo**;
12. validar o rechazar;
13. revisar **Panel de mantenimiento**;
14. comprobar drill-down;
15. comprobar reprogramación con motivo;
16. si se genera hallazgo, validar navegación preventivo ↔ correctivo;
17. crear un preventivo recurrente de Equipo y confirmar su próxima fecha hábil;
18. crear un preventivo de Edificio y confirmar que no tenga `aparato_id`;
19. ejecutar el preventivo de Edificio desde **Mi programa** y guardar bitácora;
20. generar un correctivo desde ese preventivo y confirmar que conserva la clasificación de Edificio.

## 7. Activar cutover

Antes de activar el flag:

- confirmar que no existan bitácoras PM legacy pendientes de validación que todavía requieran operación desde Calendario/Escritorio legacy;
- resolverlas o documentar explícitamente su cierre por la ruta legacy antes de ocultar esas pantallas;
- confirmar que los nuevos trabajos preventivos ya se estén creando únicamente como Tickets.

Solo después del smoke test y de esa revisión:

```env
TICKETS_PREVENTIVE_V1_ENABLED=true
```

Recrear backend para tomar el nuevo valor:

```bash
docker compose up -d --build backend
```

No requiere nueva migración.

Levantar también el worker de recurrencia:

```bash
docker compose --profile scheduler up -d --build maintenance-preventive-scheduler
```

Validar que permanezca activo:

```bash
docker compose --profile scheduler ps maintenance-preventive-scheduler
```

## 8. Verificar estado de transición

Endpoint:

```text
GET /api/pm/transition-state
```

Debe reportar:

```json
{
  "tickets_preventive_v1_enabled": true,
  "source_of_truth": "TICKETS"
}
```

Con el cutover activo:

- las escrituras preventivas legacy quedan bloqueadas;
- configuración recurrente legacy queda bloqueada;
- dashboard/calendario preventivo legacy dejan de ser operativos;
- **Consulta / Historial PM legacy** permanece disponible;
- validaciones legacy existentes pueden cerrarse;
- bitácoras ligadas a Tickets solo pueden validarse desde Tickets;
- el menú oculta las pantallas preventivas legacy operativas.

## 9. Rollback operativo

Si aparece un problema antes de generar operación real significativa en V1:

```env
TICKETS_PREVENTIVE_V1_ENABLED=false
```

y recrear backend:

```bash
docker compose up -d --build backend
```

El rollback del flag no elimina tablas ni datos y vuelve a permitir el PM legacy.

No ejecutar `flask db downgrade` como mecanismo operativo de rollback salvo diagnóstico explícito.

## 10. Observaciones posteriores al corte

Durante los primeros días revisar:

- lotes publicados vs tickets generados;
- preventivos asignados sin técnico;
- bitácoras sin evidencia;
- tickets pendientes de validación;
- rechazos y reintentos;
- reprogramaciones por motivo;
- backlog correctivo total/vencido;
- correctivos `REACTIVO` vs `DETECTADO_EN_PREVENTIVO`;
- errores 409 provenientes de rutas PM legacy, que indicarían usuarios o enlaces aún intentando operar la interfaz anterior.
- series recurrentes con `next_scheduled_date` vencida;
- duplicados de ocurrencia por `schedule_id + scheduled_date`;
- preventivos de Edificio sin clasificación o con clasificación inactiva;
- salud y logs de `maintenance-preventive-scheduler`.
