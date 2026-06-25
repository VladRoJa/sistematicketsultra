# Permissions Observability — Phase 1

## Objetivo

Documentar el estado actual de rutas y permisos sin reemplazar todavía la lógica existente.

Esta fase funciona como mapa base para construir observabilidad de accesos en Suite Ultra.

## Resultado del inventario

- Total de rutas detectadas: **171**
- Rutas sin `jwt_required`: **3**
- Write routes sin `jwt_required`: **1**

## Rutas públicas detectadas

| módulo | método | ruta | función | riesgo inicial |
|---|---:|---|---|---|
| Auth | POST | `/login` | `login` | expected_public_login |
| Inventario | GET | `/ping` | `ping` | public_health_or_root_review |
| General / Otro | GET | `/` | `index` | public_health_or_root_review |

## Conteo por módulo

| módulo | rutas |
|---|---:|
| Aperturas | 20 |
| Auth | 2 |
| Catálogos | 12 |
| General / Otro | 6 |
| Inventario | 29 |
| Nube Corporativa | 23 |
| PM | 10 |
| Planning / Metas | 15 |
| Reportes | 2 |
| Tickets | 25 |
| Track / BI | 6 |
| Usuarios / Admin | 8 |
| Warehouse | 13 |

## Conteo por riesgo inicial

| riesgo inicial | rutas |
|---|---:|
| expected_public_login | 1 |
| high_delete | 7 |
| high_job_or_import | 4 |
| low_read | 96 |
| medium_write | 61 |
| public_health_or_root_review | 2 |

## Conclusión inicial

- No se detectaron rutas de escritura abiertas fuera de `/login`.
- `/login` debe permanecer público por diseño.
- `/` y `/inventario/ping` parecen rutas de health/root y deben revisarse como públicas intencionales.
- La siguiente fase debe mapear cada ruta autenticada contra guard real, rol esperado y scope esperado.

## Archivos relacionados

- `docs/security/permissions_routes_catalog.csv`
- `permissions_routes_inventory.json`
- `permissions_routes_summary.json`