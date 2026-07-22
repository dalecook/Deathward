# Suspend / Resume — A Mid-Run Save

**Date:** 2026-07-22
**Status:** design, pending review
**Scope:** make quitting the game *suspend* the current run and relaunching *resume* it — same
position, gear, and dungeon state — while leaving permadeath untouched. Explicit **New Game**
still wipes; **death** is still permadeath.

## Problem

Today the dungeon *stone* (layout) persists across restarts (it's derived from `codex.world_seed`,
a per-game value), but a **run** is "the living, re-dealt": each `new_run` builds a fresh `World`
with a new `Player()` at the floor-1 entrance, a fresh per-run RNG, and an empty `levels` cache.
Only the Kodex (facts, corpses, magical ledgers, explored map) carries over. So quitting mid-run
and relaunching → **Continue** → a brand-new run. The player loses their position, gear, and the
floors' current state.

## Goals

- **Quitting suspends; relaunching resumes.** Return to the exact depth, position, HP, gear, pack,
  and dungeon state (monsters you killed stay dead, loot you took stays gone, tiles you explored
  stay revealed).
- **Death is still permadeath** — the run ends, the suspended save is cleared, the Kodex/corpses
  persist, and **Continue** starts a fresh run.
- **New Game still wipes everything**, suspended save included.
- **Robust:** autosave every turn, so any exit (title, window close, crash, power-loss) resumes
  cleanly. Never crash on a stale/incompatible save — fall back to a new run.

## Non-goals

- No change to permadeath, the Kodex, the stone/layout, or generation. The run save is *additive*.
- No multiple save slots, no manual save/load UI. One suspended run, autosaved.
- No change to the title's **Continue** wording (it silently resumes if a run is suspended, else
  starts a new run — as today).

## Design

### 1. Storage — a nullable `run` block in the existing save

The game already persists to one JSON file (`config.SAVE_PATH`) via `codex.save()` /
`_save_dict()` / `load()`. Add a top-level **`"run"`** key: the serialized live run when one is
suspended-alive, or absent/`null` otherwise. It travels in the same file, written by the same
`save()`.

### 2. What the `run` block holds

Everything the Kodex does **not** already hold — the *live, dynamic* run state:

- **World:** the run seed, the current `depth`, `tick`, the per-run counters (`vendor_pct`,
  `run_kills`, …), and the **run RNG state** (`self.rng.getstate()`, converted to a JSON-safe
  list) so floors descended into *after* resuming still deal deterministically.
- **Player:** depth, position, HP/max-HP, energy, gold, equipped gear (keys + weapon bonus +
  the armour `enchants` dict), the pack (inventory stacks), every status/effect timer
  (poison, frozen, invisible, levitate, haste, berserk, heroism, might, weak, stoneskin,
  resist, vigor, sanctuary, phoenix, confused, stuck, feared, blade_coat, …), the Slipstep
  hit-counter, and the victory-gift flag.
- **Each visited floor** (per depth): the **dynamic** state only —
  - **monsters:** `key, x, y, hp, max_hp, awake, intent, energy` + every status timer
    (`stunned, burning, poisoned, recharge, feared, confused, enraged, disguised, hidden`).
  - **drops:** `x, y, kind, payload, bonus, gift`.
  - **chests:** `x, y, loot`.
  - **sprung traps:** which traps have fired (`key, x, y, sprung`).
  - **explored tiles** (so the map you drew stays drawn this run).
  - the **vendor** if one is on the floor, and the **hoard** marker.
- **NOT stored** (regenerated / already persisted): the **grid/rooms/entrance/stairs** (regenerate
  deterministically from the stone via `layout_seed`); **corpses** (already in `codex.corpses`,
  restored the normal way); currently-visible tiles (recomputed from position on load).

Implementation: `to_dict()` / `from_dict()` on `World`, `Player`, `Level`, `Monster`, and the
small `Drop` / `Chest` / `Trap` records.

### 3. Autosave — every turn

After each player turn resolves (`_end_player_turn`), write the `run` block (`codex.save()` with
the freshly-serialized run). The run state is small (a handful of floors, each with a few
monsters/drops), so a per-turn JSON write is cheap. If held-key auto-walk ever hitches, debounce
to every-N-turns — an implementation tunable, not a design change.

