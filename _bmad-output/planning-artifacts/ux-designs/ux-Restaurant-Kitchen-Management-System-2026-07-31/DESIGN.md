---
name: 'Restaurant-Kitchen-Management-System'
description: 'Internal, role-gated staff tool for a restaurant kitchen (Waiter, Cook, Warehouse Manager, Admin) plus the Smart Chef AI assistant. MUI defaults, one cool accent layered on top, no restaurant branding.'
status: draft
sources:
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/prd.md'
  - '_bmad-output/planning-artifacts/prds/prd-Restaurant-Kitchen-Management-System-2026-07-24/addendum.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-Restaurant-Kitchen-Management-System-2026-07-30/ARCHITECTURE-SPINE.md'
colors:
  # All tokens not listed here inherit MUI's default light/dark palette
  # wholesale: background, paper, text.primary/secondary, divider, and the
  # semantic error/warning/success/info/grey scale used for status colors
  # (see the Colors section below). This system adds exactly one accent
  # color pair, layered on top of MUI's `primary` slot, per architecture
  # AD-13 (MUI is the only UI component library).
  accent: '#0B6E8F'
  accent-foreground: '#FFFFFF'
  accent-dark: '#4FC3D9'
  accent-foreground-dark: '#08171B'
typography:
  default:
    note: 'Inherits MUI default Roboto type scale (h1-h6, body1, body2, caption, overline) wholesale. No custom font, no custom sizes.'
  dense-row:
    note: 'Table/list rows render at MUI body2/caption text with size="small" component density, to satisfy the dense-content-over-whitespace requirement.'
rounded:
  DEFAULT:
    note: 'Inherits MUI default theme.shape.borderRadius (4px) everywhere. No override.'
spacing:
  base:
    note: 'Inherits MUI default 8px spacing unit. Density comes from component sizing (size="small" on tables, lists, inputs, buttons), not a new spacing scale.'
  dense-row-height: '36px'
components:
  status-badge:
    pending:
      color: 'grey.600 (MUI default palette, inherited)'
      icon: 'RadioButtonUncheckedIcon'
    in_preparation:
      color: 'warning.main (MUI default palette, inherited)'
      icon: 'LocalFireDepartmentIcon'
    ready:
      color: 'success.main (MUI default palette, inherited)'
      icon: 'CheckCircleIcon'
    served:
      color: 'info.main (MUI default palette, inherited)'
      icon: 'DoneAllIcon'
    closed:
      color: 'text.disabled (MUI default palette, inherited)'
      icon: 'ArchiveIcon'
    cancelled:
      color: 'error.main (MUI default palette, inherited)'
      icon: 'CancelIcon'
  table-tile:
    default-state: 'MUI Card/Paper default, no override'
    attention-state:
      color: '{components.status-badge.ready.color}'
      icon: '{components.status-badge.ready.icon}'
  kitchen-display-card:
    surface: 'MUI dark-theme background.paper (dark is this surfaces default theme)'
    elevation: 1
    corner: '{rounded.DEFAULT}'
  order-item-row:
    status: '{components.status-badge}'
    cancel-action: 'MUI destructive/error text button behind a confirm step, no override'
  ingredient-row:
    in-shortage:
      color: '{components.status-badge.cancelled.color}'
      icon: 'WarningAmberIcon'
    sort: 'in-shortage rows pinned to top, then alphabetical'
  alert-row:
    color: '{components.status-badge.cancelled.color}'
    icon: 'WarningAmberIcon'
    dismiss-control: 'none (resolves only via an Ingredient movement)'
  recipe-suggestion-card:
    surface: 'MUI Card default, no override'
    confirm-action: '{components.button-primary}'
    dismiss-action: 'MUI outlined/text button default, no override'
  nav-badge-alerts:
    color: '{components.status-badge.cancelled.color}'
    foreground: '{colors.accent-foreground}'
  nav-badge-attention:
    color: '{components.status-badge.ready.color}'
    foreground: '{colors.accent-foreground}'
  button-primary:
    background: '{colors.accent}'
    background-dark: '{colors.accent-dark}'
    foreground: '{colors.accent-foreground}'
    foreground-dark: '{colors.accent-foreground-dark}'
    corner: '{rounded.DEFAULT}'
  theme-toggle:
    style: 'MUI IconButton default, no override'
updated: '2026-07-31'
---

## Brand & Style

This is a shift-speed back-office tool for four roles who are not looking at it for pleasure: Maya is mid-rush, Amir is watching a board instead of a paper ticket rail, Noa is often not looking at the screen at all, David is doing admin between services. There is no diner-facing surface anywhere in the system, so there is no reason to dress it up for one. No restaurant branding, no warm hospitality voice, no marketing copy, no illustration. The aesthetic posture is "clean back-office software," not "restaurant app."

