# Suite Ultra Core v0.1 — Caja de la Verdad

## Objetivo

Definir la primera versión del modelo núcleo de Suite Ultra.

Este documento establece qué entidades deben funcionar como fuente oficial de verdad para los módulos operativos y de BI de la plataforma.

La intención es evitar que cada módulo cree su propia interpretación de usuarios, sucursales, departamentos, activos o permisos.

---

## Principio rector

Suite Ultra debe crecer sobre datos maestros confiables.

Los módulos pueden tener lógica específica, pero deben apoyarse en las mismas entidades base:

- Usuarios.
- Departamentos.
- Sucursales.
- Inventario general.
- Inventario por sucursal.
- Relaciones usuario-sucursal.
- Permisos por acción.

---

## Módulos afectados

Este modelo núcleo impacta principalmente a:

- Tickets.
- Inventario.
- Mantenimiento Preventivo.
- Warehouse.
- Track / BI.

---

## No alcance de v0.1

Esta fase no busca rehacer toda la Suite.

No se modificará todavía:

- Track branch catalog.
- Track branch aliases.
- Alias externos de Gasca, Wellhub, TotalPass o manual targets.
- Contratos actuales de Track.
- Contratos actuales de Tickets.
- Payloads existentes de frontend.
- Estructura completa de permisos.
- Modelos históricos ya usados por producción.

Track se revisará en una fase posterior, cuando se abra el refactor específico de canonicidad y alias.

---

## Fuentes oficiales v0.1

### Usuarios

Tabla esperada:

```text
users
```

Debe ser la fuente oficial para:

- Identidad del usuario.
- Rol.
- Sucursal principal.
- Departamento.
- Relación con sucursales asignadas.
- Auditoría de acciones.

Módulos que dependen de usuarios:

- Tickets.
- PM.
- Inventario.
- Warehouse.
- Track en acciones manuales o auditoría futura.

---

### Departamentos

Tabla esperada:

```text
departamentos
```

Debe ser la fuente oficial para:

- Departamento del usuario.
- Clasificación operativa.
- Permisos funcionales cuando aplique.

Riesgo detectado:

- `users.department_id` debe apuntar a `departamentos.id`.
- El modelo actual puede permitir `department_id` sin FK real.
- `departamentos.nombre` puede aceptar duplicados si no hay restricción.

Decisión v0.1:

- Auditar datos antes de agregar FK.
- No cambiar contratos de Tickets todavía.
- Preparar migración segura si los datos están limpios.

---

### Sucursales

Tabla esperada:

```text
sucursales
```

Debe ser la fuente oficial para:

- Sucursal operativa.
- Scope por sucursal.
- Relación con inventario.
- Relación con PM.
- Relación futura con Track.

Módulos que dependen de sucursales:

- Tickets.
- PM.
- Inventario.
- Warehouse cuando haya reportes por sucursal.
- Track en una fase posterior.

Riesgo detectado:

- Algunos módulos pueden usar strings o catálogos paralelos.
- Track actualmente tiene su propia canonicidad de sucursales.
- PM bitácoras deben tener FK real a sucursales.

Decisión v0.1:

- No tocar Track todavía.
- Reforzar PM contra `sucursales.sucursal_id`.
- Mantener compatibilidad con Tickets.

---

### Inventario general

Tabla esperada:

```text
inventario_general
```

Debe ser la fuente oficial para:

- Activo o producto global.
- Nombre del activo.
- Código interno.
- Categoría.
- Tipo.
- Metadata general del inventario.

Módulos que dependen de inventario general:

- Inventario.
- Tickets.
- PM.

Riesgo detectado:

- `inventario_general` mezcla activos físicos, productos, consumibles y posibles refacciones.
- No todo inventario debería ser elegible para PM.

Decisión v0.1:

- No separar todavía activos/productos.
- PM debe validar que el inventario exista y pertenezca a sucursal.
- En fase posterior se podrá definir elegibilidad PM por tipo/categoría.

---

### Inventario por sucursal

Tabla esperada:

```text
inventario_sucursal
```

Debe ser la fuente oficial para:

- Relación activo/producto con sucursal.
- Existencia del activo en una sucursal.
- Scope operativo de inventario.
- Base para PM por sucursal.

Riesgo detectado:

- Puede no existir restricción única sobre `inventario_id + sucursal_id`.
- Si existen duplicados, PM puede validar contra una relación ambigua.

Decisión v0.1:

- Auditar duplicados antes de migrar.
- Agregar restricción única si los datos están limpios.
- No migrar PM todavía a `inventario_sucursal_id`, pero dejarlo como dirección futura.

---

## Relación con Tickets

Tickets ya usa:

- Usuario.
- Departamento.
- Sucursal.
- Inventario.
- Estados de atención.
- Flujos de cierre.

Regla v0.1:

- No romper Tickets.
- No renombrar campos usados por Tickets.
- No cambiar payloads existentes.
- No cambiar permisos de Tickets en esta fase.
- Cualquier FK nueva debe validar primero datos existentes.

Tickets debe seguir funcionando mientras se fortalece el core.

---

## Relación con PM

PM debe montarse sobre el core de forma estricta.

PM depende de:

- Usuario ejecutor.
- Usuario validador.
- Sucursal.
- Inventario asignado a sucursal.
- Configuración preventiva.
- Bitácora.
- Validación.

Riesgos detectados:

- `pm_bitacoras.sucursal_id` debe tener FK a `sucursales`.
- `resultado` debe restringirse a valores válidos.
- `tipo_mantenimiento` debe restringirse a valores válidos.
- Deben evitarse duplicados preventivos operativos.
- Deben separarse permisos de ejecutar, validar y configurar.
- Debe evitarse autovalidación.
- Debe conservarse trazabilidad.

