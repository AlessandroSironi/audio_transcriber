# Ambient Glow UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Audio Transcriber UI with glassmorphism surfaces, animated ambient orbs, upload-zone waveform, progress glow effects, and polished micro-animations across all tabs.

**Architecture:** All changes are CSS-first; JS is limited to injecting a `.bg-orbs` div at startup, hiding the upload waveform on file select, and adding a glow to speaker headings in the viewer. No new dependencies. Degrades gracefully on browsers without `backdrop-filter`.

**Tech Stack:** Vanilla CSS (custom properties, keyframes, pseudo-elements), Vanilla JS (DOM injection, class toggle), Jinja2 HTML template.

---

## File Map

| File | Changes |
|---|---|
| `static/style.css` | All visual rules — new keyframes, glass surfaces, animations, light/reduced-motion overrides |
| `static/app.js` | Inject `.bg-orbs` div; hide/show upload waveform; add glow to speaker h2 in renderViewer |
| `app/templates/index.html` | Add `.upload-wave` HTML inside `.upload-zone` |

---

## Task 1 — Background Orbs + Noise Texture

**Files:**
- Modify: `static/style.css` — add orb keyframes, `.bg-orbs` styles, noise texture, z-index fix
- Modify: `static/app.js` — inject `.bg-orbs` div at startup

- [ ] **Step 1: Add orb CSS to the bottom of `static/style.css`**

Append after the `@media (max-width: 640px)` block:

```css
/* ── Ambient background ──────────────────────────────────── */
@keyframes orb-drift-a {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(40px, -30px) scale(1.08); }
}
@keyframes orb-drift-b {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(-30px, 40px) scale(1.06); }
}

.bg-orbs {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.bg-orbs::before {
  content: '';
  position: absolute;
  top: -200px; left: -200px;
  width: 700px; height: 700px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(99,102,241,0.07) 0%, transparent 70%);
  animation: orb-drift-a 25s ease-in-out infinite alternate;
}
.bg-orbs::after {
  content: '';
  position: absolute;
  bottom: -150px; right: -150px;
  width: 500px; height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(129,140,248,0.05) 0%, transparent 70%);
  animation: orb-drift-b 35s ease-in-out infinite alternate;
}
```

- [ ] **Step 2: Add noise texture + z-index fix to `static/style.css`**

Append immediately after the orb block from Step 1:

```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.025;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 200px 200px;
}

main { position: relative; z-index: 1; }
```

- [ ] **Step 3: Inject `.bg-orbs` div in `static/app.js`**

Add as the very first line of `static/app.js` (before the theme block):

```js
document.body.insertAdjacentHTML('afterbegin', '<div class="bg-orbs" aria-hidden="true"></div>');
```

- [ ] **Step 4: Verify visually**

```bash
source .venv/bin/activate && python run.py --no-browser
```
Open `http://localhost:8000`. Expected: faint purple glow top-left, faint blue glow bottom-right, both slowly drifting. Subtle grain texture on the background.

- [ ] **Step 5: Commit**

```bash
git add static/style.css static/app.js
git commit -m "feat: add animated ambient orb background and noise texture"
```

---

## Task 2 — Nav Bar Glassmorphism

**Files:**
- Modify: `static/style.css` — `.top-nav` backdrop-filter, logo hover glow

- [ ] **Step 1: Update `.top-nav` in `static/style.css`**

Find the `.top-nav` rule (around line 115) and replace:
```css
background: var(--surface);
```
with:
```css
background: rgba(26, 29, 39, 0.78);
backdrop-filter: blur(14px);
-webkit-backdrop-filter: blur(14px);
```

- [ ] **Step 2: Add nav logo icon hover glow**

After the `.nav-logo svg { color: var(--accent); }` rule, add:
```css
.nav-logo svg {
  transition: color var(--transition), filter var(--transition);
}
.nav-logo:hover svg {
  filter: drop-shadow(0 0 6px rgba(99,102,241,0.65));
}
```

- [ ] **Step 3: Verify visually**

