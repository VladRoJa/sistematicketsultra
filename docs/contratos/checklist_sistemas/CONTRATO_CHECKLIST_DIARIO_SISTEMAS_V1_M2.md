# Contrato — Checklist Diario de Sistemas V1 / M2
## Captura responsive, evidencias y gate de uso

Estado: ACCEPTED TÉCNICAMENTE — PR #830 pendiente de merge a `main`
Gate de entrada: CUMPLIDO — M1 ACCEPTED en `main`.
Gate de salida: CUMPLIDO técnicamente; M3 permanece bloqueado hasta que M2 esté mergeado en `main`.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar **únicamente M2**.

Antes de tocar código:

1. inspeccionar main;
2. confirmar M1 ACCEPTED;
3. probar endpoints reales de status/postpone/submit;
4. revisar routing, layout, guards e interceptors vigentes;
5. revisar patrón actual de uploads/adjuntos;
6. explicar un cambio y una prueba a la vez.

Está prohibido adelantar:

- dashboard BI;
- rankings/tendencias;
- bridge automático a Tickets V2.

## 1. Objetivo

Entregar una experiencia diaria extremadamente simple para el usuario piloto autorizado.

Durante el MVP, esta experiencia solo se habilita a SISTEMAS y ADMICORP. GERENTE no debe verla ni quedar sujeto a enforcement.

Flujo:

```text
Login
  ↓
¿check de hoy completado?
  ├─ sí → Suite normal
  └─ no
      ↓
    mostrar check
      ├─ completar
      └─ aplazar si backend lo permite
```

Después del segundo aplazamiento y vencidos 5 minutos:

```text
check pendiente
   ↓
mandatory = true
   ↓
no se puede continuar usando Suite
hasta submit válido
```

## 2. Principio UX

> El usuario que realiza el checklist solo debe decidir si algo sirve o no.

La UX se diseña para el futuro gerente, pero el rollout MVP permanece restringido a SISTEMAS/ADMICORP.

La interfaz no debe exponer:

- árbol técnico;
- causa probable;
- pieza;
- componente interno;
- diagnóstico;
- campos innecesarios.

## 3. Mobile-first

La pantalla debe diseñarse primero para teléfono.

Requisitos:

- controles táctiles grandes;
- lectura rápida;
- una mano;
- scroll vertical natural;
- sin tablas horizontales;
- sin hover como requisito;
- cámara/archivo accesible desde móvil;
- rendimiento razonable en red móvil.

Desktop reutiliza el mismo componente responsive.

## 4. Estructura visual

La captura debe agrupar preguntas por bloques claros:

- Equipo de cómputo;
- Conectividad y sistemas;
- Control de acceso;
- Sistemas auxiliares.

Cada pregunta muestra opciones visibles:

- Sí;
- No;
- No aplica.

No usar un select si tres botones/chips ofrecen mejor velocidad.

Ninguna opción preseleccionada.

## 5. Progreso

La UI debe comunicar progreso, por ejemplo:

```text
8 de 13 revisados
```

No debe permitir submit si faltan preguntas.

La lógica de validez principal vive también en backend.

## 6. Comportamiento de NO

Al seleccionar NO, la misma pregunta o un panel inmediatamente asociado muestra el detalle de incidencia.

Campos:

- Uno / Varios, solo si aplica;
- ¿Reportado a Soporte? Sí / No;
- descripción breve;
- evidencia opcional.

Texto de ayuda:

> No necesitas identificar la causa técnica.

No enviar al usuario a otra pantalla técnica.

## 7. Cambio de NO a YES/NA

Si el usuario cambia una respuesta NO a YES o NA antes de enviar:

- la UI debe ocultar detalle;
- no debe enviar una incidencia huérfana;
- decidir si conserva temporalmente el texto en memoria durante la edición solo si no genera confusión;
- backend sigue siendo autoridad y no debe persistir issue para YES/NA.

## 8. Evidencias

M2 implementa carga/adjunto según infraestructura definida en M1.

Requisitos:

- foto desde móvil;
- archivo existente;
- feedback de carga;
- error recuperable;
- evidencia asociada a la incidencia correcta;
- no confundir archivos entre dos NO diferentes.

La evidencia sigue siendo opcional.

## 9. Primera presentación

Cuando status backend indique:

```text
completed = false
can_postpone = true
mandatory = false
```

la UI presenta:

- Realizar ahora;
- Ahora no.

El copy debe comunicar que es una revisión breve.

## 10. Primer aplazamiento

Al tocar `Ahora no`:

1. llamar endpoint backend;
2. esperar confirmación;
3. ocultar flujo;
4. respetar `next_prompt_at`.

No calcular autoridad únicamente con un timer frontend.

La UI puede usar timer para UX, pero al momento de decidir debe consultar/obedecer backend.

## 11. Segunda presentación

Cuando vuelve a ser elegible y aún puede aplazar:

- mostrar checklist;
- indicar de forma discreta que queda un último aplazamiento;
- permitir `Ahora no` una vez más.

