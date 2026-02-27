---
trigger: always_on
---

El backend es la autoridad: permisos y filtrado se aplican en el servidor, no solo en UI.

No exponer endpoints que devuelvan datos fuera del scope del usuario.

Cualquier endpoint sensible debe validar: rol + sucursales permitidas (o scope).

Si falta info para validar (tablas/claims), detente y pide contrato antes de codear.