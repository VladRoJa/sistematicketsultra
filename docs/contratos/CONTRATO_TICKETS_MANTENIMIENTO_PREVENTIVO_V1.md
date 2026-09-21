# Suite Ultra — Mantenimiento Preventivo integrado a Tickets

**Documento:** Contrato funcional-técnico  
**Versión:** 1.0  
**Fecha:** 18 de septiembre de 2026  
**Estado:** Implementado en PR #655; pendiente de validación ejecutable, merge y despliegue

## 1. Objetivo

Ampliar el módulo actual de **Tickets** para incorporar la planeación, ejecución, seguimiento y análisis de mantenimientos preventivos, sin crear un módulo operativo independiente.

El objetivo del desarrollo es permitir:

- programar mantenimientos preventivos de manera individual o masiva;
- asignarlos a personal de mantenimiento;
- entregar a cada técnico un programa de trabajo usable desde celular;
- bitacorizar la ejecución del mantenimiento;
- conservar la validación actual del gerente mediante el flujo existente de Tickets;
- comparar semanalmente el cumplimiento preventivo contra el comportamiento del mantenimiento correctivo;
- mantener trazabilidad de reprogramaciones, compromisos, backlog y hallazgos;
- permitir navegación desde cualquier indicador hasta el ticket que lo origina.

Principio rector:

> **El ticket continúa siendo la unidad operativa de mantenimiento.**

El preventivo no crea un sistema paralelo. Es un ticket de mantenimiento cuyo origen es una programación.

## 2. Alcance conceptual

Los tickets de mantenimiento deberán clasificarse como:

- `CORRECTIVO`
- `PREVENTIVO`

Los correctivos corresponden al flujo actual de Tickets.

Los preventivos nacen desde una nueva capa de **Programación Preventiva**, pero una vez publicados se convierten en tickets reales y utilizan las capacidades existentes del módulo:

- sucursal;
- equipo;
- responsable;
- evidencia;
- comentarios;
- estados;
- historial;
- validación del gerente;
- permisos;
- cierre.

No deberán existir registros preventivos operativos desconectados del ticket.

## 3. Convivencia con el PM actual

Suite Ultra ya cuenta con infraestructura relacionada con Mantenimiento Preventivo.

El nuevo desarrollo deberá evitar mantener dos fuentes de verdad.

Regla:

> **Tickets será la fuente operativa oficial del mantenimiento programado.**

Antes de eliminar o reemplazar cualquier parte del PM existente deberá auditarse qué funcionalidades actuales pueden reutilizarse.

Se podrán reutilizar:

- catálogos;
- configuraciones;
- información histórica;
- estructuras de checklist;
- calendarios;
- componentes útiles.

No se deberá mantener simultáneamente un preventivo operativo en PM y otro ticket preventivo representando el mismo trabajo.

Si alguna funcionalidad PM existente continúa activa, deberá consumir o relacionarse con la misma programación/ticket y no duplicar el dato.

## 4. Programación Preventiva

Dentro del módulo Tickets se agregará una sección:

**Tickets → Programación preventiva**

No se agregará un nuevo módulo principal al menú.

La programación tendrá dos canales de captura:

1. Captura manual.
2. Carga batch mediante plantilla.

Ambos canales deberán terminar en el mismo flujo:

```text
CAPTURA MANUAL ──────┐
                     ├── BORRADOR
CARGA BATCH ─────────┘
                          ↓
                       VALIDACIÓN
                          ↓
                       PUBLICACIÓN
                          ↓
                   TICKETS PREVENTIVOS
```

Una programación deberá pertenecer a un lote identificable.

Ejemplo conceptual:

```text
Lote: PM-2026-W40
Periodo: Semana 40
Creado por: usuario
Estado: Borrador / Publicado
Registros: 35
```

Cada ticket preventivo conservará el vínculo con el lote que lo originó.

## 5. Captura manual

La captura manual deberá optimizar la creación de múltiples preventivos.

Flujo:

```text
Sucursal
    ↓
Familia de equipo
    ↓
Equipos disponibles
    ↓
Selección múltiple
    ↓
Actividad preventiva
    ↓
Fecha programada
    ↓
Responsable
    ↓
Agregar al borrador
```

Ejemplo:

```text
Sucursal:
Villas del Rey

Familia:
Caminadoras

Equipos:
☐ CAM-001
☑ CAM-002
☑ CAM-003
☐ CAM-004
☑ CAM-005

3 de 12 seleccionados

Actividad:
Mantenimiento preventivo general

Fecha:
25/09/2026

Responsable:
Juan Pérez

[Agregar 3 preventivos]
```

