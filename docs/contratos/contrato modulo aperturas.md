## Actualización de estado — Junio 2026

Este contrato se actualiza después de la implementación real del módulo de Aperturas usando Serranía como caso operativo.

### Estado actual del módulo

```text
✅ Backend base F1 implementado
✅ Modelos y migraciones F1 implementados
✅ Frontend F1 implementado
✅ Gantt operativo implementado
✅ Apertura Serranía cargada en servidor
✅ Fases reales de Serranía cargadas
✅ Tareas reales de Serranía cargadas
✅ Tareas sin fecha soportadas como checklist operativo
✅ Edición de inicio programado y fecha compromiso desde panel lateral
✅ Dependencias visibles y editables desde UI
✅ Bloqueos operativos con causa, tipo e impacto
✅ Resolución de bloqueos con comentario obligatorio
✅ Bitácora visible por tarea
✅ Panel lateral reorganizado por tabs internos
✅ KPI de tareas bloqueadas con navegación contextual
✅ Alta operativa de Serranía en sucursales
✅ Vinculación de SERRANIA en track_branch_catalog con sucursal operativa
🟠 Control financiero pendiente para F2
🟠 Partidas presupuestales pendiente para F2
🟠 Solicitudes de pago pendiente para F3
🟠 Vínculos documentales con Nube pendiente para F2/F3
🔵 Notificaciones y alertas avanzadas en roadmap
⚠️ Fuente de verdad de sucursales pendiente
```

### Cambio de estatus F1

F1 ya no debe considerarse solo “en curso”.

F1 puede considerarse funcionalmente cerrada para operación base, con Serranía como caso real cargado en servidor.

F1 cubre actualmente:

```text
apertura
sucursal
fases
tareas
fechas
Gantt
seguimiento por fase
tareas sin fecha
edición de fechas
dependencias
bloqueos
comentarios
bitácora
panel lateral usable
auditoría base
```

Quedan como polish F1 menor:

```text
mejorar textos finales de UI
compactar algunas secciones visuales
mejorar lectura ejecutiva
agregar filtros operativos de bitácora
```

### Hallazgo estructural: fuente de verdad de sucursales

Durante la carga de Serranía se detectó un problema estructural importante:

```text
Track ya conocía SERRANIA.
sucursales no conocía Serranía como entidad operativa.
Aperturas necesitaba una sucursal_id real para poder crear la apertura.
```

Esto confirma que la Suite tiene varias fuentes parciales de sucursal:

```text
sucursales
track_branch_catalog
track_branch_aliases
aperturas
tickets
PM
inventario
warehouse / track_daily_mart
```

Caso detectado:

```text
track_branch_catalog tenía SERRANIA activa,
pero con sucursal_id = null.

track_branch_aliases ya tenía aliases formales para:
- gasca_family
- manual_targets
- domiciliados_total
- wellhub_family
- totalpass_family
```

Resolución aplicada para operación inmediata:

```text
Se creó Serranía en sucursales como sucursal operativa.
Se vinculó track_branch_catalog.sucursal_id con la sucursal operativa.
```

Pendiente estructural:

```text
Crear una fuente de verdad de sucursales que unifique:
- alta
- estado operativo
- alias Track
- visibilidad por módulo
- relación con aperturas
- relación con tickets / PM / inventario
```

### Regla nueva del módulo Aperturas

Una apertura real no debe cargarse contra una sucursal improvisada.

Antes de crear una apertura productiva debe existir:

```text
1. sucursal operativa en sucursales
2. estado operativo correcto
3. si aplica, registro en track_branch_catalog
4. aliases de Track si ya existe en fuentes BI
```

Si Track conoce una sucursal y sucursales no, se debe resolver el catálogo antes de cargar cronogramas operativos.

### Estado actualizado de Serranía

Serranía ya funciona como caso real en servidor.

Estado actual:

```text
✅ Sucursal operativa creada
✅ Track catalog alineado con sucursal_id
✅ Apertura creada
✅ Fases importadas
✅ Tareas importadas
✅ Tareas sin fecha preservadas
✅ Fechas editables desde UI
✅ Gantt usable
✅ Panel lateral usable
✅ Bloqueos y bitácora disponibles
```

Serranía deja de ser solo prueba local y pasa a ser caso operativo real de Aperturas.

