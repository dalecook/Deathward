# Font Degradation Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Native desktop renders with real `SysFont`-resolved Consolas again, while the browser build keeps the bundled DejaVu Sans Mono — reverting `a93868f`'s one-font-everywhere trade-off to a platform branch.

**Architecture:** One branch inside `fontcache.get_font()`, gated by an `_is_web()` helper copied in shape from `webstore.py`'s existing platform seam. Public surface is unchanged: `render.font()` and `sprites.unknown()` keep calling `get_font(size, bold)`, and `ui.py` is untouched. Tests assert *which loader was called*, not font metrics.

**Tech Stack:** Python 3.13, pygame 2.6.1 (must also hold under pygame-ce), `unittest`, pygbag 0.9.3 for the web target.

**Spec:** `docs/superpowers/specs/2026-09-02-font-degradation-chain-design.md`

## Global Constraints

- Branch is `feature/font-degradation-chain`, already created off `main` at `28bc38c`. Never work on `main`.
- The exact native font string is `"consolas,dejavusansmono,couriernew,monospace"` — copied verbatim from the pre-`a93868f` `render.py`. Do not "improve" it.
- Web is detected as `sys.platform == "emscripten"` and nothing else. No `match_font` probing — that alternative was considered and rejected in the spec.
- Full suite: `py -3.13 -m deathward.tests`. Single class: `py -3.13 -m unittest deathward.tests.TestFontCache -v`.
- The suite is safe to run: `tests.py`'s `setUpModule` repoints `config.SAVE_PATH` at a tempdir scratch file and `tearDownModule` restores it. Verified 2026-09-02, not assumed.
- 834 tests green at branch point. This plan adds 6, for 840.
- No `print()` in game code — pygbag's one documented perf rule.
- No sizing changes anywhere. The web build stays ~20% oversized; that is a separate deferred task.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `deathward/fontcache.py` | Modify | The font seam. Gains `sys` import, `_is_web()`, `_SYS_FONTS`, and the branch in `get_font()`. Module docstring rewritten — it currently argues for the design being reverted. |
| `deathward/tests.py` | Modify (`TestFontCache`, line ~322) | Native/web split mirroring `TestWebStore`'s shape. |
| `README.md` | Modify (line 10) | Drops the now-false "no asset files" claim. Task 2 only. |

`render.py`, `sprites.py`, and `ui.py` are deliberately untouched — that is the point of keeping `get_font`'s signature.

---

### Task 1: The platform branch