La selección de equipos deberá incluir:

- multiselección;
- seleccionar todos;
- limpiar selección;
- búsqueda por código.

Solo deberán mostrarse equipos actualmente asignados a la sucursal seleccionada.

## 6. Identificación del equipo

La llave operativa será el **código de equipo**, no su nombre.

El usuario visualizará información amigable:

```text
CAM-024
Caminadora Matrix
```

pero el sistema resolverá internamente:

```text
Código
→ Inventario
→ Familia
→ Equipo
→ Sucursal actual
```

Si el código existe pero pertenece a una sucursal distinta de la indicada, deberá generarse error de validación.

## 7. Carga batch

Se proporcionará una plantilla de carga preventiva.

Campos mínimos:

- Sucursal.
- Código de equipo.
- Fecha programada.
- Actividad.
- Responsable.
- Observaciones, opcional.

No deberán solicitarse al usuario:

- IDs internos;
- familia;
- categoría interna;
- semana;
- mes;
- número de ticket;
- estado;
- gerente;
- lote.

Suite derivará dichos valores.

La familia deberá obtenerse desde el código del equipo.

La carga no generará tickets inmediatamente.

Primero deberá mostrar validación:

```text
35 registros procesados
35 correctos
0 errores
```

o:

```text
35 registros procesados
32 correctos
3 errores

Fila 12 — Código inexistente
Fila 18 — Equipo asignado a otra sucursal
Fila 24 — Posible duplicado
```

Por defecto, un lote con errores no deberá publicarse parcialmente.

La carga deberá ser idempotente frente a duplicados razonablemente detectables.

## 8. Publicación del lote

Al publicar un lote se generará un ticket preventivo por cada trabajo programado.

Cada ticket deberá conservar, como mínimo:

- tipo de mantenimiento;
- lote de origen;
- fecha programada original;
- fecha programada actual;
- equipo;
- sucursal;
- actividad;
- responsable;
- usuario creador;
- fecha de creación.

La publicación deberá ser transaccional: un fallo no deberá dejar un lote parcialmente publicado sin una condición explícitamente controlada.

## 9. Personal de mantenimiento

Se agregará un catálogo de personal de mantenimiento.

Cada registro podrá contener:

- nombre;
- usuario Suite asociado;
- cuadrilla;
- región;
- estado activo/inactivo.

Cuando el técnico utilice Suite deberá estar vinculado a un usuario real.

No deberá crearse un sistema de autenticación separado.

## 10. Cuadrillas

El personal podrá agruparse en cuadrillas.

Ejemplo:

```text
Cuadrilla MXL / SL

Juan Pérez
Pedro López
Luis Hernández
```

La cuadrilla tendrá un alcance territorial.

La programación deberá filtrar responsables razonables según región/sucursal.

Permisos superiores podrán realizar asignaciones excepcionales cuando corresponda.

## 11. Programa del técnico

El técnico tendrá una vista denominada:

**Mi programa**

Esta vista será diseñada **mobile-first**.

El puesto no debe depender de disponer de computadora.

El técnico podrá consultar desde celular:

- trabajos de hoy;
- trabajos de la semana;
- sucursal;
- código de equipo;
- equipo;
- actividad;
- fecha programada;
- estado.

No deberá exponerse al técnico el panel administrativo completo.

Ejemplo:

```text
MI PROGRAMA

Hoy · 25 Sep

VILLAS DEL REY

CAM-024
Caminadora
Mantenimiento general

[Ver trabajo]
```

La interfaz deberá funcionar correctamente desde aproximadamente 320 px de ancho y no depender de:

- hover;
- tablas horizontales;
- controles pequeños;
- interfaces pensadas exclusivamente para escritorio.

## 12. Permisos del técnico

El técnico podrá:

- consultar sus trabajos asignados;
- abrir el detalle;
- iniciar/continuar la ejecución;
- completar checklist;
- agregar observaciones;
- adjuntar evidencia;
- registrar hallazgos;
- generar un correctivo derivado;
- marcar el trabajo como realizado.

El técnico no podrá, salvo permiso administrativo explícito:

- reasignar trabajos;
- cambiar programación;
- modificar compromisos;
- validar su propio trabajo;
- alterar trabajos de otros técnicos.

