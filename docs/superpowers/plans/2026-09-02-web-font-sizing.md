# Web Font Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser build's text render at the size native text renders at, by scaling the web branch's font request by a single factor.

**Architecture:** One constant (`_WEB_SCALE = 0.85`) and one changed expression inside `fontcache.get_font()`'s web branch. Native is untouched. Scaling happens on the way to the loader, never on the way to the cache key. No call site changes — all ~165 keep passing their Consolas-tuned numbers.

**Tech Stack:** Python 3.13, pygame 2.6.1 (must also hold under pygame-ce), `unittest`, pygbag 0.9.3 for the web target.

**Spec:** `docs/superpowers/specs/2026-09-02-web-font-sizing-design.md`

## Global Constraints

- Branch is `feature/web-font-sizing`, already created off `main` at `bd0f2c6`. Never work on `main`.
- The factor is exactly `0.85`, named `_WEB_SCALE`, living in `deathward/fontcache.py`. Not in `config.py`.
- The expression is `round(size * _WEB_SCALE)`. Do NOT substitute `int(...)`, `math.floor`, or `int(size * _WEB_SCALE + 0.5)` — the spec considered and rejected those.
- **Native must stay unscaled.** `SysFont` keeps receiving the caller's `size` verbatim. This is a web-only correction.
- `_cache` stays keyed on the **requested** size, never the scaled one.
- No call sites change. `render.py`, `sprites.py`, `ui.py` must be untouched.
- Full suite: `py -3.13 -m deathward.tests`. Single class: `py -3.13 -m unittest deathward.tests.TestFontCache -v`. Plain `python` is NOT on PATH.
- The suite is safe to run: `setUpModule` repoints `config.SAVE_PATH` at a tempdir scratch file.
- 840 tests green at branch point. This plan adds 2, for 842.
- No `print()` in game code — pygbag's one documented perf rule.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `deathward/fontcache.py` | Modify | The font seam. Gains `_WEB_SCALE`, scales the web branch's request, and a docstring paragraph explaining why. |
| `deathward/tests.py` | Modify (`TestFontCache`, lines ~322-443) | One existing web test's expected size changes; two new tests; one native assertion message clarified. |

This is a single task: the constant, the expression, the tests and the docstring are one deliverable that cannot be meaningfully reviewed in halves.

---

### Task 1: Scale the web branch

**Files:**
- Modify: `deathward/fontcache.py` (module docstring, plus `get_font`)
- Test: `deathward/tests.py` — `class TestFontCache`

**Interfaces:**
- Consumes: `fontcache.get_font(size, bold=False)`, `fontcache._FONT_PATH`, `fontcache._is_web()`, `fontcache._cache` — all already exist and keep their current names and meanings.
- Produces: `fontcache._WEB_SCALE` (float, `0.85`). `get_font`'s signature and its cache key are unchanged.

- [ ] **Step 1: Write the failing tests**

Three edits inside `class TestFontCache` in `deathward/tests.py`.

**(a)** In the native branch, `test_native_resolves_through_the_os_font_registry` already proves native passes the size through unscaled — make that intent explicit by giving its size assertion a message. Replace this line:

```python
        self.assertEqual(args[1], 21)
```

with:

```python
        self.assertEqual(args[1], 21,
                         "native must ask for the size the caller requested, "
                         "unscaled -- the web scale factor is web-only")
```

**(b)** In the web branch, `test_web_loads_the_bundled_ttf_directly` currently expects the unscaled size. Replace the whole test with:

```python
    def test_web_loads_the_bundled_ttf_directly(self):
        """20 goes in, 17 comes out: round(20 * 0.85). The caller's number is a
        Consolas number and DejaVu is taller per nominal point, so the web
        branch scales the request before loading."""
        from . import fontcache
        self._become_web()
        loaded = self._spy("Font")
        fontcache.get_font(20)
        self.assertEqual(loaded[0][0], (fontcache._FONT_PATH, 17))
```

**(c)** Add these two tests at the end of the web branch section, immediately after `test_web_is_not_pygames_default_fallback_font` and before the closing of the class:

```python
    def test_web_renders_at_the_height_the_caller_asked_for(self):
        """The whole point, stated as behaviour rather than as a factor.

        Consolas' get_height() equals its nominal size exactly -- size 20 is
        20px tall -- so "web text is the size native text would be" reduces to
        "rendered height == the size requested". That holds without Consolas
        being installed, which is why this test works on any machine. These are
        every distinct size the game actually requests, 11 through 76."""
        from . import fontcache
        self._become_web()
        for n in (11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23,
                  24, 30, 32, 34, 36, 38, 40, 46, 54, 76):
            got = fontcache.get_font(n).get_height()
            self.assertLessEqual(
                abs(got - n), 1,
                "size %d rendered %dpx tall; native would render %dpx" % (n, got, n))

    def test_web_scale_factor_is_pinned(self):
        """Asserted against literal expected sizes, never against _WEB_SCALE --
        a test that reads the constant it is checking passes when someone
        changes the constant, which is the exact hole review caught last time.

        30 -> 26 is the one call site that lands on a .5 boundary. Python's
        round() is banker's rounding, so 25.5 goes to 26, not 25. That costs a
        pixel (26 renders 31px where Consolas at 30 renders 30) and is kept
        deliberately; this pins it so it does not drift silently.

        The seven sizes are chosen to catch a factor that drifts by 0.01 in
        either direction, which most sizes cannot see: 17 and 24 are the ones
        that separate 0.85 from 0.86, and 30 and 76 separate it from 0.84."""
        from . import fontcache
        self._become_web()
        for requested, expected in ((11, 9), (15, 13), (17, 14), (20, 17),
                                    (24, 20), (30, 26), (76, 65)):
            loaded = self._spy("Font")
            fontcache._cache.clear()
            fontcache.get_font(requested)
            self.assertEqual(loaded[0][0], (fontcache._FONT_PATH, expected),
                             "size %d must load at %d" % (requested, expected))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`

