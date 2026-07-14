# Contrato funcional — Control de asignación de rutinas

**Proyecto:** Suite Ultra  
**Documento:** Contrato funcional del módulo  
**Versión:** 1.0  
**Fecha:** 13 de julio de 2026  
**Estado:** Funcionalmente acordado; pendiente de contrato técnico e implementación  
**Nombre provisional:** Control de asignación de rutinas

---

## 1. Propósito

Crear una vista operativa dentro de Suite Ultra para controlar la asignación de rutinas a socios nuevos.

El módulo deberá permitir:

- Identificar qué socios nuevos ya tienen una rutina.
- Detectar qué socios continúan pendientes de rutina.
- Registrar a quienes expresamente no desean una rutina.
- Dar seguimiento por cohorte mensual.
- Consultar información por sucursal, región o nivel nacional.
- Conservar trazabilidad de cambios automáticos y manuales.
- Exportar la información a Excel cuando sea necesario.
- Sustituir en el futuro Trainingym por Gasca sin modificar el núcleo funcional del módulo.

La vista de Suite será la fuente principal de control operativo. El Excel será únicamente una salida de consulta, análisis o respaldo.

---

## 2. Principios rectores

1. Suite Ultra será la fuente de verdad del control operativo.
2. Gasca y Trainingym serán fuentes de hechos, no de decisiones operativas.
3. El estado persistirá en PostgreSQL y no dependerá de archivos editados externamente.
4. El módulo se diseñará por cohorte mensual.
5. El cruce inicial será por correo electrónico normalizado.
6. Trainingym quedará encapsulado como proveedor intercambiable.
7. Los permisos se validarán siempre en backend.
8. La ejecución diaria será idempotente.
9. Las decisiones manuales nunca deberán perderse por una nueva extracción.
10. Una rutina detectada se considerará evidencia histórica persistente.

---

## 3. Nombre funcional

El nombre provisional será **Control de asignación de rutinas**.

El nombre no deberá incluir “Trainingym”, porque Trainingym será una fuente temporal y reemplazable.

---

## 4. Alcance funcional

El módulo cubrirá:

- Ingesta de socios nuevos.
- Ingesta de evidencias de rutinas.
- Conciliación por correo.
- Clasificación por cohorte mensual.
- Estado operativo vigente.
- Registro de “No desea rutina”.
- Historial y auditoría.
- Vista operativa paginada.
- Indicadores.
- Filtros.
- Exportación Excel.
- Ejecución diaria.
- Incidencias de conciliación.
- Control jerárquico por sucursal, región y nivel global.

---

## 5. Fuentes de información

### 5.1. Socios nuevos

**Fuente inicial:** Gasca.

Gasca deberá proporcionar, como mínimo:

- Identificador del registro de origen, cuando exista.
- Nombre del socio.
- Correo electrónico.
- Sucursal.
- Fecha oficial de venta o alta como socio nuevo.
- Datos adicionales requeridos para consulta o auditoría.

La fecha oficial de venta o alta será la que determine la cohorte mensual.

### 5.2. Rutinas asignadas

**Fuente inicial:** Trainingym.

Trainingym deberá proporcionar, como mínimo:

- Correo electrónico del socio.
- Fecha de la rutina.
- Instructor o técnico.
- Identificador de rutina, cuando exista.
- Centro o sucursal, cuando esté disponible.
- Fecha de observación o extracción.

### 5.3. Fuente futura

Cuando la nueva aplicación de Gasca proporcione rutinas, deberá poder reemplazar al proveedor de Trainingym sin modificar:

- Estados funcionales.
- Cohortes.
- Vista operativa.
- Permisos.
- Historial.
- Indicadores.
- Exportaciones.
- Acciones manuales.
- Reglas de conciliación del dominio.

---

## 6. Cohorte mensual

Cada socio nuevo pertenecerá a una cohorte mensual determinada por la fecha oficial de venta o alta como socio nuevo en Gasca.

Ejemplo:

```text
Fecha de venta nueva: 2 de julio de 2026
Cohorte: julio de 2026
```

La fecha de una rutina no modificará la cohorte del socio.