El backend deberá hacer cumplir estos permisos.

## 13. Bitácora preventiva

Cada ejecución preventiva deberá generar una bitácora estructurada.

La bitácora incluirá:

- estado encontrado;
- trabajo realizado;
- observaciones;
- checklist;
- hallazgos;
- fecha/hora;
- usuario responsable.

La evidencia fotográfica será opcional y recomendada. La bitácora será obligatoria para marcar el preventivo como realizado. La ausencia de evidencia no bloqueará el envío a validación ni la validación del gerente. La interfaz del técnico iniciará con la opción de adjuntar evidencia activada por defecto para favorecer su captura; el técnico podrá desmarcarla explícitamente cuando el trabajo no requiera evidencia. Si la opción permanece activa, deberá completar la subida antes de marcar realizado.

## 14. Checklist por familia

Los checklists deberán ser configurables mediante catálogo y no quedar hardcodeados.

Ejemplo:

```text
Familia: Caminadoras

Mantenimiento general

☑ Limpieza
☑ Lubricación
☑ Revisión de banda
☑ Revisión de tensión
☑ Ruidos / vibración
☑ Prueba de funcionamiento
```

Una futura modificación del procedimiento no deberá requerir cambio de código.

## 15. Hallazgos

Encontrar una falla durante el preventivo no convierte al preventivo en fallido.

Ejemplo:

```text
Preventivo realizado
+
Hallazgo detectado
+
Correctivo generado
```

El preventivo podrá completarse aunque exista un hallazgo.

## 16. Correctivos derivados

Desde la bitácora preventiva podrá generarse un ticket correctivo.

Este ticket deberá:

- comportarse como un correctivo normal;
- conservar vínculo estructural con el preventivo origen;
- registrar `origen_correctivo = DETECTADO_EN_PREVENTIVO`.

Los correctivos normales tendrán:

`origen_correctivo = REACTIVO`.

La relación deberá navegarse en ambas direcciones.

```text
PM-2041
→ generó TK-9182
```

```text
TK-9182
→ detectado durante PM-2041
```

No deberá guardarse esta relación únicamente mediante texto u observaciones.

## 17. Validación del gerente

No se creará una nueva vista de validación.

Cuando el técnico marque un preventivo como realizado, el ticket continuará en el **flujo actual de Tickets**.

El gerente utilizará la vista actual de escritorio para:

- revisar el ticket;
- consultar bitácora;
- revisar evidencia cuando exista;
- validar;
- rechazar.

Los gerentes ya utilizan Suite desde las computadoras de sucursal.

La adaptación requerida será únicamente permitir consultar dentro del detalle del ticket:

- checklist preventivo;
- bitácora;
- evidencia cuando exista;
- hallazgos;
- correctivos relacionados.

El comportamiento actual de validación deberá preservarse.

## 18. Definición de preventivo concluido

Para efectos estadísticos:

> **Un preventivo se considera concluido únicamente cuando ha sido validado mediante el flujo actual de Tickets.**

Marcarlo como realizado por mantenimiento no equivale a cumplimiento definitivo.

## 19. Estados

No deberán agregarse estados globales nuevos si el flujo actual de Tickets puede representar correctamente el ciclo.

La programación preventiva deberá mapearse sobre los estados existentes.

Conceptualmente:

```text
PROGRAMADO
↓
TRABAJO ACTIVO
↓
REALIZADO
↓
PENDIENTE DE VALIDACIÓN
↓
VALIDADO / CONCLUIDO
```

La implementación deberá revisar el catálogo real actual antes de crear estados adicionales.

## 20. Fechas operativas

### Preventivo

Cada preventivo tendrá:

- fecha programada original;
- fecha programada actual.

### Correctivo

Cada correctivo tendrá:

- fecha compromiso original;
- fecha compromiso actual.

La fecha original deberá ser inmutable.

## 21. Reprogramaciones

Preventivos y correctivos podrán ser reprogramados.

Toda modificación deberá generar historial.

Ejemplo:

```text
23 sep → 26 sep → 30 sep → 2 oct
```

Cada evento deberá almacenar:

- fecha anterior;
- nueva fecha;
- motivo;
- usuario;
- fecha/hora.

No se deberá sobrescribir silenciosamente una fecha.

## 22. Motivos de reprogramación

Se utilizará un catálogo pequeño y configurable.

Ejemplos iniciales:

- Refacción pendiente.
- Proveedor externo.
- Equipo no disponible.
- Reprogramación operativa.
- Falta de técnico.
- Otro.

