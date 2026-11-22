---
name: expert-checker
description: Price and promotion watcher for expert.de; every price names its place; receipt rows with the cheapest path first.
colors:
  ground: "#f2f4f7"
  card: "#ffffff"
  card-sunken: "#f6f7f9"
  ink: "#1b1f24"
  ink-muted: "#5f6b7a"
  hairline: "#e3e7ec"
  hairline-strong: "#d0d6de"
  action-blue: "#1a66d6"
  action-blue-soft: "#e8f0fd"
  action-blue-ink: "#154f9f"
  best-green: "#188038"
  best-green-soft: "#e4f3e8"
  best-green-ink: "#146c2e"
  cashback-amber: "#b45f06"
  cashback-amber-soft: "#fdf0d8"
  cashback-amber-ink: "#8f4b00"
  set-teal: "#0b7285"
  set-teal-soft: "#e0f3f6"
  set-teal-ink: "#0a5c6b"
  clearance-red: "#c5221f"
  clearance-red-soft: "#fde8e6"
  clearance-red-ink: "#a11b18"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.15
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.25
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.3
  price:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.15
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.03em"
  badge:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', Roboto, 'Segoe UI', system-ui, sans-serif"
    fontSize: "11.5px"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  badge: "6px"
  control-sm: "7px"
  thumb: "8px"
  control: "9px"
  tile: "10px"
  card: "12px"
  pill: "999px"
spacing:
  "2xs": "2px"
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
  "2xl": "14px"
  "3xl": "16px"
components:
  button-secondary:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-secondary-hover:
    backgroundColor: "{colors.card-sunken}"
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "8px 13px"
  button-primary-hover:
    backgroundColor: "{colors.action-blue-ink}"
  button-small:
    rounded: "{rounded.control-sm}"
    padding: "5px 10px"
    typography: "{typography.caption}"
  button-pressed:
    backgroundColor: "{colors.action-blue-soft}"
    textColor: "{colors.action-blue-ink}"
  chip:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
  chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.ground}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
  badge-set:
    backgroundColor: "{colors.set-teal-soft}"
    textColor: "{colors.set-teal-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  badge-cashback:
    backgroundColor: "{colors.cashback-amber-soft}"
    textColor: "{colors.cashback-amber-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  badge-clearance:
    backgroundColor: "{colors.clearance-red-soft}"
    textColor: "{colors.clearance-red-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  badge-drop:
    backgroundColor: "{colors.best-green-soft}"
    textColor: "{colors.best-green-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  badge-new:
    backgroundColor: "{colors.action-blue-soft}"
    textColor: "{colors.action-blue-ink}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  badge-off:
    backgroundColor: "{colors.card-sunken}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.badge}"
    rounded: "{rounded.badge}"
    padding: "2px 7px"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "12px 14px"
  price-column:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  price-column-best:
    backgroundColor: "{colors.best-green-soft}"
    textColor: "{colors.best-green-ink}"
    rounded: "{rounded.control}"
    padding: "7px 10px"
  price-tile:
    rounded: "{rounded.tile}"
    padding: "10px 12px"
    typography: "{typography.display}"
  infobox:
    backgroundColor: "{colors.action-blue-soft}"
    textColor: "{colors.action-blue-ink}"
    rounded: "{rounded.tile}"
    padding: "10px 12px"
  input:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 11px"
  tab:
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.thumb}"
    padding: "5px 4px"
  tab-active:
    textColor: "{colors.action-blue}"
  top-bar:
    backgroundColor: "{colors.card}"
    padding: "10px 16px"
    height: "54px"
---

# Design System: expert-checker

## Overview

**Creative North Star: "Der Preisvergleich am Küchentisch"**

The comparison table a careful buyer draws by hand on the kitchen table, made native. The app plays the price-tracker category straight: white cards on a cool grey ground, the system sans of the phone, tabular numerals everywhere, and a phone-width column (max 480px) that stays a phone column even on a desktop. Nothing is decorated; every colour, badge and bold weight carries a meaning the buyer would otherwise have to write in the margin.