Ejemplo:

```text
Rutina creada: 30 de junio de 2026
Venta nueva: 2 de julio de 2026
Cohorte: julio de 2026
Estado: CON_RUTINA
Tipo de asignación: PREEXISTENTE
```

Esta regla evita marcar incorrectamente como pendiente a un socio que recibió una rutina durante un pase de cortesía previo a convertirse en cliente nuevo.

---

## 7. Identificación y conciliación

### 7.1. Llave inicial de conciliación

El cruce inicial entre Gasca y Trainingym se realizará por correo electrónico normalizado.

### 7.2. Normalización inicial

La normalización será:

- Eliminar espacios al inicio y al final.
- Convertir a minúsculas.
- Tratar correos vacíos como no conciliables.
- No modificar puntos del correo.
- No eliminar etiquetas `+`.
- No aplicar reglas particulares por proveedor de correo.
- No realizar coincidencia difusa por nombre.
- No realizar coincidencia automática por teléfono en la primera versión.

Ejemplo:

```text
Socio@Correo.com
socio@correo.com
```

Ambos valores se considerarán el mismo correo normalizado.

### 7.3. Identificador interno

Aunque el cruce con las fuentes use correo, Suite deberá asignar un identificador interno estable al registro operativo.

El correo no deberá ser la única llave primaria del dominio, debido a posibles:

- Correos duplicados.
- Correos vacíos.
- Correcciones posteriores.
- Reutilización del mismo correo.
- Altas repetidas en diferentes cohortes.
- Cambios de sucursal.

---

## 8. Estados funcionales

Cada socio nuevo tendrá un único estado vigente.

### 8.1. `SIN_RUTINA`

El socio pertenece a una cohorte de nuevos y no se ha encontrado una rutina válida asociada a su correo.

Características:

- Es un pendiente operativo.
- Se incluye en la bandeja principal del gerente.
- Cuenta dentro del universo evaluable.
- Aumenta sus días sin rutina mientras no cambie de estado.

### 8.2. `CON_RUTINA`

Se encontró al menos una rutina válida asociada al correo del socio.

Características:

- No es un pendiente operativo.
- Cuenta como cumplimiento.
- La evidencia de rutina se conserva históricamente.
- Puede distinguirse el momento de asignación respecto a la venta nueva.

Tipos funcionales:

- `PREEXISTENTE`: rutina anterior a la venta nueva.
- `MISMO_DIA`: rutina asignada el mismo día de la venta.
- `POSTERIOR`: rutina asignada después de la venta nueva.

### 8.3. `NO_DESEA_RUTINA`

El socio indicó expresamente que no desea una rutina.

Características:

- No cuenta como pendiente.
- No cuenta como socio con rutina.
- Sí permanece dentro del total de socios nuevos.
- Se excluye del universo evaluable para cumplimiento.
- Requiere una acción manual autorizada.
- Debe conservar motivo, observación, usuario y fecha.
- Debe ser reversible.
- Debe permanecer visible para auditoría.

---

## 9. Prioridad de estados

La evaluación del estado vigente seguirá esta prioridad:

```text
Si existe una rutina válida:
    CON_RUTINA

Si no existe rutina y existe una decisión vigente de rechazo:
    NO_DESEA_RUTINA

Si no existe rutina ni decisión vigente:
    SIN_RUTINA
```

La evidencia real de rutina tendrá prioridad sobre la decisión manual.

Ejemplo:

```text
10 de julio:
NO_DESEA_RUTINA

15 de julio:
Se detecta una rutina válida

Estado vigente:
CON_RUTINA
```

La decisión anterior de `NO_DESEA_RUTINA` no se elimina. Permanece en el historial.

---

## 10. Registro de “No desea rutina”

Un usuario autorizado podrá marcar a un socio como **No desea rutina**.

La acción solicitará:

- Motivo obligatorio.
- Observación opcional.
- Confirmación.

Motivos iniciales:

- No está interesado.
- Ya cuenta con rutina propia.
- Tiene entrenador externo.
- Limitación médica o indicación profesional.
- Solo utiliza clases o actividades grupales.
- Otro.