Cuando aplique `Otro`, podrá solicitarse comentario.

## 23. Permiso para reprogramar

Por defecto podrán reprogramar:

- jefe de mantenimiento;
- auxiliares autorizados;
- perfiles administrativos autorizados.

El técnico operativo no podrá reprogramar unilateralmente su propio trabajo.

El gerente de sucursal tampoco deberá modificar la programación de mantenimiento salvo que tenga permiso explícito.

## 24. Semana operativa canónica

Para este módulo, toda semana operativa se define de forma obligatoria como:

**domingo → sábado**

Esta convención aplica de manera uniforme a:

- programación preventiva;
- cohortes preventivas;
- cohortes correctivas;
- panel semanal;
- backlog histórico;
- tendencias;
- drill-downs;
- filtros por semana;
- snapshots históricos.

No deberá utilizarse semana ISO lunes-domingo para estos indicadores.

Ejemplo:

```text
Semana operativa
Domingo 20/09/2026
→
Sábado 26/09/2026
```

La lógica existente del PM/Planner que ya trabaja domingo-sábado deberá conservarse como referencia canónica.

## 25. Cohorte semanal preventiva

La semana de origen del preventivo se determina por su:

**fecha programada original**.

Un preventivo programado para Semana 39 continuará perteneciendo estadísticamente a Semana 39 aunque posteriormente se realice en Semana 40.

## 26. Cohorte semanal correctiva

La semana de origen del correctivo para medición de cumplimiento se determina por:

**fecha compromiso original**.

No por la fecha de creación.

La pregunta que responde el indicador es:

> ¿Qué correctivos debían quedar resueltos esta semana?

## 27. Resultado histórico semanal

Cada cohorte deberá distinguir:

- cumplido en tiempo;
- reprogramado;
- vencido/no realizado.

Ejemplo:

```text
Semana 39

22 comprometidos

17 cumplidos
3 reprogramados
2 vencidos
```

La reprogramación no deberá borrar la obligación original.

## 28. Cumplimiento estricto

Para preventivos:

```text
preventivos validados dentro del periodo
-----------------------------------------
preventivos programados originalmente
```

Para correctivos:

```text
correctivos validados dentro del compromiso
--------------------------------------------
correctivos comprometidos originalmente
```

Una resolución tardía podrá actualizar el estado actual del ticket, pero no convertir retroactivamente un incumplimiento histórico en cumplimiento en tiempo.

## 29. Estado actual vs resultado histórico

El sistema deberá distinguir:

**Resultado histórico**

Qué ocurrió respecto al compromiso original.

**Estado actual**

Qué terminó sucediendo posteriormente.

Ejemplo:

```text
Semana 39

Cumplimiento en tiempo:
29 / 35

Estado actual:
33 / 35 ya concluidos
```

## 30. Panel semanal

Se agregará una vista analítica dentro del ecosistema de Tickets/Mantenimiento.

Cada semana será una unidad visual.

Ejemplo:

```text
SEMANA 39

PREVENTIVOS
35 programados
29 en tiempo          82.9%
4 reprogramados       11.4%
2 vencidos             5.7%

CORRECTIVOS
22 comprometidos
17 en tiempo          77.3%
3 reprogramados       13.6%
2 vencidos             9.1%

BACKLOG
112 → 101
```

## 31. Ventana histórica

Por defecto se visualizará una ventana manejable, por ejemplo:

- últimas 6 semanas;
- últimas 8 semanas.

En escritorio podrán distribuirse varias semanas por fila.

No deberá convertirse en una tabla horizontal infinita.

## 32. Tendencias

Además de los cuadrantes semanales se incluirá una lectura histórica.

Se deberán distinguir dos conceptos:

### Cumplimiento

- porcentaje preventivo en tiempo;
- porcentaje correctivo en tiempo.

### Presión correctiva

- correctivos nuevos/recibidos;
- backlog correctivo;
- backlog vencido.

No deberán mezclarse cantidades y porcentajes como si representaran el mismo fenómeno.

## 33. Backlog

Se distinguirán:

### Backlog correctivo total

Correctivos que permanecían abiertos en un momento determinado.

### Backlog correctivo vencido

Correctivos abiertos cuyo compromiso vigente ya había vencido.

Ejemplo:

```text
Backlog total:
112 → 101

Backlog vencido:
79 → 67
```

## 34. Backlog histórico

