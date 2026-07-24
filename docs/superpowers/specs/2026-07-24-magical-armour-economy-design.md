# Magical Armour Economy (Plan C) — Design

**Date:** 2026-07-24
**Status:** Approved for planning
**Predecessors:** Plan A (ordinary armour, merged @96a7f41), Plan B Phase 1 (magical roster,
merged @09f6f93) + Phase 2 (invisibility + wall-walk, merged 2026-07-24).

## Goal

Give magical armour the same deep economy the weapons and boots already have: the rare pieces
that drop **persist** where they lie across every death, and **collecting the full findable set**
across many lives earns a permanent gold star. Also retune the magical-armour drop rates so the
collection is a genuine multi-run haul.

This is the final leg of the whole gear-triad rebalance ([[rebalance-gear-triad]]).

## Context: what already exists (do not rebuild)

Plan B Phase 1 shipped the **uniqueness + rarity** half of the armour economy:

- `items.is_magical_armour(key)` — tier ≥ 4.
- `items.FINDABLE_MAGICAL_ARMOUR` (dict by tier) and `FINDABLE_MAGICAL_ARMOUR_KEYS` (the 12
  findable pieces: 7 T4 + 5 T5). Boss-reserved `nightcloak` and `shade` are **excluded**.
- `items.roll_floor_armour_magical(rng, depth, exclude)` — the per-floor magical slot (floors 8+),
  Kodex-free so blind/omniscient runs stay bit-identical.
- `codex.armour_generated` — the per-game uniqueness set.
- `codex.record_magical_armour_placed(key, depth, x, y)` — **currently records `armour_generated`
  only**; its docstring notes persistence/collection are "Plan C, not yet built."
- Generation wiring in `dungeon.py:640-647` places the magical slot and calls
  `record_magical_armour_placed`.

The reference implementation for everything below is the **boots economy** (Plan 3B), which is a
1:1 mirror of the weapon economy. Plan C mirrors boots again for armour, with one difference:
**armour ground entries carry a `bonus`** (like weapons, unlike boots), so a magical armour the
player has DWEN-enchanted survives death at its enchanted value.

## Scope

**In scope:**
1. Distribution retune — new one-per-floor / T5-first-dibs model with pulled-down rates, lifted
   into `config.py` constants.
2. Persistence — `armour_ground` ledger, replay each life, drop-to-ground on displacement.
3. Collection — `armour_collected` ledger, pickup wiring, all-12 gold star + collector Kodex fact.
4. Serialization + a tolerant load (no version bump — new keys default empty, like Phase 1).

**Out of scope (tracked separately):**
- Vendor rework (magical items at high gold) — [[vendor-rebalance-deferred]].
- Balance-watch tuning of individual piece stats (stonegolem +5/0, Robe/Blinding/Lifeweaver) —
  playtest-driven, not a plan.
- Boss-drop wiring for `nightcloak`/`shade` — future mini-boss task
  ([[add-minibosses-floors-8-15]]). The collection star is over the **findable** set only, so it
  does not depend on boss drops.

## 1. Distribution retune

### Model

Replace the current single-present-then-split roll with a **one-magical-piece-per-floor**,
**T5-first-dibs** model. Bands for T4 and T5 differ and overlap. On a floor at depth *d* ≥ 8:

1. Look up the T5 present chance `p5` for *d* (0 if *d* < 10 — T5 only starts at floor 10).
2. Look up the T4 present chance `p4` for *d*.
3. Roll T5 first: `rng.random() < p5` → place a T5 piece; done.
4. Only if T5 **missed**, roll T4: `rng.random() < p4` → place a T4 piece.
5. Otherwise the magical slot is empty.

The floor's overall drop probability is therefore:

> **P(any) = p5 + (1 − p5) · p4**

with outcomes partitioning as: T5 = `p5`, T4 = `(1 − p5)·p4`, nothing = `(1 − p5)·(1 − p4)`.

The two `rng.random()` draws happen in a fixed order and read only `(rng, depth)` — never the
Kodex — so determinism (`TestKnowledgeIsNotPower`) is preserved. The second draw is only consumed
when the first misses; the number of draws depends only on the T5 outcome, which is itself
Kodex-independent.

Uniqueness is unchanged: after picking a tier, draw from that tier's findable pool minus
`exclude` (= `armour_generated`); if the pool is exhausted, return None (no piece).

### Rates (final)

| Tier | Band | Present |
|------|------|---------|
| **T4** | 8–9   | **20%** |
|        | 10–11 | 12% |
|        | 12–15 | 10% |
|        | 16–20 | 6% |
| **T5** | 10–13 | 8% |
|        | 14–17 | 12% |
|        | 18–20 | 20% |

