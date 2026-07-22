# Magical Boots — Deep Economy (Rarity, Uniqueness, Persistence, Collection)

**Date:** 2026-07-22
**Status:** design, pending review
**Scope:** the final magical-boots increment (Phase 3 of the roster rework). It gives the 12
magical boots the same deep economy the magical *weapons* have — a rare generation slot,
one-per-game uniqueness, death-persistence, and a collector's gold star — by mirroring the
weapon system 1:1 with a parallel boots ledger. Follows the merged Phase 1 (roster) and Phase 2
(stealth). See [[boots-rebalance]]; the weapon economy is the template ([[deep-magical-weapon-roster]]).

## Problem

Magical boots are an *interim* economy: all 12 drop through the generic `gear_pool` at flat,
common odds from floor 8 on. No rarity curve, no one-per-game uniqueness, no death-persistence,
no collection reward. A magical boot is a frequent swap, not the find of a floor — the opposite
of what the magical weapons became.

## Goals

- **Rarity:** a magical boot is a scarce, deliberate find — pulled out of the generic pool into a
  rare, one-per-floor generation slot (floors 8+), like the weapons.
- **Uniqueness:** each of the 12 magical boots exists **exactly once per game**.
- **Persistence:** a magical boot survives death — it lies where it fell and is replayed every
  life until picked up.
- **Collection:** gathering all 12 earns a permanent **gold star**, mirroring the weapon award.
- **Preserve determinism:** generation draws only from `(rng, depth, run-history)`, never the
  Kodex — blind and omniscient runs of a seed stay bit-identical (`TestKnowledgeIsNotPower`).

## Non-goals

- No change to the *ordinary* boots economy (found-only, `roll_floor_boots`, unchanged), to
  weapons, or to armour.
- No change to the magical boots' *stats or mechanics* (Phases 1–2). Only how they are
  distributed, persisted, and rewarded.
- **No mini-boss-reserved boots.** The weapons reserved 2 (Windfang, Void Scimitar) for
  mini-bosses; boots have none — all 12 are findable and the collector target is all 12. (If a
  future mini-boss track reserves some boots, that adjusts the findable set then.)

## Design (1:1 mirror of the weapon economy)

### 1. The findable set and the source of truth

- `FINDABLE_MAGICAL_BOOTS = {4: [7 tier-4 keys], 5: [5 tier-5 keys]}` and
  `FINDABLE_MAGICAL_BOOT_KEYS` (all 12) — the boots parallel of `FINDABLE_MAGICAL`.
  - T4: `swift`, `soft`, `blink`, `ironshod`, `emberstride`, `rimewalkers`, `phantom`.
  - T5: `wind`, `featherfall`, `thor`, `slipstep`, `whisperstep`.
- `is_magical_boot(key)` → `key in BOOTS and BOOTS[key].tier >= 4` — the single source of truth,
  parallel to `is_magical` (which stays weapon-only).

### 2. Rarity — a rare generation slot; leave the generic pool

- Magical boots are **removed from `gear_pool`** (drop the `tier >= 4` boots branch). `gear_pool`
  becomes armour-only (ordinary boots already left it in the distribution work). So magical boots
  no longer come from generic floor/chest/body loot or the vendor.