No crear mensajes alarmistas.

## 12. Segundo aplazamiento

Después del segundo postpone:

- Suite puede continuar hasta `mandatory_from_at`;
- al vencerse debe volver a consultar estado;
- desde mandatory, entra gate obligatorio.

No asumir que el navegador permaneció abierto exactamente 5 minutos.

## 13. Tercera presentación / mandatory

Cuando backend indique `mandatory = true`:

- no mostrar `Ahora no`;
- no permitir cerrar;
- ESC no cierra;
- click exterior no cierra;
- navegación normal no debe saltarlo;
- refresh no lo evade;
- logout/login posterior no reinicia estado;
- otra ruta directa no lo evade.

El usuario debe poder:

- contestar;
- adjuntar evidencia;
- enviar;
- recuperarse de errores de red.

No se debe dejar atrapado por un error técnico irrecuperable.

## 14. Modal vs pantalla

La implementación puede usar modal full-screen, overlay o ruta dedicada.

Debe elegirse la solución más robusta tras inspeccionar Angular actual.

Criterio:

> mandatory debe bloquear navegación funcional sin romper auth ni crear loops.

No elegir un modal pequeño si degrada móvil.

## 15. Integración con login/layout y rollout MVP

Revisar:

- `frontend/src/app/layout/layout.component.ts`;
- auth/session services;
- guards;
- interceptors;
- app.routes;
- hash routing.

No introducir un tercer origen de token.

No duplicar lógica de sesión si ya existe una fuente canónica.

Durante el MVP:

- solo SISTEMAS/ADMICORP elegibles reciben la evaluación diaria;
- GERENTE no debe disparar status/postpone/mandatory;
- ocultar menú en frontend no es suficiente: backend debe negar el acceso;
- no implementar el rollout a GERENTE detrás de una condición frontend fácil de activar;
- la futura apertura debe realizarse mediante una política/configuración backend explícita y testeada.

## 16. Evitar loops

Casos a probar:

- login -> status pendiente;
- status endpoint 401;
- submit exitoso;
- submit falla 400;
- submit falla 500;
- refresh en mandatory;
- navegación usando back;
- deep link;
- logout voluntario;
- login de otro usuario;
- login GERENTE durante MVP -> Suite normal, sin checklist;
- login SISTEMAS/ADMICORP elegible -> aplica flujo según status.

No crear un guard que bloquee también los endpoints/pantallas necesarias para resolver el checklist.

## 17. Estado local

Frontend puede mantener estado efímero de formulario.

No puede ser autoridad para:

- postpone_count;
- can_postpone;
- mandatory;
- business_date;
- completed.

Esos valores vienen del backend.

## 18. Submit

Antes de submit:

- las 14 preguntas respondidas;
- cada NO tiene detalle requerido;
- estado general seleccionado/derivado;
- uploads terminados o marcados con error.

El body no debe usar branch_id/usuario/fecha como autoridad.

## 19. Estado general UX

Si no hay NO:

- UI puede fijar/sugerir Operación normal.

Si hay NO:

- mostrar:
  - Falla menor, operación continúa;
  - Falla que afecta la operación.

No permitir NORMAL visualmente si hay NO, pero backend valida igualmente.

## 20. N/A

NO APLICA debe ser visible pero no convertirse en escape automático.

M2 no inventa reglas adicionales de cuándo aplica N/A salvo contrato.

El BI distinguirá NA de YES.

## 21. Accesibilidad y claridad

Requisitos razonables:

- labels legibles;
- estados seleccionados evidentes;
- no depender solo del color;
- foco usable;
- mensajes de error junto al campo;
- botones con tamaño táctil adecuado.

## 22. Pruebas frontend mínimas

### Render

- 14 preguntas;
- agrupaciones correctas;
- sin preselección.

### Validación

- no submit incompleto;
- NO muestra detalle;
- YES/NA ocultan detalle;
- múltiples NO mantienen detalles independientes.

### Postpone

- primera aparición permite aplazar;
- primer postpone desaparece tras backend OK;
- segunda elegible permite último postpone;
- después de segundo no inventa un tercero;
- mandatory elimina botón.

### Gate

- mandatory no cierra con ESC;
- no cierra por backdrop;
- navegación interna no evade;
- refresh conserva enforcement al reconsultar backend.

### Responsive

Probar tamaños representativos:

- móvil angosto;
- móvil estándar;
- tablet;
- desktop.

## 23. Pruebas de integración

M2 debe comprobar contra backend real de test:

- status -> UI;
- postpone -> status actualizado;
- submit -> completed;
- invalid submit -> errores;
- evidencia -> issue correcto.

## 24. Manejo de red

Si falla postpone:

- no asumir que fue exitoso;
- reconsultar estado si el resultado es ambiguo.

Si falla submit:

- preservar formulario local en lo razonable;
- no marcar completed;
- permitir retry seguro según contrato M1.

## 25. Privacidad / evidencia

No mostrar evidencias de otra incidencia por errores de indexación.

