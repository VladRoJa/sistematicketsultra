# Contrato Global — Checklist Diario de Sistemas V1

Estado: APROBADO PARA IMPLEMENTACIÓN POR MILESTONES  
Autoridad: este documento define el alcance global de V1.  
Regla de ejecución: **no implementar V1 directamente desde este archivo**. Cada conversación debe trabajar únicamente uno de los contratos M1, M2 o M3.

## 0. Objetivo

Implementar en Suite Ultra un **Checklist Diario de Sistemas por sucursal** para que los gerentes registren, de manera rápida y no técnica, si los sistemas y equipos necesarios para la operación diaria funcionan.

V1 tiene tres objetivos inseparables:

1. detectar y documentar fallas observables;
2. construir trazabilidad histórica;
3. producir BI operativo de salud de Sistemas desde la misma V1.

El módulo debe quedar preparado para integrarse posteriormente con Tickets V2, sin convertir el checklist en un formulario técnico.

## 1. Principio rector

> El checklist valida funcionalidad observable. No diagnostica causas técnicas.

El gerente debe responder únicamente si algo:

- funciona;
- permite trabajar;
- permite realizar la operación esperada.

No se le debe pedir:

- identificar componentes internos;
- diagnosticar causa;
- escoger pieza;
- determinar solución;
- clasificar técnicamente una falla.

La clasificación técnica pertenece a Tickets V2.

## 2. Frontera con Tickets V2

Flujo conceptual:

```text
Checklist diario
      ↓
Respuesta = NO
      ↓
Incidencia estructurada
      ↓
Futuro bridge a Ticket V2
      ↓
Clasificación técnica / atención
```

En V1:

- una respuesta NO crea una incidencia del checklist;
- una incidencia NO crea automáticamente un Ticket V2;
- el checklist puede conservar contexto general del catálogo;
- no se debe obligar al gerente a navegar el catálogo técnico.

## 3. Catálogo de Sistemas / Tickets V2

Las preguntas deben poder asociarse a una categoría general estable del catálogo de Sistemas/Tickets V2.

La asociación sirve para:

- BI;
- trazabilidad;
- futuro bridge.

No se debe depender del texto visible como identidad lógica. Cuando existan IDs estables del catálogo, deben usarse como referencia.

No forzar clasificaciones incorrectas para preguntas que todavía no tengan categoría definitiva, como Gasca o Suite Ultra.

## 4. Usuario objetivo y rollout MVP

Usuario objetivo final del producto:

- GERENTE con alcance sobre una sucursal.

**Rollout MVP inicial:**

- SISTEMAS;
- ADMICORP.

Durante el MVP, únicamente usuarios que el backend reconozca dentro de los perfiles/capacidades efectivas de **SISTEMAS o ADMICORP** pueden:

- ver el módulo;
- recibir el prompt diario;
- aplazar;
- completar el checklist;
- quedar sujetos al gate obligatorio;
- consultar historial/BI según el alcance definido.

Durante el MVP, GERENTE y cualquier otro perfil quedan explícitamente fuera:

- no ven menú ni acceso;
- no reciben prompt;
- no acumulan aplazamientos;
- no pueden quedar bloqueados por mandatory;
- no participan en el denominador operativo del piloto salvo datos QA deliberados.

La autorización real debe validarse en backend.

El frontend puede ocultar o guiar, pero no sustituye permisos backend.

No hardcodear un username como sustituto de una política estable si el modelo actual permite resolver el perfil/capacidad correctamente. M1 debe inspeccionar cómo se representa hoy SISTEMAS y ADMICORP y documentar la fuente de autoridad usada.

### Gate de apertura a gerentes

Terminar M1/M2/M3 **no habilita automáticamente a GERENTE**.

La apertura a gerentes requiere:

1. piloto MVP funcional;
2. validación de Sistemas sobre UX, flujo, bloqueo y BI;
3. aprobación explícita para rollout;
4. cambio de contrato/configuración de acceso;
5. pruebas de permisos antes de producción.

Hasta entonces:

```text
MVP_ACCESS = SISTEMAS | ADMICORP
GERENTE_ACCESS = OFF
```

## 5. Frecuencia y unicidad

Debe existir como máximo un **checklist oficial enviado por sucursal y fecha operativa**.

La fecha operativa debe respetar la política temporal de Suite Ultra y evitar ambigüedades UTC / America/Tijuana.

La unicidad debe protegerse en backend/DB.

## 6. Datos automáticos

No se capturan manualmente:

- sucursal;
- gerente/usuario;
- fecha;
- hora.