- New `roll_floor_boots_magical(rng, depth, exclude=())` — the rare slot, floors 8–20, at most one
  per floor:
  - **present-chance:** 14% (depth ≤ 11), 12% (≤ 15), 10% (16–20).
  - **T5-share:** 20% (≤ 11), 40% (≤ 15), 65% (16–20).
  - `exclude` (the already-generated set) filters the chosen tier's pool; if that tier is
    exhausted, nothing drops. Draws only from `(rng, depth, exclude)` — never the Kodex.
  - Returns `(boot_key, 0)` or `None`. (Boots carry no enhancement/bonus, so the bonus is always
    0 — kept in the tuple only to match the placement plumbing's shape.)

### 3. Placement + persistence in `dungeon.py`

Mirroring the weapon path:
- At floor generation, after the ordinary-boots placement, call
  `roll_floor_boots_magical(rng, d, exclude=codex.boots_generated)`; place the result as a
  `Drop(..., "gear", key)`; if placed, `codex.record_magical_boot_placed(key, d, x, y)` (records
  uniqueness + puts it on the persistence ledger).
- **Replay:** each life, the magical boots recorded in `codex.boots_ground` are re-placed where
  they fell (mirroring `_replay_magicals` for weapons) — snapshotted before the floor re-populates,
  so a boot generated *this* life isn't double-counted.

### 4. The boots ledger (`codex.py`), parallel to the weapon ledger

- `boots_generated` (list) — keys that have entered the world (uniqueness exclude set).
- `boots_ground` (dict `key -> {depth, x, y}`) — magical boots lying on a floor (persistence).
- `boots_collected` (list) — keys the hero has picked up across all lives (the collection set).
- Methods parallel to the weapon ones:
  - `record_magical_boot_placed(key, depth, x, y)` — add to generated + ground.
  - `drop_magical_boot_to_ground(key, depth, x, y)` — the hero left one on the bare floor; it
    persists across lives.
  - `magical_boot_picked_up(key)` — mark collected, remove from ground; **return True the first
    time all 12 are collected** (triggers the award).
  - `award_boots_collection()` — set `stats["magical_boots_collected_all"] = 1` (the gold star)
    and write the permanent Kodex fact.
- **Save/load + reset:** all three ledgers and the stat flag round-trip in `to_dict`/`from_dict`
  and reset with the rest on a new game.

### 5. Pickup / drop wiring (`world.py`)

- When a magical boot is **picked up / equipped** (the gear-take path, and the boots-bench cheat
  `cheat_equip_boots`), call `codex.magical_boot_picked_up(key)`; on a `True` return, fire the
  award (log + fx + the Kodex fact), mirroring how `magical_picked_up`/`award_collection` fire for
  weapons.
- When the hero **displaces a magical boot onto the bare floor** (a swap), route it to
  `drop_magical_boot_to_ground` so it persists (never into a container's ephemeral loot list),
  mirroring the weapon `_put_back` rule.

### 6. The collector's Kodex fact + gold star

- A new permanent Kodex fact for "every magical boot the deep still holds is yours," awarded once
  all 12 are collected, with its own **gold star** alongside the weapon star(s). (The exact
  wording/flavour is the user's to set, as with the weapon award.)

## Surfaces touched

- **`items.py`** — `FINDABLE_MAGICAL_BOOTS`/`_KEYS`, `is_magical_boot`, `roll_floor_boots_magical`;
  remove magical boots from `gear_pool`.
- **`codex.py`** — the three boots ledgers + their methods, `award_boots_collection`, the Kodex
  fact, `stats["magical_boots_collected_all"]`, save/load + reset.
- **`dungeon.py`** — place the floor's magical boot at generation (exclude = `boots_generated`);
  replay `boots_ground` each life.
- **`world.py`** — pickup/equip fires `magical_boot_picked_up` (+ award); displaced magical boots
  route to `drop_magical_boot_to_ground`; the boots-bench cheat marks collected.
- **`tests.py`** — uniqueness (never re-generates a taken key), persistence (survives death, replays,
  reclaims), collection award (fires once at all-12), rarity gating (floor 8+, not in `gear_pool`),
  and the bit-identical invariant.

## Testing considerations

- **Determinism / bit-identical:** `roll_floor_boots_magical` draws from `(rng, depth, exclude)`
  where `exclude` is run-history (`boots_generated`), never the Kodex — so blind and omniscient
  runs stay identical. `TestKnowledgeIsNotPower` must stay green.
- **Uniqueness:** across a game, each magical boot generates at most once; an exhausted tier drops
  nothing.
- **Persistence:** a magical boot left on the floor is present again next life at the same spot;
  reclaiming it removes it from `boots_ground` and never duplicates it.
- **Collection:** the award fires exactly once, the first time all 12 are collected; it is
  idempotent and survives save/load.
- **Not in the generic pool:** `gear_pool(depth)` contains no magical boot at any depth; the vendor
  and generic loot never surface one.

## Phased implementation (decompose in writing-plans)

Mirrors how the weapons were built. Proposed phases, each shippable and testable:

1. **Rarity + uniqueness + placement:** `is_magical_boot`, `FINDABLE_MAGICAL_BOOTS`,
   `roll_floor_boots_magical`, remove magical boots from `gear_pool`, the `boots_generated` ledger,
   and generation placement in `dungeon.py`.
2. **Persistence + collection award:** `boots_ground`/`boots_collected`, replay each life, the
   pickup/drop wiring, `award_boots_collection` + the gold star + Kodex fact, save/load.

## Open tunables (settle in playtest)

- present-chance (14/12/10) and T5-share (20/40/65).
- The collector Kodex-fact wording and the gold-star presentation.