El tablero deberá responder correctamente:

> ¿Qué backlog existía al cierre de determinada semana?

No deberá reconstruirse únicamente consultando el estado actual de los tickets.

La implementación podrá utilizar:

- eventos históricos;
- reconstrucción `as-of`;
- snapshots semanales;

según resulte más seguro y eficiente después de revisar el modelo actual.

La información histórica no deberá modificarse retroactivamente por cierres posteriores.

## 35. Antigüedad del backlog

En el drill-down del backlog vencido se deberá poder analizar:

- 1–7 días;
- 8–14 días;
- 15–30 días;
- más de 30 días.

No es necesario mostrar esta distribución en el cuadrante principal.

## 36. Correctivos recibidos

Además de los correctivos comprometidos en una semana se podrá mostrar el volumen de correctivos creados/recibidos durante esa semana.

Esto permitirá separar:

**demanda**

Cuánto trabajo está entrando.

de:

**cumplimiento**

Cuánto trabajo debía resolverse.

## 37. Correctivos detectados preventivamente

Los correctivos deberán poder segmentarse por origen:

```text
REACTIVO
DETECTADO_EN_PREVENTIVO
```

Ejemplo:

```text
Correctivos: 24

18 reactivos
6 detectados preventivamente
```

Esto permitirá analizar si el programa preventivo comienza a detectar fallas antes de que se conviertan en reportes reactivos.

Esta relación deberá interpretarse como señal operacional y no automáticamente como causalidad estadística.

## 38. Filtros del panel

El mismo panel deberá soportar diferentes niveles:

```text
Global
↓
Región
↓
Sucursal
↓
Cuadrilla
↓
Responsable
```

Los filtros serán acumulativos.

El alcance permitido dependerá de los permisos del usuario.

No se crearán dashboards distintos para cada rol si el mismo componente puede resolver el alcance mediante permisos y filtros.

## 39. Drill-down

Todo indicador deberá llevar al detalle.

Ejemplos:

```text
29 validados
→ lista de los 29 tickets
```

```text
4 reprogramados
→ tickets + motivo + nueva fecha
```

```text
67 backlog vencido
→ tickets que componían ese backlog
```

```text
6 detectados preventivamente
→ correctivo + preventivo origen
```

Principio:

> **Dato → explicación → ticket.**

No deberán existir cifras importantes sin posibilidad de inspeccionar su origen.

## 40. Alcance por rol

### Dirección / lector global

Puede consultar toda la organización según permisos.

### Regional

Puede consultar únicamente regiones/sucursales autorizadas.

### Jefe de mantenimiento

Puede:

- programar;
- cargar batch;
- publicar lotes;
- asignar;
- reprogramar;
- consultar desempeño.

### Auxiliar autorizado

Permisos configurables similares al jefe de mantenimiento.

### Técnico

Consulta únicamente su programa y trabaja sus tickets.

### Gerente

Continúa utilizando la vista actual de Tickets y valida únicamente tickets dentro de su alcance.

El backend será la fuente real de permisos.

## 41. Mobile-first para ejecución

Las interfaces del técnico deberán cumplir:

- controles táctiles suficientemente grandes;
- navegación vertical;
- formularios cortos;
- evidencia accesible desde celular;
- sin tablas complejas;
- sin hover;
- sin requerir teclado físico;
- lectura clara con pantalla angosta.

La experiencia administrativa podrá priorizar escritorio.

## 42. Auditoría

Deberá conservarse trazabilidad de:

- creación;
- publicación;
- asignación;
- reasignación;
- reprogramación;
- ejecución;
- bitácora;
- evidencia;
- hallazgos;
- generación de correctivo;
- validación;
- rechazo;
- cierre.

Los datos históricos relevantes no deberán sobrescribirse.

## 43. Integridad

Debe evitarse:

- duplicar preventivos;
- publicar dos veces un lote;
- perder fecha original;
- modificar históricos silenciosamente;
- relacionar equipo con sucursal incorrecta;
- asignar usuarios fuera de alcance sin permiso;
- validar un trabajo propio cuando el flujo requiera gerente;
- generar relaciones preventivo/correctivo mediante texto libre.

## 44. Zona horaria

Todos los cálculos operativos de semanas, cierres y compromiso deberán utilizar de manera consistente:

`America/Tijuana`

Deberá evitarse mezclar fechas UTC directamente con fechas operativas sin conversión explícita.

## 45. Cambios de base de datos

