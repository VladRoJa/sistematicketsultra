# Suite Ultra — Contrato funcional E4: Levantamiento físico, validación y conciliación de inventarios

**Módulo:** Inventarios V2  
**Entregable:** E4 — Levantamiento físico por sucursal  
**Naturaleza:** reglas de negocio permanentes, independientes del número de sucursales, fechas, campañas y archivos distribuidos.  
**Alcance inicial:** APARATOS de gimnasio. Sistemas y otras clases de activos quedan fuera de la primera implementación; podrán incorporarse con reglas específicas aprobadas.  
**Estado:** contrato funcional acordado; implementación y aceptación E4 pendientes.  
**Dependencia:** [Contrato global de Inventarios V2](CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md). E5 (apertura a gerentes) permanece condicionado a la aceptación de E4 y autorización explícita.

Este contrato define **qué debe garantizar Suite Ultra**. Los formatos de intercambio, esquemas, endpoints, PR, despliegues, cifras por campaña y avances pertenecen a anexos técnicos y bitácoras, no a este contrato. Cuando una regla del contrato global sea más restrictiva en materia de seguridad, también debe cumplirse.

## 1. Objetivo

Establecer un proceso institucional, verificable y reproducible para levantar físicamente los activos de una sucursal, compararlos con sus referencias oficiales cuando existan, detectar discrepancias y conservar un corte histórico auditable.

El proceso debe atender tanto sucursales con inventario oficial previo como sucursales cuyo inventario físico se registra por primera vez. **Levantar** y **conciliar/cerrar** son etapas distintas; ninguna implica por sí misma modificar el inventario oficial.

## 2. Responsabilidad del levantamiento

1. Cada sucursal tiene un gerente responsable de la integridad y entrega de su inventario.
2. El gerente puede delegar el conteo físico y organizarlo como prefiera, sin transferir la responsabilidad institucional.
3. Por sucursal y ciclo se recibe **un único archivo consolidado** de levantamiento. Correcciones posteriores son **versiones del mismo levantamiento**, no entregas independientes por empleado.
4. La entrega debe identificar sucursal, responsable y fecha. La identidad de sucursal declarada en el archivo debe validarse contra el catálogo oficial.
5. El sistema no exige conocer qué empleado contó individualmente cada aparato. La recepción, validación y cierre sí deben identificar a los usuarios autenticados que realizan esas operaciones.

## 3. Identidad y universo de activos

1. En APARATOS la verificación es primordialmente **por referencia y código identificador**, no por conteo genérico de modelos iguales.
2. Si un aparato ya existe oficialmente, conservar su identidad canónica y el vínculo con la sucursal. No permitir que un archivo altere silenciosamente IDs, códigos ni propiedades maestras.
3. El código interno no sustituye por sí solo la identidad oficial: duplicados, códigos vacíos, asignaciones inusuales y referencias ambiguas son incidencias explícitas por resolver.
4. Un aparato encontrado sin ID oficial se captura como **hallazgo provisional**, sin inventar IDs ni crear automáticamente registros maestros.
5. El universo esperado se define y conserva para cada levantamiento. Los cambios posteriores del stock, maestro o asignación deben detectarse para evitar comparar épocas diferentes.

## 4. Respuestas de verificación física

Cada referencia obligatoria del universo del corte debe recibir una respuesta válida:

- **SI:** el aparato fue localizado físicamente.
- **NO:** el aparato no fue localizado después de la revisión correspondiente.
- **SIN REVISAR:** falta respuesta válida, incluida celda vacía o respuesta no reconocida.

Una observación, un código listado o la ausencia de comentario no sustituyen una respuesta explícita. **Un NO nunca se infiere de una celda vacía.**

**Regla de cierre obligatorio:** ninguna sucursal puede cerrar su levantamiento mientras exista una sola referencia obligatoria SIN REVISAR. El backend calcula esta condición sobre las referencias esperadas; el Excel no es autoridad para declarar cobertura.

La presencia física de un aparato y su estado mecánico son dimensiones diferentes. Un aparato presente pero averiado no se clasifica como no localizado; puede originar un ticket de mantenimiento por flujo independiente.

## 5. Archivo oficial de intercambio

El proceso debe disponer de un archivo único por levantamiento, imprimible y editable digitalmente, que permita identificar sucursal y responsable, consultar el universo esperado, registrar respuestas y observaciones, y documentar hallazgos no registrados.

Las plantillas existentes usan las hojas **CONTROL**, **APARATOS** y **HALLAZGOS**; el detalle de celdas, columnas, versiones y compatibilidad de importación se define en un **anexo técnico versionado**, no como regla universal de negocio.

Los archivos distribuidos válidamente deben ser importables conforme a su versión. Cualquier cambio futuro al formato exige compatibilidad documentada o migración explícita, nunca la pérdida silenciosa de respuestas.

## 6. Recepción y validación

Al recibir una entrega, el backend debe:

1. Verificar usuario autorizado, identidad de sucursal, modalidad de levantamiento y archivo de versión reconocible.
2. Contrastar referencias del archivo contra el universo del levantamiento y su pertenencia a la sucursal.
3. Detectar referencias faltantes, agregadas, duplicadas, alteradas, ambiguas o desconocidas.
4. Identificar por referencia los SI, NO, SIN REVISAR y respuestas inválidas.
5. Registrar hallazgos, observaciones y errores de captura sin equipararlos con referencias oficiales.
6. Recalcular cobertura y resultados sin confiar en fórmulas, porcentajes ni totales provenientes del archivo.
7. Devolver un reporte detallado, accionable y trazable por referencia y por entrega.