### Siguiente fase recomendada

La siguiente fase no debe ser más Gantt.

La siguiente fase debe ser control operativo-financiero:

```text
F2 — Presupuesto y partidas
F3 — Solicitudes de pago
F2/F3 — Documentos vinculados desde Nube
```

Orden recomendado:

```text
1. Modelo de presupuesto de apertura
2. Partidas presupuestales
3. Proveedores y cuentas bancarias
4. Solicitudes de pago
5. Estados con Finanzas
6. Facturas y comprobantes vinculados desde Nube
7. Saldos por partida
8. Bitácora financiera
```

### Criterio actualizado de cierre F1

F1 se considera cerrado cuando:

```text
✅ Se puede crear apertura vinculada a sucursal
✅ Se pueden crear fases
✅ Se pueden crear tareas
✅ Se pueden importar tareas reales
✅ Se pueden manejar tareas sin fecha
✅ Se pueden editar fechas desde UI
✅ Se puede ver Gantt
✅ Se puede navegar por seguimiento operativo
✅ Se pueden crear dependencias
✅ Se pueden crear bloqueos operativos
✅ Se pueden resolver bloqueos con comentario
✅ Se conserva bitácora visible por tarea
✅ El panel lateral no se vuelve una cinta infinita
✅ Se puede operar Serranía desde servidor
✅ El backend valida permisos
```

Pendiente fuera de F1:

```text
control financiero
documentos vinculados
notificaciones
fuente de verdad de sucursales
```










# Suite Ultra — Contrato Técnico Módulo de Aperturas

## Centro de control operativo-financiero para aperturas Ultra

---

## Estado general del contrato

Este contrato define el Módulo de Aperturas como un centro de control operativo-financiero para coordinar nuevas sucursales Ultra desde planeación hasta entrega operativa.

Estado actual del módulo:

```text
✅ Backend base implementado
✅ Modelos y migraciones F1 implementados
✅ Frontend premium F1 implementado
✅ Gantt visual implementado
✅ Carga real inicial de Serranía probada en local
🟡 Polish UX en curso
🟠 Funciones operativas avanzadas definidas para siguiente fase
🔵 Notificaciones, alertas avanzadas y ruta crítica quedan para roadmap
```

Leyenda:

```text
✅ LISTO / IMPLEMENTADO
🟡 POLISH UX DEFINIDO / EN AJUSTE
🟠 SIGUIENTE FASE FUNCIONAL
🔵 ROADMAP / FUTURO
⚠️ DECISIÓN O RIESGO PENDIENTE
```

---

# 0. Separación de contratos

Este contrato corresponde únicamente al:

```text
Módulo de Aperturas
```

La **Nube Corporativa** tiene contrato separado.

Relación correcta:

```text
Nube Corporativa = base documental gobernada
Aperturas = centro de control operativo-financiero que consume documentos de Nube
```

Aperturas no debe reimplementar almacenamiento documental, versionado, preview ni auditoría documental.

Aperturas debe consumir documentos desde Nube mediante vínculos documentales.

Estado actual:

```text
✅ Separación conceptual definida
✅ Nube Corporativa existe como módulo separado
🟠 Falta capa formal de vinculación entre documentos y aperturas/tareas
```

---

# 1. Principio rector

No estamos construyendo una copia de Microsoft Project.

Estamos construyendo un centro de control de aperturas hecho para Ultra.

El módulo debe resolver:

```text
Quién hace qué
Para cuándo
De qué depende
Qué documento lo respalda
Qué partida presupuestal lo paga
Cuánto presupuesto queda
Qué proveedor cobra
Qué factura respalda el pago
Si Finanzas ya recibió/programó/pagó
Qué cambió, quién lo cambió y cuándo
```

Microsoft Project puede ser fuerte en Gantt.

Suite Ultra debe ser fuerte en:

```text
contexto operativo + presupuesto + pagos + documentos + responsables + trazabilidad
```

Estado actual:

```text
✅ Principio rector definido
✅ Gantt F1 implementado
✅ Operación base implementada
🟠 Control financiero queda para F2
🟠 Control documental vinculado queda para F2/F3
```

---

# 2. Objetivo del módulo

Construir un módulo robusto para coordinar aperturas de nuevas sucursales, integrando:

```text
cronograma
fases
tareas
responsables
fechas
dependencias
presupuesto autorizado
partidas
solicitudes de pago
proveedores
facturas
documentos oficiales
cambios
bitácora
alertas
tablero ejecutivo
```

El objetivo no es solo ver tareas.

El objetivo es controlar una apertura completa desde planeación hasta entrega operativa.

Estado actual:

```text
✅ Cronograma base
✅ Fases
✅ Tareas
✅ Fechas
✅ Dependencias base backend
✅ Comentarios
✅ Auditoría básica
✅ Tablero/visualización inicial
🟠 Dependencias editables desde UI
🟠 Presupuesto/partidas/pagos
🟠 Documentos oficiales vinculados
🔵 Alertas automáticas y notificaciones
```

---

# 3. Contexto operativo

La apertura actual **Serranía** se está coordinando con el método tradicional, principalmente mediante grupo de WhatsApp y archivos compartidos.

Serranía se usa como caso real para aprender problemas operativos.

La siguiente apertura objetivo es **Egade**, estimada aproximadamente en un mes.

El módulo debe estar pensado para que Egade sea la primera apertura gestionada de forma seria desde Suite Ultra.

Estado actual:

```text
✅ Serranía cargada como caso real de prueba local
✅ Gantt real de Serranía importado parcialmente a estructura Suite
✅ Se detectaron necesidades reales de UX y operación
🟡 Polish UX en curso para que el módulo sea presentable y usable
```

---

# 4. Principios UX obligatorios

La UX es requisito de éxito, no cosmético.

Si la pantalla se siente como tabla genérica, Excel web o Project mal copiado, el módulo pierde valor.

---

## 4.1 Vista ejecutiva primero

Al entrar a una apertura, la primera vista debe responder:

```text
¿Cómo va la apertura?
¿Qué está atorado?
Qué urge?
Quién debe moverse?
Qué impacto financiero hay?
```

Elementos esperados:

```text
Apertura
Estado general
% avance
Fecha objetivo
Días restantes
Tareas atrasadas
Riesgos abiertos
Presupuesto autorizado
Presupuesto comprometido
Pagos pendientes
Documentos críticos faltantes
```

Estado actual:

```text
✅ Dashboard base implementado
✅ KPIs iniciales implementados
✅ Timeline de fases implementado
🟡 Decisión UX actual: abrir directamente en Gantt para demo/operación
🟠 KPIs financieros dependen de F2 presupuesto/pagos
```

---

## 4.2 Gantt como vista operativa principal

Para el caso de Aperturas, el Gantt debe ser una vista central porque permite entender rápido:

```text
fases
fechas
duración
tareas largas
tareas críticas
bloqueos
avance del proyecto
contexto del día actual
```

Estado actual:

```text
✅ Gantt visual F1 implementado
✅ Auto-scroll al día actual implementado
✅ Botón “Ir a hoy” implementado
✅ Scroll horizontal contenido dentro del Gantt implementado
✅ Panel lateral de tarea ocultable implementado
✅ Header de fechas sticky definido y probado localmente
🟡 Abrir detalle directamente en Gantt definido como polish
🟡 Fases contraídas por default definido como polish
🟡 Ocultar tareas completadas por default definido como polish
```

Regla UX:

```text
Al abrir una apertura, el usuario debe caer cerca del día actual.
El Gantt debe permitir volver al día actual con un botón.
La fila de fechas debe permanecer visible al hacer scroll vertical.
La columna de elementos debe mantenerse visible al hacer scroll horizontal.
```

---

## 4.3 Detalle después

El detalle debe existir, pero no dominar la primera vista.

El módulo debe permitir bajar de nivel:

```text
Apertura → Fase → Tarea → Pago / Documento / Comentario / Cambio
```

Estado actual:

```text
✅ Panel lateral de tarea implementado
✅ Panel lateral ocultable implementado
✅ Comentarios por tarea implementados
✅ Acciones rápidas de tarea implementadas
🟠 Dependencias editables desde panel pendiente
🟠 Bloqueos operativos con causa pendiente
🟠 Checklist por tarea pendiente
```

---

## 4.4 No saturar con tablas

Las tablas son necesarias, pero no deben ser la experiencia principal.

Se deben usar:

```text
cards ejecutivas
timeline por fases
Gantt operativo
panel lateral de detalle
semáforos
chips de estado
badges de riesgo
filtros inteligentes
modales para acciones puntuales
```