The signature is the receipt (revised 2026-11-22, prototype/b2.html). Under the product head, rows list the cheapest path first with its place, distance, stock and badge, then the cashback deduction, then the total "Dein Preis inkl. Cashback", then the other path and set deals marked "nicht im Preis". No price sits in the card head, every price says whether cashback is included, and no fact appears twice. Colour is a vocabulary, not a mood: green means the lowest price of the last 30 days after cashback, blue is action and selection, amber is cashback, teal is a set deal, red is Aussteller, Restposten and price rises.

Density is high but legible: 15px body, 12.5px captions, hairline dividers between rows, 12px gaps between cards. Depth is a whisper (one two-layer shadow under every card). A dark theme exists with the same roles remapped; the light theme is the canonical source of tokens.

**Key Characteristics:**
- Category-standard price-tracker look, idealo and Geizhals level polish, no brand theatre.
- White cards (12px radius, soft shadow) on cool grey; hairline dividers between rows inside a card.
- System sans (SF Pro on iPhone, Roboto fallback), tabular numerals on the whole body.
- Five semantic hues, each in a triad (base, soft tint, ink), used only for their meaning.
- One badge shape and size everywhere (6px radius, 11.5px, 600 weight, soft tint + ink text).
- Product image at the left of every product head (64px thumb in the list, 150px hero on the product page).

## Colors

A grey-blue neutral ground carries five semantic hues, each as a base, a soft tint for fills and an ink for text on that tint.

### Primary
- **Action Blue** (`action-blue`): the primary button, the active bottom tab, focus outlines, the range slider accent, the back arrow. Means "you can do something here" or "this is selected".
- **Action Blue Soft / Ink** (`action-blue-soft`, `action-blue-ink`): pressed toggles, the selected device row in the calculator, the infobox, the "neu seit heute" and "Zielpreis erreicht" badges, link text.

### Secondary
- **Best Green** (`best-green`, `best-green-soft`, `best-green-ink`): a good price. Green ink on the big price row and on the verdict only when the effective price (after cashback) is the lowest of the last 30 days and at least 3 % under the 30-day high; green on the drop triangle in the trend footer and the sparkline endpoint; green deductions in the calculator. Never for the cheaper of two paths.

### Tertiary
- **Cashback Amber** (`cashback-amber`, `cashback-amber-soft`, `cashback-amber-ink`): cashback amounts in ink, the cashback badge, the deadline progress bar, the condition icon, the count bubble on the Cashback tab.
- **Set Teal** (`set-teal-soft`, `set-teal-ink`): the "Set-Deal" and "beobachtet" badges, the effective soundbar price in set rows.
- **Clearance Red** (`clearance-red`, `clearance-red-soft`, `clearance-red-ink`): "Aussteller" and "Restposten" badges, price rises, a stale-scan warning in the top bar.

### Neutral
- **Ground** (`ground`): page background, also the text colour on the dark selected chip and the toast.
- **Card** (`card`): every card, the top bar, the tab bar, inputs, buttons at rest.
- **Card Sunken** (`card-sunken`): hover fill on rows and secondary buttons, the neutral "beendet" badge, the empty progress track.
- **Ink** (`ink`): primary text; also the fill of the selected chip, the toast and the total rule in the calculator.
- **Ink Muted** (`ink-muted`): captions, column labels, places and distances, inactive tabs, "kein Markt" states.
- **Hairline / Hairline Strong** (`hairline`, `hairline-strong`): row dividers and top/bottom bar borders; the stronger step is the border of buttons, chips and inputs.

### Named Rules
**The Meaning-Only Colour Rule.** A hue appears only with its meaning: green = lowest price of the last 30 days after cashback (never "cheaper of two paths"), blue = action/selection, amber = cashback, teal = set deal, red = Aussteller/Restposten/price rise. No hue is used for decoration, headings or brand accent.