**Files:**
- Modify: `deathward/fontcache.py` (whole module: docstring, imports, `get_font`)
- Test: `deathward/tests.py` — replace `class TestFontCache` (starts line 322, ends line 360, immediately before `class TestEveryDeathTeaches`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `fontcache.get_font(size, bold=False) -> pygame.font.Font` (signature unchanged), plus two new module attributes the tests read — `fontcache._SYS_FONTS` (str) and `fontcache._is_web() -> bool`. `fontcache._FONT_PATH` (str) keeps its current name and meaning.

- [ ] **Step 1: Write the failing tests**

Replace the entire existing `class TestFontCache` block in `deathward/tests.py` with the following. Three of its four original tests survive inside it; the fourth (`test_loads_the_bundled_ttf_not_pygames_default_fallback_font`) moves into the web branch, because after this change it is only true there.

```python
class TestFontCache(unittest.TestCase):
    """fontcache is the font seam, split by platform the way webstore splits the
    save. Native desktops have an OS font registry, so SysFont resolves real
    Consolas -- which is what every size constant in the game was tuned against.
    pygbag's WASM sandbox has no registry, and SysFont does not raise there: it
    silently substitutes pygame's own proportional freesansbold.ttf, so the web
    build loads the bundled DejaVu Sans Mono directly instead.

    sys.platform is never "emscripten" under a real CPython test run, so the web
    branch is exercised by monkeypatching it, exactly as TestWebStore does. Both
    branches assert which LOADER was called rather than comparing rendered
    metrics: a machine without Consolas resolves the SysFont list to DejaVu
    anyway, which would leave a metrics comparison passing and failing for
    reasons the test cannot tell apart."""

    def setUp(self):
        pygame.font.init()
        from . import fontcache
        fontcache._cache.clear()
        self.addCleanup(fontcache._cache.clear)

    def _spy(self, name):
        """Wrap pygame.font.<name> so calls are recorded, restoring it after."""
        calls = []
        real = getattr(pygame.font, name)

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return real(*args, **kwargs)

        setattr(pygame.font, name, spy)
        self.addCleanup(setattr, pygame.font, name, real)
        return calls

    def _become_web(self):
        import sys as sys_module
        old = sys_module.platform
        sys_module.platform = "emscripten"
        self.addCleanup(setattr, sys_module, "platform", old)

    # --- shared ------------------------------------------------------------
    def test_font_path_points_at_the_bundled_asset(self):
        from . import fontcache
        self.assertTrue(os.path.exists(fontcache._FONT_PATH),
                        "the bundled font file must actually exist on disk")
        self.assertTrue(fontcache._FONT_PATH.endswith("DejaVuSansMono.ttf"))

    def test_same_size_and_weight_returns_the_cached_object(self):
        from . import fontcache
        a = fontcache.get_font(24)
        b = fontcache.get_font(24)
        self.assertIs(a, b)

    def test_bold_and_plain_are_cached_separately(self):
        from . import fontcache
        self.assertIsNot(fontcache.get_font(18, bold=False),
                         fontcache.get_font(18, bold=True))

    # --- native branch -----------------------------------------------------
    def test_native_resolves_through_the_os_font_registry(self):
        from . import fontcache
        sysfont = self._spy("SysFont")
        fontcache.get_font(21)
        self.assertEqual(len(sysfont), 1, "native must go through SysFont")
        args, kwargs = sysfont[0]
        self.assertEqual(args[0], fontcache._SYS_FONTS)
        self.assertEqual(args[1], 21)
        self.assertFalse(kwargs["bold"])

    def test_native_passes_bold_to_the_os_lookup(self):
        from . import fontcache
        sysfont = self._spy("SysFont")
        fontcache.get_font(21, bold=True)
        self.assertTrue(sysfont[0][1]["bold"],
                        "bold must be asked of the OS, not synthesised after")

    def test_native_never_touches_the_bundled_ttf(self):
        """The regression this whole change reverts: a93868f handed native the
        web's font. SysFont loads its resolved face through pygame.font.Font
        internally, so this filters for OUR bundled path rather than asserting
        Font went uncalled."""
        from . import fontcache
        loaded = self._spy("Font")
        fontcache.get_font(19, bold=True)
        bundled_loads = [a for a, _ in loaded if a and a[0] == fontcache._FONT_PATH]
        self.assertEqual(bundled_loads, [],
                         "native must not load the bundled font")

    # --- web branch --------------------------------------------------------
    def test_web_loads_the_bundled_ttf_directly(self):
        from . import fontcache
        self._become_web()
        loaded = self._spy("Font")
        fontcache.get_font(20)
        self.assertEqual(loaded[0][0], (fontcache._FONT_PATH, 20))

    def test_web_never_calls_sysfont(self):
        """SysFont does not raise in the WASM sandbox -- it silently returns
        pygame's proportional freesansbold. Calling it at all is the bug."""
        from . import fontcache
        self._become_web()
        sysfont = self._spy("SysFont")
        fontcache.get_font(20)
        self.assertEqual(sysfont, [])

    def test_web_synthesises_bold_on_the_bundled_face(self):
        from . import fontcache
        self._become_web()
        self.assertTrue(fontcache.get_font(18, bold=True).bold)
        self.assertFalse(fontcache.get_font(18, bold=False).bold)

    def test_web_is_not_pygames_default_fallback_font(self):
        """Moved from the one-font-everywhere design, where it guarded every
        platform. Only the web branch loads a .ttf by path now."""
        from . import fontcache
        self._become_web()
        bundled = fontcache.get_font(20)
        default = pygame.font.Font(None, 20)
        self.assertNotEqual(bundled.size("Deathward"), default.size("Deathward"),
                            "must not be silently using pygame's default fallback font")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`

Expected: FAIL — specifically the three native tests, because today every platform
goes through `pygame.font.Font` and nothing ever calls `SysFont`:

- `test_native_resolves_through_the_os_font_registry` → `AssertionError: 0 != 1 : native must go through SysFont`
- `test_native_passes_bold_to_the_os_lookup` → `IndexError: list index out of range`
- `test_native_never_touches_the_bundled_ttf` → fails, the bundled load is recorded

The **web tests should already pass** at this point. That is correct and expected: the
web branch's behaviour is exactly what the module does for everyone today. They are here
to pin it down so Task 1 cannot drift it while fixing native.

- [ ] **Step 3: Rewrite `deathward/fontcache.py`**

Keep the existing GPL header comment block at the top of the file exactly as it is. Replace everything below it — docstring, imports, and `get_font` — with:

```python
"""The monospace font, resolved differently depending on where we are running.

Native desktops have an OS font registry, so pygame.font.SysFont can find real
Consolas by name. It is better hinted than anything we bundle, and every size
constant at every call site was tuned against it.

pygbag's WASM/Pyodide sandbox has no such registry -- and SysFont does not raise
there, it silently falls back to pygame's own freesansbold.ttf. That is a real,
different, PROPORTIONAL font, which is ruinous in a game drawn entirely from
glyphs on a grid. So the web build loads a bundled DejaVu Sans Mono directly with
pygame.font.Font, which needs no font-discovery step at all. (Its license is in
assets/fonts/LICENSE-DejaVu.txt; it was already the second name in the SysFont
list below, so it is the closest match to what native players see.)

The known cost of branching on platform rather than probing discovery: a native
macOS without fc-list fails lookup the same silent way (pygame #3156) and lands on
freesansbold rather than on the bundle. Mac is deferred; revisit with
pygame.font.match_font if it ever ships.
"""

import os
import sys

import pygame

_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "fonts", "DejaVuSansMono.ttf")

_SYS_FONTS = "consolas,dejavusansmono,couriernew,monospace"

_cache = {}


def _is_web():
    return sys.platform == "emscripten"


def get_font(size, bold=False):
    key = (size, bold)
    if key not in _cache:
        if _is_web():
            f = pygame.font.Font(_FONT_PATH, size)
            f.set_bold(bold)
        else:
            f = pygame.font.SysFont(_SYS_FONTS, size, bold=bold)
        _cache[key] = f
    return _cache[key]
```

Note the cache stays keyed on `(size, bold)` alone. Platform cannot change mid-process in production, so keying on it would be dead complexity — which is exactly why `setUp` clears `_cache`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`
Expected: `Ran 10 tests ... OK`

- [ ] **Step 5: Prove the tests can fail**

Temporarily invert the branch in `get_font` — change `if _is_web():` to `if not _is_web():` — and re-run:

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`
Expected: FAIL. At minimum `test_native_resolves_through_the_os_font_registry`,
`test_native_never_touches_the_bundled_ttf`, `test_web_loads_the_bundled_ttf_directly`
and `test_web_never_calls_sysfont` must go red.

Then **restore the correct `if _is_web():`** and re-run to confirm `OK` again. Do not
commit the inverted version. A test that has not been watched to fail is not evidence.

- [ ] **Step 6: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 840 tests ... OK` (834 at branch point, +6 here).

If anything outside `TestFontCache` fails, stop and report rather than adjusting it —
nothing else in the suite should care which font loads.

- [ ] **Step 7: Commit**

```bash
git add deathward/fontcache.py deathward/tests.py
git commit -m "fonts degrade by platform: native gets Consolas back, web keeps the bundle"
```

---

### Task 2: The README's stale boast

**Files:**
- Modify: `README.md:10`

**Interfaces:**
- Consumes: nothing. Independent of Task 1's code — it can be reviewed and rejected on its own.
- Produces: nothing.

- [ ] **Step 1: Fix the claim**

The line reads:

```markdown
Python + Pygame, standard library only. **No asset files** — every creature, wall,
```

That stopped being true at `a93868f`: the web build ships `DejaVuSansMono.ttf`. Replace with:

```markdown
Python + Pygame, standard library only. **No art assets** — every creature, wall,
```

The rest of the sentence is untouched and still accurate: the sprites really are drawn procedurally. `sprites.py:16`'s own "No asset files" comment is scoped to sprite art and stays as it is.

- [ ] **Step 2: Verify nothing else asserts the old claim**

Run: `grep -rn "no asset\|No asset" README.md deathward/`
Expected: two hits — the corrected README line, and `sprites.py:16`, which is correctly scoped.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: the web build ships a font, so drop the no-asset-files boast"
```

---

## Noted but NOT in scope

Two other pieces of README drift were found while writing this plan. Neither is touched
by either task; both need the user's say-so:

- `README.md:212` claims **641 tests**. The real number is 834 today, 840 after Task 1.
- The file map at `README.md:230-245` lists no `fontcache.py` and no `webstore.py`,
  though both have existed since 2026-08-31.

## Verification

Automated coverage ends at Task 1 Step 6. The remaining claims can only be settled by eye,
and are the user's to make per their standing manual-playtest rule:

- **Native:** launch `py -3.13 run_deathward.py`. Text should be real Consolas at the sizes
  it had before 2026-08-31 — noticeably tighter than today's build.
- **Browser:** the pygbag build should look exactly as it does now. This change must be a
  no-op on web; if anything moved there, something is wrong.