Estado actual:

```text
✅ Cards ejecutivas implementadas
✅ Timeline implementado
✅ Gantt implementado
✅ Panel lateral implementado
✅ Chips/estados visuales implementados
🟡 Crear tarea desde modal flotante definido como polish
```

---

## 4.5 Mobile controlado

Móvil no será para planear toda una apertura.

Móvil debe servir para:

```text
revisar estado
comentar
aprobar/rechazar
marcar avance rápido
ver documentos
subir evidencia
responder alertas
```

Desktop será para planeación completa.

Estado actual:

```text
🟠 No implementado todavía
🔵 Relevante para aprobaciones, bloqueos y notificaciones
```

---

# 5. Pilares funcionales

---

## 5.1 Control operativo

Incluye:

```text
apertura
fases
tareas
responsables
fechas
dependencias
estados
avances
comentarios
cambios
bloqueos
checklists
```

Estado actual:

```text
✅ Apertura
✅ Fases
✅ Tareas
✅ Fechas
✅ Estados
✅ Avances
✅ Comentarios
✅ Auditoría básica
✅ Dependencias base backend
🟠 Dependencias editables desde UI
🟠 Bloqueos operativos estructurados
🟠 Checklist por tarea
🟠 Edición de fechas con preview de impacto
```

---

## 5.2 Control financiero

Incluye:

```text
presupuesto autorizado
partidas presupuestales
solicitudes de pago
proveedores
cuentas bancarias
facturas
comprobantes
estatus con Finanzas
saldos por partida
```

Estado actual:

```text
🟠 Definido para F2
🟠 Hay documentos reales de pago/presupuesto de Serranía como insumo
🟠 Falta modelo financiero formal
```

---

## 5.3 Control documental

Incluye documentos vinculados desde Nube:

```text
planos
contratos
permisos
cotizaciones
facturas
evidencias
checklists
manuales
```

Estado actual:

```text
✅ Nube Corporativa existe como módulo separado
✅ Warehouse soporta almacenamiento documental
✅ Nube maneja versiones, publicación, visibilidad y auditoría
🟠 Falta vínculo formal documento → apertura / fase / tarea
```

Regla:

```text
Aperturas no guarda archivos directamente.
Aperturas vincula documentos publicados o controlados desde Nube Corporativa.
```

---

## 5.4 Control de cambios y auditoría

Toda operación relevante debe poder responder:

```text
Qué cambió
Quién lo cambió
Cuándo lo cambió
Valor anterior
Valor nuevo
Motivo o comentario
```

Estado actual:

```text
✅ Auditoría básica de apertura/fase/tarea/comentario/dependencia implementada
🟠 Falta auditoría específica para bloqueos
🟠 Falta auditoría de impacto por cambio de fechas
🟠 Falta auditoría documental vinculada a Aperturas
```

---

# 6. Modelo funcional F1 implementado

## 6.1 Tablas / entidades F1

Estado:

```text
✅ LISTO
```

Entidades implementadas:

```text
openings
opening_phases
opening_tasks
opening_task_dependencies
opening_task_comments
opening_audit_logs
```

También se agregó estado operativo a sucursales:

```text
sucursales.operational_status
```

Estados operativos de sucursal:

```text
PLANEADA
EN_APERTURA
ACTIVA
PAUSADA
CANCELADA
CERRADA
```

Estado actual:

```text
✅ Sucursal Serranía puede existir como EN_APERTURA
✅ Apertura Serranía puede vincularse a sucursal
```

---

## 6.2 Backend F1

Estado:

```text
✅ LISTO
```

Endpoints base implementados:

```text
GET    /api/openings
POST   /api/openings
GET    /api/openings/<opening_id>
PATCH  /api/openings/<opening_id>

GET    /api/openings/<opening_id>/phases
POST   /api/openings/<opening_id>/phases
PATCH  /api/openings/<opening_id>/phases/<phase_id>

GET    /api/openings/<opening_id>/tasks
POST   /api/openings/<opening_id>/tasks
PATCH  /api/openings/<opening_id>/tasks/<task_id>

GET    /api/openings/<opening_id>/task-dependencies
GET    /api/openings/<opening_id>/tasks/<task_id>/dependencies
POST   /api/openings/<opening_id>/tasks/<task_id>/dependencies
DELETE /api/openings/<opening_id>/task-dependencies/<dependency_id>

GET    /api/openings/<opening_id>/tasks/<task_id>/comments
POST   /api/openings/<opening_id>/tasks/<task_id>/comments
```

