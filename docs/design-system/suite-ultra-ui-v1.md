# Suite Ultra UI v1

## Objetivo

Definir la primera versión formal del sistema visual de Suite Ultra.

Este documento servirá como guía para el refactor visual de módulos existentes y para el diseño de nuevos módulos.

---

## Principios de diseño

### 1. Consistencia

Todos los módulos deben sentirse parte de la misma plataforma.

Aplica para:

- Menú principal.
- Submenús.
- Cards.
- Tablas.
- Botones.
- Badges.
- Formularios.
- Estados vacíos.
- Estados de carga.

---

### 2. Claridad operativa

Suite Ultra es una plataforma interna de operación y BI. La interfaz debe priorizar lectura rápida, acciones claras y trazabilidad.

---

### 3. Diseño por módulos

Cada módulo debe tener identidad visual consistente, pero sin romper el layout global.

Módulos actuales:

- Tickets
- Mantenimiento Preventivo
- Inventario
- Warehouse
- Track / BI
- Catálogos
- Permisos
- Asistencia

---

### 4. Submenús usables

Los submenús no deben depender de hover frágil ni estar separados visualmente del menú principal.

Reglas:

- El submenú debe estar pegado al módulo activo.
- No debe existir un espacio incómodo entre menú y submenú.
- Debe ser posible mover el cursor sin que el panel desaparezca accidentalmente.
- El módulo activo debe ser evidente.

---

### 5. Tokens antes que colores directos

Los colores deben venir de variables globales.

Ejemplo:

```css
background: var(--ultra-orange);
color: var(--ultra-surface);
```

Evitar:

```css
background: #e54525;
```

salvo en definición de tokens.

---

## 6. Convención de banderas de refactor

Durante el refactor visual de Suite Ultra UI v1, toda sección nueva o modificación estructural relevante debe marcarse con una bandera visible en el archivo.

El objetivo es facilitar:

- Búsqueda con `grep`.
- Revisión de cambios.
- Limpieza posterior.
- Rollback parcial.
- Separación entre código heredado y código nuevo del refactor.

---

### Formato para TypeScript

```ts
// ============================================================================
// Suite Ultra UI v1 - <descripción corta>
// ============================================================================
```

---

## Loader Suite Ultra UI v1

### Objetivo

Definir un loader visual de marca para Suite Ultra.

El loader debe sentirse como parte de la identidad oficial de Ultra y funcionar como pantalla de espera durante login, carga inicial o procesos pesados.

### Comportamiento visual

- Fondo oscuro con gradientes suaves.
- Logo Ultra al centro.
- Logo con pulso sutil.
- Anillo exterior giratorio.
- Halo naranja respirando.
- Texto de carga.
- Dots animados.

### Reglas

- No usar GIFs.
- No depender de imágenes externas cuando pueda usarse SVG.
- No bloquear lógica de autenticación.
- Mantener el loader como componente compartido.
- Evitar animaciones agresivas o mareantes.