Concretely, that means inheriting MUI's defaults almost entirely and adding exactly one deliberate layer on top: a single cool accent color for primary actions and highlights (per architecture AD-13, MUI is the only UI library in this system). Everything else, MUI's neutral surfaces, its semantic error/warning/success/info palette, its type ramp, its shadows, its corners, is used as shipped. The discipline here is the same one Drift-style shadcn products use: if the interface can't justify overriding a default, it doesn't override it. The one place this system does invent real visual vocabulary is the traffic-light status convention (Colors, below) and its pairing with icons and labels, because that convention carries real operational weight (colorblind legibility at the kitchen display) rather than being decorative.

The system is genuinely theme-aware: every screen supports a real light/dark toggle, not a per-role hardcoded look. The Kitchen Display initializes in dark mode by default (glare and distance-legibility at the pass), every other role's home surface initializes in light mode, and any user can flip either way at any time.

## Colors

The palette is MUI's default light/dark palette plus one accent pair and one status-color convention layered on top. Nothing else is introduced.

- **{colors.accent} (`#0B6E8F`, light mode) / {colors.accent-dark} (`#4FC3D9`, dark mode)** is the only brand-layer color in the system. It replaces MUI's default `primary` slot. Used for primary buttons (Confirm actions, Submit order, Log movement), active nav items, and the theme toggle's active state. `{colors.accent}` on white carries a measured contrast ratio of 5.76:1; `{colors.accent-dark}` on MUI's dark background (`#121212`) carries 9.05:1. Both clear WCAG 2.2 AA (4.5:1) for text and UI components in their respective mode. Paired foreground text/icon colors are `{colors.accent-foreground}` (`#FFFFFF`, on the light accent) and `{colors.accent-foreground-dark}` (`#08171B`, on the dark accent), each verified above 8:1 against its fill.
- **MUI's semantic scale** (`error`, `warning`, `success`, `info`, `grey`, `text.disabled`) is inherited wholesale and is what powers the status-color convention below. It is not restated as new hex tokens here; the delta this system adds is only the *mapping* of those existing tokens onto the Order/OrderItem status vocabulary, and the rule that color is never the only signal.
- **Status-color convention (traffic-light family, colorblind-safe):** every OrderItem and Order status, everywhere it appears (Table tile, Order Item row, Kitchen Display card, Order/table detail), renders as a color from the table below, paired with a distinct icon and a text label. Color alone never carries the meaning, which is the specific accessibility requirement driving this table (the Kitchen Display in particular has to be legible to a colorblind cook).

  | Status | Applies to | Color (MUI token) | Icon |
  |---|---|---|---|
  | `pending` | OrderItem, Order | `{components.status-badge.pending.color}` (neutral, not started) | `{components.status-badge.pending.icon}` |
  | `in_preparation` | OrderItem, Order | `{components.status-badge.in_preparation.color}` (amber) | `{components.status-badge.in_preparation.icon}` |
  | `ready` | OrderItem, Order | `{components.status-badge.ready.color}` (green) | `{components.status-badge.ready.icon}` |
  | `served` | Order only (OrderItem has no `served` state, per PRD glossary and FR-11/FR-12) | `{components.status-badge.served.color}` (blue, "delivered, not yet closed") | `{components.status-badge.served.icon}` |
  | `closed` | Order only | `{components.status-badge.closed.color}` (muted, terminal) | `{components.status-badge.closed.icon}` |
  | `cancelled` | OrderItem only (Order has no `cancelled` state; a cancelled item is simply excluded from the Order's derived status per FR-12) | `{components.status-badge.cancelled.color}` (red) | `{components.status-badge.cancelled.icon}` |

  The same red token (`{components.status-badge.cancelled.color}`) is reused for the Ingredient-in-shortage state and the Alert row, since both represent the same "needs action, uncorrected" meaning as a cancelled item, just in the inventory domain instead of the order domain.

Avoid: a second brand color, warm/kitchen-themed accents (fire, wood, harvest tones were explicitly rejected in favor of a cool blue/teal, per the Discovery decision log), decorative gradients, and color-only status indication anywhere.

## Typography

Inherits MUI's default Roboto type ramp wholesale, see `{typography.default}`. No custom font, no custom display size. The one delta is density: because this system favors dense tables and lists over whitespace-heavy cards, row-level text renders at MUI's `body2`/`caption` roles inside `size="small"` components (`{typography.dense-row}`), rather than the more generously padded default component sizing. Headings and page titles use MUI's default `h5`/`h6` roles, unchanged.

## Layout & Spacing

Inherits MUI's default 8px spacing unit (`{spacing.base}`). The one addition is `{spacing.dense-row-height}` (36px), used for table/list rows across Tables, Ingredients, Order Item rows, and Alert rows, tighter than MUI's default row height, in service of the dense-content decision. Single-surface responsive web, desktop/PC browser only: no mobile or tablet breakpoints are defined (see EXPERIENCE.md Foundation).

## Elevation & Depth

Inherited from MUI as-is: default `Paper`/`Card` elevation (1) for rows and cards, elevation 2-3 reserved for dialogs and menus per MUI defaults. No custom shadow language is introduced. The one thing worth stating explicitly: the Kitchen Display's cards (`{components.kitchen-display-card}`) stay at elevation 1 even against a dark background, rather than adding a heavier shadow to compensate, dark-mode legibility here comes from status color and icon contrast, not elevation.

## Shapes

Inherits MUI's default corner radius (`{rounded.DEFAULT}`, 4px) everywhere, buttons, cards, inputs, dialogs. Status badges use MUI's `Chip` component, which is already pill-shaped (`rounded/full`) by default, no override needed.

## Components

Everything not listed below is used as MUI ships it: `Button`, `TextField`, `Select`, `Dialog`, `Table`, `List`, `AppBar`, `Drawer`, `Skeleton`, `Snackbar`/`Alert`. The delta components are the ones carrying this system's status-color convention and its two attention-cue mechanisms.

- **Status badge (`{components.status-badge}`)**, the shared atom behind every status rendering in the system. Built on MUI `Chip`: colored fill or outline per the status-color table above, plus the matching icon, plus the text label spelled out (never abbreviated to a color swatch alone). Used inside Table tile, Order Item row, Kitchen Display card, and Order/table detail.
- **Table tile (`{components.table-tile}`)**, MUI `Card`, default surface in its normal state. In its attention state (an occupied table has an item ready to serve), it takes on `{components.table-tile.attention-state}`, the same green-plus-check treatment as the `ready` status badge, applied at the tile level rather than a new color, so the visual vocabulary stays consistent with the rest of the traffic-light convention.
- **Kitchen Display card (`{components.kitchen-display-card}`)**, MUI `Paper`/`Card` at elevation 1, rendered on the dark-theme background by default. One card per table, grouping that table's Order Items. Each item's advance-status control is a single large click target (no drag, no multi-select), sized generously given this surface is read from a short distance.
- **Order Item row (`{components.order-item-row}`)**, status badge plus dish name, quantity, and note. The cancel action is a destructive-variant MUI button gated behind a confirm step (see Component Patterns in EXPERIENCE.md for the behavioral rule this protects, AD-11's no-auto-reversal invariant). Pick-up and mark-ready are each a single click, no confirm step.
- **Ingredient row (`{components.ingredient-row}`)**, default MUI table row; an in-shortage row switches to the same red token as a cancelled OrderItem (`{components.ingredient-row.in-shortage.color}`) plus a warning icon, and is sorted to the top of the list, not just color-flagged in place.
- **Alert row (`{components.alert-row}`)**, same red-plus-icon treatment as an in-shortage Ingredient row. Deliberately has no dismiss control in its own right; it only leaves the list when the underlying shortage is resolved via a Stock Movement.
- **Recipe Suggestion card (`{components.recipe-suggestion-card}`)**, MUI `Card`, default surface. Shows the requesting Cook and the ingredients the suggestion drew on. Exactly two actions: Confirm into Dish (`{components.button-primary}`, the only accent-colored action on this card) and Dismiss (plain outlined/text button, no override).
- **Nav badges (`{components.nav-badge-alerts}`, `{components.nav-badge-attention}`)**, both are MUI `Badge` on a nav item. The Alerts badge (Noa) uses the same red token as a cancelled/in-shortage state, since it signals an unresolved problem. The "tables need attention" counter (Maya) uses the same green token as a `ready` status, since it signals a positive, actionable state (food is up), not a fault. Neither clears via a dismiss action, only via the underlying event resolving (see EXPERIENCE.md State Patterns).
- **Theme toggle (`{components.theme-toggle}`)**, MUI `IconButton` default, present in the app bar on every surface. No custom iconography beyond MUI's own sun/moon icons.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Inherit MUI defaults for anything not explicitly listed above | Introduce a second UI component library or a second accent color |
| Use `{colors.accent}` / `{colors.accent-dark}` only for primary actions and active/selected chrome | Use the accent color to indicate status (that's the traffic-light table's job) |
| Pair every status color with an icon and a text label | Ship a status indicator that relies on color alone |
| Keep tables and lists dense (`{spacing.dense-row-height}`, `size="small"`) | Pad rows out with whitespace "for polish" on a tool built for shift speed |
| Reuse the `ready`-green and `cancelled`/shortage-red tokens for the two attention-cue badges | Invent a third badge color for alerts or attention counts |
| Write plain, factual microcopy (see EXPERIENCE.md Voice and Tone) | Add restaurant branding, marketing language, or celebratory copy anywhere |