Se obtienen de:

- sesión autenticada;
- permisos efectivos;
- backend;
- timestamp del servidor.

Debe conservarse al menos:

- branch_id;
- performed_by_user_id;
- business_date;
- created_at;
- submitted_at.

## 7. Presentación diaria y aplazamiento controlado

Al iniciar sesión, Suite debe consultar el estado del checklist diario **solo para usuarios incluidos en el rollout vigente**.

Durante el MVP:

- SISTEMAS y ADMICORP pueden entrar al flujo;
- GERENTE no debe recibir ninguna consulta/prompt que pueda activar enforcement sobre su sesión.

Si está pendiente, se presenta el flujo.

El usuario piloto puede aplazarlo **máximo dos veces por día**.

Reglas:

1. Primera aparición:
   - puede contestar;
   - puede elegir `Ahora no`.

2. Primer aplazamiento:
   - se registra en backend;
   - no vuelve a mostrarse antes de 5 minutos.

3. Segunda aparición:
   - puede contestar;
   - puede aplazar una última vez.

4. Segundo aplazamiento:
   - se registra en backend;
   - no vuelve a mostrarse antes de 5 minutos.

5. Tercera presentación elegible:
   - el checklist es obligatorio;
   - no existe `Ahora no`;
   - no puede cerrarse;
   - no puede descartarse con ESC/click exterior;
   - no se puede continuar utilizando Suite hasta enviarlo correctamente.

Definición canónica:

> Se permiten dos aplazamientos diarios. Después del segundo aplazamiento y transcurridos cinco minutos, el checklist entra en estado obligatorio.

No interpretar la regla como “tercer login”.

Cerrar sesión, refrescar, cambiar navegador o cambiar de dispositivo no reinicia los aplazamientos.

El contador y los timestamps deben vivir en backend, no únicamente en localStorage.

## 8. UX

La captura debe ser:

- mobile-first;
- responsive;
- rápida;
- visual;
- usable con una mano;
- funcional en escritorio;
- un único flujo, no dos implementaciones separadas.

La UI debe parecer una revisión operativa, no un formulario administrativo largo.

## 9. Respuestas principales

Cada pregunta:

- SÍ;
- NO;
- NO APLICA.

Valores internos sugeridos:

- YES;
- NO;
- NA.

Ninguna respuesta preseleccionada.

Todas las preguntas principales son obligatorias.

## 10. Preguntas V1

### Equipo de cómputo

1. ¿Las computadoras de la sucursal funcionan correctamente?
2. ¿Los monitores, teclados y mouse funcionan?
3. ¿Las impresoras funcionan correctamente?
4. ¿Las terminales bancarias permiten realizar cobros?

### Conectividad y sistemas

5. ¿Las computadoras tienen conexión a internet?
6. ¿Gasca abre y permite realizar las operaciones necesarias?
7. ¿Suite Ultra permite realizar las operaciones necesarias de la sucursal?

### Control de acceso

8. ¿Los torniquetes permiten la entrada y salida?
9. ¿Los lectores de acceso permiten validar correctamente a los usuarios?
10. ¿Las pantallas de los torniquetes funcionan?

### Sistemas auxiliares

11. ¿La música ambiental funciona?
12. ¿Las pantallas/TV funcionan?
13. ¿El sistema de cámaras funciona?

Agregar nuevas preguntas requiere cambio explícito de contrato.

## 11. Alcance semántico

Las preguntas evalúan funcionalidad, no:

- velocidad;
- rendimiento;
- calidad percibida;
- antigüedad;
- apariencia;
- satisfacción.

Ejemplo válido:

> ¿Gasca abre y permite realizar las operaciones necesarias?

Ejemplo no válido:

> ¿Gasca funciona rápido?

## 12. Respuesta NO e incidencia

Cada respuesta `NO` genera su propia incidencia.

No existe un detalle global compartido por varias fallas.

Una incidencia V1 contiene, cuando aplique:

- alcance: UNO / VARIOS;
- reportado a Soporte: SÍ / NO;
- descripción breve obligatoria;
- evidencia opcional;
- timestamps;
- referencia a la respuesta.

La UI debe explicar:

> No necesitas identificar la causa técnica.

El campo UNO/VARIOS solo aplica cuando tenga sentido para la pregunta.

## 13. Evidencia

La evidencia pertenece a una incidencia concreta, no ambiguamente al checklist completo.

Debe permitir al menos:

- fotografía;
- archivo.

En V1 la evidencia es opcional salvo cambio explícito de contrato.

## 14. Estado general

Estados canónicos:

- NORMAL;
- MINOR_FAILURE;
- OPERATIONAL_IMPACT.

Etiquetas:

- Operación normal;
- Falla menor, operación continúa;
- Falla que afecta la operación.

Reglas backend:

- si todas las respuestas son YES/NA → solo NORMAL;
- si existe al menos un NO → NORMAL no es válido.

## 15. Persistencia conceptual

Como mínimo:

```text
daily_system_check
daily_system_check_answer
daily_system_check_issue
daily_system_check_issue_attachment
```

Puede existir persistencia adicional para estado de prompt/aplazamiento si el diseño lo requiere.

Las preguntas deben tener claves estables, por ejemplo:

- COMPUTERS_WORKING;
- PERIPHERALS_WORKING;
- PRINTERS_WORKING;
- BANK_TERMINALS_WORKING;
- INTERNET_WORKING;
- GASCA_WORKING;
- SUITE_ULTRA_WORKING;
- TURNSTILES_WORKING;
- ACCESS_READERS_WORKING;
- TURNSTILE_SCREENS_WORKING;
- AMBIENT_AUDIO_WORKING;
- TV_SCREENS_WORKING;
- CAMERAS_WORKING.

El texto visible puede evolucionar sin romper histórico ni BI.

## 16. Estado de prompt / aplazamiento

El diseño debe persistir de forma auditable al menos la semántica de:

- branch_id;
- business_date;
- postpone_count;
- last_postponed_at;
- next_prompt_at;
- mandatory_from_at o estado equivalente;
- completed_at.

La cardinalidad exacta usuario/sucursal se define en M1 tras revisar el modelo real de sesión y roles, pero debe cumplirse:

- el estado no se reinicia por logout;
- no se reinicia por otro dispositivo;
- no se puede exceder dos aplazamientos válidos;
- el backend decide si todavía puede aplazarse.

## 17. Auditoría

Un checklist enviado no se sobrescribe silenciosamente.

V1 puede optar por no permitir edición posterior.

Si se habilita corrección en el futuro, deberá auditar:

- actor;
- timestamp;
- valor anterior;
- valor nuevo;
- motivo si aplica.

## 18. Historial obligatorio

V1 debe permitir consulta histórica por:

- rango de fechas;
- sucursal;
- estado general;
- pregunta/sistema;
- resultado.

Debe poder abrirse el detalle del checklist y de cada incidencia.

## 19. BI obligatorio en V1

BI no es “posterior” ni “nice to have”.

V1 no se considera terminada sin una vista de **Salud Operativa de Sistemas**.

Debe responder al menos:

- ¿qué sucursales completaron hoy?;
- ¿cuáles siguen pendientes?;
- ¿cuántas están normales?;
- ¿cuáles tienen falla menor?;
- ¿cuáles tienen afectación operativa?;
- ¿qué sistemas fallan hoy?;
- ¿qué sistema falla más?;
- ¿qué sucursal acumula más fallas?;
- ¿las fallas se reportan a Soporte?;
- ¿la tendencia mejora o empeora?

## 20. BI mínimo

### Cumplimiento

- sucursales esperadas;
- checklists completados;
- checklists pendientes;
- % cumplimiento;
- tendencia por día.

### Salud

- % NORMAL;
- % MINOR_FAILURE;
- % OPERATIONAL_IMPACT.

### Fallas

- total de respuestas NO;
- incidencias por pregunta/sistema;
- incidencias por sucursal;
- recurrencia;
- ranking de sistemas con fallas;
- ranking de sucursales con fallas.

### Soporte

- reportadas;
- no reportadas;
- proporción reportada/no reportada.

### Aplazamiento

V1 debe poder medir al menos:

- completado sin aplazar;
- completado después de 1 aplazamiento;
- completado después de 2 aplazamientos;
- entró en modo obligatorio.

### Tiempo

Como mínimo:

- día;
- semana;
- mes.

## 21. Matriz / semáforo

Debe existir una visualización rápida por sucursal.

Semántica:

- VERDE = NORMAL;
- AMARILLO = MINOR_FAILURE;
- ROJO = OPERATIONAL_IMPACT;
- GRIS = pendiente.

Los colores son UX; la lógica depende de estados backend.

## 22. Drill-down

Los agregados BI deben permitir llegar al dato fuente.

Ejemplo:

```text
Cámaras
18 incidencias
    ↓
Sucursales
    ↓
Fechas
    ↓
Checklist
    ↓
Incidencia / evidencia
```

No construir un dashboard desconectado del histórico.

## 23. Fuente de verdad BI

Los indicadores deben poder recalcularse desde:

```text
Checklist
→ Respuestas
→ Incidencias
→ Estado de prompt/aplazamiento
```

No guardar únicamente contadores agregados como sustituto de la fuente.

## 24. Permisos BI

M3 debe definir el alcance de lectura para:

- Sistemas;
- administradores;
- gerencias/regionales si aplica.

La autorización se valida en backend.

No asumir que quien llena el checklist puede consultar todo el BI global.

## 25. Fuera de alcance V1

- diagnóstico técnico;
- reparación;
- asignación automática a técnicos;
- creación automática de Ticket V2;
- clasificación técnica detallada;
- SLA de Tickets V2;
- resolución mediante Tickets V2;
- escalamiento automático;
- evaluación de rendimiento/velocidad;
- integración con proveedores externos;
- agregar preguntas solo porque existan categorías en el catálogo.

## 26. Tres milestones obligatorios

### M1 — Core backend, datos y reglas

Contrato:

`CONTRATO_CHECKLIST_DIARIO_SISTEMAS_V1_M1.md`

Objetivo:

- modelo de datos;
- migraciones Alembic;
- preguntas estables;
- permisos;
- fecha operativa;
- unicidad;
- respuestas/incidencias;
- estado general;
- aplazamiento backend;
- endpoints base;
- pruebas backend.

Gate:

el backend puede determinar de forma autoritativa si una sucursal debe ver el checklist, si puede aplazarlo y persistir un envío válido completo, sin depender de UI.

### M2 — Captura responsive y gate de uso

Contrato:

`CONTRATO_CHECKLIST_DIARIO_SISTEMAS_V1_M2.md`

Objetivo:

- UX mobile-first;
- flujo de respuestas;
- detalles NO;
- evidencia;
- dos aplazamientos;
- espera de 5 minutos;
- tercer prompt obligatorio;
- integración segura con login/routing;
- pruebas frontend/flujo.

Gate:

un usuario piloto autorizado de SISTEMAS/ADMICORP puede completar el flujo en móvil/escritorio y no puede evadir el estado obligatorio mediante navegación normal; un GERENTE no autorizado por el rollout MVP no ve ni sufre el gate.

### M3 — Historial y BI

Contrato:

`CONTRATO_CHECKLIST_DIARIO_SISTEMAS_V1_M3.md`

Objetivo:

- historial;
- filtros;
- detalle;
- dashboard Salud Operativa;
- semáforo;
- tendencias;
- cumplimiento;
- aplazamientos;
- drill-down;
- permisos BI;
- acceptance integral V1.

Gate:

Suite puede responder operacionalmente qué está fallando, dónde, con qué frecuencia y cómo se comporta el piloto. La apertura a gerentes sigue bloqueada hasta aprobación explícita de Sistemas.

## 27. Gates entre milestones

M2 no inicia hasta M1 ACCEPTED en main.

M3 no inicia hasta M2 ACCEPTED en main.

No basta con código parcial.

Cada milestone debe:

1. inspeccionar main;
2. revalidar supuestos;
3. trabajar solo su alcance;
4. ejecutar sus pruebas;
5. declarar acceptance explícita antes de desbloquear el siguiente.

## 28. Regla de evolución

```text
CHECKLIST
¿Qué funciona y qué no?

BI
¿Qué está ocurriendo, dónde y con qué frecuencia?

TICKETS V2
¿Qué falló técnicamente y cómo se atiende?
```

Si una nueva funcionalidad obliga al gerente a diagnosticar técnicamente, debe evaluarse como parte de Tickets V2.

## 29. Resultado esperado de V1

Al terminar M3, V1 debe estar operativa de extremo a extremo **en modo MVP restringido a SISTEMAS/ADMICORP** y permitir responder:

- ¿todas las sucursales hicieron su revisión?;
- ¿cuáles no?;
- ¿qué está fallando hoy?;
- ¿qué sistemas fallan de forma recurrente?;
- ¿qué sucursales concentran incidencias?;
- ¿qué porcentaje se reporta a Soporte?;
- ¿cuántos usuarios piloto aplazan y cuántas veces?;
- ¿la salud operativa mejora o empeora?

## 30. Estado

```text
Checklist Diario de Sistemas V1
GLOBAL — APROBADO
M1 — ACCEPTED EN PR #829 / PENDIENTE MERGE A MAIN
M2 — BLOQUEADO HASTA MERGE DE M1 EN MAIN
M3 — BLOQUEADO POR M2
ROLLOUT GERENTES — BLOQUEADO POR APROBACIÓN DE SISTEMAS
```