**The Triad Rule.** Each semantic colour is used as base (borders, icons, solid fills), soft (tinted background) and ink (text on the soft tint). Text on a soft tint is always the ink step, never the base.

**The Light-Canon Rule.** The light theme is the token source; the dark theme (`prefers-color-scheme` or `data-theme="dark"`) remaps every role to a lifted equivalent and never introduces a new role.

## Typography

**Display Font:** system sans (`-apple-system`, SF Pro Text; Roboto, Segoe UI fallback)
**Body Font:** the same stack
**Label/Mono Font:** none; all numerals are `font-variant-numeric: tabular-nums` on the body

**Character:** The phone's own typeface, set tight and plain. Weight does the hierarchy (400 / 500 / 600 / 700), not size; prices are the only large type.

### Hierarchy
- **Display** (700, 22px, 1.15): the price in a detail tile; 26px (700) for the headline cashback amount, 24px for the calculator total.
- **Headline** (600, 17px, 1.25): the top-bar title and the product title in the detail hero; 16px on detail screens.
- **Title** (600, 15px, 1.3): product name in the list row, offer title; 14.5px for store and set-deal names.
- **Price** (700, 19px, 1.15): the price in a list-row column; 17–20px for store prices, scenario totals and cashback amounts in rows.
- **Body** (400, 15px, 1.45): default text; 14px in buttons, settings values and calculator lines; 13.5px in facts, conditions and the infobox.
- **Caption** (400, 12.5px, 1.4): subtitles, places, distances, notes, hints; 12px and 11.5px for sub-lines under prices.
- **Label** (600, 11px, 0.03em, uppercase): reserved; the receipt rows use Body weights (row label 500, big row label 600, big price 20px 700 in the list and 26px on the product page).
- **Section** (600, 13px): card-group headings ("Abholung im Umkreis") with a 12px muted hint on the right.

### Named Rules
**The Tabular Rule.** Every number is tabular; prices never wrap (`white-space: nowrap`), and the weight 700 is reserved for prices, amounts and totals.

**The Place Line Rule.** A price is always followed by its place in caption size: the store name in 500 weight ink, then postcode, city and distance in muted.

## Layout

One centred column, max 480px, that keeps its phone proportions at every width; above 560px it gains 1px hairline borders left and right. A sticky top bar (min 54px, 10px 16px padding) holds the title, the location/radius/scan-age meta on the right. The screen scrolls with 12px 16px padding and a 96px bottom reserve for the fixed three-tab bar; cards stack with a 12px gap, and each group is preceded by a 13px section heading with an aligned hint.

Inside a card, rows are grids: the list head `64px minmax(0,1fr)` with 12px 14px padding, receipt rows `minmax(0,1fr) auto` with 7px vertical padding, store/set/device rows `minmax(0,1fr) auto` with 11px 14px padding. Rows are divided by 1px hairlines (`border-top`, none on the first child). Products are separate cards with a 12px gap; on the product page every store is its own card with an 8px gap. Spacing steps observed: 2, 4, 6, 8, 10, 12, 14, 16px. Safe-area insets are respected on the top bar, tab bar and toast.

## Elevation & Depth