Reload `http://localhost:8000`. Expected: nav bar is slightly translucent (orbs visible through it when scrolled over content). Logo mic icon glows on hover.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: nav bar glassmorphism and logo hover glow"
```

---

## Task 3 — Card & Surface Glassmorphism

**Files:**
- Modify: `static/style.css` — glass background on cards, viewer, file-preview, hw-strip, tx-card

- [ ] **Step 1: Update surface backgrounds in `static/style.css`**

Find the `.card` rule and replace:
```css
background: var(--surface);
```
with:
```css
background: rgba(26, 29, 39, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

Find the `.file-preview` rule and replace `background: var(--surface-2);` with:
```css
background: rgba(35, 39, 56, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

Find the `.hw-strip` rule and replace `background: var(--surface-2);` with:
```css
background: rgba(35, 39, 56, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

Find the `.viewer-body` rule and replace `background: var(--surface);` with:
```css
background: rgba(26, 29, 39, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

Find the `.tx-card` rule and replace `background: var(--surface);` with:
```css
background: rgba(26, 29, 39, 0.72);
backdrop-filter: blur(8px);
-webkit-backdrop-filter: blur(8px);
```

- [ ] **Step 2: Upgrade card + tx-card hover states**

Find `.card` and append:
```css
.card:hover {
  box-shadow: 0 8px 32px rgba(99,102,241,0.15), var(--shadow-sm);
  border-color: rgba(99,102,241,0.35);
}
```

Find the `.tx-card:hover` rule and replace it entirely with:
```css
.tx-card:hover {
  transform: translateY(-3px);
  border-color: rgba(99,102,241,0.45);
  box-shadow: 0 8px 32px rgba(99,102,241,0.18), 0 2px 8px rgba(0,0,0,0.3);
}
```

- [ ] **Step 3: Verify visually**

Reload. Expected: all cards look glass-like with depth. Orb glow bleeds through card surfaces slightly. Cards lift and glow indigo on hover.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: glassmorphism surfaces on cards and panels"
```

---

## Task 4 — Gradient Headings

**Files:**
- Modify: `static/style.css` — gradient text on `.card-title` and `.nav-logo`

- [ ] **Step 1: Add gradient text rules to `static/style.css`**

Find the `.card-title` rule and replace it entirely with:
```css
.card-title {
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .08em;
  margin-bottom: 12px;
  background: linear-gradient(135deg, var(--text-muted) 20%, var(--accent));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

Find `.nav-logo` and add to the rule:
```css
.nav-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 1rem;
  white-space: nowrap;
  background: linear-gradient(135deg, var(--text) 40%, var(--accent));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

Note: `color: var(--text)` must be removed from `.nav-logo` since `-webkit-text-fill-color` overrides `color`. The SVG child keeps its own color via `color: var(--accent)` on `.nav-logo svg`.

- [ ] **Step 2: Fix nav logo SVG color**

Since `-webkit-text-fill-color` on a parent does not affect SVG stroke/fill attributes, the SVG icon color is set separately. Verify `.nav-logo svg { color: var(--accent); }` is still present (it should be).

- [ ] **Step 3: Verify visually**

Reload. Expected: card titles and nav logo text show a subtle gradient from muted-grey to indigo.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: gradient text on card titles and nav logo"
```

---

## Task 5 — Upload Zone: Breathing Glow + Drag-Over + Waveform

**Files:**
- Modify: `static/style.css` — `@keyframes upload-breathe`, `@keyframes wave-bar`, upload zone states, waveform bars
- Modify: `app/templates/index.html` — add `.upload-wave` div inside `.upload-zone`
- Modify: `static/app.js` — hide waveform on file select, show on clear

- [ ] **Step 1: Add `upload-breathe` and `wave-bar` keyframes to `static/style.css`**

Add inside the existing `/* ── Keyframes ──` block:
```css
@keyframes upload-breathe {
  0%, 100% { box-shadow: 0 0 0 transparent; }
  50%       { box-shadow: 0 0 40px rgba(99,102,241,0.13), inset 0 0 20px rgba(99,102,241,0.04); }
}

@keyframes wave-bar {
  from { transform: scaleY(0.35); opacity: 0.22; }
  to   { transform: scaleY(1);    opacity: 0.5; }
}
```

- [ ] **Step 2: Update `.upload-zone` and its states in `static/style.css`**

Find `.upload-zone` and append `animation: upload-breathe 3s ease-in-out infinite;` to its existing rules.

Find `.upload-zone:hover, .upload-zone.drag-over` and add `animation: none;` to stop the breathe on hover.

Replace the `.upload-zone.drag-over` rule with:
```css
.upload-zone.drag-over {
  background: radial-gradient(ellipse at center, rgba(99,102,241,0.14) 0%, transparent 70%);
  border-color: var(--accent);
  box-shadow: 0 0 60px rgba(99,102,241,0.22), inset 0 0 30px rgba(99,102,241,0.07);
  animation: none;
}
```

- [ ] **Step 3: Add waveform bar styles to `static/style.css`**

Append after the upload-zone rules:
```css
/* Upload zone waveform */
.upload-wave {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 36px;
  margin: 0 auto 14px;
}
.upload-wave span {
  width: 3px;
  border-radius: 99px;
  background: var(--accent);
  animation: wave-bar 1.1s ease-in-out infinite alternate;
  transform-origin: bottom;
}
.upload-wave span:nth-child(1) { height: 12px; animation-delay: 0ms; }
.upload-wave span:nth-child(2) { height: 20px; animation-delay: 150ms; }
.upload-wave span:nth-child(3) { height: 28px; animation-delay: 75ms; }
.upload-wave span:nth-child(4) { height: 16px; animation-delay: 225ms; }
.upload-wave span:nth-child(5) { height: 22px; animation-delay: 110ms; }
```

- [ ] **Step 4: Add `.upload-wave` HTML to `app/templates/index.html`**

Find the `.upload-zone` div and add the waveform immediately before the `<svg class="upload-icon"` element:
```html
<div class="upload-wave" id="upload-wave" aria-hidden="true">
  <span></span><span></span><span></span><span></span><span></span>
</div>
```

So the upload-zone content order becomes:
```html
<div class="upload-zone" id="drop-zone">
  <div class="upload-wave" id="upload-wave" aria-hidden="true">
    <span></span><span></span><span></span><span></span><span></span>
  </div>
  <svg class="upload-icon" ...>...</svg>
  <span class="upload-label">...</span>
  <span class="upload-sub">...</span>
  <input type="file" ... />
</div>
```

- [ ] **Step 5: Wire up waveform show/hide in `static/app.js`**

In the `handleFile` function, after `filePreview.classList.add('visible');`, add:
```js
document.getElementById('upload-wave').style.display = 'none';
```

In the `clearBtn` event listener, after `filePreview.classList.remove('visible');`, add:
```js
document.getElementById('upload-wave').style.display = '';
```

- [ ] **Step 6: Verify visually**

Reload. Expected: five animated bars visible inside the upload zone when no file is selected. Bars disappear when a file is picked. Upload zone gently breathes with a faint glow. Drag a file over → dramatic radial sweep + bright border.

- [ ] **Step 7: Commit**

```bash
git add static/style.css app/templates/index.html static/app.js
git commit -m "feat: upload zone breathing glow, waveform decoration, drag-over sweep"
```

---

## Task 6 — Progress Bar Glow + Stage Timeline

**Files:**
- Modify: `static/style.css` — ripple-ring on active dot, glow tip on progress bar, connector scaleX fill

- [ ] **Step 1: Add `ripple-ring` keyframe to `static/style.css`**

Inside the `/* ── Keyframes` block, add:
```css
@keyframes ripple-ring {
  0%   { transform: scale(1);   opacity: 0.55; }
  100% { transform: scale(1.9); opacity: 0; }
}
```

- [ ] **Step 2: Add ripple to active stage dot**

Ensure `.stage-dot` has `position: relative` (add if missing). Then add:
```css
.stage-node.active .stage-dot::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  animation: ripple-ring 1.2s ease-out infinite;
  pointer-events: none;
}
```

- [ ] **Step 3: Update `.progress-bar-wrap` and `.progress-bar` for glow tip**

Find `.progress-bar-wrap` and change `overflow: hidden` to `overflow: visible`. (The bar's own `border-radius: 99px` clips the gradient to the bar shape; overflow visible is needed so the glow box-shadow isn't clipped by the parent.)

Find `.progress-bar.running` and add:
```css
box-shadow: 4px 0 14px 2px rgba(99,102,241,0.55);
```

- [ ] **Step 4: Update stage connectors to scaleX fill animation**

Find `.stage-connector` and replace entirely with:
```css
.stage-connector {
  flex: 1;
  height: 2px;
  background: var(--border);
  position: relative;
  overflow: hidden;
}
.stage-connector::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--green);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.stage-connector.done::before {
  transform: scaleX(1);
}
```

Remove the old `.stage-connector.done { background: var(--green); }` rule (it is now redundant and would fight the new approach).

- [ ] **Step 5: Verify visually**

Start a transcription job on a test file. Expected:
- Active stage dot shows a pulsing sonar-ring expanding outward
- Progress bar shows a right-edge glow while running
- Stage connectors fill left-to-right smoothly when a stage completes

- [ ] **Step 6: Commit**

```bash
git add static/style.css
git commit -m "feat: progress bar glow tip, stage dot ripple, connector fill animation"
```

---

## Task 7 — Library Card Spring Animation

**Files:**
- Modify: `static/style.css` — replace card fade-up with spring-in keyframe

- [ ] **Step 1: Add `card-spring-in` keyframe**

Inside the `/* ── Keyframes` block, add:
```css
@keyframes card-spring-in {
  from { opacity: 0; transform: translateY(20px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
```

- [ ] **Step 2: Update `.tx-card` animation**

Find `.tx-card` and replace `animation: fade-up .22s ease both;` with:
```css
animation: card-spring-in 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
```

- [ ] **Step 3: Verify visually**

Go to Library tab (add a transcription first if empty, or temporarily add a dummy card via DevTools). Expected: cards spring in with a slight overshoot — they pop into place rather than sliding flatly.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: library cards spring-in animation with cubic-bezier overshoot"
```

---

## Task 8 — Viewer Speaker Heading Glow

**Files:**
- Modify: `static/app.js` — add inward glow box-shadow to speaker h2 in `renderViewer`

- [ ] **Step 1: Update `renderViewer` in `static/app.js`**

Find the `renderViewer` function's speaker-coloring block:
```js
container.querySelectorAll('h2').forEach(h2 => {
  const m = h2.textContent.match(/Speaker (\d+)/i);
  if (m) {
    const n = Math.min(parseInt(m[1]), 8);
    h2.style.cssText = `
      border-left: 3px solid var(--sp${n});
      color: var(--sp${n});
      padding: 6px 12px;
      background: hsla(${(n-1)*47},60%,60%,.08);
      border-radius: 4px;
      display: inline-block;
      margin: 20px 0 8px;
    `;
  }
});
```

Replace with:
```js
const SP_HUES = [240, 287, 340, 28, 75, 170, 200, 55];
container.querySelectorAll('h2').forEach(h2 => {
  const m = h2.textContent.match(/Speaker (\d+)/i);
  if (m) {
    const n = Math.min(parseInt(m[1]), 8);
    const hue = SP_HUES[n - 1];
    h2.style.cssText = `
      border-left: 3px solid var(--sp${n});
      color: var(--sp${n});
      padding: 6px 12px;
      background: hsla(${hue},60%,60%,.08);
      box-shadow: inset 4px 0 14px hsla(${hue},60%,60%,.14);
      border-radius: 4px;
      display: inline-block;
      margin: 20px 0 8px;
    `;
  }
});
```

- [ ] **Step 2: Verify visually**

Open a transcription with multiple speakers. Expected: speaker headings show a soft inward glow on the left edge matching the speaker's accent color.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: speaker headings inward glow in viewer"
```

---

## Task 9 — Settings & Form Polish

**Files:**
- Modify: `static/style.css` — input focus glow ring, model card selected glow

- [ ] **Step 1: Upgrade input focus state in `static/style.css`**

Find `.form-input:focus` and replace it with:
```css
.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.2);
}
```

- [ ] **Step 2: Upgrade model card selected state**

Find `.model-card.selected` and append:
```css
box-shadow: 0 0 0 1px rgba(99,102,241,0.5), 0 4px 20px rgba(99,102,241,0.15);
```

- [ ] **Step 3: Verify visually**

Go to Settings tab. Expected: clicking a text input shows a soft glow ring around it. Selected model card glows indigo.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: form input glow ring and model card selection glow"
```

---

## Task 10 — Toast Slide-In

**Files:**
- Modify: `static/style.css` — replace fade-up with slide-in from right, add side-glow for success/error

- [ ] **Step 1: Add `toast-slide-in` keyframe**

Inside `/* ── Keyframes`, add:
```css
@keyframes toast-slide-in {
  from { transform: translateX(calc(100% + 28px)); opacity: 0; }
  to   { transform: translateX(0); opacity: 1; }
}
```

- [ ] **Step 2: Update `.toast` animation and add status glow**

Find `.toast` and replace `animation: fade-up .2s ease;` with:
```css
animation: toast-slide-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
```

Find `.toast.success` and replace `border-color: var(--green);` with:
```css
border-color: var(--green);
box-shadow: inset -3px 0 0 var(--green), 0 4px 24px rgba(0,0,0,0.4);
```

Find `.toast.error` and replace `border-color: var(--red);` with:
```css
border-color: var(--red);
box-shadow: inset -3px 0 0 var(--red), 0 4px 24px rgba(0,0,0,0.4);
```

- [ ] **Step 3: Verify visually**

Save settings or delete a transcription to trigger a toast. Expected: toast springs in from the right edge. Success toasts have a green left-edge stripe; error toasts have red.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: toast slide-in animation with status side-glow"
```

---

## Task 11 — Light Mode Compat + Reduced Motion

**Files:**
- Modify: `static/style.css` — `[data-theme="light"]` glass overrides, `@media (prefers-reduced-motion)`

- [ ] **Step 1: Add light-mode glass overrides to `static/style.css`**

Append after the `[data-theme="light"]` block:
```css
[data-theme="light"] .top-nav {
  background: rgba(244, 246, 251, 0.82);
}
[data-theme="light"] .card,
[data-theme="light"] .tx-card,
[data-theme="light"] .viewer-body {
  background: rgba(255, 255, 255, 0.82);
}
[data-theme="light"] .file-preview,
[data-theme="light"] .hw-strip {
  background: rgba(238, 240, 248, 0.82);
}
[data-theme="light"] .bg-orbs::before {
  background: radial-gradient(circle, rgba(99,102,241,0.04) 0%, transparent 70%);
}
[data-theme="light"] .bg-orbs::after {
  background: radial-gradient(circle, rgba(129,140,248,0.03) 0%, transparent 70%);
}
```

- [ ] **Step 2: Add reduced-motion overrides**

Append at the very end of `static/style.css`:
```css
/* ── Reduced motion ─────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .bg-orbs::before,
  .bg-orbs::after,
  .upload-zone,
  .upload-wave span,
  .stage-node.active .stage-dot::after,
  .progress-bar.running,
  .tx-card,
  .toast {
    animation: none !important;
    transition: none !important;
  }
}
```

- [ ] **Step 3: Verify light mode**

Toggle to light mode via the sun icon. Expected: nav and cards are white-glass, orb glows are much fainter, all text remains legible.

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: light mode glass compat and prefers-reduced-motion support"
```

---

## Task 12 — Final Smoke Test

- [ ] **Step 1: Full end-to-end visual check**

```bash
python run.py --no-browser
```
Open `http://localhost:8000` and verify each tab:

- **Upload tab**: orbs visible in background, waveform bars animate, breathing glow on drop zone, drag a file → radial sweep, select file → waveform hides, file preview appears
- **During transcription**: active stage dot shows ripple ring, progress bar has right-edge glow, connectors fill left-to-right
- **Library tab**: cards spring in with overshoot, hover lifts with indigo glow
- **Viewer tab**: speaker headings show inward color glow
- **Settings tab**: input focus shows glow ring, selected model card glows
- **Toasts**: slide in from right, success/error have side stripe
- **Light mode**: toggle sun icon — glass surfaces, faint orbs, all legible
- **Nav**: translucent glass, logo icon glows on hover

- [ ] **Step 2: Final commit (if any last-minute fixes needed)**

```bash
git add -p  # review any fixup changes
git commit -m "fix: ambient glow ui final polish tweaks"
```
