---
trigger: always_on
---

En Angular: toda la lógica va en .ts, nunca en .html.

Prohibido: asignaciones/expresiones complejas en el template; solo bindings simples.

Si se necesita lógica de UI, crear getters/métodos/props en el componente TS o helpers reutilizables.

Siempre indicar archivo y nombre de función/método cuando se proponga un cambio.