No exponer rutas físicas del servidor.

Respetar permisos backend para lectura/descarga.

## 26. Fuera de alcance M2

- dashboard global;
- rankings;
- tendencias;
- export BI;
- SLA;
- creación automática de tickets;
- diagnóstico;
- cambios al catálogo técnico salvo necesidad explícita aprobada.

## 27. Gate de salida

M2 queda ACCEPTED solo si:

1. captura de 14 preguntas funciona;
2. responsive móvil/escritorio validado;
3. NO genera UI de detalle sencilla;
4. evidencia queda ligada correctamente;
5. primer y segundo postpone funcionan;
6. separación de 5 min se respeta mediante backend;
7. mandatory no puede evadirse por navegación normal;
8. submit exitoso libera gate;
9. errores de red no dejan estado falso;
10. GERENTE no ve ni sufre el gate durante MVP;
11. SISTEMAS/ADMICORP sí respetan el gate;
12. pruebas frontend/integración están verdes.

### 27.1 Decisiones implementadas

- La captura vive en un componente standalone full-screen montado dentro de `LayoutComponent`, no en un route guard ni en un `MatDialog`. Esto permite cubrir deep-links autenticados sin crear loops de navegación o de autenticación.
- El frontend reutiliza `SessionService` y los interceptors existentes. M2 no introduce otro origen de token ni autoridad local para `postpone_count`, `mandatory`, `business_date` o `completed`.
- Durante el MVP, únicamente SISTEMAS/ADMICORP candidatos inicializan el flujo en frontend; backend sigue siendo la autoridad y rechaza perfiles fuera del piloto. GERENTE, ADMINISTRADOR genérico y TECNICO permanecen fuera.
- Para el piloto, un usuario autorizado puede seleccionar una sucursal existente cuando su sesión no trae una sucursal válida. Esta selección es contexto de QA/MVP y no amplía permisos. La futura apertura a GERENTE debe retirar esa libertad y aplicar el scope contratado para gerencia.
- Las evidencias se envían dentro del mismo `today/submit`: JSON puro cuando no hay archivos o `multipart/form-data` con `payload` + campos `evidence__<question_key>`. No se crean drafts ni adjuntos huérfanos previos al submit.
- La evidencia se valida por contenido y no solo por extensión: JPG/JPEG, PNG, WEBP y PDF, máximo 15 MB, SHA-256, `storage_key` restringido al árbol del checklist y cleanup físico cuando la transacción falla.
- Cada archivo se liga a la incidencia de su `question_key`; evidencia sobre una respuesta sin incidencia/NO se rechaza y hace rollback.
- El gate usa `cdkTrapFocus`, bloquea scroll de fondo y queda sobre las capas normales de Suite. La reautenticación por sesión expirada conserva una capa superior temporal para evitar que un mandatory impida renovar la sesión.
- Si todavía no se conoce el estado diario y falla la consulta técnica, el flujo no bloquea Suite indefinidamente y reintenta. Si ya se conocía `mandatory=true`, una falla posterior de red conserva el gate hasta recuperar conexión.
- La máquina de estados visible se deriva del status backend: completado libera Suite; espera de aplazamiento oculta y programa reconsulta; mandatory fuerza captura; una reconsulta no borra respuestas si el usuario ya empezó.
- No se implementó BI, historial visual ni bridge a Tickets V2 en M2.

### 27.2 Evidencia de aceptación

- Suite local `backend/tests/system_daily_check`: `56 passed, 1 skipped`; el único skip requiere PostgreSQL dedicado y se ejecuta en CI.
- La suite incluye pruebas de evidencia/multipart mediante `Flask.test_client`, validación por contenido, asociación por `question_key` y cleanup transaccional.
- Prueba frontend pura y tipada de la máquina de estados y rollout del gate: compilación TypeScript + ejecución Node con exit code 0; SISTEMAS/ADMICORP entran al MVP y GERENTE/ADMINISTRADOR genérico permanecen fuera.
- Angular completo después de integración en `LayoutComponent`, hardening de focus/layers y refactor de estado: `EXITCODE:0`.
- GitHub Actions `System Daily Check M2`: SUCCESS sobre el head de implementación `83855a77`; incluye backend PostgreSQL 16, prueba frontend de estados/rollout y Angular build.
- GitHub Actions `System Daily Check M1` sobre el mismo head `83855a77`: SUCCESS.
- Smoke de `create_app()`: exactamente cuatro rutas `/api/system-daily-checks` registradas.
- Smoke backend de rollout MVP: SISTEMAS y ADMICORP elegibles; GERENTE, ADMINISTRADOR genérico y TECNICO no elegibles; exit code 0.
- `git diff --check`: sin errores antes del commit documental de aceptación.
- PR #830 verificado `mergeable=true` contra `main` sobre el head `83855a77` antes del commit documental de aceptación.

## 28. Estado final esperado

```text
M1 — ACCEPTED EN MAIN
M2 — ACCEPTED EN MAIN
M3 — ACCEPTED EN MAIN
```
