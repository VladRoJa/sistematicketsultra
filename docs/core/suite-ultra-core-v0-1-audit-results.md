# Suite Ultra Core v0.1 — Resultados de auditoría

## Fecha

Auditoría inicial de datos para preparar Caja de la Verdad v0.1.

---

## Resultado general

La auditoría mostró que PM e inventario están suficientemente limpios para avanzar con constraints específicas, pero la relación `users.department_id` todavía no está lista para FK.

---

## Hallazgos limpios

Las siguientes auditorías no regresaron problemas:

- Departamentos duplicados exactos.
- Departamentos duplicados por nombre normalizado.
- Inventario por sucursal duplicado.
- Inventario por sucursal con inventario inexistente.
- Inventario por sucursal con sucursal inexistente.
- PM bitácoras con sucursal inexistente.
- PM bitácoras con inventario inexistente.
- PM bitácoras donde inventario no pertenece a sucursal.
- PM bitácoras con resultado inválido.
- PM bitácoras con tipo de mantenimiento inválido.
- PM preventivo duplicado por activo/sucursal/fecha.
- PM validaciones con bitácora inexistente.
- PM validaciones con usuario validador inexistente.
- PM configuraciones con inventario/sucursal inexistente.
- PM configuraciones duplicadas.

PM actualmente está vacío o contiene solo datos de prueba descartables.

---

## Hallazgo principal: users.department_id = 1000

Se detectaron usuarios con `department_id = 1000`.

Ese valor no existe en `departamentos`.

Usuarios afectados:

- ADMICORP
- FABIAN
- OSCAR
- JULIAN
- EDMUNDO
- ISAIRIS
- FAUSTO
- CARLOSP
- ROBERTO

Conclusión:

`department_id = 1000` es un valor mágico/legacy y no puede recibir FK hacia `departamentos.id` hasta corregirse.

---

## Departamento real esperado

`department_id` debe apuntar siempre a `departamentos.id`.

Departamentos existentes relevantes:

- 8 = Corporativo.
- 9 = Sucursales.

Decisión preliminar:

- ADMICORP debería usar `department_id = 8`.
- LECTOR_GLOBAL corporativos deberían usar `department_id = 8`.
- GERENTE_REGIONAL debería usar `department_id = 9`.

No se aplicará este data-fix hasta centralizar reglas de scope y revisar dependencias.

---

## usuario_sucursal

La tabla `usuario_sucursal` sí está activa.

Auditorías realizadas:

- Sin duplicados.
- Sin usuarios inexistentes.
- Sin sucursales inexistentes.

Conclusión:

`usuario_sucursal` debe considerarse parte de la Caja de la Verdad v0.1 como fuente del scope multi-sucursal.

---

## Semántica definida

### sucursal_id = 1000

Reservado para usuario root/admin técnico.

No debe otorgar acceso global por sí solo.

### sucursal_id = 100

Corporativo operativo.

Puede representar usuarios corporativos, pero el acceso amplio debe depender de rol/permiso y no únicamente del número.

### usuario_sucursal

Fuente oficial para scope operativo multi-sucursal.

### department_id

Departamento real del usuario.

Nunca debe usar `1000`.

---

## Dependencias detectadas de 100 / 1000

Se detectaron checks directos en módulos existentes:

- Tickets.
- Inventario.
- Notificaciones.
- Algunos flujos administrativos.
- Filtros de tickets.
- PM usa principalmente `sucursales_ids`.
- Track autoriza principalmente por rol.

Decisión:

No se deben modificar usuarios ni agregar FK `users.department_id` hasta crear un helper central de scope y migrar los módulos gradualmente.

---

## Decisiones de migración

### Permitido avanzar

- FK `pm_bitacoras.sucursal_id` hacia `sucursales.sucursal_id`.
- Checks de `pm_bitacoras.resultado`.
- Checks de `pm_bitacoras.tipo_mantenimiento`.
- Unique de `inventario_sucursal(inventario_id, sucursal_id)`.

### Pausado

- FK `users.department_id` hacia `departamentos.id`.

Motivo:

Existen usuarios con `department_id = 1000` y módulos que todavía usan valores mágicos 100/1000 para lógica de permisos.

---

## Próximo paso recomendado

Crear helper central de scope:

```text
backend/app/utils/scope_utils.py