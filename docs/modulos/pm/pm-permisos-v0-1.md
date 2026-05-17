# PM Permisos v0.1 — Suite Ultra

## Objetivo

Definir una primera matriz de permisos para Mantenimiento Preventivo.

PM no debe depender solo de que el usuario tenga acceso a una sucursal. También debe validar qué tipo de acción quiere realizar.

---

## Principio

El backend es la fuente real de permisos.

El frontend puede ocultar botones o guiar al usuario, pero nunca debe ser la única protección.

---

## Acciones PM

PM se divide en cuatro acciones principales:

1. Consultar PM.
2. Ejecutar bitácora PM.
3. Validar bitácora PM.
4. Configurar programación PM.

---

## Scope por sucursal

Todas las acciones PM deben respetar scope por sucursal.

La fuente de scope será:

```text
scope_utils.py