Validaciones implementadas:

```text
✅ JWT requerido
✅ Roles de lectura/admin
✅ Apertura existente
✅ Fase dentro de apertura
✅ Tarea dentro de apertura
✅ Dependencia dentro de apertura
✅ No dependencia consigo misma
✅ Anti-duplicado de dependencia
✅ Estados válidos
✅ Prioridades válidas
✅ Avance 0-100
✅ Comentario no vacío
```

---

## 6.3 Frontend F1

Estado:

```text
✅ LISTO
```

Ruta:

```text
/#/aperturas
/#/aperturas/:openingId
```

Archivos principales:

```text
frontend/src/app/openings/openings.routes.ts
frontend/src/app/openings/models/opening.model.ts
frontend/src/app/openings/services/openings.service.ts
frontend/src/app/openings/pages/openings-list/
frontend/src/app/openings/pages/opening-detail/
```

Funcionalidades implementadas:

```text
✅ Listado de aperturas
✅ Alta rápida de apertura
✅ Detalle de apertura
✅ Dashboard visual
✅ Timeline por fases
✅ Tareas agrupadas por fase
✅ Panel lateral de tarea
✅ Comentarios
✅ Dependencias visibles
✅ Acciones rápidas
✅ Gantt visual
✅ Botón Ir a hoy
✅ Auto-scroll al día actual
✅ Panel lateral ocultable
✅ Scroll horizontal contenido
✅ Header de fechas sticky probado localmente
```

---

# 7. Gantt F1

## 7.1 Función del Gantt

El Gantt debe permitir ver:

```text
fases
rango de fechas
tareas
tareas sin fecha
avance
estado
día actual
bloqueos
dependencias relevantes
```

Estado actual:

```text
✅ Gantt visual implementado
✅ Día actual visible
✅ Navegación a hoy implementada
✅ Scroll interno implementado
✅ Corrección de encimado entre fechas y columna Elemento definida/probada
```

---

## 7.2 Reglas UX del Gantt

Reglas actuales y próximas:

```text
✅ El Gantt debe hacer auto-scroll al día actual.
✅ Debe existir botón “Ir a hoy”.
✅ La fila de fechas debe quedar visible al hacer scroll vertical.
✅ La columna Elemento debe quedar fija al hacer scroll horizontal.
🟡 Al abrir un proyecto, debe iniciar en Gantt.
🟡 Las fases deben iniciar contraídas para vista general.
🟡 Las tareas completadas deben poder ocultarse/mostrarse.
🟡 Cada fase debe poder expandirse/contraerse individualmente.
```

---

# 8. Carga real de Serranía

Estado:

```text
✅ LISTO EN LOCAL
```

Se cargó el cronograma real de Serranía como caso de prueba.

Fuente:

```text
Cronograma Apertura Plaza Serranía Mty NL 110526
```

Fases detectadas:

```text
Proyecto Arq.
Arranque preventa
Operaciones - Deportes
Soft opening
```

Tareas cargadas:

```text
30 tareas base
```

Regla aplicada:

```text
Cuando una tarea trae barras partidas en el Excel, F1 consolida como:
fecha_inicio = primera barra detectada
fecha_compromiso = última barra detectada
```

Riesgo:

```text
⚠️ Si las barras partidas representan tramos reales, en futuro conviene soportar segmentos de tarea.
```

---

# 9. Dependencias

## 9.1 Dependencias base

Estado:

```text
✅ Backend listo
✅ Visibilidad base lista
🟠 Edición desde UI pendiente
```

La dependencia representa una relación planeada:

```text
Tarea B depende de Tarea A
```

Ejemplo:

```text
Armado de equipos depende de Recepción de equipo de gimnasio en local
```

---

## 9.2 Dependencias editables desde panel lateral

Estado:

```text
🟠 SIGUIENTE FASE FUNCIONAL
```

Regla propuesta:

```text
Click en tarea del Gantt
→ abre panel lateral
→ sección “Esta tarea depende de”
→ botón “Agregar dependencia”
→ seleccionar tarea requerida
→ guardar
→ la dependencia queda registrada y auditada
```

