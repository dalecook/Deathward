# Weapon Rebalance — Magical Roster & Deep Economy (Floors 8–20)

**Date:** 2026-07-19
**Status:** design, pending review
**Scope:** the second of the two weapon passes. Phase 1 built the *ordinary* tier
(floors 1–7) and the per-instance `bonus`/persistence machinery. This phase expands and
rebalances the *magical* tier (floors 8–20): a new Tier 5, thirteen named magical weapons
(ten new), a deep-floor loot economy, and a persistence system that makes magical weapons
absolutely unique, world-persistent artifacts. Armour and boots remain out of scope.

## Problem

The magical tier is three weapons (Steel Rapier/crit, Flame Brand/burn, Vampiric
Kris/lifesteal) covering thirteen floors, drawn as a **flat, uniform-random pool** with
no depth progression. Two of the three (Brand, Kris) are clearly stronger than the third
yet share its tier. Descent past floor 8 stops feeling like it escalates, and there is
no scarcity or reward structure to make a deep-floor weapon feel like a *find*.

## Goals

- **A real magical progression** across floors 8–20 without dumping power early.
- **Two magical tiers** (4 and 5) where Tier 5 wins on **mechanical reach** (AoE + status
  on a crowd), not merely bigger single-hit numbers — honouring the gear-triad thesis
  that upgrades are *tactical decisions*, not inflation.
- **Scarcity as fiction:** the deeper you go, the fewer adventurers died there, so the
  less loot lies around — but what remains is *better* (masterwork steel, top-tier magic).
- **Magical weapons as unique, world-persistent artifacts** — each generated at most once
  per game and staying where it lies across lives, so the roster is a *draw without
  replacement* and **dying becomes a tactic** for fishing the shrinking pool. This is the
  most on-theme extension of "failure is the only progression."
- **Weapons never a guaranteed find deep down.** A great weapon with poor armour still
  gets you killed, so the game need not hand them out; magical weapons are rare, and a run
  may see few or none.
- **Reuse existing systems** (burn, cleave, crit, lifesteal, stun, fear, poison, the
  `speed_mod` economy, the hardened stun/freeze code) rather than inventing a dozen new
  ones. Only three genuinely new mechanics.
- Preserve the core invariants: **knowledge is information, never power** (all generation
  and combat randomness draws from the world RNG, independent of the Kodex) and
  blind-vs-omniscient runs of a seed stay **bit-identical**.

## Non-goals (this phase)

- **Armour and boots** — untouched, separate future passes.
- **Building the mini-bosses.** Two weapons are mini-boss rewards, but the bosses
  themselves belong to the [add-minibosses-floors-8-15] task. This phase defines those two
  weapons, excludes them from the found pool, and leaves a clean drop-hook; until the
  bosses exist they are reachable only via the CTRL+12 weapon-bench cheat for testing.
- **Armour/boots persistence** — the new magical-weapon ledger (§7) is *weapons only*.
  Phase 1's per-instance `bonus`/corpse/victory-keep machinery is inherited for free; this
  phase adds the ledger on top, but does not touch armour or boots persistence.

## Design

### 1. Two magical tiers and the power ordering

A new **Tier 5** sits above Tier 4. The full power ordering used by the "keep the better
weapon" corpse tie-break becomes:

```
shiv 0  <  bone 1  <  bronze 2  <  steel 3  <  magical-T4 4  <  magical-T5 5
```

The tie-break already compares `(tier, bonus)` as integers (`codex.leave_corpse`), so
adding tier 5 needs no new comparison logic — only the new weapons carry `tier=5`.

### 2. The through-line: focused (T4) vs unleashed (T5)