Floors 8–9 get the higher 20% T4 because they have no T5 backstop (T5 starts at floor 10); this
removes the early dead zone.

### Resulting per-floor probability

| Floor | p5 | p4 | P(any) |
|-------|----|----|--------|
| 8–9   | —   | 20% | **20.0%** |
| 10–11 | 8%  | 12% | **19.0%** |
| 12–13 | 8%  | 10% | **17.2%** |
| 14–15 | 12% | 10% | **20.8%** |
| 16–17 | 12% | 6%  | **17.3%** |
| 18–19 | 20% | 6%  | **24.8%** |

Floor 20 is the Warden's floor (`depth >= DEPTH_MAX` → `_populate_boss`, no magical slot rolled),
so the "18–20" band is effectively "18–19" for placement. Expected **≈ 2.4 magical armours per
full floors-8-to-19 run**, i.e. roughly **6 death-runs to complete the 12-piece set** — a genuine
long-haul grind (vs ~1.5/run as Phase 1 shipped, or ~7/run at the un-tuned rates).

### Config constants

Lift the six rates and the band boundaries out of the inline literals in
`items.roll_floor_armour_magical` into named `config.py` constants (so future tuning is a one-line
edit). Suggested shape — the plan may adjust names:

```python
# Magical-armour drop bands (Plan C). One magical piece per floor, T5 rolled first.
ARMOUR_MAGICAL_T4_BANDS = [(8, 9, 0.20), (10, 11, 0.12), (12, 15, 0.10), (16, 20, 0.06)]
ARMOUR_MAGICAL_T5_BANDS = [(10, 13, 0.08), (14, 17, 0.12), (18, 20, 0.20)]
```

`roll_floor_armour_magical` reads these; a band lookup returns 0.0 when depth is in no band.

## 2. Persistence

Mirror `boots_ground` / `magical_ground`.

**Codex state (`codex.py`):**
- New ledger `self.armour_ground = {}` — `key -> {"depth", "x", "y", "bonus"}`. (`armour_generated`
  already exists.)
- Add to `__init__`, `to_dict`, `from_dict` (tolerant: `data.get("armour_ground", {})`), and
  `reset` (new game clears it). These are **codex** save keys (per-game, alongside
  `armour_generated`), not part of the `RUN_SAVE_VERSION` suspend/resume save — the tolerant
  `data.get(...)` load means an older codex save simply reads back empty ledgers, no migration or
  version bump needed (exactly how Phase 1 added `armour_generated`).
- `record_magical_armour_placed(key, depth, x, y)` — extend to also write
  `self.armour_ground[key] = {"depth": depth, "x": x, "y": y, "bonus": 0}` (fresh generation is
  never masterworked). Keep appending to `armour_generated`.
- New `drop_magical_armour_to_ground(key, depth, x, y, bonus)` — mirror
  `drop_magical_to_ground`: records `armour_generated` (idempotent) and writes `armour_ground`
  **with the actual bonus**, so a DWEN-enchanted magical armour re-grounds at its enchanted value.

**Replay (`dungeon.py`):**
- `_generate` (dungeon.py:444-451): snapshot `persisted_armours = dict(codex.armour_ground)`
  **before** `_populate`, then `self._replay_magicals(persisted_armours)` after — exactly as
  weapons and boots are snapshot + replayed. `_replay_magicals` is already generalized
  (`bonus=loc.get("bonus", 0)`), so it re-places armour with its stored bonus with no change.

## 3. Collection

Mirror `boots_collected` / `magical_boot_picked_up` / `award_boots_collection`.

**Codex state (`codex.py`):**
- New ledger `self.armour_collected = []` — every magical armour ever picked up this game.
  Add to `__init__`, `to_dict`, `from_dict` (tolerant), `reset`.
- New stat `self.stats["magical_armours_collected_all"] = 0` (add to the stats init + its
  `from_dict` defaulting).
- New `magical_armour_picked_up(key)` — mirror `magical_boot_picked_up`:
  ```python
  def magical_armour_picked_up(self, key):
      from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
      self.armour_ground.pop(key, None)
      if key not in self.armour_generated:
          self.armour_generated.append(key)
      was_complete = FINDABLE_MAGICAL_ARMOUR_KEYS <= set(self.armour_collected)
      if key not in self.armour_collected:
          self.armour_collected.append(key)
      now_complete = FINDABLE_MAGICAL_ARMOUR_KEYS <= set(self.armour_collected)
      return now_complete and not was_complete
  ```
  A boss-reserved piece picked up (from a future boss drop) is added to `armour_collected`
  harmlessly; the `FINDABLE_... <= set(...)` superset check still governs the star, so boss pieces
  neither block nor are required for it.
