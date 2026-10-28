# Suite Ultra — Fase B / B2: Nube P1, nueve lecturas HTTP/JWT/IDOR

**Estado:** suite de regresión aislada y propuesta de pruebas, no despliegue. **Origen:** #1161 y acta P34, nueve GET P1 en [matriz de Nube](permissions_phase_a_p34_nube_pilot_p1_reads_20261027.csv). B1 PR #1162 está pendiente de CI en el momento de abrir B2. B2 se construye **independientemente desde main**: no presupone B1 fusionado y no altera `internal_documents_access.py`.

## Matriz de evidencia

| GET P1 | 401 anónimo | 403 objeto no visible | 404 documento/versión | 200 autorizado, contenido sintético |
|---|---|---|---|---|
| `/api/internal-documents` | B2 | N/A colección: filtrar filas | N/A | Suites A13 listado, count/paginación |
| `/<document_id>` | B2 | B2 (gerente privado / SISTEMAS consolidado) | B2 | B2 detalle |
| `/<document_id>/versions` | B2 | B2 antes de ORM | B2 | B2 versiones; histórico restringido |
| `/<document_id>/links` | B2 | B2 antes de ORM | B2 | B2 vínculos |
| `/<document_id>/external-resources` | B2 | B2 antes de ORM | B2 | B2 recursos |
| `/by-link` | B2 | N/A colección: filtrar filas | N/A | Suite heredada especial A13/by-link |
| `/<document_id>/download` | B2 | B2 antes de path/send_file | B2 | B2 envío sustituido con Response sintética |
| `/<document_id>/versions/<version_id>/download` | B2 | B2 antes de ORM/path/send_file | B2 versión inexistente | B2 válido sin archivo; **vínculo document_id+version_id** requerido |
| `/<document_id>/audit` | B2 | B2 antes de query/serialize | B2 | B2 log ficticio |

### Casos de seguridad concretos

- **JWT (401):** nueve endpoints rechazan sesión ausente *antes* de recuperar documentos.
- **Alcance por documento (403):** `GERENTE` de sucursal 8 no puede acceder a `PRIVATE` cuyo dueño es usuario de otra sucursal. Un `SISTEMAS` manager no puede omitir el `CUSTOM` del **Consolidado de agregadoras** (A12/A13). Ambos casos se prueban para las **siete** rutas que aceptan `document_id`.
- **IDOR y filtración (404):** un `document_id` inexistente no debe llevar a `send_file`; si `version_id` no pertenece al documento, la consulta exige ambos IDs y devuelve 404 sin path, envío ni nombre de archivo.
- **Autorizaciones positivas (200):** usuarios manager autorizados leen detalles, versiones, vínculos y recursos con dobles de ORM; descarga vigente/histórica devuelve *únicamente* una respuesta sintética (no existe archivo físico); auditoría retorna un log sintético.
- **Colecciones:** las suites existentes A13 prueban que el listado excluye consolidado para SISTEMAS **antes** de count/offset/limit y que `by-link` filtra cada documento con `can_view_internal_document`. La nueva suite comprueba contratos estáticos para ambos, sin abrir la base de producción.

## Límites y gates

- B2 **no crea permisos, grants ni scopes**. Los decoradores `@jwt_required`, resolutor `get_current_internal_document_context` desde DB, reglas `GLOBAL/CUSTOM/PRIVATE`, sensibilidad, borradores/archivados, exclusiones especiales A12/A13 y guardias de descarga/auditoría se conservan.
- **No prueba la política completa en producción** ni convierte la autorización de un manager en lectura de cualquier documento; los resultados son de fixtures sintéticos y guards reales. El runner debe mantener bloqueo de archivos reales, de SMS, SQL productivo y de cambios DB.
- Si alguna regresión revela un defecto en el guard, **no ajustar acceso dentro de este PR**: detener, informar y preparar un fix aislado validado.
- El cierre de B2 exige pruebas verdes y PR sin conflictos. No hay deploy requerido de backend para tests/docs; el piloto B1 sigue independiente y su merge depende de CI propia.
- **Siguiente gate** dentro de #1161: decidir si el compare-only ya refleja las diferencias de objeto correctamente antes de habilitar edición de permisos. Ningún `grants_overlay` ni `grants_enforced` autorizado.

**Archivos:** `backend/tests/routes/test_permissions_phase_b_b2_nube_p1_gets.py`, esta matriz y CI B2; sin alteración de rutas o modelos.