Cuando el motivo sea `Otro`, la observación será obligatoria.

La decisión deberá registrar:

- Socio.
- Cohorte.
- Sucursal.
- Estado anterior.
- Estado nuevo.
- Motivo.
- Observación.
- Usuario responsable.
- Fecha y hora.
- Tipo de actor.
- Alcance desde el que se realizó.
- Identificador de la acción o evento.

### 10.1. Reversión

La acción deberá poder revertirse por un usuario autorizado.

Al revertir:

- Si existe evidencia válida de rutina, el estado permanece `CON_RUTINA`.
- Si no existe evidencia de rutina, el estado vuelve a `SIN_RUTINA`.
- La reversión se registra como un nuevo evento.
- El registro original no se borra.

---

## 11. Procesamiento incremental

El control no se reconstruirá únicamente con los archivos del día.

Suite conservará persistentemente:

- Socios nuevos observados.
- Cohorte mensual.
- Datos normalizados.
- Evidencias de rutinas.
- Estado vigente.
- Decisiones manuales.
- Historial de cambios.
- Incidencias.
- Ejecuciones de proveedores.
- Metadatos de origen.

La ejecución diaria deberá:

1. Consultar socios nuevos de Gasca.
2. Consultar rutinas del proveedor activo.
3. Normalizar los datos.
4. Incorporar registros nuevos.
5. Actualizar registros existentes.
6. Detectar nuevas evidencias de rutina.
7. Reconciliar estados afectados.
8. Conservar decisiones manuales.
9. Registrar incidencias.
10. Registrar conteos y resultados.
11. Evitar duplicados.
12. Cerrar la ejecución como exitosa o fallida.

Una rutina encontrada en julio podrá actualizar a un socio de la cohorte de junio.

El procesamiento no se limitará exclusivamente al mes actual.

---

## 12. Persistencia de evidencias

Una vez que Suite haya registrado una rutina válida, una extracción posterior que no la incluya no devolverá automáticamente al socio a `SIN_RUTINA`.

La rutina se tratará como un hecho histórico persistente.

Solo podrá invalidarse mediante:

- Corrección explícita y trazable del proveedor.
- Acción administrativa autorizada.
- Proceso de conciliación documentado.
- Regla técnica futura aprobada expresamente.

Una ausencia temporal en una extracción no se considerará evidencia de que la rutina dejó de existir.

---

## 13. Incidencias de conciliación

Los registros que no puedan clasificarse automáticamente no deberán incorporarse silenciosamente a `SIN_RUTINA`.

Incidencias iniciales:

- `EMAIL_VACIO`
- `EMAIL_DUPLICADO_GASCA`
- `EMAIL_DUPLICADO_RUTINAS`
- `SUCURSAL_NO_RESUELTA`
- `FECHA_VENTA_INVALIDA`
- `COHORTE_NO_DETERMINADA`
- `COINCIDENCIA_AMBIGUA`
- `REGISTRO_ORIGEN_INVALIDO`
- `PROVIDER_INCOMPLETO`
- `CENTRO_TRAININGYM_NO_RESUELTO`

Las incidencias deberán:

- Permanecer visibles.
- Tener estado.
- Indicar fuente.
- Conservar detalle técnico sanitizado.
- Poder resolverse o cerrarse.
- No contaminar los indicadores de pendientes confirmados sin una regla explícita.

---

## 14. Vista operativa

La pantalla funcionará como una bandeja operativa similar conceptualmente a la vista de Tickets.

### 14.1. Pestañas

#### Pendientes sin rutina

Muestra únicamente socios con estado `SIN_RUTINA`.

Será la vista principal para gerentes.

#### Con rutina

Muestra socios con estado `CON_RUTINA`.

#### No desean rutina

Muestra socios con estado `NO_DESEA_RUTINA`.

#### Incidencias

Muestra registros que no pueden clasificarse automáticamente.

#### Todos

Muestra el universo completo autorizado.

### 14.2. Comportamiento

La vista deberá:

- Paginar desde backend.
- Aplicar filtros en backend.
- Respetar el alcance autorizado.
- Mostrar indicadores según filtros.
- Permitir abrir detalle.
- Permitir acciones autorizadas.
- Mantener separadas las reglas de visualización y autorización.

No se deberá copiar el patrón heredado de cargar todo y paginar únicamente en memoria.

---

## 15. Información visible

La tabla podrá mostrar:

- Nombre del socio.
- Correo.
- Sucursal.
- Región.
- Fecha de venta nueva.
- Cohorte mensual.
- Estado vigente.
- Días sin rutina.
- Fecha de primera rutina.
- Fecha de última rutina.
- Instructor.
- Tipo de asignación.
- Motivo de no deseo.
- Fecha de última actualización.
- Fuente de rutina.
- Indicador de incidencia.

El detalle podrá mostrar:

- Datos originales de Gasca.
- Datos normalizados.
- Evidencias de rutina.
- Estado vigente.
- Historial de estados.
- Decisiones manuales.
- Incidencias.
- Ejecuciones que actualizaron el registro.
- Observaciones.
- Fuente y referencias externas disponibles.

---

## 16. Filtros

La vista permitirá filtrar por:

- Cohorte mensual.
- Estado.
- Sucursal.
- Región.
- Fecha de alta.
- Rango de días sin rutina.
- Instructor.
- Fuente de rutina.
- Tipo de asignación.
- Incidencia.
- Texto libre por nombre o correo.

Los filtros disponibles dependerán del alcance y capacidades del usuario.

---

## 17. Alcance operativo y permisos

Todas las vistas, acciones, indicadores y exportaciones deberán respetar tres niveles de alcance.

### 17.1. `GERENTE`

Puede:

- Consultar únicamente su sucursal.
- Ver indicadores de su sucursal.
- Marcar `NO_DESEA_RUTINA` dentro de su sucursal.
- Revertir decisiones según permisos.
- Exportar únicamente información de su sucursal.

### 17.2. `GERENTE_REGIONAL`

Puede:

- Consultar su pool autorizado de sucursales.
- Ver un consolidado regional.
- Bajar al detalle por sucursal.
- Ejecutar acciones dentro de su pool.
- Exportar información de su alcance regional.

### 17.3. Dirección y roles globales autorizados

Pueden:

- Consultar todas las regiones y sucursales.
- Ver consolidados nacionales.
- Bajar a región y sucursal.
- Revisar acciones manuales.
- Corregir o revertir estados según permisos.
- Exportar información global.

### 17.4. Fuente de autorización

El backend deberá reconstruir el usuario y alcance vigente desde la base de datos.

Los claims JWT podrán apoyar la sesión, pero no serán la única fuente de autorización.

El frontend:

- Ocultará o mostrará acciones según capacidades.
- No será la fuente real de permisos.
- No sustituirá las validaciones del backend.

La lista exacta de roles globales se definirá en el contrato técnico usando los catálogos existentes de Suite.

---

## 18. Acciones funcionales

Acciones iniciales:

- Ver detalle.
- Marcar `NO_DESEA_RUTINA`.
- Revertir `NO_DESEA_RUTINA`.
- Agregar observación.
- Exportar vista actual.
- Exportar reporte mensual completo.
- Consultar historial.
- Consultar incidencias.

Acciones administrativas futuras, sujetas a contrato técnico:

- Corregir conciliación.
- Resolver incidencia.
- Invalidar evidencia.
- Reprocesar un socio.
- Reprocesar una cohorte.
- Reejecutar un proveedor.

---

## 19. Indicadores

La pantalla mostrará al menos:

- Total de socios nuevos.
- Con rutina.
- Sin rutina.
- No desean rutina.
- Socios evaluables.
- Porcentaje de asignación.
- Porcentaje que no desea rutina.
- Promedio de días para asignación.
- Mediana de días para asignación.
- Incidencias abiertas.

Fórmulas:

```text
Socios evaluables =
    Con rutina + Sin rutina
```

```text
Porcentaje de asignación =
    Con rutina / Socios evaluables
```

```text
Porcentaje que no desea rutina =
    No desea rutina / Total socios nuevos
```