Hybrid, with shadows kept nearly invisible. Every card floats on one soft two-layer shadow; rows inside a card are separated by hairlines, not shadows; selection and state are tonal (soft tint fills, a 1px coloured border on the winning price column). Hover is a tonal lift to the sunken card colour. No hard offset shadows, no borders around cards.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(27,31,36,.06), 0 2px 8px rgba(27,31,36,.06)`): every card and the toast. Dark theme: `0 1px 2px rgba(0,0,0,.5), 0 2px 10px rgba(0,0,0,.35)`.

### Named Rules
**The One-Shadow Rule.** There is exactly one shadow token. Depth differences are expressed by tint and hairline, never by a second shadow.

## Shapes

Gently rounded everywhere, with a radius ladder tied to size: badges 6px, small buttons 7px, thumbs/inputs/tabs 8px, buttons and price columns 9px, tiles/logos/infobox 10px, cards 12px, chips and count bubbles pill (999px). The back button is a 36px circle. Product images sit in a white 8px-radius box with `background-size: contain` (white even in dark mode). Selection outlines are 1px (`hairline-strong` on controls, the semantic base colour on a winning column). Focus is a 2px `action-blue` outline with 2px offset. Bar charts and progress bars use 2–3px radii.

## Components

### Buttons
- **Shape:** rounded control (9px); small variant 7px.
- **Secondary (default):** white card fill, 1px `hairline-strong` border, ink text, 500 weight 14px, 8px 13px padding; hover fills `card-sunken`. Optional 16px inline SVG icon with 6px gap.
- **Primary:** `action-blue` fill, white text, no border; hover darkens to `action-blue-ink`. One per card at most (e.g. "Beobachten" next to the URL input).
- **Small:** 5px 10px padding, 12.5px; used in row action strips ("Bei diesem Markt öffnen", "PLZ kopieren", "Im Rechner").
- **Pressed (`aria-pressed="true"`):** `action-blue-soft` fill, `action-blue-ink` text, border removed; a toggle, not a primary.
- **Disabled:** 50% opacity.
- **Focus:** 2px `action-blue` outline, 2px offset, on every button, link, input and select.

### Chips
- **Style:** pill (999px), white fill, 1px `hairline-strong` border, 13px ink text, 5px 12px padding, 6px gap in a wrapping row.
- **State:** selected (`aria-pressed="true"`) inverts to ink fill with ground-coloured text at 500 weight. Used as the cashback filter ("Geld zurück" / "Zugaben" / "alles").

### Badges
- **Style:** one shape everywhere: inline-flex, 6px radius, 2px 7px padding, 11.5px 600, nowrap, optional 11px inline SVG. Soft tint background, matching ink text.
- **Variants:** Set-Deal / beobachtet (teal), Cashback (amber), Aussteller / Restposten / price rise (red), price drop (green), neu / Zielpreis erreicht (blue), beendet / echter Preis (neutral sunken with muted text).

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** card white; rows inside hover to `card-sunken`.
- **Shadow Strategy:** the single card shadow (see Elevation).
- **Border:** none; rows are divided by 1px `hairline` top borders. Notes at the foot of a card sit above a hairline in 12.5px muted.
- **Internal Padding:** 12px 14px for rows, 14px for hero/summary/calculator, 11px 14px for compact rows.

### Inputs / Fields
- **Style:** 1px `hairline-strong` border, 9px radius (8px in the alert and calculator forms), white fill, inherited font, 9px 11px padding; number inputs right-aligned, 100–110px wide; range inputs use `accent-color: action-blue`.
- **Focus:** the global 2px blue outline.
- **Placeholder:** muted.

### Navigation
- **Top bar:** sticky, card white, hairline bottom, 54px min, title 17px 600 clamped to two lines, meta block right-aligned 12px muted with 500-weight ink values; a red `warn` class for stale scans; detail screens add a 36px circular back button in `action-blue`.
- **Bottom tabs:** fixed, card white, hairline top, three equal columns, 24px SVG icon over an 11px 500 label; inactive muted, active (`aria-current="page"`) `action-blue`. A pill count bubble in `cashback-amber` with 10px white text sits top-right of the icon.
- **Transition:** screens fade in 160ms ease-out (opacity .5 → 1, 3px rise) only when reduced motion is not requested.

### Receipt Rows (signature)
Under the card head (64px thumb, name 15px 600, subtitle 12px muted) the rows of a receipt, `minmax(0,1fr) auto`, hairlines between them: first the cheapest path with a 13px check, its label ("Abholung" or "Versand"), the offer's red badge (Aussteller, Restposten), and a 12px muted sub-line with store, distance, stock and "kein Cashback" or "ohne Cashback"; then the cashback deduction in amber ink with purchase and registration dates; then the big row "Dein Preis inkl. Cashback" (20px 700 in the list, 26px on the product page, green ink only at a 30-day low); then the other path in muted 500 with "mit Cashback X €"; then set deals in teal ink marked "nicht im Preis". Without a cashback the first row is the big row. No price in the head; no fact twice.

### Trend Footer
Full-width button row under the receipt: an 88 × 30px sparkline of the daily best price (muted line, 12 % area fill, endpoint dot in green at a 30-day low, a dashed amber drop to the price after cashback), then two 12px lines: the movement ("▼ 80 € seit gestern" or "▼ 240 € in 30 Tagen", triangle green for a drop and red for a rise) and the verdict ("Tiefstpreis seit 30 Tagen", "60 € über dem 30-Tage-Tief von 3.399 €", plus "noch 96 € bis zum Zielpreis" when a target is set); right: "Mehr" with a chevron that opens the sunken area with stores within the radius, the three cheapest shippers and all promotions including Zugaben.

### Store Card
Every store on the product page is its own card: name 14.5px 600 with a check on the chosen store and the red badge, price 17px 700 right-aligned with an 11.5px sub-line ("Abholung", "inkl. Versand", "ohne Cashback"), address line 12.5px muted with postcode and city in 500 ink, stock line, an amber "mit 150 € Cashback 1.349 €" line, then small buttons "Im Markt öffnen" and "PLZ 15834" (copy).

### Product Page Order
Hero (150px image, title 19px, subtitle, link), receipt rows and trend text, cashback explanation, then "Aktionen" (cashback offer card, set deals, Zugaben), then alert settings (mode and optional target), the 30-day chart, stores within the radius, shipping.

### Offer Card and Device Row (cashback)
Offer: 48px brand tile (10px radius, uppercase 9.5px 700 letterspaced wordmark) left, title 15px 600, 20px 700 amber-ink amount, a 5px amber progress bar for the deadline, and a badge row; ended offers at 60% opacity. Device rows: `minmax(0,1fr) auto auto`, selected row in `action-blue-soft`, cashback amount in amber ink, price in ink.

### Calculator and Infobox
Calculator lines `minmax(0,1fr) auto`, 14px, deductions in green ink, the total separated by a 2px ink rule with a 24px 700 value. The infobox is a 10px-radius `action-blue-soft` panel with blue ink text and an 18px icon. Condition rows (`cond`) are the same shape without a fill, with an amber 18px icon.

## Do's and Don'ts

### Do:
- **Do** list the cheapest path first in the receipt rows with its place and distance, then cashback, total, the other path and set deals; tint the big row green only at a 30-day low after cashback.
- **Do** use the single badge shape (6px radius, 2px 7px, 11.5px 600, soft tint + ink) for every status; pick the hue by meaning.
- **Do** keep every number tabular and every price `nowrap` in weight 700.
- **Do** place a product image at the left of every product row in a white 8px box.
- **Do** separate rows inside a card with a 1px hairline and reserve the one card shadow for the card itself.
- **Do** mark selection and pressed states with the blue soft/ink pair, never with a filled primary button.

### Don't:
- **Don't** introduce a hue outside the five semantic triads, or use a triad for decoration or headings.
- **Don't** publish a single "best price" without its path and place.
- **Don't** put a price in the card head, colour the cheaper of two paths, or repeat a fact in two rows.
- **Don't** add a second shadow, a card border, or a hard offset shadow; depth is tint and hairline.
- **Don't** break the 480px column or let a price wrap.
- **Don't** use expert or manufacturer logos as the app's identity (PRODUCT.md brand commitment).
