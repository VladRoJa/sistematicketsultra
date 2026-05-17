# Paleta oficial Ultra

## Objetivo

Este documento define la paleta oficial de Ultra para Suite Ultra y su uso recomendado dentro de la interfaz.

La paleta debe usarse como base para componentes, navegación, botones, tablas, cards, estados visuales y documentación.

---

## Colores oficiales

### Ultra Orange / Red

- Pantone: 179 C
- HEX: `#E54525`
- RGB: `229, 69, 37`

Uso recomendado:

- Color primario de marca.
- Botones principales.
- Elementos activos del menú.
- Acentos visuales.
- Indicadores de selección.
- Bordes o líneas de énfasis.

No usar para:

- Errores del sistema.
- Estados negativos.
- Alertas críticas.

Para errores se debe usar un rojo semántico separado.

---

### Ultra Black

- Referencia: 90% Black

Uso recomendado:

- Header principal.
- Navegación.
- Fondos premium.
- Texto de alto énfasis.
- Contrastes fuertes.

---

### Ultra Blue

- Pantone: 2728 C
- RGB: `44, 69, 149`
- HEX aproximado: `#2C4595`

Uso recomendado:

- Color complementario.
- Estados informativos.
- Secciones relacionadas con Primaria / Ultra Kids.
- Acentos secundarios cuando el naranja no sea adecuado.

---

## Tokens CSS propuestos

```css
:root {
  --ultra-orange: #e54525;
  --ultra-orange-dark: #c93a20;
  --ultra-orange-soft: #fde8e2;

  --ultra-blue: #2c4595;
  --ultra-blue-soft: #e8edff;

  --ultra-black-90: #1a1a1a;
  --ultra-charcoal: #2b2b2b;

  --ultra-gray-900: #252525;
  --ultra-gray-700: #4b5563;
  --ultra-gray-500: #6b7280;
  --ultra-gray-300: #d1d5db;
  --ultra-gray-200: #e5e7eb;
  --ultra-gray-100: #f3f4f6;

  --ultra-bg: #f6f7f9;
  --ultra-surface: #ffffff;

  --ultra-success: #16a34a;
  --ultra-warning: #f59e0b;
  --ultra-danger: #dc2626;
  --ultra-info: var(--ultra-blue);
}