# Maintenance Planner V2

Módulo paralelo al PM legacy. No sustituye `/api/pm`, no crea tablas nuevas y no modifica la semántica de las bitácoras preventivas existentes.

## Objetivo

Dar una vista de junta sobre los tickets reales del departamento de Mantenimiento:

- vencidos;
- trabajos para hoy;
- agenda semanal;
- tickets activos sin fecha compromiso;
- tickets que requieren refacción;
- reprogramación rápida con motivo trazable.

## Contrato público

Blueprint: `/api/maintenance-planner`

- `GET /board`
  - `start_date=YYYY-MM-DD`
  - `end_date=YYYY-MM-DD`
  - `branch_id=<id>` opcional y repetible
  - `estado=<estado>` opcional
- `PUT /tickets/<ticket_id>/schedule`
  - `due_date: YYYY-MM-DD`
  - `reason: string`

## Dependencias explícitas

El módulo solo depende de contratos existentes de Suite Ultra:

1. `Ticket` como fuente operativa de verdad.
2. `filtrar_tickets_por_usuario(user)` para alcance por permisos/sucursal.
3. `can_pm_view(user)` y `can_pm_execute(user)` para capacidades de mantenimiento.
4. `UserORM` únicamente en la capa HTTP para resolver la identidad JWT.

No conoce componentes Angular del PM legacy ni sus endpoints.

## Persistencia

No tiene tablas propias. La fecha compromiso se conserva en `tickets.fecha_solucion` y cada cambio se agrega a `tickets.historial_fechas` con:

```json
{
  "origen": "maintenance_planner_v2"
}
```

Esto evita dos agendas divergentes y permite retirar el Planner sin migración de datos.

## Patrón para futuros módulos plug-and-play

La estructura es deliberada:

```text
feature_module/
├── __init__.py       # superficie pública
├── routes.py         # transporte HTTP/JWT
├── service.py        # reglas del módulo + adaptadores al dominio existente
└── README.md         # contrato, dependencias y desmontaje
```

En frontend:

```text
feature-module/
├── feature.component.ts
├── feature.component.html
├── feature.component.css
└── feature.service.ts
```

La aplicación raíz solo debe registrar el blueprint y la ruta Angular. El resto de Suite Ultra no debe importar internals del módulo.

## Desmontaje

Para retirar V2 sin afectar PM legacy:

1. eliminar la ruta Angular `/maintenance-planner`;
2. retirar el registro de `maintenance_planner_bp`;
3. eliminar `frontend/src/app/maintenance-planner/`;
4. eliminar `backend/app/maintenance_planner/`.

No requiere rollback de DB.