**Importar o validar un archivo no modifica stock, maestro, asignaciones, ni genera automáticamente solicitudes o decisiones E2/E3.**

## 7. Modalidades de levantamiento

**Levantamiento de verificación:** existe un inventario oficial previo. Se congela la identidad y estado de las referencias esperadas para contrastarlas con las respuestas físicas. Referencias omitidas o sin SI/NO quedan pendientes; detectar cambios oficiales posteriores.

**Levantamiento inicial:** no existe un universo oficial suficiente para comparar. Se registran los aparatos encontrados de forma provisional y se somete su identificación y eventual alta a un procedimiento autorizado, diferente de asumir que ya existe stock oficial.

No debe considerarse terminado un levantamiento inicial por el mero hecho de tener **cero referencias oficiales esperadas**. Debe existir evidencia de la revisión física realizada, validación del contenido entregado y resolución de los registros que requieran identificación oficial, conforme a la política de cierre aplicable.

## 8. Conciliación y relación con E2/E3

El sistema debe distinguir entre localizado, no localizado, sin revisar, hallazgo no registrado, error de identidad y conflicto con el inventario oficial actual.

Las discrepancias se revisan antes de generar propuestas. Las solicitudes compatibles siguen el flujo de **E2** y las decisiones autorizadas siguen **E3**, conservando vínculos al levantamiento y evidencia original.

Una reimportación no debe duplicar solicitudes ni efectos, ni reemplazar una decisión autorizada. Crear un artículo maestro nuevo requiere un procedimiento de alta autorizado; **E3 no habilita por sí solo altas maestras automáticas**.

La conciliación no debe convertir un faltante físico en una salida/consumo V1 ficticia ni modificar existencias sin autorización.

## 9. Versiones y trazabilidad

Cada levantamiento debe poseer identidad estable, sucursal, responsable, referencia temporal, universo del corte y estado. Registrar sus archivos originales y versiones recibidas, validaciones, resultados, discrepancias, solicitudes/decisiones relacionadas, actores y eventos de cierre.

La entrega corregida conserva las versiones anteriores y la evidencia de los cambios. La carga idéntica repetida debe ser idempotente. Ninguna versión puede reescribir retrospectivamente el corte oficial ni ocultar conflictos posteriores.

Los datos deben permitir reconstruir qué se esperaba, qué se declaró físicamente, qué se corrigió y quién decidió.

## 10. Estados y cierre

El proceso distinguirá como mínimo: preparación, en proceso, entregado, en conciliación y cerrado. Los nombres técnicos y transiciones autorizadas se fijarán en el diseño de implementación.

El backend solo permitirá un **cierre oficial** cuando:

1. Todas las referencias obligatorias tengan respuesta válida; no existan pendientes SIN REVISAR.
2. No queden inconsistencias de identidad sin resolver.
3. Las discrepancias estén resueltas o expresamente documentadas como excepciones autorizadas según una política de cierre definida y auditable.
4. La entrega final, su versión y la evidencia histórica estén conservadas.
5. El usuario que solicita el cierre posea facultades efectivas para esa sucursal y operación.

La cobertura física del 100 % **no equivale** a conciliación del 100 %. Una entrega incompleta puede conservarse y revisarse, pero nunca mostrarse como inventario conciliado/cerrado. Reapertura o cancelación, si se habilitan, deben ser trazables.

## 11. Seguridad y permisos

Toda lectura, importación, conciliación y transición de estado debe validar permisos y ámbito efectivo **en backend**. El archivo recibido es una entrada no confiable: su contenido no concede roles ni alcance territorial.

La responsabilidad del gerente **no** le confiere por sí sola permisos técnicos para crear, aprobar o modificar inventario oficial.

La apertura productiva de Inventarios V2 a GERENTE y GERENTE_REGIONAL está reservada al **gate E5**; E4 debe validarse inicialmente con usuarios ya autorizados, sin habilitación implícita por menú, URL o API.

Preservar las garantías de autorización y auditoría de E2/E3, las migraciones Alembic para cambios de esquema y la trazabilidad histórica de V1.

## 12. Criterios de aceptación y gobierno documental

E4 se aceptará cuando pueda demostrarse, con QA automatizado y al menos un levantamiento real autorizado, que Suite Ultra:

- Registra levantamientos reproducibles por sucursal y ciclo.
- Procesa un archivo consolidado y sus reentregas sin perder evidencias.
- Distingue entre levantamiento inicial y verificación de inventario existente.
- Identifica exactamente todos los aparatos sin respuesta y **bloquea su cierre**.
- Detecta errores de identidad, duplicados, omisiones y conflictos sin falsificar resultados.
- Concilia hallazgos mediante procesos autorizados, sin afectar stock al importar.
- Conserva historial, actores, versiones, excepciones y corte oficial verificable.
- Rechaza accesos fuera de ámbito y no habilita E5 por accidente.

Este documento contiene reglas institucionales. Se mantienen separados:

- **Anexo técnico versionado:** estructura de Excel, APIs, modelos, validaciones e implementación.
- **Bitácora de desarrollo:** PR, commits, migraciones, pruebas, QA y despliegues.
- **Bitácora operativa:** campañas, sucursales participantes, archivos entregados/recibidos e incidencias.

Las variaciones de fechas, nombres de sucursales, cantidad de clubes o archivos no exigen cambiar este contrato mientras se conserven sus reglas.