`NO_DESEA_RUTINA` no formará parte del denominador de cumplimiento.

Los indicadores deberán respetar:

- Alcance.
- Cohorte.
- Filtros.
- Sucursal.
- Región.
- Estado.
- Fecha de corte aplicable.

---

## 20. Exportación Excel

El Excel será una exportación bajo demanda.

### 20.1. Exportar vista actual

Respetará:

- Pestaña activa.
- Cohorte.
- Estado.
- Sucursal.
- Región.
- Filtros aplicados.
- Orden solicitado, cuando sea viable.
- Alcance autorizado.

### 20.2. Exportar reporte mensual completo

Generará un archivo con pestañas:

- `Resumen`
- `Nuevos sin rutina`
- `Nuevos con rutina`
- `No desean rutina`
- `Incidencias`, cuando existan

### 20.3. Regla de operación

El Excel:

- No será la fuente de verdad.
- No se utilizará para devolver decisiones al sistema.
- No sustituirá la vista operativa.
- No permitirá actualizar estados mediante reimportación en la primera versión.

---

## 21. Ejecución diaria

La actualización será realizada por un worker independiente del backend web.

El horario exacto será configurable.

Zona horaria de negocio:

```text
America/Tijuana
```

Cada ejecución deberá registrar:

- Fecha de negocio.
- Fecha y hora de inicio.
- Fecha y hora de término.
- Proveedores ejecutados.
- Estado de la ejecución.
- Número de intentos.
- Registros descargados.
- Registros válidos.
- Registros rechazados.
- Registros nuevos.
- Registros actualizados.
- Rutinas detectadas.
- Cambios de estado.
- Incidencias.
- Error técnico sanitizado.
- Artefactos de diagnóstico disponibles.
- Hashes o referencias del material de origen cuando aplique.

Estados preliminares de ejecución:

- `PENDING`
- `RUNNING`
- `SUCCESS`
- `FAILED`
- `PARTIAL`
- `REPLACED`, cuando aplique al versionado técnico

Una ejecución fallida no deberá consolidar información incompleta como si fuera exitosa.

---

## 22. Idempotencia

Reejecutar el mismo proveedor para la misma fecha de negocio no deberá:

- Duplicar socios.
- Duplicar evidencias de rutina.
- Duplicar eventos.
- Duplicar decisiones.
- Borrar acciones manuales.
- Cambiar cohortes sin una corrección real.
- Crear múltiples estados vigentes.

Si el contenido cambia para una fecha previamente procesada, el sistema deberá:

- Detectar la diferencia.
- Actualizar únicamente los registros afectados.
- Conservar la evidencia del cambio.
- Registrar la ejecución y su relación con la versión anterior.

La deduplicación no deberá depender únicamente del nombre de archivo o título documental.

---

## 23. Failover de Trainingym

Trainingym deberá implementarse como un proveedor aislado.

El flujo de autenticación manejará explícitamente:

- Formulario de login visible.
- Credenciales capturadas.
- Credenciales enviadas.
- Formulario refrescado.
- Campos borrados.
- Selección de centro.
- Centro seleccionado.
- Sesión autenticada.
- Reporte accesible.
- Bloqueo o challenge.
- Pantalla inesperada.

### 23.1. Reintento de credenciales

Si después de pulsar iniciar sesión el formulario se refresca y borra las credenciales, el proveedor deberá:

1. Detectar que continúa en el formulario de login.
2. Confirmar que los campos quedaron vacíos o que el login no avanzó.
3. Volver a escribir usuario y contraseña.
4. Verificar que los campos contienen valores.
5. Reintentar el envío.
6. Reevaluar el estado.
7. Continuar con selección de centro cuando corresponda.

### 23.2. Selección de centro

La selección de centro deberá:

- Detectarse explícitamente.
- Reintentarse de forma independiente.
- Confirmar el centro seleccionado.
- No confundirse con un centro no requerido.
- Fallar de manera controlada si el centro sí es requerido y no pudo seleccionarse.

### 23.3. Validación de éxito

El proveedor no considerará exitoso el login hasta confirmar:

- Que el formulario de contraseña ya no está activo.
- Que la sesión salió del flujo de autenticación.
- Que el centro requerido quedó aplicado.
- Que el reporte puede abrirse.
- Que el contenido esperado de Power BI es accesible.

### 23.4. Diagnóstico

En fallas deberán conservarse, de manera sanitizada:

- Screenshot.
- URL.
- Estado detectado.
- HTML o trace cuando sea seguro.
- Número de intento.
- Paso fallido.
- Tiempo transcurrido.

Nunca deberán registrarse:

- Usuario.
- Contraseña.
- Tokens.
- Cookies sensibles.
- Contenido de campos secretos.

---

## 24. Arquitectura de proveedores

El dominio deberá consumir contratos neutrales.

Proveedores iniciales:

- `GascaNewMembersProvider`
- `TrainingymRoutineAssignmentsProvider`

Proveedor futuro:

- `GascaRoutineAssignmentsProvider`

Toda la lógica específica de Trainingym deberá permanecer dentro de su adaptador:

- Login.
- Playwright.
- Selección de centro.
- Power BI.
- Fechas.
- Exportación.
- Selectores.
- Reintentos.
- Turnstile.
- Artefactos.
- Conversión de datos.

El dominio principal no deberá importar Playwright ni depender de nombres específicos de Trainingym.

---

## 25. Transición futura de Trainingym a Gasca

La sustitución podrá realizarse mediante un periodo de comparación.

Ejemplo:

```text
Proveedor principal: Trainingym
Proveedor sombra: Gasca
```

Durante el periodo de sombra se podrán medir:

- Rutinas detectadas por ambos.
- Rutinas detectadas solo por Trainingym.
- Rutinas detectadas solo por Gasca.
- Diferencias de fecha.
- Diferencias de instructor.
- Correos no conciliados.
- Diferencias de centro o sucursal.

Después de validar cobertura:

```text
Proveedor principal: Gasca
Proveedor sombra: Trainingym
```

Finalmente podrá retirarse Trainingym sin modificar el dominio operativo.

---

## 26. Auditoría

El sistema conservará historial de:

- Alta del socio en el control.
- Cambio de datos de origen.
- Cambio de cohorte.
- Detección de rutina.
- Cambio automático de estado.
- Marcado como `NO_DESEA_RUTINA`.
- Reversión manual.
- Corrección administrativa.
- Creación y resolución de incidencias.
- Ejecuciones de proveedores.
- Exportaciones.
- Invalidación de evidencia, cuando exista.

Los eventos automáticos deberán indicar:

```text
actor_type = SYSTEM
```

Los eventos manuales deberán guardar:

- Usuario.
- Rol.
- Alcance.
- Fecha y hora.
- Motivo.
- Observación.
- Entidad afectada.

La auditoría no deberá depender únicamente de un JSON mutable dentro del registro principal.

---

## 27. Privacidad y datos personales

El módulo manejará información personal de socios.

El contrato técnico deberá definir:

- Campos visibles por rol.
- Campos exportables.
- Enmascaramiento, cuando aplique.
- Retención de datos.
- Retención de archivos raw.
- Retención de screenshots y traces.
- Acceso a auditoría.
- Protección de correos y datos personales.

Los artefactos de diagnóstico no deberán exponer credenciales ni datos innecesarios.

---

## 28. Relación con Warehouse y Nube

Warehouse podrá utilizarse para:

- Conservar archivos crudos.
- Registrar hash.
- Conservar evidencia de origen.
- Mantener metadata de proveedor y fecha de negocio.

Nube podrá utilizarse para:

- Publicar cortes o reportes cuando exista una necesidad documental.
- Conservar exportaciones ejecutivas.
- Consultar evidencia histórica autorizada.

Sin embargo:

- El estado vigente no vivirá en Warehouse.
- Las decisiones manuales no vivirán en Nube.
- Las tablas operativas no dependerán de documentos.
- La idempotencia del dominio no dependerá de títulos de archivos.
- La vista operativa será la interfaz principal.

