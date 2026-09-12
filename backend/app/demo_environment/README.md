# Entorno DEMO de Suite Ultra

## Objetivo

`ULTRA DEMO` es una sucursal operativa de prueba dentro de la misma instancia de
producción. Su propósito es permitir demostraciones y validaciones end-to-end de
Tickets, Inventario, Mantenimiento y Maintenance Planner sin afectar una
sucursal real ni contaminar BI.

No es una base de datos alterna ni un fork funcional de Suite Ultra.

## Contrato de participación

La propiedad canónica es `Sucursal.is_demo`.

| Audiencia | DEMO | Uso esperado |
| --- | --- | --- |
| `operational` | incluida | Tickets, Inventario, PM, Planner |
| `analytical` | excluida | Track, Forecast, Control, consolidados ejecutivos |

No se debe utilizar un `sucursal_id` especial ni condiciones hardcodeadas como
`if sucursal_id != 27`. El ID lo asigna PostgreSQL y la semántica depende
únicamente de `is_demo`.

## Invariantes

Una sucursal demo:

- puede estar `ACTIVA` para ejercitar flujos transaccionales reales;
- puede tener inventario, movimientos, tickets e historial;
- aparece en catálogos operativos;
- no debe vincularse a `track_branch_catalog`;
- no debe tener asignaciones en `suite_sucursal_region_assignment`;
- no debe participar en Control ni en consolidaciones analíticas;
- debe identificarse visualmente como DEMO cuando una pantalla operativa la
  presenta.

El servicio `ensure_demo_branch()` valida las dos invariantes analíticas antes
de confirmar la operación.

## Provisionamiento

La migración de esquema **no crea datos operativos**. Después de ejecutar la
migración, el provisionamiento es una acción explícita e idempotente:

```bash
python -m scripts.ensure_demo_branch
```

Resultado esperado en la primera ejecución:

```json
{
  "status": "ok",
  "demo_branch": {
    "created": true,
    "is_demo": true,
    "serie": "DEMO",
    "sucursal": "ULTRA DEMO",
    "sucursal_id": 0
  }
}
```

`sucursal_id` es ilustrativo: nunca se debe asumir un valor concreto.

En ejecuciones posteriores `created` debe ser `false`. Si existe una sucursal
con serie `DEMO` que no esté marcada como demo, o si la demo fue vinculada a
Track/regiones, el script falla de forma explícita y hace rollback.

## Datos de demostración

No se crean automáticamente usuarios, inventario ni tickets. Deben generarse
usando los mismos flujos de Suite que se desean validar. Esto permite probar de
verdad:

1. alta/asignación de inventario a `ULTRA DEMO`;
2. creación de ticket de Mantenimiento para un equipo demo;
3. asignación y fecha compromiso;
4. visualización en Maintenance Planner;
5. reprogramación desde modal o drag & drop;
6. historial de cambios;
7. cierre del ticket;
8. validación de que Control/Track no cambiaron por esos datos.

## Catálogo de sucursales

`GET /api/sucursales/listar` soporta:

```text
audience=operational
```

Incluye DEMO y es el valor por defecto por compatibilidad con módulos
transaccionales.

```text
audience=analytical
```

Excluye DEMO y debe usarse en módulos que representen la operación real de
Ultra.

## Regla para nuevos módulos

Antes de consumir el catálogo de sucursales, el módulo debe declarar su
audiencia:

- si modifica o simula operación: `operational`;
- si suma, compara, proyecta o reporta la compañía: `analytical`.

La complejidad debe quedarse en esta frontera y no propagarse como excepciones
por ID en cada pantalla.
