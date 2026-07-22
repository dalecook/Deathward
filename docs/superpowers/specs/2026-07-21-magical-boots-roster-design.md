# Magical Boots — Roster Rework & Movement Identities

**Date:** 2026-07-21
**Status:** design, pending review
**Scope:** rework the magical boots (tiers 4–5, floors 8+) from the interim relocation into a
proper roster where every boot is a distinct *identity*, not a bare speed number — mirroring
what the magical weapon roster did. Covers the roster and its mechanics; the **deep economy**
(rarity, one-per-game uniqueness, death-persistence) is a deliberate follow-up, as it was for
weapons. Builds on the merged boots ordinary-tier + distribution work ([[boots-rebalance]]).

## Problem

The magical boots today are the five exotic boots *relocated* to tiers 4/5 with their stats
untouched (Plan 1's interim move). Two of them — Swift (+25) and Windwalkers (+40) — are bare
speed numbers with no identity, the exact "boots are just a speed stat" problem the whole boots
rebalance set out to fix. The tier split is provisional and the roster is thin. Boots should
answer *how you move*; the magical tier is where distinct movement powers should live.

## Goals

- Every magical boot has a **distinct identity** across five archetypes: **speed**, **movement-
  trick**, **stealth**, **warding**, **control** (plus one reactive-escape and one dodge).
- A coherent **tier axis** for non-combat boots: **T4 = a bounded movement trick** (a limited,
  situational tool) → **T5 = that power unbound** (reshapes how you play the floor). Several
  identities form clean bounded→unbound pairs.
- Reuse existing engine plumbing wherever possible (blink, monster stun, the wake/aggro system,
  the trap trigger, the freeze status).
- Preserve determinism: any generation/combat RNG draws from the world RNG only (never the
  Kodex); blind-vs-omniscient bit-identical runs stay green.

## Non-goals

- The **deep economy** — rarity gating, one-per-game uniqueness, and death-persistence of magical
  boots (the equivalent of the weapons' later plans). Deferred to a follow-up. This pass leaves
  magical boots dropping via the existing `gear_pool` path on floors 8+.
- Ordinary boots, weapons, armour — untouched.
- Mini-boss reward boots — out of scope (see [[add-minibosses-floors-8-15]] for that track).

## Design

### Tier philosophy

Weapons split T4 *focused* (single target) → T5 *unleashed* (borrows cleave, hits a crowd).
Boots deal no damage, so the axis is **T4 = a bounded movement trick → T5 = the same kind of
power, unbound**. Bare speed is an accepted identity (it buys back armour's speed tax), laddered
across tiers.

### The roster (12 boots: 5 T5 + 7 T4)

**T5 — unbound freedom**

| key (proposed) | Name | Spd | Identity |
|---|---|---|---|
| `wind` | Windwalkers | +40 | pure speed |
| `featherfall` | Featherfall | +25 | triggers **no** trap — weight *and* magical (glyph/gas) |
| `whisperstep` | Whisperstep | +10 | monsters wake only within **2 tiles** (+ room-alert) |
| `thor` | Thor's Boots | +10 | each strike knocks back **all** adjacent enemies |
| `slipstep` | Slipstep | +10 | every **4th** hit taken: blink 2 random tiles + stun the attacker 1 turn |

**T4 — bounded trick / warding / control**

| key (proposed) | Name | Spd | Def | Identity |
|---|---|---|---|---|
| `swift` | Sandals of Mercury | +25 | — | pure speed |
| `blink` | Boots of Blinking | +15 | — | leap 3 tiles (SHIFT+dir) |
| `soft` | Padded Soles | +10 | — | monsters wake only within **half** range (~4 tiles) (+ room-alert) |
| `ironshod` | Ironshod Boots | +5 | — | knockback on the primary target |
| `emberstride` | Emberstride | 0 | +2 | immune to **freezing** |
| `rimewalkers` | Rimewalkers | 0 | +2 | immune to **fire/burn damage** |
| `phantom` | Phantom Boots | 0 | — | **25%** chance to dodge any incoming hit |

**Bounded→unbound pairs:** speed (Mercury→Windwalkers), stealth (Padded Soles→Whisperstep),
control (Ironshod→Thor's). Standalone: Blinking, Featherfall, Slipstep (movement-tricks),
Emberstride/Rimewalkers (warding), Phantom (dodge).

### Mechanics

**1. Speed — Windwalkers, Sandals of Mercury.** No new mechanic; `boots.speed` already flows
through `player.speed`. Ladder: Leather +10 (ordinary) → Mercury +25 (T4) → Windwalkers +40 (T5).

**2. Blink — Boots of Blinking.** Existing (`player_blink`, SHIFT+dir leap of 3). Unchanged.

**3. Featherfall — no traps.** The wearer triggers **no** trap of any kind. Today's softsole only
skips weight traps (`PRESSURE = {dart, spike, alarm}`, traps.py); Featherfall additionally skips
the non-weight ones (`glyph` the fire rune, `gas`) — you float above the rune and the cloud. It
deliberately outclasses the old soles.

**4. Stealth — Padded Soles (T4) & Whisperstep (T5).** The novel subsystem. A monster wakes when
it is in the player's FOV **and** within a wake radius — today a fixed 9 tiles
(`monster_can_see_player`, world.py:314). A stealth boot shrinks that radius: **Padded Soles →
half (~4)**, **Whisperstep → 2**. You will see a sleeping monster across a lit room and can path
around it. Gated by a **room-alert**:
- **Region model (Option A):** the player is always either inside a Room (`Room.contains`,
  dungeon.py) or, if in no room, in "the corridors" — the whole corridor network treated as a
  single region. (Segmenting corridors into discrete stretches was rejected as fiddly.)
- **Alert latch:** on entering a region the alert is off. While the player is in a region, if any
  monster *in that region* is awake, the region becomes **alerted** and stays alerted until the
  player **leaves the region** (a Room↔corridor or Room↔Room transition resets it). While alerted,
  the stealth radius reverts to the normal 9 — the alarm is raised, everyone's looking. This makes
  pre-awake monsters (orcs, noise-woken monsters) naturally blow your cover in that room.

**5. Control — Ironshod (T4) & Thor's Boots (T5).** Ironshod's kick already knocks back the
**primary** target one tile (`_knockback`, world.py:574) — with an axe it shoves only the one in
your swing direction, not the cleaved crowd. **Thor's Boots** unbind it: **every adjacent enemy**
is knocked back on each strike, so it finally pairs with cleave (hit and scatter the whole crowd).
Reuses `_knockback` per adjacent monster.

**6. Slipstep — reactive escape.** A counter of hits *taken*; on **every 4th hit**, the wearer
**blinks 2 random tiles** away (reusing `blink_tile_near`; if boxed in, no blink) and **stuns the
attacker for 1 turn** (`m.stunned = 1`). Deterministic counter, styled after the hammer's stun
cadence (config `HAMMER_STUN_CADENCE`) so no RNG cost and legible timing. The random leap is a
wildcard (can drop you somewhere better or worse); the stun buys a beat against the crowd.

**7. Warding — Emberstride (immune freezing) & Rimewalkers (immune fire damage).** The player's
only immobilizing status is `player.frozen` (the beholder's gaze; player.py:76) — **Emberstride**
negates it (never frozen). **Rimewalkers** negates **fire/burn damage** to the player (brand,
pyroclast, fire glyph, fire trap, burn DoT do nothing). Both carry **+2 def**. (These are the two
honest *non-movement* boots — a deliberate resistance archetype, extending the defense-on-boots
line the ordinary mail/plate opened.)

**8. Phantom — dodge.** A **25%** chance to negate an incoming hit entirely (rolls in the
player-damage path; draws the world RNG). Distinct from the warders (which negate a *specific*
element) — Phantom sometimes sidesteps *anything*.

### Data model

`Boots` (items.py) currently carries `key, name, tier, speed, trait, note, defense`. The reworked
identities need a few parameters the single `trait` string can't hold: the **stealth wake radius**
(4 vs 2), the **Phantom dodge chance** (0.25), and the **Slipstep cadence/leap** (every 4th, 2
tiles). These become either fields on `Boots` or config constants keyed by the identity — the
implementation plan settles the exact shape. Parameterless identities (featherfall, thor,
emberstride, rimewalkers, ironshod) stay a `trait` flag.

### Retiring / redefining the interim boots

- `swift` → **Sandals of Mercury** (rename only; still +25 pure speed, T4).
- `soft` → **Padded Soles** redefined: **loses** the pressure-plate skip; becomes the T4 stealth
  boot (half wake radius). The plate-skip niche is gone (Featherfall covers all-trap immunity).
- `blink`, `ironshod`, `wind` → kept as-is (Boots of Blinking, Ironshod, Windwalkers).
- New keys/boots: `featherfall`, `whisperstep`, `thor`, `slipstep`, `emberstride`, `rimewalkers`,
  `phantom` — each needs a sprite in `_boots_sprite`.

## Surfaces touched

- **`items.py`** — the `BOOTS` table (renames, redefinition, seven new boots); `Boots` gains the
  identity parameters.
- **`world.py`** — `monster_can_see_player` takes the stealth wake radius + room-alert; the region
  model + alert latch; Thor's knock-back-all in the attack resolution; Slipstep's on-hit
  blink+stun in the player-damage path; Phantom's dodge roll; Emberstride/Rimewalkers immunity
  hooks.
- **`traps.py`** — Featherfall skips all traps (extend the softsole check to every trap).
- **`dungeon.py`** — a `region_of(x, y)` helper (which Room, else "corridor") for the stealth
  alert.
- **`player.py`** — freeze/burn immunity checks; the Slipstep hit-counter state.
- **`config.py`** — constants for the stealth radii, dodge chance, Slipstep cadence/leap.
- **`sprites.py`** — a distinct sprite per new boot in `_boots_sprite`.
- **`tests.py`** — per-mechanic tests; determinism/bit-identical must stay green.

## Phased implementation (decompose in writing-plans)

This is too large for one plan. Proposed phases, each shippable and testable on its own:

1. **Roster + reused-mechanic boots:** the `BOOTS` table (renames/redefinition/new entries), the
   parameter-carrying data model, sprites, and the identities that reuse existing systems —
   Featherfall (traps), Thor's (knock-back-all), Slipstep (blink+stun counter),
   Emberstride/Rimewalkers (freeze/burn immunity), Phantom (dodge).
2. **The stealth subsystem:** the region model, `region_of`, the wake-radius reduction, and the
   room-alert latch (Padded Soles + Whisperstep). The novel, highest-risk piece — its own plan.
3. **Deep economy (later):** rarity, one-per-game uniqueness, death-persistence — mirroring the
   weapons' economy plans.

## Open tunables (settle in playtest)

- All speeds (esp. Thor's/Whisperstep/Slipstep +10; the T4 warders/Phantom at 0).
- Stealth radii (Padded Soles ~4 = half of 9; Whisperstep 2).
- Phantom dodge chance (25%).
- Slipstep cadence (every 4th hit), leap distance (2), random vs. away-from-attacker, keep-stun.
- Whether Featherfall should spare magical glyphs (texture: "even floating won't save you") vs.
  all traps.
