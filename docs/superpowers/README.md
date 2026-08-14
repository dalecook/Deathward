# Design archive

**These documents are history, not documentation.**

Every file under `specs/` and `plans/` is dated, and it describes what was decided *on
that date*. None of them is updated after its work merges. If a spec and the code
disagree, **the code is right** — read `deathward/` and `deathward/tests.py`, in that
order, and treat anything here as a record of how the code got that way.

That is deliberate. These are the reasoning trail: what was considered, what was
rejected, and why. Rewriting them to match today's code would destroy the only thing
they are good for, and would not make them trustworthy anyway — nothing verifies them.

- **`specs/`** — the *what and why*. Design intent, settled with the author before any
  code existed.
- **`plans/`** — the *how*. Task-by-task implementation breakdowns derived from a spec.

## Reading them safely

Later documents supersede earlier ones silently. A decision stated flatly in a July 21
spec may have been reversed on July 23, and the July 21 file will not mention it. Two
known examples, both real:

- The armour ordinary-tier spec (`specs/2026-07-22-armour-rebalance-ordinary-tier-design.md`)
  states that `thorn` and `silk` were **removed**. True that day. They returned the
  following day as magical T4 pieces and are live in `items.py` now.
- Several early gear specs predate the decision that gear is **found-only**. The vendor
  sells consumables and nothing else.

When in doubt: `git log` is the honest chronology, and the test suite is the honest spec.

## Chronology

Read top to bottom for how the game's gear economy was actually built.

### Weapons — 17–20 July
| date | doc |
|---|---|
| 07-17 | `specs/…weapon-rebalance-ordinary-1-8-design.md` → `plans/…weapon-rebalance-ordinary-1-8.md` |
| 07-19 | `specs/…magical-weapon-roster-design.md` → `plans/…plan-1-roster-and-combat.md` |
| 07-20 | `plans/…plan-2-deep-economy.md` |
| 07-20 | `plans/…plan-3-uniqueness-persistence.md` |

### Boots — 21–22 July
| date | doc |
|---|---|
| 07-21 | `specs/…boots-rebalance-ordinary-tier-design.md` → `plans/…boots-rebalance-ordinary-tier.md` |
| 07-21 | `specs/…boots-distribution-generation-placed-design.md` → `plans/…boots-distribution-generation-placed.md` |
| 07-21 | `specs/…magical-boots-roster-design.md` → `plans/…magical-boots-phase1-roster.md` |
| 07-22 | `plans/…magical-boots-phase2-stealth.md` |
| 07-22 | `specs/…magical-boots-economy-design.md` → `plans/…phase3a-rarity-uniqueness.md`, `plans/…phase3b-persistence-collection.md` |

### Armour — 22–24 July
| date | doc |
|---|---|
| 07-22 | `specs/…armour-rebalance-ordinary-tier-design.md` → `plans/2026-07-23-armour-rebalance-ordinary-tier.md` |
| 07-23 | `specs/…magical-armour-roster-design.md` → `plans/…magical-armour-phase1-roster.md` |
| 07-24 | `plans/…magical-armour-phase2.md` (invisibility, wall-walk) |
| 07-24 | `specs/…magical-armour-economy-design.md` → `plans/…magical-armour-economy.md` |

### Suspend / resume — 22 July
| date | doc |
|---|---|
| 07-22 | `specs/…suspend-resume-save-design.md` → `plans/…phase1-serialization.md`, `plans/…phase2-wiring.md` |
