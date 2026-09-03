# Death Reveals Only The Killer

**Date:** 2026-09-03
**Status:** design, pending review
**Scope:** a death teaches you about the thing that killed you, or it teaches you nothing.
Removes the fallback cascade that substituted an unrelated subject, and stops damage-over-time
losing the identity of its source.

## Problem

Two separately-reported bugs turned out to share one mechanism, exactly as the user suspected.

`Codex.reveal_on_death` (`codex.py:1110`) runs a cascade: the first-death fact, then **the
killer** (steps 2-4), then **the nearest unlearned thing on the floor** (step 5), then a carried
item's true name, then self/dungeon secrets, then anything at all, then an inexhaustible
telemetry tier. Its docstring promises "Never returns None".

Both reports are step 5 firing, for different reasons:

1. **Poison deaths.** `player.py:204` tags every poison tick `"poison"`, which is not one of the
   Kodex's 22 subjects. The gas vent (`traps.py:151`) sets `player.poison` and discards its own
   identity, so the killer is unidentifiable and step 5 substitutes a floor monster. A real save
   confirmed it: `deaths_by` held `"poison"`, and `kobold.rule` was granted on a death with zero
   kobold encounters.
2. **Fully-known killers.** When the cause *is* a valid subject but every tier is already known,
   steps 2-4 find nothing and step 5 substitutes a floor monster.

A third defect was found during investigation and is worth recording even though the fix
deletes rather than repairs it: **step 5 was never "nearest".** Both the docstring and the
step's own comment claim "nearest first", but `World.floor_subjects()` (`world.py:2617`) returns
`level.monsters` in spawn/append order, then traps — no distance, no player position, and no
check that the player ever saw the thing. That is why the substituted lesson felt random: it was
whichever monster happened to be first in the level's spawn list, anywhere on the floor.

Two further cause tags are not Kodex subjects and so also produce a substituted lesson today:
the Potion of Venom's self-poison (`world.py:1985`) and Shademail's crush damage
(`world.py:2444`, tagged `"shade"`).

## The rule

**A death teaches about its killer, or it teaches nothing.** No substitutes.

## Goals

