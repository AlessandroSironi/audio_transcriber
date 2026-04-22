# Spec: Ambient Glow UI Redesign

**Date:** 2026-04-22  
**Scope:** All tabs — Upload, Library, Viewer, Settings  
**Approach:** Option A — Ambient Glow  
**Files changed:** `static/style.css`, `static/app.js`, `app/templates/index.html`

---

## Goal

Upgrade the visual quality of the Audio Transcriber UI from clean-but-minimal to polished-premium without restructuring layout, adding dependencies, or compromising performance. All changes are CSS-first; JS touches are limited to class toggling.

---

## 1. Global Atmosphere

### Background orbs
Two `position: fixed` radial-gradient orbs rendered via `body::before` and `body::after` pseudo-elements. They sit behind all content (`z-index: 0`) with `pointer-events: none`.

- **Orb 1** (top-left): ~600px diameter, `rgba(99,102,241,0.06)` — purple
- **Orb 2** (bottom-right): ~400px diameter, `rgba(129,140,248,0.04)` — blue-indigo

### Orb animation
Each orb runs an independent CSS keyframe:

- `@keyframes orb-drift-a`: translates `(0,0)` → `(40px, -30px)` and scales `1.0` → `1.08` over **25s**, `ease-in-out infinite alternate`
- `@keyframes orb-drift-b`: translates `(0,0)` → `(-30px, 40px)` and scales `1.0` → `1.06` over **35s**, `ease-in-out infinite alternate`

Different durations prevent synchronization, creating a living ambient-light feel.

### Noise texture
`body::before` (or a dedicated `.noise` div) renders a 64×64 SVG fractal noise at `opacity: 0.025` via `background-image: url("data:image/svg+xml,...")`. Adds film-grain depth without affecting legibility.

> **Implementation note:** The orbs and noise must be on separate pseudo-elements or the stacking order gets complex. Use `body::before` for noise, a `.bg-orbs` div (injected by JS at startup) with its own `::before`/`::after` for the orbs.

---

## 2. Navigation Bar

- `backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px)`
- `background: rgba(26, 29, 39, 0.75)` (was solid `var(--surface)`)
- `border-bottom` stays, but lightened slightly for the glass effect to read
- Nav logo SVG icon: on hover, stroke transitions to `var(--accent)` with a `filter: drop-shadow(0 0 6px rgba(99,102,241,0.6))` glow

---

## 3. Cards & Surfaces

### Glassmorphism base
All `.card`, `.file-preview`, `.hw-strip`, `.viewer-body`, `.upload-zone`, `.tx-card`:
```
background: rgba(26, 29, 39, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

### Gradient border trick
Replace solid `1px solid var(--border)` with a pseudo-element gradient border on `.card` and `.tx-card`:
- Wrap content in a relative container; `::before` pseudo-element set to `background: linear-gradient(135deg, rgba(99,102,241,0.3), transparent 50%, rgba(129,140,248,0.15))`, positioned absolutely with `inset: 0`, `border-radius` matching the card, `z-index: -1`, `padding: 1px`.
- Simpler alternative (preferred): use `border-image` or `outline` trick — but since `border-radius` + `border-image` don't mix in CSS, use the `background-clip` pseudo-element approach.

### Hover glow
```css
.card:hover, .tx-card:hover {
  box-shadow: 0 8px 32px rgba(99, 102, 241, 0.18), 0 2px 8px rgba(0,0,0,0.3);
  border-color: rgba(99, 102, 241, 0.4);
  transform: translateY(-2px);
}
```

### Gradient headings
Card titles and the main nav logo text:
```css
background: linear-gradient(135deg, var(--text) 30%, var(--accent));
-webkit-background-clip: text;
background-clip: text;
-webkit-text-fill-color: transparent;
```
Applied to `.card-title`, `.nav-logo` text, `.setup-heading`.

---

## 4. Upload Zone

### Idle breathing glow
```css
@keyframes upload-breathe {
  0%, 100% { box-shadow: 0 0 0px transparent, inset 0 0 0px transparent; }
  50%       { box-shadow: 0 0 40px rgba(99,102,241,0.12), inset 0 0 20px rgba(99,102,241,0.04); }
}
.upload-zone { animation: upload-breathe 3s ease-in-out infinite; }
```
Animation pauses on drag-over (replaced by the active state below).

### Drag-over state
```css
.upload-zone.drag-over {
  background: radial-gradient(ellipse at center, rgba(99,102,241,0.15) 0%, transparent 70%);
  border-color: var(--accent);
  box-shadow: 0 0 60px rgba(99,102,241,0.25), inset 0 0 30px rgba(99,102,241,0.08);
  animation: none;
}
```

### Decorative waveform
Three animated `<span>` bars injected inside the upload zone by JS (hidden once a file is selected):
```html
<div class="upload-wave" aria-hidden="true">
  <span></span><span></span><span></span><span></span><span></span>