Debe permitir:

```text
agregar dependencia
eliminar dependencia
evitar dependencia consigo misma
evitar duplicados
mostrar tarea bloqueante/requerida
```

No debe incluir todavía:

```text
drag & drop entre barras
líneas visuales avanzadas
reprogramación automática
ruta crítica
```

---

# 10. Bloqueos operativos

Estado:

```text
🟠 DEFINIDO PARA SIGUIENTE FASE
```

Diferencia conceptual:

```text
Dependencia = relación planeada
Bloqueo = problema activo
```

Ejemplo de dependencia:

```text
Armado de equipos depende de Recepción de equipo.
```

Ejemplo de bloqueo:

```text
Armado de equipos está bloqueado porque el equipo no ha llegado al local.
```

El botón actual de bloquear no debe quedarse como solo cambio de estado.

Regla futura:

```text
Bloquear tarea debe pedir causa.
```

Causas posibles:

```text
Otra tarea del proyecto
Proveedor
Pago / presupuesto
Permiso / licencia
Documento pendiente
Decisión pendiente
Otro
```

Campos sugeridos:

```text
blocked_task_id
blocker_type
blocking_task_id
reason
impact_level
status
created_by_user_id
resolved_by_user_id
created_at
resolved_at
```

Cuando existan notificaciones:

```text
Si una tarea se bloquea por otra tarea:
→ notificar responsable de la tarea bloqueante
→ notificar responsable de la tarea bloqueada
→ notificar líder de apertura
→ registrar auditoría
```

---

# 11. Creación de nuevas tareas

Estado actual:

```text
✅ Crear tarea existe
🟡 Mejorar UX a modal flotante
```

Problema actual:

```text
El formulario plano ocupa espacio permanente dentro de la pantalla.
Compite contra el Gantt y el detalle operativo.
```

Regla propuesta:

```text
La creación de nuevas tareas debe ejecutarse desde un modal flotante.
```

Flujo esperado:

```text
Botón “Nueva tarea”
→ abre modal
→ capturar datos
→ guardar
→ cerrar modal
→ refrescar Gantt
```

También debe poder abrirse desde una fase:

```text
Fase → + Tarea
```

Al abrir desde una fase:

```text
la fase debe venir preseleccionada
```

Campos mínimos:

```text
Título
Fase
Fecha inicio
Fecha compromiso
Prioridad
Responsable
Descripción
Requiere documento
Requiere pago
```

---

# 12. Checklist y subtareas

Estado:

```text
🔵 ROADMAP / FUTURO
```

Decisión técnica actual:

```text
Primero checklist por tarea.
Después subtareas reales si el proceso lo exige.
```

No se recomienda simular subtareas como tareas normales con prefijo visual.

Motivo:

```text
ensucia reportes
confunde avance
rompe orden
complica dependencias
debilita auditoría
```

Fase recomendada:

## Fase 1: Checklist por tarea

Ejemplo:

```text
Remodelación
☐ Demolición
☐ Piso
☐ Pintura
☐ Baños
☐ Espejos
☐ Eléctrico
☐ Entrega final
```

Tabla futura sugerida:

```text
opening_task_checklist_items
```

Campos:

```text
id
opening_id
task_id
title
status
sort_order
completed_at
completed_by_user_id
created_at
updated_at
```

## Fase 2: Subtareas reales

Solo si se requiere:

```text
parent_task_id en opening_tasks
```

Esto implicaría decidir:

```text
si el avance padre se calcula desde hijas
si las hijas tienen dependencias
si las hijas tienen comentarios
si aparecen en dashboard
si heredan fechas
si pueden bloquear/desbloquear tareas
```

---

# 13. Edición de fechas con preview de impacto

Estado:

```text
🟠 DEFINIDO PARA SIGUIENTE FASE
```

Objetivo:

```text
Permitir modificar fechas de una tarea mostrando antes el impacto sobre tareas dependientes.
```

Regla:

```text
El sistema no debe reprogramar automáticamente en primera versión.
Debe mostrar impacto y pedir confirmación.
```

Ejemplo:

```text
Tarea: Remodelación
Fecha actual: 15 jun → 25 jul
Nueva fecha: 20 jun → 28 jul
```

