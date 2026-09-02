# Fonts — A Platform Branch, Not One Font Everywhere

**Date:** 2026-09-02
**Status:** design, pending review
**Scope:** revert `a93868f`'s one-font-everywhere trade-off to a platform-conditional branch.
Native desktop goes back to real `SysFont`-resolved Consolas; the browser build keeps the
bundled DejaVu Sans Mono. One function changes.

## Problem

`a93868f` bundled DejaVu Sans Mono and routed **every** platform through
`pygame.font.Font(path, size)`. That fixed a real browser bug — pygbag's WASM/Pyodide sandbox
has no OS font registry, so `SysFont("consolas,…")` silently fell back to pygame's own
`freesansbold.ttf`, a *proportional* font, in a game drawn entirely from glyphs on a grid.

But it fixed the browser by degrading native. Windows lost real Consolas, which was never
broken, and picked up DejaVu at size constants that had been tuned against Consolas. Measured
on the dev machine at nominal size 20, `"Deathward"` renders:

| path | size | height |
|---|---|---|
| `SysFont` → Consolas | 99×20 | 20 |
| bundled DejaVu | 108×24 | 24 |

~20% taller and ~9% wider — which is the arithmetic behind the "fonts are too big" report.

The native consequence *was* flagged before `a93868f` shipped, but it was never offered as a
real choice with an alternative on the table. This spec is that choice, made the other way.

## Goals

- **Native desktop renders exactly as it did before `a93868f`** — real Consolas on Windows via
  OS font discovery, at the size constants already tuned for it.
- **The browser build is unchanged from today** — bundled DejaVu Sans Mono, no OS font
  discovery, no proportional-font fallback.
- **The public surface does not move.** `render.font()` and `sprites.unknown()` keep calling
  `fontcache.get_font(size, bold)`; `ui.py` is untouched.

## Non-goals

- **No sizing work.** Native's sizing resolves for free here (Consolas is what the constants
  were tuned against). The web build keeps rendering ~20% oversized. That fix stays a separate,
  deferred task — it can only be judged by eye in a browser, and bundling it would hold a
  structural, unit-testable change hostage to a manual verification path that has stalled twice
  behind pygbag's audio-permission gate.
- **No bold-rendering fix.** See "Accepted risks".
- **No `match_font` probing.** A true degradation chain (probe OS discovery on every platform,
  fall back to the bundle when it returns `None`) was considered and rejected — see below.

## Design

### The branch

`fontcache.get_font(size, bold=False)` keeps its signature and its cache. Inside, one branch,
with `_is_web()` copied in shape from the existing precedent in `webstore.py`:

```python
def _is_web():
    return sys.platform == "emscripten"
```

- **Web** (`_is_web()`) → `pygame.font.Font(_FONT_PATH, size)` then `.set_bold(bold)`.
  Exactly today's behaviour.
- **Native** (everything else) → `pygame.font.SysFont(
  "consolas,dejavusansmono,couriernew,monospace", size, bold=bold)`. The exact font string
  from before `a93868f`.

The `.ttf` and its license stay bundled — the web build still needs them.

### Why the cache stays keyed on `(size, bold)`

Platform cannot change mid-process in production, so adding it to the key would be dead
complexity. The one consequence is that tests must clear `_cache` when they flip
`sys.platform`, which the test design below does explicitly.

### Documentation that must change with it

`fontcache.py`'s module docstring currently argues *for* one-font-everywhere — "it renders
identically everywhere: native Windows/Mac/Linux and the browser build alike." That will be
the opposite of what the module does. It gets rewritten to explain the split and its reason:
native has a font registry and real Consolas is both better-hinted and what the size constants
were tuned against; the WASM sandbox has no registry, so it takes the bundled fallback.
`TestFontCache`'s class docstring gets the same treatment.

`README.md:10` claims "standard library only. **No asset files**". That stopped being true at
`a93868f` and stays untrue, since the web build ships the `.ttf`. One-line honesty fix included
here. (`sprites.py`'s "no asset files" is about procedural sprite art and remains true.)

## Testing

Mirror `TestWebStore`'s native/web split: monkeypatch `sys.platform`, restore via
`addCleanup`, clear `_cache` in `setUp` and restore in `tearDown` so branch tests neither leak
into each other nor into the wider suite.

Assert **which loader was called**, not font metrics. A metrics comparison would be silently
vacuous on any box without Consolas — a Linux CI machine resolves the `SysFont` string to
DejaVu anyway, making "native differs from bundled" trivially false for the right reason and
the wrong one indistinguishably. So:

- native branch calls `pygame.font.SysFont` (spy), with the expected font string
- web branch calls `pygame.font.Font` (spy) with `_FONT_PATH`
- existing tests survive unchanged: cache identity, bold/plain cached separately, the bundled
  asset exists on disk, and the bundled font is not pygame's default fallback

Then invert the branch by hand and confirm the new tests go red. A test that has not been
watched to fail is not evidence.

## Accepted risks

- **Native macOS may render worse than it does today.** pygame's `SysFont` discovery on macOS
  depends on `fc-list`, which is not part of a stock system (pygame bug #3156). Without it,
  discovery fails silently and native Mac lands on proportional `freesansbold` — worse than the
  DejaVu it gets today. This is the cost of choosing a platform branch over a probing chain.
  Mac is already deferred in the release plan and no Mac is available to test on, so this is
  accepted knowingly rather than fixed. If Mac ships later, revisit with `match_font`.
- **Bold differs between paths.** `SysFont(..., bold=True)` asks the OS for a real bold face;
  the bundled path synthesises it with `.set_bold()`. This asymmetry exists in the codebase
  today and is not worth chasing.

## Verification

- Full suite green (834 tests at branch point). Confirm what the suite writes and deletes
  before running it — it has destroyed a real save once.
- Manual playtest, both targets: **native** should show real Consolas at correct sizes;
  **browser** should look exactly as it does today.