La publicación diaria automática en Nube no es requisito indispensable de la primera versión.

---

## 29. Fuera de alcance de la primera versión

No se incluye inicialmente:

- Crear rutinas desde Suite.
- Modificar rutinas en Trainingym.
- Modificar rutinas en Gasca.
- Enviar mensajes automáticos al socio.
- Alertas por WhatsApp.
- Coincidencia difusa por nombre.
- Conciliación automática por teléfono.
- Control mediante Excel de regreso.
- Aplicación móvil específica.
- Eliminación física de históricos.
- Sustitución inmediata de Trainingym.
- Edición masiva de estados.
- Reglas predictivas o alertas inteligentes.
- Medición de calidad de la rutina.
- Validación de que el socio ejecutó la rutina.

---

## 30. Casos funcionales mínimos

### Caso 1. Rutina posterior

```text
Venta nueva: 2 de julio
Rutina: 5 de julio
Resultado: CON_RUTINA
Tipo: POSTERIOR
Días para asignación: 3
```

### Caso 2. Rutina preexistente

```text
Pase de cortesía: junio
Rutina: 30 de junio
Venta nueva: 2 de julio
Resultado: CON_RUTINA
Tipo: PREEXISTENTE
Cohorte: julio
```

### Caso 3. Sin rutina

```text
Venta nueva: 2 de julio
Sin evidencia de rutina al corte
Resultado: SIN_RUTINA
```

### Caso 4. No desea rutina

```text
Venta nueva: 2 de julio
Gerente registra rechazo: 4 de julio
Resultado: NO_DESEA_RUTINA
```

### Caso 5. No desea y luego aparece rutina

```text
Rechazo registrado: 4 de julio
Rutina detectada: 8 de julio
Resultado vigente: CON_RUTINA
Historial: conserva rechazo anterior
```

### Caso 6. Rutina desaparece de una extracción

```text
Rutina detectada: 5 de julio
Extracción del 8 de julio no la incluye
Resultado vigente: CON_RUTINA
```

### Caso 7. Correo vacío

```text
Socio nuevo sin correo
Resultado: incidencia EMAIL_VACIO
No se clasifica silenciosamente como SIN_RUTINA
```

### Caso 8. Correo duplicado

```text
Dos registros incompatibles comparten correo
Resultado: incidencia de duplicidad
No se resuelve automáticamente sin regla aprobada
```

### Caso 9. Reejecución

```text
Misma fecha de negocio y mismo contenido
Resultado: no crea duplicados ni eventos redundantes
```

### Caso 10. Gerente regional

```text
Usuario regional consulta el módulo
Resultado: solo recibe su pool de sucursales
Puede consolidar y bajar a detalle
```

---

## 31. Criterios de aceptación funcional

La primera versión se considerará funcional cuando:

1. Los socios nuevos estén segmentados por cohorte mensual.
2. La cohorte se determine por la fecha oficial de Gasca.
3. Una rutina previa a la venta nueva se reconozca correctamente.
4. La conciliación se realice por correo normalizado.
5. Los socios puedan clasificarse en los tres estados definidos.
6. `NO_DESEA_RUTINA` pueda registrarse con motivo.
7. `NO_DESEA_RUTINA` pueda revertirse.
8. Las decisiones manuales queden auditadas.
9. Una rutina detectada cambie automáticamente el estado a `CON_RUTINA`.
10. La decisión manual previa permanezca en el historial.
11. Las decisiones manuales no se pierdan con la ejecución diaria.
12. Una rutina previamente observada no desaparezca por una extracción incompleta.
13. Los correos vacíos o duplicados generen incidencias.
14. Las incidencias no se mezclen silenciosamente con pendientes confirmados.
15. Los gerentes vean únicamente su sucursal.
16. Los regionales vean únicamente su pool.
17. Los roles globales autorizados vean el consolidado completo.
18. Los indicadores respeten filtros y alcance.
19. `NO_DESEA_RUTINA` no cuente como pendiente ni como cumplimiento.
20. La exportación coincida con la vista autorizada.
21. La exportación respete los filtros activos.
22. Las reejecuciones no creen duplicados.
23. Cada ejecución quede registrada.
24. Una falla de Trainingym no bloquee Gunicorn.
25. El login de Trainingym reintente cuando el formulario borre credenciales.
26. La selección de centro se valide y reintente.
27. El proveedor no declare éxito sin acceso real al reporte.
28. El dominio pueda sustituir Trainingym por Gasca sin cambiar la vista ni los estados.
29. La vista pagine y filtre desde backend.
30. El código mantenga separados dominio, providers, scheduler, API y frontend.