Cualquier campo, tabla o relación nueva deberá implementarse mediante migración Alembic.

No se realizarán cambios manuales de esquema en producción.

Entre las estructuras que probablemente serán necesarias se encuentran, sujeto a revisión del modelo actual:

- tipo de mantenimiento;
- lotes de programación;
- programación preventiva;
- historial de reprogramación;
- catálogo de personal/cuadrillas;
- checklist/catalogación;
- bitácora preventiva;
- relaciones preventivo-correctivo;
- snapshots o estructuras históricas del panel si resultan necesarias.

No se deberán crear tablas duplicadas si el modelo actual ya resuelve correctamente alguna de estas entidades.

## 46. Arquitectura frontend

La funcionalidad permanecerá dentro del ecosistema de Tickets.

Las piezas deberán mantenerse separadas en:

- `.ts`
- `.html`
- `.css`

La lógica estará en TypeScript.

El HTML contendrá únicamente estructura, bindings simples y llamadas a métodos ya definidos.

La vista móvil del técnico y las vistas administrativas podrán compartir servicios, pero no deberán convertirse en un único componente gigante.

## 47. Arquitectura backend

El backend deberá centralizar:

- creación/publicación;
- permisos;
- validaciones;
- asignación;
- reprogramación;
- historial;
- métricas;
- drill-down.

El frontend no será responsable de imponer seguridad.

Los endpoints deberán respetar JWT, sucursales y alcance del usuario.

## 48. Compatibilidad con Tickets actuales

Los correctivos existentes deberán seguir funcionando.

La migración deberá ser retrocompatible.

Los tickets históricos de mantenimiento deberán poder clasificarse razonablemente como correctivos sin modificar su comportamiento previo.

El desarrollo no deberá romper:

- creación actual;
- consulta;
- cierre;
- validación;
- permisos;
- filtros;
- relaciones con inventario.

## 49. Resultado esperado

Al terminar el desarrollo Suite deberá permitir responder preguntas como:

- ¿Qué preventivos estaban programados esta semana?
- ¿Cuántos se cumplieron en tiempo?
- ¿Cuántos fueron reprogramados?
- ¿Quién tenía asignado cada trabajo?
- ¿Qué hizo hoy cada técnico?
- ¿Qué trabajo fue validado por la sucursal?
- ¿Qué correctivos debían resolverse esta semana?
- ¿Cuáles siguen vencidos?
- ¿Cuántas veces se ha reprogramado un ticket?
- ¿Está bajando el backlog?
- ¿Están disminuyendo los correctivos reactivos?
- ¿Qué fallas están siendo detectadas mediante preventivos?
- ¿Qué región/sucursal/cuadrilla explica un resultado?
- ¿Qué tickets forman cada indicador?

## 50. Principio final

El desarrollo no deberá convertirse únicamente en un calendario de mantenimiento.

Debe funcionar como un sistema de:

**planeación → ejecución → validación → trazabilidad → medición → explicación.**

La finalidad es poder observar con evidencia si el mantenimiento preventivo se está ejecutando y si, con el tiempo, la operación correctiva y el backlog disminuyen.

## 51. Estado de implementación V1

La implementación correspondiente a este contrato se encuentra en la PR **#655** sobre la rama `feat/tickets-preventive-maintenance`.

Se implementaron las siete fases funcionales:

1. semántica canónica de mantenimiento en Tickets;
2. programación manual y batch;
3. cuadrillas, responsables y Mi programa mobile-first;
4. bitácora, evidencia, checklist y correctivo derivado;
5. validación del gerente integrada a Tickets;
6. panel semanal, backlog histórico y drill-down;
7. transición reversible del PM legacy.

También quedaron cubiertos los requisitos transversales de:

- reprogramación auditada para preventivos y correctivos;
- catálogo configurable de motivos;
- preservación de fecha original;
- historial de reprogramaciones;
- navegación preventiva ↔ correctiva;
- backlog vencido histórico;
- aging de backlog;
- separación de correctivos reactivos y detectados preventivamente;
- feature flag de cutover `TICKETS_PREVENTIVE_V1_ENABLED`.

El procedimiento de activación y rollback se documenta en:

`docs/contratos/ROLLOUT_TICKETS_MANTENIMIENTO_PREVENTIVO_V1.md`

La PR permanece como draft hasta ejecutar las pruebas Python/Angular en un entorno con acceso al repositorio y realizar el smoke test previo al cutover.