- New `award_armour_collection()` — mirror `award_boots_collection`: set
  `stats["magical_armours_collected_all"] = 1`, grant the collector Kodex fact once, `save()`.

**Collector Kodex fact (`codex.py` FACTS table, near lines 86-96):**
Register `self.magical_armour_collector` as a `"self"` / `"secret"` fact. Placeholder wording
(user may reword — the boots/weapon lines were also placeholders):
```python
_f("self.magical_armour_collector", "self", "secret",
   "EVERY WARD THE DEEP STILL KEEPS",
   "You have worn every magical armour this dungeon will yield -- the whole rare roster, "
   "gathered by one hand across many deaths. A gold star of its own, for the back that has "
   "borne every ward the deep still keeps."),
```

**Wiring (`world.py`) — three sites, each mirroring the existing `is_magical_boot` branch:**
- **`_take` equip path (world.py:1327-1331):** add, after the boots branch:
  ```python
  if is_magical_armour(payload):
      if self.codex.magical_armour_picked_up(payload):
          self.codex.award_armour_collection()
          self.log("<placeholder collection line>", config.GOLD)
  ```
- **`cheat_equip_armour` (CTRL+34 bench):** add the same pickup/award branch the boots bench has
  (`cheat_equip_boots`, world.py:1423-1427), so the bench can complete the set.
- **`_put_back` (world.py:1599-1614):** compute `magical_armour = is_magical_armour(gear.key)`;
  add it to the container-exclusion guard so a displaced magical armour never goes into a
  chest/body (`not (magical or magical_boot or magical_armour)`); and add the drop-to-ground
  branch: `elif magical_armour: self.codex.drop_magical_armour_to_ground(gear.key, self.depth,
  p.x, p.y, getattr(gear, "bonus", 0))`.

## Determinism

The retuned `roll_floor_armour_magical` reads only `(rng, depth, exclude)`; `exclude` is
`armour_generated`, which is identical between a blind and an omniscient run of the same
game/seed (it tracks what was *placed*, not what was *seen*). All ledger writes
(`armour_ground`, `armour_collected`) are driven by placement and pickup, not by Kodex knowledge.
`TestKnowledgeIsNotPower` must stay green.

## Full lifecycle (acceptance narrative)

A rare magical armour rolls on a deep floor → placed as a floor drop + recorded in
`armour_ground` (bonus 0) and `armour_generated`. The player dies without grabbing it → next life,
`_replay_magicals` re-places it on the same tile. The player finally walks over it and equips it →
`magical_armour_picked_up` pops it from `armour_ground` and adds it to `armour_collected`. Later
the player swaps it off while looting a chest → `_put_back` sends it to **bare ground** (not the
chest) and re-grounds it via `drop_magical_armour_to_ground`. When all 12 findable pieces are in
`armour_collected`, the equip that completes the set fires `award_armour_collection` → gold star +
permanent collector Kodex fact.

## Testing approach (TDD, per task)

- **Distribution:** `roll_floor_armour_magical` returns None below floor 8; on floors 8–9 draws
  only T4; T5 possible only from floor 10; a floor whose T5 hit places a T5 and consumes no T4;
  respects `exclude` (no duplicate keys); returns None when a tier pool is exhausted; determinism
  spot-check (same rng+depth → same result regardless of a Kodex).
- **Persistence:** `record_magical_armour_placed` writes `armour_ground`; a persisted armour is
  re-placed by `_replay_magicals` on the matching floor and clears whatever the fresh deal put on
  its tile; a bonus round-trips (drop enchanted → re-ground → replay preserves bonus).
- **Collection:** picking up the last findable piece returns True once (and only once);
  `award_armour_collection` sets the stat and grants the fact idempotently; a boss piece in
  `armour_collected` neither completes nor blocks the star.
- **Serialization:** `armour_ground` + `armour_collected` round-trip through `to_dict`/`from_dict`;
  a pre-Plan-C save (no keys) loads with empty ledgers (no crash, no version bump).
- **Wiring:** `_put_back` routes a magical armour to bare ground, never a container; the `_take`
  equip path fires the award on the completing pickup.
- **Determinism:** `TestKnowledgeIsNotPower` stays green.

## Open items / notes

- Collector fact + collection log lines are **placeholders**; surface to the user for wording,
  same as the boots/weapon lines.
- The armour bench cheat is CTRL+34 (`cheat_equip_armour`); it needs the same pickup/award wiring
  as the boots bench so it can drive the collection to completion in testing.
