# Subject Completion Line — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark the entry that finishes learning a subject, on both surfaces that ever reveal one — and let a death with no lesson pass in silence rather than announcing its own emptiness.

**Architecture:** One new predicate on `Codex` answers "is every tier of this subject known?", and both renderers ask it the same way. `draw_autopsy` drops its card entirely when there is no fact; `draw_learned_banner` grows by one line when there is a completion. No change to what grants facts or to `reveal_on_death`.

**Tech Stack:** Python 3.13, pygame 2.6.1, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-03-subject-completion-line-design.md`

## Global Constraints

- Branch is `fix/death-reveals-only-the-killer`, already checked out at `4c28b4e`. This work is a fifth task-group on an existing unmerged branch. Never work on `main`.
- The approved line is exactly: `You have learned everything this one has to teach.` — one sentence, identical on both surfaces. The old second sentence ("It killed you anyway.") and the `NOTHING NEW` heading are **deleted**.
- The completion test is **`fact.tier in TIER_ORDER and codex.subject_complete(fact.subject)`** — never a test for `fact.tier == "counter"`. The Potion of Insight grants facts out of tier order.
- `reveal_on_death` is NOT touched. It still returns a `Fact` or `None`, and `game.py`'s `self.fact is not None` guard stays exactly as it is.
- The two card renderers are NOT unified. That duplication is real, recorded in the spec as a non-goal, and deliberately deferred.
- Python is `py -3.13`. Plain `python` is NOT on PATH. Full suite: `py -3.13 -m deathward.tests`. Single class: `py -3.13 -m unittest deathward.tests.<ClassName> -v`.
- The suite is safe to run: `setUpModule` redirects the save path to a tempdir.
- **Clear `deathward/__pycache__` between any mutation and its restore.** A same-length edit made in the same second reuses stale bytecode, and a restored file keeps testing as mutated.
- 851 tests green at branch point. This plan adds 7, for 858.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `deathward/codex.py` | Modify | Gains `subject_complete(subject)` — the single condition both renderers ask. |
| `deathward/ui.py` | Modify (`draw_autopsy` 637, `draw_learned_banner` 458) | The death card disappears when there is no lesson; both cards carry the completion line. |
| `deathward/tests.py` | Modify | New `TestSubjectCompletion`; two tests added to `TestAutopsyWithNothingToTeach`; one added for the banner. |

---

### Task 1: The Codex knows when it is finished with something

**Files:**
- Modify: `deathward/codex.py` (add a method beside `progress`, ~line 964)
- Test: `deathward/tests.py` — new class

**Interfaces:**
- Consumes: `TIER_ORDER` and `FACTS`, both already module-level in `codex.py`.
- Produces: `Codex.subject_complete(subject) -> bool`. Tasks 2 and 3 both call it as `codex.subject_complete(fact.subject)`.

- [ ] **Step 1: Write the failing tests**

Add this class to `deathward/tests.py`, immediately before `class TestAutopsyWithNothingToTeach`:

```python
class TestSubjectCompletion(unittest.TestCase):
    """The line "You have learned everything this one has to teach" hangs on this
    predicate. It asks whether every tier a subject HAS is known -- deliberately
    not whether the counter was just granted, because a Potion of Insight grants
    any unlearned fact regardless of tier order and can hand over a counter while
    the tell is still missing."""

    def test_a_monster_needs_all_three_tiers(self):
        codex = FakeSave()
        self.assertFalse(codex.subject_complete("kobold"))
        codex.known.append("kobold.rule")
        self.assertFalse(codex.subject_complete("kobold"))
        codex.known.append("kobold.tell")
        self.assertFalse(codex.subject_complete("kobold"))
        codex.known.append("kobold.counter")
        self.assertTrue(codex.subject_complete("kobold"))

    def test_a_trap_completes_without_a_tell_it_never_had(self):
        """Traps have rule and counter only -- there is nothing to read on a
        pressure plate. Demanding a tell would leave every trap permanently
        incomplete and the line would never fire for one."""
        codex = FakeSave()
        self.assertNotIn("gas.tell", FACTS, "this test's premise")
        codex.known.append("gas.rule")
        self.assertFalse(codex.subject_complete("gas"))
        codex.known.append("gas.counter")
        self.assertTrue(codex.subject_complete("gas"))

    def test_a_counter_granted_out_of_order_is_not_completion(self):
        """The Potion of Insight case, and the whole reason this is a predicate
        rather than a test for the counter tier."""
        codex = FakeSave()
        codex.known.append("kobold.rule")
        codex.known.append("kobold.counter")       # insight jumped the queue
        self.assertFalse(codex.subject_complete("kobold"))
        codex.known.append("kobold.tell")          # the real last thing
        self.assertTrue(codex.subject_complete("kobold"))

    def test_a_subject_with_no_tiers_is_never_complete(self):
        """all() over an empty sequence is True, so without a guard every string
        that is not a subject -- "poison", a typo, anything -- would report
        complete and the line would fire on facts that have no tiers."""
        codex = FakeSave()
        self.assertFalse(codex.subject_complete("poison"))
        self.assertFalse(codex.subject_complete("nonesuch"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestSubjectCompletion -v`
Expected: FAIL — all four error with
`AttributeError: 'FakeSave' object has no attribute 'subject_complete'`.

- [ ] **Step 3: Add the predicate**

In `deathward/codex.py`, add this method immediately after the `progress` method (which reads `return len(self.known), TOTAL_FACTS`):

```python
    def subject_complete(self, subject):
        """True when every tier this subject has is known.

        Monsters have three (rule, tell, counter); traps have two, because there
        is nothing to read on a pressure plate. Asked of a fact just revealed,
        this answers "was that the last thing this one had to teach?"

        Deliberately NOT the same as "that was the counter". reveal_random -- the
        Potion of Insight -- grants any unlearned fact regardless of tier order,
        so it can hand over a counter while the tell is still missing. A subject
        with no tiers at all is never complete: all() over an empty sequence is
        True, which would otherwise report every non-subject as finished.
        """
        keys = ["%s.%s" % (subject, tier) for tier in TIER_ORDER
                if "%s.%s" % (subject, tier) in FACTS]
        return bool(keys) and all(k in self.known for k in keys)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestSubjectCompletion -v`
Expected: `Ran 4 tests ... OK`

- [ ] **Step 5: Prove the tests can fail**

Temporarily drop the empty-guard — change the return to `return all(k in self.known for k in keys)` — then:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestSubjectCompletion -v
```

Expected: FAIL — `test_a_subject_with_no_tiers_is_never_complete` goes red, because
`all([])` is True.

Restore `return bool(keys) and all(...)`, `rm -rf deathward/__pycache__` again, and confirm green. Do not commit the weakened version.

- [ ] **Step 6: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 855 tests ... OK` (851 + 4). A single `skipped 'no clear line on this seed'` in `TestFireIsVisible` is pre-existing and seed-dependent.

- [ ] **Step 7: Commit**

```bash
git add deathward/codex.py deathward/tests.py
git commit -m "the Kodex can say when it is finished with a subject"
```

---

### Task 2: The death screen — no card when there is no lesson, a closing line when there is a last one

**Files:**
- Modify: `deathward/ui.py` (`draw_autopsy`, line 637; and the `from .codex import ...` line at line 23)
- Test: `deathward/tests.py` — two tests added to `class TestAutopsyWithNothingToTeach`

**Interfaces:**
- Consumes: `Codex.subject_complete(subject) -> bool` from Task 1.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add these two methods to the existing `class TestAutopsyWithNothingToTeach` in `deathward/tests.py`, after its two current tests. Keep both existing tests as they are.

```python
    def test_a_death_with_no_lesson_draws_no_card(self):
        """The card's 2px border runs down x=150 through its whole height, so a
        pixel there is border when a card is drawn and plain background when it
        is not. Compared against x=20 on the same row, which is background in
        both cases, so this asserts nothing about specific colour values."""
        pygame.init()
        w = World(FakeSave(), seed=12)

        lesson = pygame.Surface((config.W, config.H))
        ui.draw_autopsy(lesson, w, w.codex, FACTS["rat.rule"], "rat", 99.0)
        self.assertNotEqual(lesson.get_at((150, 300)), lesson.get_at((20, 300)),
                            "a lesson must draw the card border")

        silence = pygame.Surface((config.W, config.H))
        ui.draw_autopsy(silence, w, w.codex, None, "rat", 99.0)
        self.assertEqual(silence.get_at((150, 300)), silence.get_at((20, 300)),
                         "no lesson must draw no card at all")

    def test_the_entry_that_finishes_a_subject_says_so(self):
        """Same fact, same number of known facts -- so the progress counter reads
        identically and cannot be what differs. The only variable is whether the
        kobold is finished."""
        pygame.init()
        w = World(FakeSave(), seed=12)
        fact = FACTS["kobold.counter"]

        unfinished = FakeSave()
        unfinished.known = ["kobold.rule", "kobold.counter", "rat.rule"]
        a = pygame.Surface((config.W, config.H))
        ui.draw_autopsy(a, w, unfinished, fact, "kobold", 99.0)

        finished = FakeSave()
        finished.known = ["kobold.rule", "kobold.tell", "kobold.counter"]
        b = pygame.Surface((config.W, config.H))
        ui.draw_autopsy(b, w, finished, fact, "kobold", 99.0)

        self.assertNotEqual(pygame.image.tostring(a, "RGB"),
                            pygame.image.tostring(b, "RGB"),
                            "finishing a subject must change what is drawn")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestAutopsyWithNothingToTeach -v`

Expected: FAIL on both new tests.
`test_a_death_with_no_lesson_draws_no_card` fails on its second assertion — today a
card is drawn even with no fact. `test_the_entry_that_finishes_a_subject_says_so` fails
because nothing yet distinguishes the two, so the surfaces are byte-identical.
The two pre-existing tests must still PASS.

- [ ] **Step 3: Import `TIER_ORDER` into the UI**

In `deathward/ui.py`, line 23 currently reads:

```python
from .codex import CAUSE_NAME, FACT_LIST, KODEX_TABS, TOTAL_FACTS, fact_title, facts_in
```

Replace it with:

```python
from .codex import (CAUSE_NAME, FACT_LIST, KODEX_TABS, TIER_ORDER, TOTAL_FACTS,
                    fact_title, facts_in)
```

- [ ] **Step 4: Rewrite the tail of `draw_autopsy`**

In `deathward/ui.py`, replace everything from the `card = pygame.Rect(150, 168, ...)` line through the end of the function with:

```python
    if fact is None:
        # No lesson, no card. The absence IS the message: a bordered box
        # announcing nothing takes the same space and ceremony as a real entry
        # and delivers none. The closing lines move up into the space the card
        # would have filled, so the screen reads as short rather than as broken.
        text(surf, "the dungeon is unchanged.  you are not.",
             (cx, 198), 15, config.CORPSE, center=True)
        text(surf, "ENTER  go back down        K  kodex",
             (cx, 234), 17, config.PLAYER, center=True, bold=True)
        return

    card = pygame.Rect(150, 168, config.W - 300, 250)
    pygame.draw.rect(surf, (14, 16, 22), card, border_radius=6)
    pygame.draw.rect(surf, config.PLAYER, card, 2, border_radius=6)

    tag = "TELEMETRY RECOVERED" if fact.tier == "telemetry" else "NEW KODEX ENTRY"
    head = pygame.Surface((card.w, 26), pygame.SRCALPHA)
    head.fill((*config.PLAYER, 26))
    surf.blit(head, card.topleft)
    text(surf, tag, (card.left + 16, card.top + 6), 13, config.PLAYER, bold=True)
    known, total = codex.progress()
    text(surf, "%d/%d" % (known, total), (card.right - 16, card.top + 13), 13,
         config.DIM, right=True)

    text(surf, fact_title(fact, codex), (card.left + 22, card.top + 46), 23,
         config.INK, bold=True)
    body = fact.text
    n = int(min(len(body), reveal_t * 95))
    y = card.top + 90
    for ln in wrap(body[:n], 15, card.w - 44):
        text(surf, ln, (card.left + 22, y), 15, config.INK)
        y += 22

    if n < len(body):
        return                       # still typing: the closing beats wait their turn

    if fact.tier in TIER_ORDER and codex.subject_complete(fact.subject):
        text(surf, "You have learned everything this one has to teach.",
             (card.left + 22, y + 10), 15, config.CORPSE)

    text(surf, "the dungeon is unchanged.  you are not.",
         (cx, card.bottom + 30), 15, config.CORPSE, center=True)
    text(surf, "ENTER  go back down        K  kodex",
         (cx, card.bottom + 66), 17, config.PLAYER, center=True, bold=True)
```

Everything above that point — the dimming layer, `cx`, "YOU DIED", the killed-by line and the death-count line — is unchanged.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestAutopsyWithNothingToTeach -v`
Expected: `Ran 4 tests ... OK`

- [ ] **Step 6: Prove the completion test has teeth**

Temporarily change the completion condition to `if False and fact.tier in TIER_ORDER and ...`, then:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestAutopsyWithNothingToTeach -v
```

Expected: FAIL — `test_the_entry_that_finishes_a_subject_says_so` goes red, proving it is
detecting the line itself and not some incidental difference.

Restore the real condition, `rm -rf deathward/__pycache__`, confirm green. Do not commit the disabled version.

- [ ] **Step 7: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 857 tests ... OK` (855 + 2).

- [ ] **Step 8: Commit**

```bash
git add deathward/ui.py deathward/tests.py
git commit -m "the death screen falls silent when it has nothing to say"
```

---

### Task 3: The mid-run banner carries the same line

**Files:**
- Modify: `deathward/ui.py` (`draw_learned_banner`, line 458)
- Test: `deathward/tests.py` — one new class

**Interfaces:**
- Consumes: `Codex.subject_complete(subject) -> bool` from Task 1; `TIER_ORDER`, imported into `ui.py` by Task 2.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Add this class to `deathward/tests.py`, immediately after `class TestAutopsyWithNothingToTeach`:

```python
class TestBannerMarksCompletion(unittest.TestCase):
    """Kills, sprung traps, identified items and the Potion of Insight all reveal
    through this one banner -- only deaths use the autopsy card. Marking
    completion on the card alone would leave most completions silent: traps
    finish on a THIRD springing, which is ordinary play."""

    def test_the_entry_that_finishes_a_subject_says_so(self):
        """Same fact and the same number of known facts, so the banner's own
        progress counter reads identically. The only variable is completion."""
        pygame.init()
        fact = FACTS["kobold.counter"]

        unfinished = FakeSave()
        unfinished.known = ["kobold.rule", "kobold.counter", "rat.rule"]
        a = pygame.Surface((config.W, config.H))
        ui.draw_learned_banner(a, fact, 9.0, unfinished)

        finished = FakeSave()
        finished.known = ["kobold.rule", "kobold.tell", "kobold.counter"]
        b = pygame.Surface((config.W, config.H))
        ui.draw_learned_banner(b, fact, 9.0, finished)

        self.assertNotEqual(pygame.image.tostring(a, "RGB"),
                            pygame.image.tostring(b, "RGB"),
                            "finishing a subject must change what is drawn")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestBannerMarksCompletion -v`
Expected: FAIL — the two surfaces are byte-identical, because nothing yet distinguishes a completing reveal from any other.

- [ ] **Step 3: Grow the banner and add the line**

In `deathward/ui.py` `draw_learned_banner`, replace these two lines:

```python
    lines = wrap(fact.text, 14, 560)
    h = 96 + len(lines) * 19
```

with:

```python
    lines = wrap(fact.text, 14, 560)
    finished = fact.tier in TIER_ORDER and codex.subject_complete(fact.subject)
    h = 96 + len(lines) * 19 + (19 if finished else 0)
```

Then, in the same function, replace this block:

```python
    yy = 60
    for ln in lines:
        text(card, ln, (16, yy), 14, config.DIM)
        yy += 19
    surf.blit(card, (x, y))
```

with:

```python
    yy = 60
    for ln in lines:
        text(card, ln, (16, yy), 14, config.DIM)
        yy += 19
    if finished:
        text(card, "You have learned everything this one has to teach.",
             (16, yy + 2), 13, config.CORPSE)
    surf.blit(card, (x, y))
```

The `"move on when you have read it"` hint is positioned at `(16, h - 22)`, so it stays pinned to the bottom edge as the card grows. Do not move it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `py -3.13 -m unittest deathward.tests.TestBannerMarksCompletion -v`
Expected: `Ran 1 test ... OK`

- [ ] **Step 5: Prove the test has teeth**

Temporarily change the assignment to `finished = False`, then:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestBannerMarksCompletion -v
```

Expected: FAIL — the surfaces become identical again.

Restore the real condition, `rm -rf deathward/__pycache__`, confirm green. Do not commit the disabled version.

- [ ] **Step 6: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 858 tests ... OK` (857 + 1).

- [ ] **Step 7: Commit**

```bash
git add deathward/ui.py deathward/tests.py
git commit -m "a corpse, a sprung trap and a drained flask can finish a subject too"
```

---

## Verification

Automated coverage ends at Task 3 Step 6. The rest is the user's:

- Die to a monster you have not finished learning → card, no completion line.
- Die to the one that finishes it → card plus *"You have learned everything this one has to teach."*
- Die to it again → **no card at all**, just YOU DIED, the killed-by line, the death count and the closing lines sitting higher up the screen.
- Spring the same trap a third time → the mid-run banner carries the line, one row taller.