Expected: FAIL. Today the web branch passes the size through unscaled, so:

- `test_web_loads_the_bundled_ttf_directly` → `AssertionError` comparing `(path, 20)` against `(path, 17)`
- `test_web_scale_factor_is_pinned` → `AssertionError: size 11 must load at 9`
- `test_web_renders_at_the_height_the_caller_asked_for` → `AssertionError: size 11 rendered 13px tall; native would render 11px`

The native tests and edit (a) should still PASS — native is not changing, and (a) only adds a message to an assertion that already held.

- [ ] **Step 3: Add the constant and scale the request**

In `deathward/fontcache.py`, add the constant immediately below `_SYS_FONTS`:

```python
_SYS_FONTS = "consolas,dejavusansmono,couriernew,monospace"

_WEB_SCALE = 0.85
```

Then, in `get_font`, change the web branch's loader line only. From:

```python
            f = pygame.font.Font(_FONT_PATH, size)
```

to:

```python
            f = pygame.font.Font(_FONT_PATH, round(size * _WEB_SCALE))
```

Leave the `else:` branch, the cache key, `set_bold`, and everything else exactly as they are.

- [ ] **Step 4: Extend the module docstring**

In `deathward/fontcache.py`, the docstring paragraph that begins "pygbag's WASM/Pyodide sandbox has no such registry" ends with "...it is the closest match to what native players see.)". Insert this new paragraph immediately after that one, before the paragraph beginning "The known cost of branching":

```
DejaVu is not metrically identical to Consolas, though: its glyphs stand about
17% taller at the same nominal size, and every size constant in this game is a
Consolas number. So the web branch scales the request down by _WEB_SCALE before
loading. Consolas renders exactly `size` pixels tall, which makes the test for
this pleasingly direct -- web text must too, within a pixel. Note the scale
applies on the way to the loader and never to the cache key: a caller asking for
15 gets a 13px face, filed under 15.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`
Expected: `Ran 12 tests ... OK`

- [ ] **Step 6: Prove the tests can fail**

Temporarily change `_WEB_SCALE = 0.85` to `_WEB_SCALE = 1.0` and re-run:

Run: `py -3.13 -m unittest deathward.tests.TestFontCache -v`
Expected: FAIL — at minimum `test_web_loads_the_bundled_ttf_directly`,
`test_web_scale_factor_is_pinned` and `test_web_renders_at_the_height_the_caller_asked_for`
must go red.

Now try a subtler one: change it to `_WEB_SCALE = 0.86` and re-run.
Expected: FAIL — `test_web_scale_factor_is_pinned` must catch it, firing on **size 17**
(`size 17 must load at 14`, since `round(17 * 0.86)` is 15). Most sizes round identically
under 0.85 and 0.86; 17 and 24 are the two in the pinned set that can see the difference,
which is why they are in it. If this mutation does NOT go red, stop and report — the pinned
set has lost its teeth and the plan is wrong.

Then **restore `_WEB_SCALE = 0.85`** and re-run to confirm `OK` again. Do not commit either
mutation. A test that has not been watched to fail is not evidence.

- [ ] **Step 7: Confirm native really is untouched**

Run: `git diff` and confirm the only changed lines in `deathward/fontcache.py` are the new
constant, the one loader line inside the `if _is_web():` branch, and the docstring paragraph.
The `else:` branch must appear nowhere in the diff.

Run: `git status --short` and confirm only `deathward/fontcache.py` and `deathward/tests.py`
are modified. `render.py`, `sprites.py` and `ui.py` must not appear.

- [ ] **Step 8: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 842 tests ... OK` (840 at branch point, +2 here). A single skip in
`TestFireIsVisible` reading `skipped 'no clear line on this seed'` is pre-existing and
seed-dependent — not caused by this change.

If anything else fails, stop and report rather than adjusting it — no other test should care
what size the web branch loads.

- [ ] **Step 9: Commit**

```bash
git add deathward/fontcache.py deathward/tests.py
git commit -m "web text renders at the size the caller asked for"
```

---

## Verification

Automated coverage ends at Step 8. The rest is the user's, per their standing manual-playtest rule:

- **Browser:** build with pygbag and compare against native. Text should now look the same size, not ~17% larger.
- **Native:** must be visibly unchanged from `bd0f2c6`. If native moved at all, the scale leaked out of the web branch.
