# The Last Thing A Subject Has To Teach

**Date:** 2026-09-03
**Status:** design, pending review
**Scope:** replace the NOTHING NEW autopsy card with silence, and mark the *completion* of a
subject on the entry that finishes it — in both places a Kodex entry is ever revealed.

## Problem

The death-reveal change (see `2026-09-03-death-reveals-only-the-killer-design.md`) made a
death teach its killer or nothing, and gave the nothing case a card reading **NOTHING NEW /
You have learned everything this one has to teach. It killed you anyway.**

Playtest rejected it. A card announcing an absence takes the same space and ceremony as a real
lesson while delivering none — it makes an anticlimax into an event, and it repeats on every
subsequent death to the same killer.

The information is worth having; the moment was wrong. It belongs on the entry that *completes*
a subject, once, when the completing fact is revealed — not on every death afterwards.

## The rule

**When a revealed fact leaves every tier of its subject known, the card that reveals it ends
with:**

> You have learned everything this one has to teach.

**And a death that teaches nothing shows no card at all.**

## Goals

- A death with no lesson is quiet: no card, no header band, no progress counter.
- Completing a subject is marked exactly once, at the moment it happens, wherever it happens.
- One sentence, one voice, both surfaces.

## Non-goals

- **No change to `reveal_on_death`.** It still returns a `Fact` or `None`, and `game.py`'s
  `self.fact is not None` guard stays exactly as it is. This is a rendering change.
- **No unification of the two card renderers.** `ui.draw_autopsy`'s card and
  `ui.draw_learned_banner` are structurally the same widget — rounded rect, tinted header band,
  tag, `known/total` counter, bold title, wrapped body — differing in palette, sizing rule and
  reveal behaviour. Collapsing them would make this a one-site change instead of two. That is a
  real cleanup and is deliberately deferred: this branch is already four tasks deep and through
  a whole-branch review, and the duplication predates it.
- No change to what grants facts, to thresholds, or to the Kodex browser.

## Design

### 1. Completion is a Codex question

New method on `Codex`:

```python
def subject_complete(self, subject):
    """True when every tier this subject has is known."""
```

It walks `TIER_ORDER`, considers only the tiers that actually exist in `FACTS` for that subject,
and returns whether all of them are in `self.known`. Monsters have three (`rule`, `tell`,
`counter`); traps have two (`rule`, `counter` — there is nothing to read on a pressure plate).

Both renderers ask the same question:

```python
fact.tier in TIER_ORDER and codex.subject_complete(fact.subject)
```

The `tier` guard keeps the line off facts that have no tiers at all — `self.corpse`, the
`id.<flavor>` identities, the three collector awards, and telemetry.

**Why "complete", not "the counter".** `counter` is last in `TIER_ORDER` for every subject, so
it is tempting to test for it directly. That breaks on the Potion of Insight: `reveal_random`
grants *any* unlearned fact, ignoring tier order, so it can hand over `kobold.counter` while
`kobold.tell` is still missing. Testing completion instead of position handles that with no
special case — the line stays off the early counter and appears later on the tell, which really
is the last thing that kobold had to teach *this player*.

There is a second reason it needs no special case: a subject can only be revealed while
something about it is unknown, so any reveal that finds the subject complete **is** the
completing reveal. The line cannot repeat.

### 2. Both surfaces, because there are two renderers

Five events grant a Kodex entry, but they converge on two renderers:

| Event | Renderer |
|---|---|
| death | `ui.draw_autopsy`'s card |
| kill (monsters, 1st/3rd/8th) | `ui.draw_learned_banner` |
| springing a trap (1st/3rd) | `ui.draw_learned_banner` |
| using an unknown item | `ui.draw_learned_banner` |
| Potion of Insight | `ui.draw_learned_banner` |

Marking completion only on the autopsy would leave most completions silent — traps complete on
a **third springing**, which is ordinary play, and Insight can complete anything at any moment.

- **`draw_autopsy`:** the line renders beneath the fact body, in the muted `config.CORPSE`
  colour used by the existing closing line, and only once the typewriter has finished, so it
  lands after the lesson rather than during it.
- **`draw_learned_banner`:** the line renders beneath the body lines and above the existing
  *"move on when you have read it"* hint. The banner already sizes itself to its content
  (`h = 96 + len(lines) * 19`); its height grows by one line when the completion line is
  present, following that existing rule rather than fighting it.

### 3. The empty death loses its card

When `fact is None`, `draw_autopsy` draws no card: no rectangle, no border, no header band, no
tag, no progress counter. The screen keeps **YOU DIED**, the killed-by line and the death-count
line.

The two closing lines are currently positioned from the card's bottom edge (y=448 and y=484).
With no card they would strand under roughly 300px of void, which reads as a rendering fault
rather than as silence, so on a no-lesson death they move up to where the card would have begun
— y=198 and y=234. The screen stays composed, and is visibly shorter than a death that taught
something.

The `NOTHING NEW` heading and the sentence *"It killed you anyway."* are deleted.

## Testing

`subject_complete` carries the logic, so it gets direct coverage:

- a monster reports complete only once `rule`, `tell` and `counter` are all known
- a trap reports complete on `rule` + `counter`, without ever needing a `tell` it does not have
- a subject missing any one tier reports False
- the Potion of Insight case: `counter` granted before `tell` reports False; granting the
  `tell` afterwards reports True
- a subject with no facts at all reports False rather than vacuously True

Then render smoke tests, in the style already used for the autopsy:

- a no-fact autopsy draws no card and does not raise
- an autopsy whose fact completes its subject draws the line
- a banner whose fact completes its subject draws the line and is taller than one whose fact
  does not

## Verification

- Full suite green: `py -3.13 -m deathward.tests`.
- Manual playtest: die to a monster you have not finished learning (card, no line), die to the
  one that finishes it (card plus the line), die to it again (no card at all), and complete a
  trap by springing it a third time (banner plus the line).