- Steps 2-4 (the killer's `rule`, `tell`, `counter`, in that order) are the only lesson a death
  can give, apart from the first-death fact.
- When the killer is fully known, unknown to the Kodex, or unidentifiable, the death teaches
  nothing and the autopsy says so.
- A gas-vent poison death is attributed to **`gas`** — so it teaches `gas.rule` and files
  `deaths_by["gas"]` correctly, instead of a generic `"poison"` that teaches a stranger.

## Non-goals

- **The five secret facts are not rehomed here.** `self.energy`, `self.armour`, `self.stairs`,
  `dungeon.hoard` and `dungeon.deep` are granted only by the step being deleted. Converting them
  to experience triggers is the agreed next piece of work, deliberately kept separate. See
  "Accepted interim cost".
- No change to Shademail's `"shade"` tag. It is not a Kodex subject, so that death now teaches
  nothing, which the new rule makes correct rather than broken.
- No new Kodex subjects, no new facts, no rebalancing of what the existing facts say.

## Design

### 1. The cascade collapses

`reveal_on_death` keeps step 1 (`self.corpse`, so a player's first death still explains death
itself) and steps 2-4 (the killer's tiers in `TIER_ORDER`). Steps 5 through 9 are deleted. The
method may now return `None`, and its docstring says so.

`floor_subjects` and `carried_flavors` become unused parameters and come off the signature. The
new signature is:

```python
def reveal_on_death(self, cause):
```

Three things become unreachable and are deleted with it:

- `World.floor_subjects()` (`world.py:2617`) — its only caller was `game.py:195`
- `Codex._telemetry_fact()` (`codex.py:1190`) — existed only to make the cascade inexhaustible.
  Note it writes into `self.telemetry`, which is serialized and rendered in the Kodex's Lore
  tab. Entries already in a player's save keep rendering; no new ones are ever generated. The
  `self.telemetry` list, its load/save round-trip, and its rendering all stay — only the
  generator goes.
- `Player.carried_flavors()` (`player.py:288`) — its only caller was `game.py:195`

`SELF_SECRETS` and `DUNGEON_SECRETS` (`codex.py:637-638`) stay defined but unreferenced, with a
comment pointing at the deferred trigger work. Deleting and re-adding them a week later is
churn. The five facts themselves stay in `FACTS` untouched.

### 2. Poison remembers where it came from

New `Player.poison_source`, added to `_PLAYER_STATE` so a suspended run restores it.

**No `RUN_SAVE_VERSION` bump is needed.** `Player.from_dict` reads `data.get(k, getattr(p, k))`,
so a save written before this change simply falls back to the default. (This is unlike
`Monster.from_dict`, which indexes `data[k]` and forced the bump to 5 — the contrast is why this
was checked rather than assumed.)

- Gas vent (`traps.py:151`) sets `poison_source = "gas"` alongside the poison it applies.
- The tick (`player.py:204`) reports `world.hurt_player(1, self.poison_source or "poison", silent=True)`.
- `poison_source` clears when `poison` reaches 0, beside the existing "burns itself out" branch.
- The Potion of Venom (`world.py:1982`) sets no source. Self-inflicted poison therefore reports
  `"poison"`, which is not a subject, and teaches nothing. Under the new rule that is simply
  correct, and needs no special case — this closes an open design question from the original bug
  note without adding code.

### 3. The autopsy learns to say nothing

`ui.draw_autopsy` (`ui.py:637`) reads `fact.tier`, `fact_title(fact, codex)` and `fact.text`
unconditionally; `game.py:474` computes `len(self.fact.text)` for the typewriter reveal. Both
must tolerate `None`.

When there is no fact, the card shows:

> **NOTHING NEW**
> You have learned everything this one has to teach. It killed you anyway.

The banner replaces the usual "NEW KODEX ENTRY" / "TELEMETRY RECOVERED" heading, and the reveal
animation is skipped rather than typing an empty string.

## Testing

- a gas-vent poison tick that kills the player attributes the death to `gas`: it teaches
  `gas.rule` and records `deaths_by["gas"]`, with no `"poison"` key
- a death to a killer whose `rule`/`tell`/`counter` are all known returns `None`
- a death to a cause with no Kodex subject at all (self-inflicted venom) returns `None`
- the killer's tiers are taught in `TIER_ORDER` across successive deaths: `rule`, then `tell`,
  then `counter`
- the first death ever still returns `self.corpse`
- a floor full of unlearned monsters does **not** produce a lesson when the killer is exhausted —
  the regression guard for the deleted step 5
- `draw_autopsy` renders with `fact=None` without raising

`test_500_deaths_never_repeat_a_lesson` is rebuilt around the new rule: deaths teach their
killer until that killer is exhausted, then teach nothing, and no lesson is ever repeated. The
"never repeats" half of that proof survives; the "always teaches" half is what this change
deliberately retires.

## Documentation

`README.md:212` describes the guarantee being removed — "hundreds of consecutive deaths never
repeat a lesson (and the telemetry tier is inexhaustible)". It is reworded to describe what the
suite now proves. The README's other load-bearing proof — same seed, empty Kodex versus complete
Kodex, bit-identical dungeons — is untouched, so "knowledge is information, never power" still
holds exactly as written.

## Accepted interim cost

Until the trigger work lands, the five secret facts are unobtainable, and the user has accepted
this knowingly, having been shown the precise consequences:

- all five sit in the Kodex's **Lore** tab and render as `[ SEALED ] something about yourself`
  (or `the dungeon`) above the line **"this entry is written by dying"** — which becomes false
- `TOTAL_FACTS` is 98 and progress displays as `len(known), TOTAL_FACTS`, so completion caps at
  **93/98** and 100% is unreachable

Rejected alternatives: shipping both changes together, and adding temporary scaffolding to hide
the five. The reasoning for accepting the gap is that the user is the only person who will run
an intermediate build, and the trigger work is next.

## Verification

- Full suite green: `py -3.13 -m deathward.tests`.
- Manual playtest: die to a fully-known monster and see the NOTHING NEW card; die to a gas vent
  and see a `gas` entry rather than a stranger.
