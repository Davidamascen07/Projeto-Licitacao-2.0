---
name: Technical Precision
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45474c'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#75777d'
  outline-variant: '#c5c6cd'
  surface-tint: '#545f73'
  primary: '#091426'
  on-primary: '#ffffff'
  primary-container: '#1e293b'
  on-primary-container: '#8590a6'
  inverse-primary: '#bcc7de'
  secondary: '#5c5f61'
  on-secondary: '#ffffff'
  secondary-container: '#e0e3e5'
  on-secondary-container: '#626567'
  tertiary: '#1e1200'
  on-tertiary: '#ffffff'
  tertiary-container: '#35260c'
  on-tertiary-container: '#a38c6a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e3fb'
  primary-fixed-dim: '#bcc7de'
  on-primary-fixed: '#111c2d'
  on-primary-fixed-variant: '#3c475a'
  secondary-fixed: '#e0e3e5'
  secondary-fixed-dim: '#c4c7c9'
  on-secondary-fixed: '#191c1e'
  on-secondary-fixed-variant: '#444749'
  tertiary-fixed: '#fadfb8'
  tertiary-fixed-dim: '#ddc39d'
  on-tertiary-fixed: '#271902'
  on-tertiary-fixed-variant: '#564427'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  mono-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  panel-gap: 1px
  container-padding: 24px
---

## Brand & Style
The design system is engineered for high-utility document analysis, prioritizing cognitive clarity and professional rigor. The brand personality is clinical, reliable, and efficient, moving away from marketing-centric aesthetics toward a functional "work-tool" environment. 

The visual style follows a **Modern Corporate/SaaS** approach with a heavy emphasis on **Minimalism**. It utilizes a "data-first" hierarchy where the interface recedes to let the document content and analysis results take precedence. Visual noise is minimized through the elimination of unnecessary decorative elements, relying instead on systematic spacing and a restrained color palette to guide the user's focus.

## Colors
The color strategy employs a "Low-Saturation Professional" foundation. 
- **Primary (#1e293b):** A deep navy used for structural elements like sidebars, primary navigation, and high-emphasis text to provide a sense of stability.
- **Secondary/Background (#f8fafc):** A cool light gray used for the main application canvas to reduce eye strain during long-form reading and analysis.
- **Surface (#ffffff):** Pure white is reserved for active work areas (document viewers, chat bubbles, and input fields) to create a clear "layer" above the background.
- **Accents:** Emerald green is used exclusively for "Completed" states and "Success" confirmations. Amber is used for "In Progress" states or "System Warnings."

## Typography
This design system utilizes **Inter** for all UI elements to ensure maximum legibility across small font sizes common in data-heavy dashboards. 

- **Weight Usage:** Semi-bold (600) is reserved for structural headings. Medium (500) is used for interactive labels and buttons. Regular (400) is used for all body copy and metadata.
- **Readability:** Body text uses a slightly increased line-height (1.5x) to facilitate the reading of dense document abstracts and chat outputs.
- **Code/Technical:** For document metadata or technical identifiers, a monospaced font (JetBrains Mono) is used at a smaller scale.

## Layout & Spacing
The layout follows a **Fixed-Fluid Hybrid** dashboard model. The dashboard is divided into three primary functional zones:
1.  **Sidebar (Fixed, 280px):** For file management and navigation.
2.  **Central Stage (Fluid):** The primary document viewing area.
3.  **Analysis Panel (Fixed, 400px):** For chat-based interaction and insights.

Spacing is governed by an 8px grid system. Margins within panels are generous (24px) to prevent the "cluttered" feel of traditional legacy software, while gutters between major panels are kept minimal (1px borders or 8px gaps) to maintain a cohesive single-page environment. For mobile, the panels stack vertically with the Analysis Panel pinned to the bottom as a drawer.

## Elevation & Depth
Depth is conveyed through **Tonal Layering** and **Low-Contrast Outlines** rather than heavy shadows.

- **Level 0 (Background):** The application shell in `#f8fafc`.
- **Level 1 (Panels):** Document viewer and chat container use a white background with a 1px border (`#e2e8f0`).
- **Level 2 (Popovers/Modals):** Elements that float above the UI use a subtle ambient shadow: `0 4px 12px rgba(30, 41, 59, 0.08)` to indicate temporary presence without breaking the technical aesthetic.
- **Active States:** Subtle 2px "Focus" rings in the primary color are used for keyboard navigation and active input states.

## Shapes
The design system uses a **Soft (0.25rem)** roundedness profile. This provides a professional, modern feel that is less aggressive than sharp corners but more formal than highly rounded "consumer" apps. 
- **Standard (4px):** Buttons, inputs, and small cards.
- **Large (8px):** Main panel containers and modals.
- **Full:** Only used for status indicators/pills to distinguish them from interactive buttons.

## Components
- **Buttons:** Primary buttons use the `#1e293b` background with white text. Secondary buttons use a transparent background with a 1px border. There is no gradient or gloss.
- **Input Fields:** Use a white background, 1px border in `#cbd5e1`, and a subtle 4px corner radius. Placeholder text is in `#94a3b8`.
- **Status Chips:** Small, semi-pill shapes. Success uses a light emerald tint background with dark emerald text; Warning uses a light amber tint with dark amber text.
- **Document Cards:** Used in the upload/file list section. They feature a file-type icon, title, and "Date Modified" metadata in `body-sm`.
- **Chat Bubbles:** The AI response uses a very light gray background (`#f1f5f9`), while user queries are simple text with a left-side primary color accent border to differentiate participants without using "bubble" shapes.
- **Data Tables:** Borderless rows with a 1px bottom separator. Header row uses `label-md` styling for clear categorization.