# Web Font Sizing — One Factor, Web Only

**Date:** 2026-09-02
**Status:** design, pending review
**Scope:** the browser build renders ~17% taller than native at every size. Scale the web
branch's font request by a single factor so web text lands on the same rendered height as
native. Native is untouched. One constant, one expression.

## Problem

`bd0f2c6` split font loading by platform: native resolves real Consolas through `SysFont`,
web loads the bundled DejaVu Sans Mono. That fixed native — its size constants were tuned
against Consolas in the first place — and deliberately left web alone.

But every size constant in the game is still a *Consolas* number, and DejaVu is not
metrically identical. Measured on the dev machine, `"Deathward"` at nominal size 20:

| path | width | height |
|---|---|---|
| Consolas (native) | 99 | 20 |
| bundled DejaVu (web) | 108 | 24 |

~20% taller and ~9% wider. That is the "fonts are too big" report, now confined to the
browser.

The game requests **22 distinct font sizes across ~165 call sites**, from 11 to 76. Re-tuning
them individually is not on the table; a single factor in the one place both branches already
pass through is.

## The measurement that shapes this

Consolas has a convenient property: **`get_height()` equals the nominal size exactly** — size
20 renders 20px tall, size 76 renders 76px tall, across the entire range. DejaVu's is ~1.17×
that.

So "match native" reduces to "make the rendered height equal the requested size", which is
checkable without Consolas being installed anywhere. Two candidate factors were measured
across all 22 sizes in use:

| factor | max height error | max width error (9-char string) |
|---|---|---|
| **0.85** — match height | **1px** | up to 27px narrower |
| 0.89 — match width | up to 4px taller | up to 9px |

**0.85 chosen.** Height error is ~0 across the whole range, and height is the property that
reads as "too big". The errors also run in the safe direction — web text is never *wider*
than native, so it cannot overflow a panel or change a `wrap()` break. The 27px worst case
falls at nominal 76, a centred title-screen string; at the sizes that carry the game (11-17,
about two-thirds of all call sites) the width error is a pixel or two.

Rejected: a per-size lookup table matching Consolas exactly at all 22 sizes. Perfection on a
cosmetic issue, plus a table someone has to maintain.

## Goals

- **Web text renders at the height native text renders at** — within 1px, at every size in use.
- **Native is bit-for-bit unchanged.** This is a web-only correction.
- **No call site changes.** All ~165 keep passing their Consolas-tuned numbers.

## Non-goals

- No change to native rendering, the bold asymmetry between the two paths, or the macOS
  `fc-list` risk — all inherited unchanged from `bd0f2c6`.
- No layout, spacing, or panel-geometry changes. Nothing in the game reads font height or
  linesize (verified: the only `get_height()` call in game code is on a Surface, in
  `sprites.py:599`), and panel widths at `ui.py:276-278` are computed from measured text, so
  they adapt on their own.
- No per-size table, and no attempt to match width as well as height.

## Design

### The scale

In `deathward/fontcache.py`, web branch only:

```python
_WEB_SCALE = 0.85

# inside get_font():
f = pygame.font.Font(_FONT_PATH, round(size * _WEB_SCALE))
```

Native continues to pass `size` to `SysFont` unscaled.

### The cache is unaffected

`_cache` stays keyed on the **requested** size. A caller asking for 15 gets a 13px DejaVu
under the key `(15, bold)`. Scaling happens on the way to the loader, not on the way to the
key, so nothing about caching or its test coverage changes.

### Rounding

`round()` is Python's banker's rounding. Size 30 — used twice — is the only call site whose
scaled value lands exactly on `.5`: `round(25.5)` is **26**, not 25.

Measured, 26 renders 31px tall where Consolas at 30 renders 30px. So banker's rounding costs
1px here, and 25 would have been exact. This is accepted rather than worked around: 1px is
inside the tolerance this design already commits to at every other size, and `round()` is the
obvious expression a reader expects. The alternative — `int(size * _WEB_SCALE + 0.5)` — buys
one pixel at one of 22 sizes in exchange for an expression that looks like a mistake.

The 30 → 26 mapping is pinned by a test so the choice stays deliberate and visible.

No minimum-size floor is added. The smallest size in use is 11, which scales to 9; a guard
against sizes that no call site passes would be dead code.

## Testing

The load-bearing test does not require Consolas to be installed, which matters because it
must hold on any machine:

- **for a requested size N, the web branch's font renders within 1px of N pixels tall** —
  checked across a representative spread of the sizes actually in use. This is the goal
  stated directly: web text is the size native text would be. Verified to hold for all 22
  sizes from 11 to 76.

Alongside it:

- the web branch requests `round(N * 0.85)` — asserted against the **literal** `0.85`, never
  against `_WEB_SCALE`. A test that reads the constant it is checking passes when the constant
  is mutated, which is exactly the hole the previous branch's review caught.
- size 30 maps to 26 specifically, pinning the banker's-rounding decision.
- **native requests N unscaled** — the regression guard that keeps this web-only. Without it,
  someone could apply the scale to both branches and no test would object.

## Verification

- Full suite green: `py -3.13 -m deathward.tests`.
- Manual playtest, both targets: the **browser** build should now look like the native one;
  **native** must be visibly unchanged.

## Known limitation

The 0.85 factor is calibrated against Consolas as installed on the dev machine. "Web matches
native here" is the right target for shipping, but a native Linux box resolving a different
font from the `SysFont` list will not match web quite as closely. That is inherent to matching
a platform-resolved font and is accepted, as with the macOS risk in the preceding spec.