A magical weapon is built from an **effect family**. The **Tier 4** version delivers the
effect **focused** — single target, fast. The **Tier 5** version is the same fantasy
**unleashed** — it borrows an ordinary attack shape (usually the axe's **cleave**) so the
effect lands on a whole crowd. Tier 5's power is *reach*, not inflated single-hit numbers.

### 3. The roster — 7 Tier 4 + 6 Tier 5

All magical weapons are **found unenhanced** (`bonus = 0`) and **scroll-enchantable**
(uncapped, as phase 1). None carry a speed tax except **Windfang**, which carries a
speed *bonus*.

**Tier 4 — focused (avg damage in parens):**

| key | name | shape | dmg | trait(s) | notes |
|---|---|---|---|---|---|
| `rapier` | Razor Sharp Rapier | rapier | 4–6 (5) | crit | 1-in-4 doubles; spiky pure damage. Reuses existing `rapier` key. |
| `brand` | Flame Brand | sword | 4–8 (6) | burn | downgraded from 5–10. Reuses `brand` key. |
| `betrayers_edge` | Betrayer's Edge | sword | 4–6 (5) | enrage | chance to send the target into an Orc-like rage — it attacks any adjacent creature, **including you**. |
| `fulgurite` | Fulgurite | axe | 4–6 (5) | cleave + anti-incorporeal | cleaves; **×1.5 damage vs incorporeal** (wraith, poltergeist). The answer to armour-ignoring ghost mobs. |
| `winters_edge` | Winter's Edge | sword | 3–6 (4.5) | freeze | chance to freeze (one turn, reuses the `stunned` system). Control tax on damage. |
| `sacrificial_dagger` | Sacrificial Dagger | dagger | 3–5 (4) | lifesteal | low raw damage; sustain is the payoff. |
| `windfang` | Windfang | sword | **5–5 flat** | haste | `speed_mod = +20`. Low, *reliable* damage + extra tempo. **Floor-8 mini-boss reward.** |

**Tier 5 — unleashed:**

| key | name | shape | dmg | trait(s) | notes |
|---|---|---|---|---|---|
| `basilisk_maul` | Basilisk Maul | mace | 5–9 (7) | poison + stun | top single-target: venom that both envenoms and holds rigid. |
| `pyroclast` | Pyroclast | greataxe | 5–8 (6.5) | cleave + burn | ignites every body it cleaves. |
| `reapers_whisper` | Reaper's Whisper | scythe | 5–8 (6.5) | cleave + fear | scatters the whole crowd it reaps through. |
| `kris` | Vampiric Kris | dagger | 4–7 (5.5) | cleave + lifesteal | heals off **each** cleaved body — terrifying sustain in a swarm. Reuses `kris` key. |
| `glacial_flail` | Glacial Flail | flail | 4–7 (5.5) | cleave + freeze | freezes every adjacent enemy — room control. |
| `void_scimitar` | Scimitar of the Void | scimitar | **7–7 flat** | instakill | **10%** chance to delete a monster outright. **Floor-15 mini-boss reward.** |

The three existing keys (`rapier`, `brand`, `kris`) are **reused and retuned**; the other
ten are new keys.

### 4. Balance philosophy — utility, not inflation

**Magical weapons trade raw damage for their trait; they do not simply out-number the
deep enhanced Steel.** A scroll-fed Steel +3 (6–8, avg 7) remains a legitimate
pure-damage choice a player might keep over a utility magical weapon. Within a tier, raw
damage trades against utility, so **nothing is an auto-include**: the pure-damage picks
(Rapier, Brand, Basilisk) hit hardest; the control/sustain/haste picks (Winter's Edge,
Sacrificial Dagger, Windfang) hit softer and win on effect. All bands are playtest
tunables.

### 5. Traits — reused vs. new

| trait | status | mechanic |
|---|---|---|
| crit | reuse | 1-in-4 → ×2 damage (existing) |
| burn | reuse | ignite: `burning`, ~2 dmg/turn (existing) |
| lifesteal | reuse | heal `dmg // 2` (existing) |
| cleave | reuse | hits every adjacent enemy for `max(1, dmg//2)` (existing) |
| stun | reuse | the hardened player-turn stun (existing, phase-1.5 fix) |
| fear | reuse | the `feared` flee state from Scroll of Fear (existing) |
| **freeze** | reuse-as-theme | applies `stunned` (loses its turn), themed as cold; a chance on hit. Reads differently from the hammer because it rides a fast/AoE weapon. |
| **haste** | reuse | positive `weapon.speed_mod` (+20). No new code — phase 1 added `speed_mod`. |
| **cleave + status** | new combo | the "unleashed" rule: a Tier-5 cleave also applies its status (burn/freeze/fear) to **each** cleaved target, and lifesteal heals off each. Extends the existing cleave loop. |
| **enrage** | **new** | a `enraged` monster state: for its duration it attacks the nearest creature — **other monsters or the player** — reusing the Orc-style targeting. Chance on hit, timed. |
| **anti-incorporeal** | **new** | a new `incorporeal` marker on wraith + poltergeist; Fulgurite deals **×1.5** damage to them (rounded). |
| **instakill (void)** | **new** | a % chance to remove a monster outright with **no corpse/Slain body and no dropped loot** (the void swallows it). Guard rails in §8. |
| **poison (Basilisk)** | **new** | a lingering `poisoned` DoT modelled on `burning` — the venom keeps eating after the blow. |

Default tunables for the new/parametric traits (all revisited in playtest):
freeze chance ~25% / 1 turn; enrage chance ~20% / ~6 turns; Fulgurite ×1.5 vs incorporeal;
Windfang `speed_mod +20`; Void instakill 10%; Basilisk poison ~3 turns / ~2 dmg per turn.

### 6. Deep-floor weapon economy

Phase 1's single "magical when present" rule for floors 8+ is **replaced**:

- **Floors 1–7:** ordinary tier (phase 1, unchanged).
- **Floors 8–15 — up to *two* weapons (this band breaks the one-per-floor cap):**
  - a **non-magical slot**: *enhanced Steel only* — never base +0 this deep. Normally
    +1/+2, occasionally +3. Its present-chance **decays each floor to 0 at floor 15**.
    The **+3 (masterwork) chance itself climbs with depth** — a deeper corpse was a better
    adventurer. (Extends the phase-1 enhancement roll; scroll enchant stays uncapped.)
  - a **magical slot**: the rare magical roll (§7).
- **Floors 16–20:** the magical slot only (0 or 1 weapon).

**The scaling path is the enchant economy, not fresh drops.** Weapons persist and enchant,
so the hero descends *with* their weapon and grows it via `krav` (Scroll of Enchant Weapon,
uncapped). To keep that path alive deep, **`krav`/`dwen` stay reliably available on floors
8–20** (may even be biased slightly deeper, since that is when carried gear most needs to
scale). This — not a guaranteed weapon drop — is what keeps a run Warden-viable; magical
*weapons* stay a rare treasure. (A pity-net forcing a weapon after a drought was considered
and **deferred** — revisit after playtest.)

Fiction: shallow floors are thick with the weapons of the many who died there; deep
floors hold few, but the few are masterwork or magical.

### 7. Magical rarity, uniqueness, and persistence

**Rarity (starting values — all tunable).** One magical slot per floor (8–20) at a rare,
depth-declining present-chance; if it fires, the tier is a depth crossover (Tier-4 share
high shallow → low deep, Tier-5 the reverse):

| Floors | Magical present | Tier-5 share (of that) |
|---|---|---|
| 8–11 | 18% | 20% |
| 12–15 | 15% | 40% |
| 16–20 | 12% | 65% |

Combined with the enhanced-Steel slot (70% at floor 8, −10%/floor, 0 at floor 15), this
yields roughly **~2.8 enhanced-Steel and ~1.9 magical finds per run, a Tier-5 in ~55% of
runs, and ~12% of runs no magical at all** — "rare, maybe none," as intended. (Floor 20 is
the Warden arena; if the boss floor places no loot, the magical slot runs 16–19.)

**Absolute uniqueness — a draw *without replacement*, across the whole game.** A magical
weapon is generated **at most once per game**. The instant it is placed into the world it
is **spent from the pool forever** — whether or not the player picks it up (it persists in
place, so a second copy must never generate). The flat per-floor chance is unchanged, but
as the pool shrinks the odds a drop is a *specific* remaining weapon rise. This makes
**dying a tactic**: stash a weapon you don't want, dive again, and the narrowed pool fishes
toward the one you do. A **new game** (Kodex wipe, fresh Stone) resets the whole roster.

**Persistence — magicals are world objects; non-magicals are ephemeral.** Non-magical drops
still evaporate on each life's re-deal. **Magical weapons stay exactly where they lie** — on
the ground or on a corpse — across every life. This needs new persistent
save state, the **magical-weapon ledger**: each magical is *in-pool*, *lying at
`(floor, x, y, +n)`*, or *carried*. Each life, floor generation **replays the ledger**
(re-placing lying weapons at their saved spots) and only introduces *new, in-pool* weapons
via the rare slot. Pickup/drop moves a weapon between *carried* and a world location; dying
moves *carried* onto the corpse. Over many lives the dungeon becomes salted with the
artifacts of the player's past selves — thematically core.

**Invariant note.** The ledger and collected-set are *power earned by doing* (like corpses
and the victory-keep), **not knowledge** — the Kodex still never changes what generates, so
the bit-identical proof holds. All generation draws from the world RNG in a fixed order.

**The specific weapon** chosen within a tier comes from the **findable, still-in-pool**
weapons — excluding the two mini-boss weapons and anything already generated this game.

### 8. Mini-boss weapons and the void guard rails

**Windfang** (T4, floor-8 boss) and **Scimitar of the Void** (T5, floor-15 boss) are
excluded from the found pool entirely — obtainable only by defeating the matching
mini-boss. Because the mini-bosses are a separate task, this phase:

- adds both weapons to `WEAPONS` with their stats and sprites,
- excludes them from `roll_floor_weapon`'s findable pool,
- leaves a documented drop-hook for the mini-boss task to call,
- keeps them reachable via the **CTRL+12 weapon-bench cheat** so they can be playtested now.

The floor-8 boss should be **wind/speed-themed to match Windfang** (a swift blinker or an
aerial wraith-kin — "the gear matches the killer"); a note for the mini-boss task.

**Void instakill guard rails** (correctness, not just balance):
- **All bosses immune** — the Warden (else you skip the victory) and both mini-bosses.
- **Gift-carrying monsters immune** — the once-per-game gift item must never be voided.
- On a successful void: the monster is removed with **no Slain body, no drop, no loot** —
  a real cost that balances the power (voiding a loaded monster forfeits its haul).
- The 10% roll draws from the world RNG (bit-identical preserved). Starts at 10%,
  tunable down in playtest.

### 9. Renames, sprites, and Kodex

- **Key reuse:** `rapier` → Razor Sharp Rapier (still crit, retuned 4–6); `brand` → Flame
  Brand (retuned 4–8); `kris` → Vampiric Kris (now Tier 5, gains cleave, 4–7). Ten new
  keys for the rest. Old saves/corpses referencing `rapier`/`brand`/`kris` stay valid.
- **Sprites:** ten new `_weapon_sprite` branches (dagger, mace, flail, scythe, greataxe,
  scimitar, and the themed swords/axe), tinted to their element.
- **Kodex:** each new weapon and the three new mechanics (enrage, anti-incorporeal, void)
  want Kodex facts. Vampiric Kris's cleave gets an in-fiction justification: a blade so
  light, balanced and impossibly keen that a single draw carries clean through into the
  next body — and drinks from each.
- **The collector's reward.** Picking up every *findable* magical weapon (the 11) is a
  flagged achievement — a Kodex line and a stat: *"You have drawn every blade the deep still
  holds."* Completing all **13** (once the two boss weapons exist) earns the **second gold
  star**.
- **The homage.** Every respawn greets the hero with a pop-up — *"You wake, again, and the
  deep is patient."* — mirrored by a Kodex entry. A nod to Planescape: Torment's Mortuary,
  and a small anchor for the game's death-as-progression soul.

### 10. Optional polish — flat-damage display

Flat-damage weapons (Windfang 5–5, Void 7–7) work with no code change (`randint(5,5)`),
but `desc()` would render "5-5 dmg". A one-line special-case rendering "5 dmg" when
`lo == hi` is a nice-to-have.

## Surfaces touched

- **`items.py`** — thirteen magical weapons (3 retuned keys + 10 new); the tier-5 constant;
  `roll_floor_weapon` reworked into the two-slot deep economy (enhanced-steel slot with
  depth-decay + climbing +3; magical slot with declining presence + tier crossover;
  boss-locked exclusion); optional `desc()` flat-damage polish.
- **`monsters.py`** — `incorporeal` marker on wraith + poltergeist; the `enraged` state
  and its targeting; a `poisoned` DoT tick (modelled on `burning`).
- **`world.py`** — trait resolution for the new/extended effects: freeze (apply `stunned`),
  enrage, anti-incorporeal damage multiplier, cleave-applies-status, the void instakill
  (with boss/gift immunity and no-loot removal), poison. **Magical drops persist** — a
  ground-dropped magical is written to the ledger, not evaporated on the re-deal; pickup
  removes it from the ledger.
- **`dungeon.py`** — the two-slot deep economy (enhanced-Steel + magical); **ledger replay**
  at generation (re-place lying magicals at their saved spots) and only new-from-pool via
  the rare slot.
- **`sprites.py`** — ten new weapon sprites.
- **`codex.py`** — the **magical-weapon ledger** and collected-set (persistent save state,
  with save-format migration defaulting them empty); Kodex facts for new weapons/mechanics,
  the collector's achievement, and the respawn homage line; confirm the tier tie-break holds
  at tier 5.
- **`game.py` / `render.py`** — the respawn pop-up (*"You wake, again, and the deep is
  patient."*).
- **`items.py`** (loot weighting) — keep `krav`/`dwen` reliably available (slightly biased
  deeper) so the enchant scaling path holds on floors 8–20.
- **`cheats.py` / weapon bench** — expose the thirteen magical weapons (incl. the two
  boss-locked) for CTRL+12 testing.
- **`tests.py`** — roster shape and bands; two-slot deep economy; steel decay to 0 at
  floor 15; +3-climbs-with-depth; magical presence decline + tier crossover; boss-locked
  exclusion from the found pool; tier-5 corpse tie-break; each new mechanic (freeze,
  enrage, anti-incorporeal, void with immunities); flat-damage weapons; the bit-identical
  invariant with the new generation.

## Testing considerations

- **Determinism / bit-identical:** all new generation and the void roll must draw from the
  world RNG in a fixed order, independent of the Kodex. This is the load-bearing existing
  `TestKnowledgeIsNotPower` proof.
- **Boss/gift immunity to void** must be covered directly (Warden, mini-boss stand-in,
  gift-carrier) — these are correctness guards, not just balance.
- **Save compatibility:** new keys are additive; the three reused keys keep working, so
  existing corpses/saves load unchanged. The ledger/collected-set default empty on old saves.
- **No-cap enchant** already renders arbitrary `+n` (phase 1) — new weapons inherit it.
- **Ledger persistence:** a magical left on the ground (or a corpse) is still at the same
  spot after a simulated new life; a non-magical drop is gone. A magical generated in one
  life never re-generates later in the same game; a **new game** resets it.
- **Enchant availability:** `krav` reliably appears on deep floors (a sanity check on the
  scaling path).
- **The collector's achievement** fires exactly when all findable magicals have been held.

## Open tunables (safe to settle in playtest)

- Magical present-chance and T4/T5 crossover — starting values in §7 (18/15/12%;
  T5 share 20/40/65%).
- Enhanced-Steel slot: 70% at floor 8, −10%/floor to 0 at 15 (starting); the +3
  chance-by-depth curve.
- The deferred **pity net** (guaranteed weapon after a drought) — revisit post-playtest.
- Void instakill 10% → lower if it evaporates too many deep elites.
- Freeze chance/duration; enrage chance/duration; Fulgurite's ×1.5 vs incorporeal;
  Windfang's +20 speed.
- Basilisk's poison DoT: turns and damage per turn.
- Every damage band in §3.
