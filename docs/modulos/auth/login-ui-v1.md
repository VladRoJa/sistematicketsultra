# Login UI v1

## Objetivo

Aplicar Suite Ultra UI v1 a la pantalla de login sin modificar la lógica funcional de autenticación.

La pantalla de login debe reflejar la identidad visual oficial de Ultra y funcionar como entrada formal a Suite Ultra.

---

## Alcance

Se aplicará una capa visual nueva a:

- Contenedor principal.
- Card de inicio de sesión.
- Marca Suite Ultra / Ultra Gym.
- Campos de usuario y contraseña.
- Botón de inicio de sesión.
- Estados de carga.
- Mensajes de error si ya existen.
- Fondo visual usando la paleta oficial Ultra.

---

## No alcance

No se modificará:

- Servicio de autenticación.
- Payload de login.
- Endpoint `/api/auth/login`.
- Manejo de JWT.
- SessionService.
- LocalStorage.
- Guards.
- Interceptors.
- Permisos.
- Backend.

---

## Reglas de implementación

- No agregar lógica nueva en HTML.
- No cambiar validaciones existentes.
- No cambiar nombres de controles.
- No cambiar servicios.
- No usar estilos inline.
- Usar tokens globales de Suite Ultra UI v1.
- Mantener componentes en archivos separados `.ts`, `.html` y `.css`.

---

## Archivos esperados

La ruta exacta debe confirmarse antes de modificar, pero probablemente será una de estas:

```text
frontend/src/app/login/login.component.ts
frontend/src/app/login/login.component.html
frontend/src/app/login/login.component.css