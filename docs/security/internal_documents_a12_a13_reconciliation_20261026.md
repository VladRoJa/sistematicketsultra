# Nube Corporativa — Reconciliación A-12/A-13 (2026-10-26)

## Resultado de la auditoría de `main`

La descripción histórica del [PR #1072](https://github.com/VladRoJa/sistematicketsultra/pull/1072) era una **fotografía RED anterior a las correcciones**. Es un PR de diagnóstico en borrador y **NO debe fusionarse**: sus aserciones antiguas no prueban el estado actual del sistema. No constituye una vulnerabilidad nueva confirmada.

| Caso | Política/corrección existente | Commit fusionado | Evidencia |
|---|---|---|---|
| A-12, lectura de auditoría del consolidado | Manager de Nube **y** visibilidad de documento; el consolidado debe estar publicado y respetar CUSTOM incluso para SISTEMAS | [#1074](https://github.com/VladRoJa/sistematicketsultra/pull/1074), `38dadf38e49f1a2f68b8a1cd321086f365bbb192` | `internal_documents_access.can_view_internal_document_audit` y `require_internal_document_audit_access`, pruebas A-12 |
| A-13, listado raíz de manager | SISTEMAS distinto de ADMICORP excluye título consolidado mediante `upper(trim(title)) != ...` **antes** de count/offset/limit. Mantiene listado normal y rama ADMICORP | [#1077](https://github.com/VladRoJa/sistematicketsultra/pull/1077), `ebb9e9080fb76d98696b451c429610701f43a779` | `internal_documents_routes.list_internal_documents`, pruebas A-13 |

### Este milestone: evidencia nueva, no otra implementación

Se agrega `backend/tests/routes/test_internal_documents_a12_a13_http_jwt_reconcile.py` con rutas reales de Flask y `@jwt_required` activo. Actores/documentos/logs se simulan con dobles; no se accede a PostgreSQL productivo ni se registra ninguna mutación. A-12 prueba respuestas **401/403/200**, variantes del título, que una denegación ocurre antes de leer/serializar el log, preservación del manager para un documento común y acceso explícito positivo. A-13 comprueba la exclusión y **paginación/total** bajo JWT, con distintos títulos, y conserva el listado autorizado de ADMICORP.

CI `.github/workflows/internal-documents-a13-list-parity-ci.yml` incorpora este test y ejecuta las regresiones A-12, A-13, A-11 y visibilidad del consolidado. No cambia ningún guard, endpoint, modelo, grant, rol, contrato de acceso ni pantalla. Sin migraciones ni despliegue requeridos.

### Límite de la evidencia y asuntos independientes

- Esta verificación incluye **JWT de Flask-JWT-Extended real**, pero la identidad y los documentos de prueba provienen de dobles de DB. **No equivale a prueba end-to-end sobre PostgreSQL ni a inspección de datos reales.**
- La política del consolidado se identifica por título normalizado. Unicode exótico, títulos renombrados, clasificación durable por un identificador, visibilidad de listados no-manager y otras rutas de Nube están fuera del alcance de este cierre; requieren análisis separado.
- La rama ADMICORP de A-13 se mantiene como en producción; este milestone no modifica su política de visibilidad ni demuestra que cualquier documento CUSTOM sin regla de acceso pueda listarse de forma universal.
- La Fase A completa del [issue #1053](https://github.com/VladRoJa/sistematicketsultra/issues/1053) **permanece abierta**, pues faltan paridad de otras rutas/guards y criterios globales. El [PR documental #1058](https://github.com/VladRoJa/sistematicketsultra/pull/1058) sigue abierto y debe reconciliar estos commits antes del cierre documental.

**Criterio de aceptación de este milestone:** la suite HTTP/JWT en CI verde, código productivo sin modificaciones, documentación corrigiendo el estado histórico A-12/A-13 y referencia cruzada en issue #1053. Sin merge ni despliegue sin autorización.