</div>
```
Each bar: `width: 3px`, `border-radius: 99px`, `background: var(--accent)`, `opacity: 0.35`. Heights animate between 8px and 28px with staggered `animation-delay` (0ms, 150ms, 75ms, 225ms, 110ms) on a `@keyframes wave-bar` cycle of 1.1s `ease-in-out infinite alternate`.

When a file is selected, `.upload-wave` gets `display: none`.

---

## 5. Progress & Stage Timeline

### Stage dot ripple
Active stage dot gets a sonar ping via `::after`:
```css
.stage-node.active .stage-dot::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  animation: ripple-ring 1.2s ease-out infinite;
  opacity: 0;
}
@keyframes ripple-ring {
  0%   { transform: scale(1);   opacity: 0.6; }
  100% { transform: scale(1.8); opacity: 0; }
}
```

### Progress bar glowing tip
A `::after` pseudo on `.progress-bar`:
```css
.progress-bar::after {
  content: '';
  position: absolute;
  right: -2px; top: -2px; bottom: -2px;
  width: 8px;
  border-radius: 99px;
  background: #fff;
  box-shadow: 0 0 10px 4px rgba(99,102,241,0.7);
  opacity: 0;
  transition: opacity 0.3s;
}
.progress-bar.running::after { opacity: 1; }
```

### Stage connector fill
Replace background-color swap with a `scaleX` transform:
```css
.stage-connector {
  transform-origin: left;
  transform: scaleX(0);
  background: var(--green);
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.stage-connector.done { transform: scaleX(1); }
```
The old `var(--border)` track is rendered by the parent element's background.

---

## 6. Library Cards

### Spring stagger-in
```css
.tx-card {
  animation: card-spring-in 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes card-spring-in {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
```
`animation-delay` set per-card by JS (already done via inline style).

---

## 7. Viewer — Speaker Sections

Speaker `h2` headers get an inward glow via `box-shadow`:
```css
/* example for speaker 1 */
h2[data-speaker="1"] {
  box-shadow: inset 4px 0 12px rgba(99,102,241,0.2);
}
```
Each speaker color's glow matches its `--spN` hue. Applied inline by `renderViewer()` in `app.js` alongside the existing `cssText` assignment.

---

## 8. Settings — Inputs & Model Cards

### Input focus glow
```css
.form-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
  outline: none;
}
```

### Model card selected shimmer
Selected `.model-card` gets a slow border shimmer:
```css
.model-card.selected {
  border-color: var(--accent);
  background: var(--accent-glow);
  box-shadow: 0 0 20px rgba(99,102,241,0.15);
}
```

---

## 9. Toast Notifications

```css
.toast {
  transform: translateX(100%);
  animation: toast-slide-in 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes toast-slide-in {
  to { transform: translateX(0); }
}
.toast.success { box-shadow: inset -3px 0 0 var(--green), 0 4px 24px rgba(0,0,0,0.4); }
.toast.error   { box-shadow: inset -3px 0 0 var(--red),   0 4px 24px rgba(0,0,0,0.4); }
```

---

## 10. Light Mode Compatibility

The orb opacities are low enough to read in light mode. Add `[data-theme="light"]` overrides:
- Orb 1: `rgba(99,102,241,0.04)`
- Orb 2: `rgba(129,140,248,0.03)`
- Glass surfaces revert to `background: rgba(255,255,255,0.8)`

---

## Implementation Constraints

- No new npm packages or CDN resources
- `backdrop-filter` degrades gracefully (browsers without support get solid surfaces)
- All animations respect `@media (prefers-reduced-motion: reduce)` — wrap all non-essential keyframes in a `prefers-reduced-motion` check that sets `animation: none`
- The `.bg-orbs` div is injected by one line at the top of `app.js`; it is not part of the Jinja template (keeps the HTML clean)
- Stage connector `scaleX` approach requires the connector element to have `overflow: hidden` on the parent or a track background — verify against existing markup before implementing
