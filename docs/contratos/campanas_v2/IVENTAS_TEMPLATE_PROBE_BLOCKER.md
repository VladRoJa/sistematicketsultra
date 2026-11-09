# Campañas V2 — Bloqueo del probador automático de plantillas iVentas

Fecha de revisión: 2026-11-09 (America/Tijuana).
Base inspeccionada: `main`, commit `9dd54eb97a7380d23c6cf3600b72914a7cbbb8cf`
(PR #1226). Rama aislada: `codex/iventas-template-probe-investigation`.

## Resultado

**NO VERIFICABLE online con los mecanismos confirmados durante esta revisión.**
No se confirmó un endpoint autenticado de solo lectura para inventario de
plantillas. Esto no demuestra que iVentas carezca de ese endpoint: falta el
contrato y una respuesta autorizada que permitan verificarlo.

El criterio de aceptación del botón automático queda pendiente de esa evidencia
externa. Este cambio es solo diagnóstico: no añade botón, endpoint, cliente
HTTP ni pase al preflight. No se usó el catálogo local para simular una consulta
exitosa. No se hicieron envíos, campañas en iVentas, cambios productivos,
migraciones, merge ni despliegue. No se leyeron credenciales ni se reutilizaron
sesiones del panel.

## Evidencia y límites de la investigación

- Se leyó `AGENTS.md`. Solo se encontró ese archivo de instrucciones en el
  checkout; no hay `graphify-out/graph.json`.
- [PR #1225](https://github.com/VladRoJa/sistematicketsultra/pull/1225),
  integrado el 2026-11-05 mediante
  `52278b216590f13147757024fdb02dc58cc3727b`, es ancestro de la base revisada.
  Su descripción declara que no hay API autenticada de inventario confirmada.
  Su alcance es evidencia manual de operador, no consulta online.
- `IVENTAS_TEMPLATE_OPERATOR_EVIDENCE.md` mantiene explícitamente ese límite.
- Los clientes existentes en `backend/app/integrations/iventas/` confirman:
  `client.py`: GET `/v1/integrations/contacts`;
  `campaigns_client.py`: GET `/v2/broadcast/stats/{campaign_id}`;
  `broadcast_provider.py`: POST `/v2/broadcast`.
  Ninguno implementa lectura de inventario de plantillas. El POST está fuera
  de alcance y no se ejecutó. La autenticación de contactos o estadísticas
  no acredita permisos para otra API.
- `template_inventory.py` declara que es un lector offline de JSON aportado
  por operador hasta verificar independientemente un contrato autenticado.
  El formato observado demuestra cómo interpretar registros, no cómo obtenerlos
  ni si el listado es completo.
- Se consultaron las páginas públicas oficiales de
  [iVentas](https://iventas.com/) y
  [campañas masivas](https://iventas.com/campanas-masivas/), y se buscaron
  referencias de API/plantillas en dominios oficiales y
  `"rest.iventas.mx" "template"`. No se encontró en lo consultado un contrato
  de listado con ruta, autenticación y paginación verificables.
- El enlace público de inicio de sesión lleva a
  [dash.iventas.com/login](https://dash.iventas.com/login); la lectura pública
  devuelve que requiere JavaScript. No se inspeccionó un inventario autenticado,
  no se analizaron sesiones privadas ni se probaron rutas supuestas.
  El comportamiento del panel autenticado sigue sin verificar.

## Flujo confirmado en el código actual

| Capa | Archivo y función | Relación confirmada |
| --- | --- | --- |
| Centro de envío | `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2-governed-console-dialog.component.ts`, `registerTemplateEvidence()`, y su HTML/CSS separados | Captura manual, confirmación del operador y nueva revisión; el HTML avisa que no es consulta automática. |
| Servicio Angular | `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2.service.ts` | Usa la ruta Suite `dispatch/template-evidence`; no consulta inventario al proveedor. |
| Ruta Flask | `backend/app/routes/marketing_campaign_v2_routes.py`, `register_campaign_v2_provider_template_evidence_endpoint()` | JWT, configuración dispatch global y capacidad de envío existentes; registra evidencia manual. |
| Evidencia | `backend/app/services/marketing_campaign_v2_template_evidence_service.py`, `register_template_evidence()` | Solo recuperación fallida; construye preflight y exige `accepted` explícito para todos sus canales efectivos. Persiste hash, actor, referencia, firmas y vigencia; no JSON bruto. |
| Validador | `backend/app/integrations/iventas/template_inventory.py`, `parse_template_inventory()` / `evaluate_template_coverage()` | Rechaza registros ambiguos; ausencia del par plantilla/canal produce `not_observed`, que no demuestra ausencia en iVentas. |
| Preflight | `backend/app/services/marketing_campaign_v2_preflight_service.py`, `build_campaign_v2_preflight()` | Resuelve plantilla, destinatarios congelados, binding y emisor; en recuperación fallida exige evidencia vigente o agrega `PROVIDER_TEMPLATE_UNVERIFIED`. |
| Enrutamiento | `backend/app/services/marketing_campaign_v2_channel_routing_service.py`, `resolve_sender_binding()` | Conserva origen comercial INDEPENDENCIA y valida emisor TEC_MXL contra snapshot y bindings vigentes; deriva de configuración de campaña, no de un mapeo nuevo. |

No debe extrapolarse el gate de evidencia de recuperación fallida a todas las
campañas: el código lo condiciona a `FAILED_RECOVERY_SOURCE`.
Tampoco debe aplicarse retroactivamente una ruta nueva a campañas ya congeladas.

## Evidencia externa mínima para desbloquear

Obtener del proveedor o de una captura autorizada de una consulta de inventario,
sin enviar ni guardar cambios en iVentas:

1. Método y URL exactos, documentados u observados; confirmación de que consultar
   no crea campañas ni consume mensajes.
2. Mecanismo de autenticación autorizado para integración de servidor, permisos
   necesarios y alcance de cuenta/canal. No aportar tokens, cookies ni claves
   al PR. Una sesión del navegador no autoriza por sí misma su reutilización.
3. Ejemplo de respuesta sanitizada con nombre de plantilla, estado e identidad
   inequívoca del canal real. Verificar compatibilidad con el parser existente;
   cualquier envoltorio requiere evidencia de su contrato.
4. Filtros, paginación y señal de finalización/completitud del inventario para
   el canal solicitado. Una página vacía o un listado parcial no prueba ausencia.
5. Semántica documentada de estados y errores: autorización insuficiente,
   canal ajeno, inexistencia, rate limit y fallos temporales.

No se proponen rutas ni nuevos nombres de campos del proveedor.

## Semántica exigida al futuro probador

| Resultado | Evidencia necesaria |
| --- | --- |
| DISPONIBLE | Respuesta autenticada válida que confirme aprobación utilizable de la plantilla exacta en el canal emisor efectivo. El JSON observado usa `accepted`; validar el contrato online antes de mapearlo. |
| NO DISPONIBLE | Rechazo explícito aplicable al par plantilla/canal, o ausencia demostrada por una consulta completa y autorizada para ese alcance. No confundir no utilizable con inexistente. |
| NO VERIFICABLE | Sin contrato o credenciales autorizadas, timeout, red, 401/403, rate limit, payload ambiguo, estado desconocido o inventario incompleto. `not_observed` aislado pertenece aquí. |

Los resultados deben conservar sucursal de origen, sucursal emisora y canal
real resueltos por el mismo preflight de la campaña. El chequeo futuro no
autoriza costo/envío, no reserva cuota ni modifica evidencia histórica.
Su integración deberá conservar las autorizaciones, auditoría y condiciones
vigentes de envío.

## Alternativa mínima disponible hoy

Para campañas de recuperación fallida, seguir
[el procedimiento existente de evidencia manual](IVENTAS_TEMPLATE_OPERATOR_EVIDENCE.md):
un operador autorizado consulta el inventario en iVentas sin despachar,
conserva captura rastreable y registra JSON original, fecha y referencia en el
Centro de envío. El servicio exige todos los canales efectivos en `accepted`,
captura de menos de una hora y vigencia de 24 horas desde captura.
Cambios en plantilla o ruta invalidan la evidencia.

Esto sigue siendo atestación manual, no satisface el botón automático ni
demuestra ausencia por canales faltantes. Para otras campañas, conservar la
verificación externa y las condiciones actuales sin extender el alcance.

## Validaciones ejecutadas

- `git clone --single-branch --branch main https://github.com/VladRoJa/sistematicketsultra.git sistematicketsultra`: correcto; checkout inicialmente limpio.
- `git rev-parse HEAD`, `git rev-parse origin/main` y `git log -1 --format='%H %s'`: base `9dd54eb...`, PR #1226.
- `git ls-remote origin refs/heads/main`: no pudo resolver github.com en ese intento. Se contrastaron archivos de main mediante el conector GitHub; no se afirma una segunda actualización de refs por CLI.
- `git switch -c codex/iventas-template-probe-investigation`: correcto.
- `git merge-base --is-ancestor 52278b216590f13147757024fdb02dc58cc3727b HEAD`: exit 0.
- Búsqueda con `rg --files`, `rg -n` y lecturas `Get-Content` de las capas anteriores y de las pruebas existentes. Algunos patrones glob en argumentos de ruta Windows se rechazaron; se corrigieron usando directorios y filtros `-g`. Dos lecturas exploratorias usaron nombres inexistentes (sender_routing_service y tests/conftest); se localizaron los archivos reales channel_routing_service y tests/marketing/conftest antes de concluir.
- `py --version`: alias Windows sin ejecutable utilizable; se localizó el Python empaquetado con la aplicación.
- `docker version --format '{{.Server.Version}}'`: daemon Linux local no disponible.
- Desde `backend`, Python empaquetado `-m pytest tests/marketing/test_iventas_template_inventory.py -q`: no ejecutó pruebas, falta módulo pytest.
- Python empaquetado `-B -` con `importlib.util.spec_from_file_location` sobre el archivo real `template_inventory.py`: **7 comprobaciones aisladas correctas** usando datos sintéticos: accepted con otro canal no observado, denied, inventario vacío, estado desconocido, rechazo de envoltorio no soportado, IDs discordantes y estados duplicados contradictorios. No importa Flask ni realiza red/BD.
- Las suites completas de evidencia, enrutamiento y preflight no se ejecutaron en este entorno. No se atribuye su resultado al smoke aislado del parser.
- No se compiló Angular: no se modifica frontend ni código de ejecución.

Único archivo afectado: este diagnóstico. No hay cambios de esquema, lógica,
permisos, cuotas, auditoría ni configuración de campañas.
