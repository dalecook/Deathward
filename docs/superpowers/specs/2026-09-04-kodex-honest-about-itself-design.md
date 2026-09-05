# The Kodex Stops Lying About Itself

**Date:** 2026-09-04
**Status:** design, pending review
**Scope:** delete the five tutorial facts that have no way to be earned, and fix the sealed-entry
hint that tells the player the wrong way to earn 39 of the others.

## Problem

Two faults, both about the Kodex misdescribing itself.

**1. Five facts nobody can earn.** `self.energy`, `self.armour`, `self.stairs`, `dungeon.hoard`
and `dungeon.deep` are system tutorials — turns are a currency, armour is subtraction, down is
free, hoards are guarded, why you cannot see. They were granted only by the fallback cascade
that `dd40f71` deleted, so they had no path a player could aim at — only a Potion of Insight,
which grants any unlearned fact at random, could ever have produced them. The agreed plan was
to give them experience triggers; the decision instead is to **cut them**. They explain genre
conventions a roguelike player already brings with them, and the game is stronger for not
stopping to teach what its
audience knows.

**2. The sealed hint is wrong on 39 of 93 entries.** An unlearned entry renders as:

```
[ SEALED ]  something about the kobold
this entry is written by dying.
```

That second line is printed for every category. It is now false for:

- **18 scrolls and 18 potions** — the `id.<flavor>` facts. Deleting the cascade's step 6 removed
  the only path that granted them on death, so they are now obtainable *only* by reading or
  drinking the thing. **This branch's predecessor caused those 36.**
- **3 collector awards** in the Lore tab, earned by collecting every magical weapon, boot or
  armour set. Pre-existing.

It is also true-but-incomplete on the 42 monster and 10 trap entries: dying is the fast road,
but killing and springing write them too, and a player reading only the Kodex would never learn
that.

## Goals

- Every fact in `FACTS` has a path by which a player can earn it.
- Every sealed entry describes a way to earn *that* entry.

## Non-goals

- No experience triggers for the five. They are deleted, not rehomed — this supersedes the
  deferred trigger work entirely.
- No change to what grants anything, to thresholds, or to any reveal path. This is deletion plus
  display copy.
- No save migration. `TOTAL_FACTS` derives from `FACT_LIST`, and the only live save has learned
  none of the five (checked). The single-developer repo makes a migration path dead code.

## Design

### 1. Delete the five, and the constants that named them

Remove the five `_f(...)` definitions from `deathward/codex.py`, and remove `SELF_SECRETS` and
`DUNGEON_SECRETS` along with the comment added in `dd40f71` explaining that they were waiting for
triggers. Those two lists exist only to name these five facts.

Consequences, all automatic:

- `TOTAL_FACTS` is `len(FACT_LIST)`, so it drops **98 → 93** and Kodex completion becomes
  reachable again.
- The Lore tab keeps five entries — THE DEAD DO NOT LEAVE, the three collector awards, and YOU
  WAKE, AGAIN — so it does not empty out.
- The `dungeon` subject disappears entirely. Nothing iterates subjects expecting it.
- The only test referencing `TOTAL_FACTS` is a bound that still holds at 93.

### 2. Make the sealed hint tell the truth

`ui.draw_codex` currently prints one hard-coded line under every sealed entry. It gains a helper
beside the existing `_kodex_sealed_label`, which selects by category — and, within Lore, by
whether the fact is a collector award:

| Tab | Hint |
|---|---|
| Monsters | `this entry is written by dying to it, or by killing enough of them.` |
| Traps | `this entry is written by springing it, or by dying to it.` |
| Scrolls | `this entry is written by reading it.` |
| Potions | `this entry is written by drinking it.` |
| Lore — the three collector awards | `this entry is written by collecting every one.` |
| Lore — everything else | `this entry is written by dying.` |

Copy approved by the user; reproduce it character for character.

The Gear tab is untouched: it has its own sealed branch, with its own hint (`this entry is
written by finding it.`), which is already accurate.

## Testing

- each of the five deleted keys is absent from `FACTS`, in a test whose docstring records that
  they were cut deliberately as genre conventions the player already brings — so nobody
  "restores the missing tutorials" later
- `TOTAL_FACTS` is 93, pinning the count against an accidental re-add
- the hint helper returns the right line for each of the six cases, asserted against the literal
  strings rather than against a constant the implementation also reads
- a monster fact and an `id.` fact get different hints — the regression guard for the specific
  bug, since one shared hint is exactly what was wrong

## Verification

- Full suite green: `py -3.13 -m deathward.tests`.
- Manual: open the Kodex (`K`), and check the Scrolls and Potions tabs tell you to read and drink
  rather than to die, and that the Lore tab's collector awards ask you to collect.
