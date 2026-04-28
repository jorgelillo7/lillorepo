---
name: Lloros League
description: Fantasy football league dashboard — casual but opinionated
colors:
  primary: "#2d3748"
  secondary: "#4a5568"
  muted: "#718096"
  background: "#f7fafc"
  surface: "#ffffff"
  border: "#e2e8f0"
  accent: "#38a169"
  accent-hover: "#276749"
  accent-light: "#c6f6d5"
  danger: "#e53e3e"
  warning: "#d69e2e"
typography:
  heading:
    fontFamily: Oswald
    fontWeight: "700"
    fontSize: 3rem
    letterSpacing: 0.05em
  subheading:
    fontFamily: Oswald
    fontWeight: "500"
    fontSize: 1.5rem
  body:
    fontFamily: Roboto
    fontWeight: "400"
    fontSize: 1rem
    lineHeight: 1.6
  label:
    fontFamily: Roboto
    fontWeight: "500"
    fontSize: 0.875rem
rounded:
  sm: 4px
  md: 8px
  lg: 12px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 48px
components:
  card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    borderRadius: "{rounded.lg}"
    padding: "{spacing.lg}"
  nav-link:
    color: "{colors.secondary}"
    activeColor: "{colors.primary}"
    activeBorderColor: "{colors.accent}"
    activeFontWeight: "700"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    hoverBackgroundColor: "{colors.accent-hover}"
    borderRadius: "{rounded.md}"
  pagination-active:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    borderColor: "{colors.accent}"
  search-input:
    focusRingColor: "{colors.accent}"
    borderRadius: "{rounded.lg}"
---

## Overview

Sport dashboard con personalidad — mezcla de marcador de fútbol y tablón de anuncios de una liga de amigos. El tono es desenfadado pero el layout es limpio. El verde acento remite al campo de juego; los grises oscuros aportan legibilidad sin resultar corporativos.

La app no es un producto comercial, es una intranet de liga privada. El diseño puede ser directo y denso en información; no hay que vender nada.

## Colors

El verde `#38a169` es el único color "vivo" de la paleta y debe usarse con criterio:

- **Primary (#2d3748):** Texto principal, titulares de contenido, iconos de UI.
- **Secondary (#4a5568):** Texto secundario, labels, metadatos.
- **Muted (#718096):** Fechas, pies de nota, contenido de menor jerarquía.
- **Accent (#38a169):** Indicador de nav activo, botones de acción confirmada, números de página activos, highlights de autor. Único color "vivo" — no usar como decoración.
- **Background (#f7fafc):** Base de página, levemente off-white para reducir fatiga visual frente a blanco puro.
- **Surface (#ffffff):** Cards y paneles elevados sobre el fondo.
- **Border (#e2e8f0):** Separadores y bordes de card — sutil, no prominente.

## Typography

Dos familias, roles bien separados:

- **Oswald** para el logotipo `LLOROS LEAGUE` y títulos de sección con alto impacto. Siempre en peso 500 o 700, nunca por debajo. El tracking amplio (0.05em) en el heading principal refuerza el carácter deportivo.
- **Roboto** para todo el cuerpo de texto: comunicados, tablas, formularios, metadatos. Legible en densidades de información alta.

No mezclar las dos familias en el mismo bloque de texto.

## Layout

- **Max-width:** `max-w-4xl` (56rem) centrado — suficiente para tablas de datos sin resultar excesivamente ancho en desktop.
- **Padding de página:** `p-4` en móvil, `p-8` en desktop.
- La cabecera usa un layout de tres columnas en desktop (espaciador / título centrado / selector de temporada) que colapsa a centrado en móvil.
- Las cards usan `shadow-md` en reposo y `shadow-lg` en hover para dar profundidad sin ser excesivas.

## Components

### Card

La unidad básica de contenido. Fondo blanco, borde sutil `#e2e8f0`, radio `rounded-xl` (12px), padding `p-6`. Todas las páginas de contenido usan cards como contenedor principal.

### Nav

Barra horizontal bajo el header. Los links inactivos son `#4a5568`; el activo usa `#2d3748` en negrita con un subrayado de 2px en `#38a169`. No usar color de fondo en el item activo — el subrayado es el indicador.

### Search Input

Input de ancho completo con `focus:ring-2 focus:ring-green-500`. El foco debe ser claramente visible.

### Pagination

Botones con borde, radio `rounded-md`. La página activa invierte colores: fondo `#38a169`, texto blanco.

## Do's and Don'ts

- **Do:** Usar `accent` para un único elemento interactivo activo por contexto.
- **Do:** Mantener la densidad de información alta — esta app la necesita.
- **Don't:** Usar Oswald en peso < 500.
- **Don't:** Añadir nuevos colores sin actualizar este archivo primero.
- **Don't:** Usar sombras más pronunciadas que `shadow-lg` — el diseño es plano con sombra funcional.