Preview esperado:

```text
Impacto crítico:
- Armado de equipos inicia el 13 jul, pero depende de Remodelación que terminaría el 28 jul.
- Pruebas de equipos inicia el 21 jul, pero la tarea previa terminaría el 28 jul.

Impacto moderado:
- Limpieza profunda queda con poco margen antes de apertura.
```

Tipos de alerta:

```text
Crítica:
La tarea dependiente queda programada antes de que termine su predecesora.

Moderada:
No rompe dependencia, pero reduce margen operativo.

Informativa:
El cambio no rompe nada, pero modifica el plan.
```

Orden recomendado:

```text
1. Dependencias editables
2. Edición de fechas
3. Preview de impacto
4. Guardar con auditoría
5. Futuro: guardar y notificar
```

---

# 14. Notificaciones

Estado:

```text
🔵 ROADMAP / FUTURO
```

Casos relevantes:

```text
tarea bloqueada
tarea desbloqueada
cambio de fecha con impacto
nueva dependencia
comentario crítico
documento requerido faltante
pago pendiente
aprobación/rechazo
```

Canales posibles:

```text
notificación interna Suite
correo
Telegram operativo
WhatsApp futuro si se decide
```

Regla:

```text
Las notificaciones deben venir después de tener bien definidos dependencias, bloqueos y responsables.
```

---

# 15. Control financiero F2

Estado:

```text
🟠 F2
```

Debe incluir:

```text
presupuesto autorizado por apertura
partidas presupuestales
proveedores
cuentas bancarias
solicitudes de pago
facturas
comprobantes
estatus Finanzas
saldos
```

Flujo conceptual:

```text
Apertura
→ Partida presupuestal
→ Solicitud de pago
→ Proveedor
→ Factura/comprobante
→ Validación Finanzas
→ Programado/Pagado
```

No debe mezclarse de forma desordenada con tareas.

La relación correcta es:

```text
Una tarea puede requerir pago.
Una tarea puede estar vinculada a una solicitud de pago.
Una solicitud de pago pertenece a una partida.
Una partida pertenece al presupuesto de apertura.
```

---

# 16. Control documental vinculado F2/F3

Estado:

```text
🟠 F2/F3
```

Aperturas debe consumir documentos desde Nube Corporativa.

Entidad propuesta:

```text
internal_document_links
```

Debe permitir vincular documentos a:

```text
OPENING
PHASE
TASK
SUCURSAL
PROVIDER
PAYMENT_REQUEST
GENERAL
```

Roles documentales:

```text
PLANO
PERMISO
CONTRATO
COTIZACION
FACTURA
COMPROBANTE
CHECKLIST
EVIDENCIA
MANUAL
FINANCIERO
CONSTRUCCION
OPERACION
```

Reglas:

```text
Un documento puede estar vinculado a múltiples entidades.
Un vínculo puede marcarse como principal/oficial.
La Nube mantiene versión y visibilidad.
Aperturas solo muestra el vínculo y contexto operativo.
```

---

# 17. Permisos

Estado:

```text
✅ Base implementada
🟠 Refinamiento futuro por roles específicos
```

Roles actuales de administración/lectura:

```text
ADMIN
ADMINISTRADOR
SUPER_ADMIN
SISTEMAS
APERTURAS_ADMIN
APERTURAS_MANAGER
APERTURAS_COLABORADOR
APERTURAS_FINANZAS
APERTURAS_LECTOR
GERENTE_REGIONAL
LECTOR_GLOBAL
```

Regla:

```text
El backend es la fuente real de permisos.
El frontend solo oculta o guía la UI.
```

Pendiente futuro:

```text
permisos por apertura
permisos por área
permisos financieros separados
permisos de aprobación
permisos de bloqueo/desbloqueo
permisos de edición de fechas
```

---

# 18. Riesgos y decisiones pendientes

## Riesgo 1: Que el módulo se vuelva otro Excel visual

Mitigación:

```text
Gantt ejecutivo
panel lateral
modales
fases contraídas
acciones contextuales
menos formularios planos
```

Estado:

```text
🟡 En polish UX
```

---

## Riesgo 2: Dependencias sin gobierno

Si las dependencias se agregan sin claridad, pueden confundir.

Mitigación:

```text
Nombrar claramente “Esta tarea depende de”
evitar duplicados
evitar dependencia consigo misma
auditar cambios
```

Estado:

```text
🟠 Pendiente UI
```

---

## Riesgo 3: Botón bloquear incompleto

Bloquear solo como estado rojo no basta.

Mitigación:

```text
Convertir bloqueo en evento operativo con causa, impacto y responsable.
```

Estado:

```text
🟠 Definido para siguiente fase
```

---

## Riesgo 4: Subtareas mal modeladas

Crear subtareas como tareas falsas ensucia el sistema.

Mitigación:

```text
Primero checklist por tarea.
Después tareas hijas reales si se requiere.
```

Estado:

```text
🔵 Roadmap
```

---

## Riesgo 5: Reprogramación automática peligrosa

Mover fechas automáticamente puede romper acuerdos reales.

Mitigación:

```text
Primero preview de impacto.
No mover automáticamente sin confirmación.
```

Estado:

```text
🟠 Definido para siguiente fase
```

---

# 19. Orden recomendado de implementación desde este punto

## F1 Polish UX inmediato

Estado:

```text
🟡 EN CURSO
```

Prioridad:

```text
1. Gantt abre por default
2. Fases contraídas por default
3. Ocultar/mostrar tareas completadas
4. Header de fechas sticky
5. Columna Elemento fija sin encimarse
6. Crear tarea desde modal flotante
```

---

## F1.1 Operación viva

Estado:

```text
🟠 SIGUIENTE FASE FUNCIONAL
```

Prioridad:

```text
1. Dependencias editables desde panel lateral
2. Eliminar dependencias desde panel lateral
3. Bloqueos operativos con causa
4. Edición de fechas con preview de impacto
5. Auditoría reforzada de cambios operativos
```

---

## F2 Financiero

Estado:

```text
🟠 F2
```

Prioridad:

```text
1. Presupuesto autorizado
2. Partidas
3. Proveedores
4. Solicitudes de pago
5. Facturas/comprobantes
6. Estatus Finanzas
7. Saldos por partida
```

---

## F3 Documental vinculado

Estado:

```text
🟠 F3
```

Prioridad:

```text
1. Vincular documentos desde Nube a apertura/fase/tarea
2. Marcar documento oficial/principal
3. Mostrar documentos críticos faltantes
4. Evidencias por tarea
5. Historial documental contextual
```

---

## F4 Notificaciones y alertas

Estado:

```text
🔵 ROADMAP
```

Prioridad:

```text
1. Notificar bloqueo
2. Notificar cambio de fecha con impacto
3. Notificar tarea crítica atrasada
4. Notificar documento faltante
5. Notificar pago pendiente
6. Integración Telegram/correo
```

---

# 20. Criterio de cierre F1

F1 puede considerarse cerrada cuando:

```text
✅ Existe apertura vinculada a sucursal.
✅ Existen fases.
✅ Existen tareas.
✅ Existen fechas.
✅ Existe Gantt visual.
✅ El Gantt abre en contexto del día actual.
✅ La fila de fechas permanece visible.
✅ La columna Elemento permanece visible.
✅ El panel lateral no estorba cuando no se usa.
✅ Se pueden ver comentarios.
✅ Se pueden ver dependencias existentes.
✅ Se puede crear nueva tarea sin saturar la pantalla.
✅ Se puede usar Serranía como caso real de demostración.
✅ La UI se entiende en menos de 30 segundos.
```

Estado actual:

```text
✅ Gran parte de F1 ya está implementada.
🟡 Faltan polish UX menores antes de considerar F1 presentable.
```

---

# 21. Mensaje ejecutivo para presentar

Suite Ultra Aperturas no es un Gantt aislado.

Es la base de un sistema interno para controlar aperturas de sucursales completas, conectando operación, fechas, responsables, presupuesto, pagos, proveedores, documentos y trazabilidad.

La primera versión ya permite convertir un cronograma real como Serranía en una vista operativa dentro de Suite. El siguiente paso no es hacer “más pantallas”, sino cerrar el ciclo operativo:

```text
planear
asignar
bloquear
depender
ajustar fechas
medir impacto
documentar
pagar
auditar
notificar
```

Esto permite que futuras aperturas como Egade no dependan únicamente de WhatsApp, archivos dispersos y seguimiento manual.