### 4. Resume — reconstruct the World from the `run` block

On **Continue**, if a valid suspended `run` block exists (present and the player is alive), rebuild
the `World` from it instead of `new_run()`:

- `World(codex, seed=run.seed)`; restore the run RNG via `setstate`.
- Restore the `Player` from its dict.
- For each saved floor: build the `Level` for that depth so its **grid regenerates from the stone**
  (`layout_seed`), then **skip the fresh `_populate`** and instead load the saved monsters / drops
  / chests / sprung-traps / explored (corpse comes from `codex.corpses` as usual). A `Level.restore`
  path, parallel to its normal generate path.
- Set the current `level`/`depth`, recompute FOV, enter `PLAY`.

If the `run` block is absent, or fails the version guard, **Continue** falls back to `new_run()`.

### 5. Lifecycle — when the `run` block is written / cleared

- **Every player turn (alive):** written (autosave).
- **Death (`on_death`):** cleared to `null`, then saved — so the next **Continue** is a fresh run.
- **New Game (`wipe`):** cleared with everything else.
- **Victory / fresh-dungeon respawn:** cleared (a new stone means the old run is meaningless).

### 6. Version guard

Add a `RUN_SAVE_VERSION` in `config`. Stamp it into the `run` block. On load, if it (or the
existing `LAYOUT_VERSION`) doesn't match — i.e. a build changed the generator or the run-save
shape — **discard the `run` block** (treat as no suspended run) rather than restore a stale or
malformed state. The Kodex load already does this for the map; the run block gets the same
treatment.

## Surfaces touched

- **`player.py`** — `Player.to_dict()` / `from_dict()` (all mutable state + gear + pack).
- **`monsters.py`** — `Monster.to_dict()` / `from_dict()` (key + all dynamic fields).
- **`dungeon.py`** — `Level.to_dict()` / `from_dict()` and a **restore** construction path (grid
  from the stone, dynamic state from the save); `Drop` / `Chest` / `Trap` (de)serialization.
- **`world.py`** — `World.to_dict()` / `from_dict()` (seed, depth, tick, counters, RNG state,
  player, levels); the resume path.
- **`codex.py`** — the `run` block in `_save_dict` / `_load_from`; helpers to set/clear it; the
  version guard.
- **`game.py`** — autosave hook after each turn; **Continue** resumes when a live run exists;
  `on_death` clears the run; New Game / victory clear it.
- **`config.py`** — `RUN_SAVE_VERSION`.
- **`tests.py`** — round-trip serialization (a World → dict → World is identical), resume
  reconstructs position/gear/floor-state, death clears the run, version-mismatch falls back,
  autosave writes each turn.

## Testing considerations

- **Round-trip fidelity:** serialize a mid-run `World` (player mid-floor, some monsters dead, some
  loot taken, buffs active) → dict → new `World`; assert player state, each floor's monsters/drops/
  chests/traps/explored, and the RNG state all match.
- **Layout regenerates, dynamic state overlays:** a restored floor has the same grid as a
  freshly-generated one (same stone) but the saved monsters/drops, not fresh ones.
- **RNG continuity:** after resume, descending into a *new* floor generates the same contents it
  would have without the suspend (RNG state preserved).
- **Lifecycle:** death nulls the run block; New Game wipes it; a stale-version block is discarded.
- **Determinism invariant unaffected:** the run save is per-run state, not Kodex — the blind-vs-
  omniscient `TestKnowledgeIsNotPower` is untouched.

## Phased implementation (decompose in writing-plans)

1. **Serialization layer:** `to_dict`/`from_dict` for `Player`, `Monster`, the level records, and
   `Level` (incl. the restore-construction path) + `World`. Pure, round-trip-tested in isolation —
   no behavior change yet.
2. **Save/resume wiring + lifecycle:** the `run` block in the save, autosave each turn, the
   **Continue**-resume path, clearing on death/new-game/victory, and the version guard.

## Open tunables (settle in playtest)

- Autosave cadence (every turn vs. debounced during auto-walk).
- Whether to also store currently-visible tiles vs. recompute on load (recompute is simpler).