Decisión v0.1:

- Antes de rediseñar frontend PM, reforzar backend y migraciones base.
- PM no debe crecer sobre datos sucios o permisos ambiguos.

---

## Relación con Warehouse

Warehouse almacena reportes, archivos y snapshots.

Warehouse puede seguir teniendo catálogos propios de fuentes/reportes:

- Sources.
- Families.
- Operational roles.
- Report types.
- Uploads.
- Audit logs.

Regla v0.1:

- Warehouse no reemplaza la caja de verdad.
- Warehouse guarda fuentes externas y documentos.
- Cuando un reporte tenga sucursal, deberá resolverse eventualmente contra sucursal oficial.

---

## Relación con Track

Track actualmente maneja canonicidad propia mediante:

- Branch catalog.
- Branch aliases.
- Familias de fuentes.
- Nombres externos.

Regla v0.1:

- No tocar Track en esta fase.
- No romper alias actuales.
- No forzar migración ahora.
- Preparar el core para que, en una fase futura, Track pueda apuntar a `sucursales.sucursal_id`.

Dirección futura:

```text
track_branch_catalog.sucursal_id nullable FK → sucursales.sucursal_id
```

Pero esto pertenece a una fase posterior.

---

## Reglas de scope por sucursal

Debe existir una regla común para resolver qué sucursales puede ver o modificar un usuario.

Regla objetivo:

```text
1. Roles globales pueden acceder a todas las sucursales.
2. Usuarios con sucursales asignadas usan esa lista.
3. Usuarios sin lista asignada usan su sucursal principal.
4. El backend siempre debe validar el scope.
5. El frontend solo guía u oculta UI, no protege realmente.
```

Módulos que deben usar esta regla:

- Tickets.
- PM.
- Inventario.
- Warehouse si aplica.
- Track si en el futuro se agregan permisos por sucursal.

---

## Migraciones candidatas v0.1

Estas migraciones no deben ejecutarse sin auditoría previa.

### Candidatas

- FK `users.department_id` → `departamentos.id`.
- FK `pm_bitacoras.sucursal_id` → `sucursales.sucursal_id`.
- Unique `inventario_sucursal(inventario_id, sucursal_id)`.
- Check `pm_bitacoras.resultado IN ('OK', 'FALLA', 'OBS')`.
- Check `pm_bitacoras.tipo_mantenimiento IN ('PREVENTIVO', 'CORRECTIVO', 'ESTETICO', 'MEJORA')`.

---

## Auditorías requeridas antes de migrar

Antes de agregar FKs o constraints, se deben revisar datos existentes.

### Usuarios con departamento inválido

```sql
SELECT u.id, u.username, u.department_id
FROM users u
LEFT JOIN departamentos d ON d.id = u.department_id
WHERE d.id IS NULL;
```

### Inventario por sucursal duplicado

```sql
SELECT inventario_id, sucursal_id, COUNT(*) AS total
FROM inventario_sucursal
GROUP BY inventario_id, sucursal_id
HAVING COUNT(*) > 1;
```

### PM bitácoras con sucursal inexistente

```sql
SELECT p.id, p.sucursal_id
FROM pm_bitacoras p
LEFT JOIN sucursales s ON s.sucursal_id = p.sucursal_id
WHERE s.sucursal_id IS NULL;
```

### PM bitácoras con resultado inválido

```sql
SELECT id, resultado
FROM pm_bitacoras
WHERE resultado NOT IN ('OK', 'FALLA', 'OBS');
```

### PM bitácoras con tipo de mantenimiento inválido

```sql
SELECT id, tipo_mantenimiento
FROM pm_bitacoras
WHERE tipo_mantenimiento NOT IN ('PREVENTIVO', 'CORRECTIVO', 'ESTETICO', 'MEJORA');
```

### PM preventivo duplicado por activo/sucursal/fecha

```sql
SELECT inventario_id, sucursal_id, fecha, tipo_mantenimiento, COUNT(*) AS total
FROM pm_bitacoras
WHERE tipo_mantenimiento = 'PREVENTIVO'
GROUP BY inventario_id, sucursal_id, fecha, tipo_mantenimiento
HAVING COUNT(*) > 1;
```

---

## Orden recomendado

### Fase 1 — Auditoría

Ejecutar queries de auditoría y revisar si hay datos sucios.

### Fase 2 — Limpieza si aplica

Corregir datos antes de aplicar constraints.

### Fase 3 — Migraciones core

Agregar FKs, unique constraints y checks seguros.

### Fase 4 — Helpers de permisos

Centralizar scope por sucursal y permisos PM por acción.

### Fase 5 — PM backend hardening

Normalizar enums, validar duplicados y reforzar flujo.

### Fase 6 — Frontend PM

Diseñar vistas PM sobre backend confiable.

---

## Commits esperados

```text
docs(core): define Suite Ultra core truth model v0.1
chore(core): audit truth model data integrity
feat(core): add truth model database constraints
refactor(core): centralize branch scope helpers
refactor(pm): harden PM permissions and enums
```

---

## Criterio de éxito v0.1

Suite Ultra Core v0.1 se considera listo cuando:

- Las FKs candidatas pueden aplicarse sin romper datos.
- Inventario por sucursal no tiene duplicados.
- PM bitácoras solo aceptan resultados válidos.
- PM bitácoras solo aceptan tipos de mantenimiento válidos.
- PM bitácoras apuntan a sucursales reales.
- Los módulos existentes no se rompen.
- PM puede continuar su diseño frontend sobre una base confiable.