---

## 32. Decisiones cerradas

Quedan funcionalmente cerradas:

- El módulo será una vista operativa de Suite.
- No se controlará mediante Excel de regreso.
- El Excel será bajo demanda.
- El cruce inicial será por correo.
- Habrá tres estados vigentes.
- `NO_DESEA_RUTINA` no cuenta como pendiente ni como cumplimiento.
- Las cohortes serán mensuales.
- La fecha de Gasca definirá la cohorte.
- Una rutina preexistente será válida.
- Una rutina detectada tendrá prioridad sobre el rechazo manual.
- El historial nunca se borrará.
- La ejecución será incremental.
- Trainingym será un proveedor temporal.
- Gasca podrá reemplazarlo.
- El proceso largo se ejecutará fuera de Gunicorn.
- El backend será la fuente real de permisos.
- La interfaz deberá contemplar gerente, regional y dirección.

---

## 33. Pendientes para contrato técnico

El contrato técnico deberá resolver:

1. Modelo de tablas.
2. Claves únicas.
3. Identidad interna del socio por cohorte.
4. Política exacta de duplicados.
5. Fuente exacta de socios individuales en Gasca.
6. Campos reales disponibles en Gasca.
7. Campos reales disponibles en Trainingym.
8. Identificador estable de rutina.
9. Catálogo de sucursales y alias.
10. Catálogo exacto de roles globales.
11. Capacidades y acciones del módulo.
12. Endpoints.
13. Paginación.
14. Índices SQL.
15. Historial de eventos.
16. Modelo de ejecuciones.
17. Advisory locks o mecanismo de concurrencia.
18. Worker y horario.
19. Configuración de providers.
20. Política de backfill inicial.
21. Retención de raw y artifacts.
22. Manejo de ejecuciones parciales.
23. Estructura de exportación.
24. Diseño final de la pantalla.
25. Estrategia de pruebas.
26. Estrategia de despliegue.
27. Migraciones Alembic.
28. Integración con permisos existentes.
29. Integración opcional con Warehouse.
30. Periodo de comparación Gasca vs Trainingym.

---

## 34. Referencias arquitectónicas verificadas

La investigación previa del repositorio confirmó la existencia de patrones reutilizables en:

- Cobranza recurrente y su scheduler.
- Publicación de documentos en Warehouse/Nube.
- Vista, filtros, acciones y exportación de Tickets.
- Scope de sucursales y pool regional.
- RPA Gasca SMS.
- Worker de Track.
- Versionado persistente de ejecuciones.
- Imagen Docker con Chromium, Xvfb y Playwright.

También confirmó que no deben copiarse literalmente:

- Marcas de ejecución únicamente en memoria.
- Deduplicación documental por título.
- Paginación completa en frontend.
- Procesos Playwright dentro de requests de Gunicorn.
- Roles globales hardcodeados de forma distinta por módulo.
- Autorización basada únicamente en claims JWT.
- Uso de nombres textuales de sucursal cuando existe un ID canónico.

---

## 35. Aprobación y evolución

Este documento representa el contrato funcional acordado antes de iniciar implementación.

Cualquier cambio posterior en:

- Estados.
- Fórmulas.
- Cohortes.
- Alcances.
- Reglas de prioridad.
- Identidad.
- Fuentes.
- Exportación.
- Acciones manuales.

Deberá reflejarse primero en una nueva versión de este contrato.

El siguiente documento será:

> **Contrato técnico — Control de asignación de rutinas**

Ese contrato deberá aterrizar este diseño sobre la arquitectura real de Suite Ultra antes de escribir código productivo.
