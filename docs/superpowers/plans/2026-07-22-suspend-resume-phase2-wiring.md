# Suspend/Resume — Phase 2: Save-File & Game-Loop Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Phase 1 serialization layer into the game: a nullable `run` block in the save file (autosaved every turn), **Continue** resumes it when present, and death / new-game / fresh-dungeon clear it — so quitting suspends the run and relaunching resumes it exactly, while permadeath is unchanged.

**Architecture:** The codex (the single JSON save) gains a `self.run` field: the serialized live run (`World.to_dict()`) or `None`. `World._autosave()` writes it after every player turn (folding map memory in first). `Game.continue_run()` rebuilds the world from a valid saved block (`World(codex, restore=...)`) or falls back to a fresh run. Death clears the block (permadeath intact); a new game or a fresh-dungeon victory-respawn clears it with the rest of the place-state. A `RUN_SAVE_VERSION` guard discards a stale/incompatible block rather than crashing.

**Tech Stack:** Python 3.13, `unittest`. Tests live in the single file `deathward/tests.py`.

## Global Constraints

- **Test command:** `py -3.13 -m deathward.tests` (NOT `python`/`py` — those resolve to 3.14, which lacks pygame). Single test: `py -3.13 -m deathward.tests <Class>.<method> -v`. Run from repo root.
- **Permadeath is unchanged.** Death still ends the run; the run block is cleared on death so the next **Continue** is a fresh run. The Kodex, corpses, and map memory persist exactly as today.
- **Determinism invariant untouched.** `TestKnowledgeIsNotPower` must stay green — the run save is per-run state, never read during generation.
- **Never crash on a stale/incompatible save.** A run block whose `version` != `config.RUN_SAVE_VERSION`, or that fails to deserialize, is discarded and **Continue** falls back to `new_run()`. Same treatment the existing `LAYOUT_VERSION` guard gives a stale map.
- **Backward compatible.** A pre-Phase-2 save (no `"run"` key) loads cleanly with `self.run = None`.
- **Map memory before serialize:** `World.to_dict()` does NOT store the `explored` grid (it is recalled from `codex.maps` on resume). The autosave MUST call `remember_map()` before serializing, or mid-floor exploration is lost on resume.
- Phase 1 (the serialization layer: `World.to_dict()` / `World(codex, restore=...)`, and the per-object `to_dict`/`from_dict`) is already merged on `main` — this phase only wires it in. Do NOT modify the serialization layer.

## File Structure

- `deathward/config.py` — add `RUN_SAVE_VERSION`.
- `deathward/codex.py` — `self.run` field (init), the versioned run block in `_save_dict`/`_load_from`, and the clear in `new_dungeon` (`wipe` clears it for free via `__init__`).
- `deathward/world.py` — `World._autosave()` and its call at the end of `_end_player_turn`.
- `deathward/game.py` — `Game.continue_run()` (resume-or-fresh), the title-key wiring, the run-block stamp in `new_run`, the clear in `on_death`, and the refresh in `quit`.
- `deathward/tests.py` — round-trip of the run block through save/load + version/layout guards (Task 1); autosave writes the block each turn and skips when dead (Task 2); Continue resumes vs. falls back, death clears, new_run stamps (Task 3).

---

## Task 1: Run-block storage in the codex + version guard

**Files:**
- Modify: `deathward/config.py` (after `LAYOUT_VERSION`, line ~41)
- Modify: `deathward/codex.py` (`__init__` ~681, `_load_from` ~732, `_save_dict` ~757, `new_dungeon` ~856)
- Test: `deathward/tests.py` (new `TestRunBlockPersistence`)

**Interfaces:**
- Consumes: `config.RUN_SAVE_VERSION`.
- Produces:
  - `Codex.run` — attribute: the suspended run dict (a `World.to_dict()` payload) or `None`.
  - `_save_dict()` emits `"run"` as `None` or `{"version": RUN_SAVE_VERSION, "world": <run dict>}`.
  - `_load_from(data)` sets `self.run` to the inner `"world"` payload only when the wrapper's `version` matches; otherwise `None`. A `LAYOUT_VERSION` mismatch (which already calls `new_dungeon()`) also clears it.
  - `new_dungeon()` sets `self.run = None`; `wipe()` clears it via `__init__`.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestRunBlockPersistence(unittest.TestCase):
    """The suspended-run block travels in the save, guarded by its own version,
    and is cleared by a fresh dungeon or a new game."""

    def test_run_block_round_trips_through_save_dict(self):
        c = FakeSave()
        c.run = {"depth": 3, "player": {"x": 5}}
        d = c._save_dict()
        self.assertEqual(d["run"], {"version": config.RUN_SAVE_VERSION,
                                    "world": {"depth": 3, "player": {"x": 5}}})
        c2 = FakeSave()
        c2._load_from(d)
        self.assertEqual(c2.run, {"depth": 3, "player": {"x": 5}})

    def test_none_run_block_round_trips_as_none(self):
        c = FakeSave()
        c.run = None
        c2 = FakeSave()
        c2._load_from(c._save_dict())
        self.assertIsNone(c2.run)

    def test_a_stale_version_run_block_is_discarded(self):
        c = FakeSave()
        data = c._save_dict()
        data["run"] = {"version": config.RUN_SAVE_VERSION + 1,
                       "world": {"depth": 9}}
        c._load_from(data)
        self.assertIsNone(c.run, "a run block from another build must not be trusted")

    def test_a_layout_mismatch_discards_the_run_block(self):
        c = FakeSave()
        data = c._save_dict()
        data["run"] = {"version": config.RUN_SAVE_VERSION, "world": {"depth": 4}}
        data["layout_version"] = config.LAYOUT_VERSION + 1
        c._load_from(data)
        self.assertIsNone(c.run, "a re-cut dungeon makes the old run meaningless")

    def test_an_old_save_without_a_run_key_loads_as_none(self):
        c = FakeSave()
        data = c._save_dict()
        del data["run"]
        c._load_from(data)
        self.assertIsNone(c.run)

    def test_new_dungeon_clears_the_run_block(self):
        c = FakeSave()
        c.run = {"depth": 2}
        c.new_dungeon()
        self.assertIsNone(c.run)

    def test_a_fresh_codex_has_no_run_block(self):
        self.assertIsNone(FakeSave().run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestRunBlockPersistence -v`
Expected: FAIL — `AttributeError: 'FakeSave' object has no attribute 'run'` (and/or `KeyError: 'run'`).

- [ ] **Step 3: Write minimal implementation**

In `deathward/config.py`, after `LAYOUT_VERSION = 4` (line ~41):

```python
# Bumped when the run-save (suspend/resume) serialization shape changes. A save
# whose run block carries a different version is discarded -- Continue falls back
# to a fresh run -- exactly as LAYOUT_VERSION discards a stale map.
RUN_SAVE_VERSION = 1
```

In `deathward/codex.py` `__init__`, right after `self.layout_migrated = False` (line ~681):

```python
        self.run = None          # the suspended live run (World.to_dict()), or None
```

In `_load_from`, after `self.boots_collected = data.get("boots_collected", [])` (line ~732) and BEFORE the `layout_version` check (line ~736):

```python
        # The suspended run, if the save carries one whose shape this build still
        # understands. A version bump (the serialization changed) discards it, as
        # does a layout mismatch below (new_dungeon nulls it) -- a run over a
        # dungeon that no longer exists is meaningless.
        raw_run = data.get("run")
        if raw_run and raw_run.get("version") == config.RUN_SAVE_VERSION:
            self.run = raw_run.get("world")
        else:
            self.run = None
```

In `_save_dict`, add to the returned dict (e.g. after the `"boots_collected"` entry):

```python
            "run": (None if self.run is None
                    else {"version": config.RUN_SAVE_VERSION, "world": self.run}),
```

In `new_dungeon`, after `self.gift_item = None` (line ~856):

```python
        self.run = None          # a new stone: any suspended run is meaningless now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestRunBlockPersistence -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green. (If a pre-existing test asserts the exact key set of `_save_dict()`, update it to include `"run"` — search for `_save_dict` in tests.py.)

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/codex.py deathward/tests.py
git commit -m "Codex carries a versioned run block: suspend/resume storage + guard"
```

---

## Task 2: Autosave the run every turn

**Files:**
- Modify: `deathward/world.py` (`_end_player_turn` ~1938; add `_autosave`)
- Test: `deathward/tests.py` (new `TestAutosave`)

**Interfaces:**
- Consumes: `World.to_dict()` (Phase 1), `World.remember_map()` (world.py:296), `self.codex.run` (Task 1), `codex.save()`.
- Produces:
  - `World._autosave()` — folds map memory in, sets `self.codex.run = self.to_dict()`, and calls `self.codex.save()`. No-op when `self.dead`.
  - `_end_player_turn()` calls `self._autosave()` after the turn resolves.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestAutosave(unittest.TestCase):
    """Every resolved player turn writes the live run into the codex, so any exit
    resumes here -- but a turn that ends in death does not (permadeath clears it)."""

    def test_a_resolved_turn_writes_the_run_block(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w._end_player_turn()
        self.assertIsNotNone(codex.run, "a completed turn must autosave the run")
        self.assertEqual(codex.run["depth"], w.depth)
        self.assertEqual(codex.run["player"]["x"], w.player.x)
        self.assertEqual(codex.run["player"]["y"], w.player.y)

    def test_autosave_folds_in_the_map_memory(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        w._end_player_turn()
        self.assertIn(str(w.depth), codex.maps,
                      "the explored map must be remembered before serializing")

    def test_a_dead_players_turn_does_not_autosave(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w.dead = True
        w._end_player_turn()
        self.assertIsNone(codex.run, "death clears the run; a dead turn must not rewrite it")

    def test_autosave_is_skipped_if_death_lands_during_the_world_turn(self):
        # _autosave guards on self.dead itself, so a death during advance() (a
        # monster's killing blow) still leaves the run block untouched.
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w.dead = True
        w._autosave()
        self.assertIsNone(codex.run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestAutosave -v`
Expected: FAIL — `test_a_resolved_turn_writes_the_run_block` fails (`codex.run` stays `None`), and `_autosave` doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `deathward/world.py`, add the `_autosave` method (e.g. right after `_end_player_turn`):

```python
    def _autosave(self):
        """Persist the live run every turn, so quitting and relaunching resumes
        exactly here. Map memory is folded in first: to_dict does not store the
        explored grid -- it is recalled from the codex on resume."""
        if self.dead:
            return
        self.remember_map()
        self.codex.run = self.to_dict()
        self.codex.save()
```

Then call it at the end of `_end_player_turn`. The current tail is:

```python
        self.advance()
        self.level.compute_fov(p.x, p.y)
        return True
```

Change it to:

```python
        self.advance()
        self.level.compute_fov(p.x, p.y)
        self._autosave()
        return True
```

(The early `if self.dead: return True` before `advance()` already means a turn the player did not survive to the end of does not reach `_autosave`; the guard inside `_autosave` covers a death that lands during `advance()`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestAutosave -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green. (Many existing tests advance turns and will now exercise `_autosave` → `to_dict` each turn against a `FakeSave` whose `save()` is a no-op; that is intended coverage. `TestKnowledgeIsNotPower` must remain green.)

- [ ] **Step 6: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Autosave the live run after every resolved player turn"
```

---

## Task 3: Game lifecycle — Continue resumes, death clears, new run stamps

**Files:**
- Modify: `deathward/game.py` (`new_run` ~107, `on_death` ~153, title handler ~263, `quit` ~593; add `continue_run`)
- Test: `deathward/tests.py` (new `TestSuspendResumeLifecycle`)

**Interfaces:**
- Consumes: `Codex.run` (Task 1), `World.to_dict()` / `World(codex, restore=...)` (Phase 1), `game.PLAY`.
- Produces:
  - `Game.continue_run()` — resumes from `self.codex.run` when present and valid (`World(codex, restore=run)`, `state = PLAY`); on a malformed block discards it and falls back to `new_run()`; with no block, `new_run()`.
  - `new_run()` stamps `self.codex.run = self.world.to_dict()` before saving, so a just-started run is immediately resumable.
  - `on_death()` sets `self.codex.run = None` before saving (permadeath: next Continue is fresh).
  - `quit()` refreshes `self.codex.run` from the live world (when alive) before saving.
  - The title **Continue** key calls `continue_run()` instead of `new_run()`.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestSuspendResumeLifecycle(unittest.TestCase):
    """Quitting suspends; Continue resumes exactly; death clears the run so the
    next Continue is a fresh descent."""

    def _game(self):
        from .game import Game
        g = Game.__new__(Game)          # bypass pygame init
        g.codex = FakeSave()
        g.victory_gear = None
        g.banner = None
        g.banner_age = 0.0
        g.world = None
        g.state = None
        return g

    def test_continue_resumes_a_suspended_run_at_its_depth(self):
        from .game import PLAY
        g = self._game()
        w = World(g.codex, seed=4)
        w.new_level(3)                  # descend; a fresh run would be depth 1
        g.codex.run = w.to_dict()
        g.world = None                  # simulate a relaunch
        g.continue_run()
        self.assertEqual(g.world.depth, 3, "Continue must resume the suspended floor")
        self.assertEqual(g.state, PLAY)

    def test_continue_with_no_suspended_run_starts_fresh_and_stamps_a_block(self):
        g = self._game()
        g.codex.run = None
        g.continue_run()
        self.assertEqual(g.world.depth, 1, "no suspended run -> a fresh descent")
        self.assertIsNotNone(g.codex.run, "a fresh run is immediately resumable")

    def test_a_malformed_run_block_falls_back_to_a_fresh_run_without_crashing(self):
        g = self._game()
        g.codex.run = {"garbage": True}
        g.continue_run()                # must not raise
        self.assertIsNotNone(g.world)
        self.assertEqual(g.world.depth, 1)

    def test_death_clears_the_run_block(self):
        g = self._game()
        g.world = World(g.codex, seed=4)
        g.world.death_cause = "rat"
        g.codex.run = g.world.to_dict()
        g.reveal_t = 0.0
        g.on_death()
        self.assertIsNone(g.codex.run, "permadeath: the suspended run is cleared")

    def test_new_run_stamps_a_resumable_block(self):
        g = self._game()
        g.new_run()
        self.assertIsNotNone(g.codex.run)
        self.assertEqual(g.codex.run["depth"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSuspendResumeLifecycle -v`
Expected: FAIL — `Game` has no attribute `continue_run`; `new_run`/`on_death` don't touch `codex.run` yet.

- [ ] **Step 3: Write minimal implementation**

In `deathward/game.py`, add `continue_run` (place it just after `new_run`):

```python
    def continue_run(self):
        """CONTINUE from the title. Resume the suspended run if one was saved and is
        still valid; otherwise begin a fresh run. Either way the Kodex, the stone,
        the map memory and the dead carry over, exactly as before.

        The deserialize is wrapped defensively: a save from a broken/interrupted
        write must never crash the title screen -- it falls back to a fresh run."""
        run = self.codex.run
        if run is not None:
            try:
                self.world = World(self.codex, restore=run)
            except Exception:
                self.world = None
            if self.world is not None:
                self.victory_gear = None
                self.banner = None
                self.banner_age = 0.0
                self.state = PLAY
                return
            self.codex.run = None        # malformed -- discard and start fresh
        self.new_run()
```

In `new_run`, immediately before `self.codex.save()` (line ~143):

```python
        self.codex.run = self.world.to_dict()   # immediately resumable
```

In `on_death`, immediately before `self.codex.save()` (line ~160):

```python
        self.codex.run = None            # permadeath: the next Continue is a fresh run
```

In the title-screen key handler, change the **Continue** line (line ~263) from:

```python
                self.new_run()               # CONTINUE: keeps the kodex and the dead
```
to:
```python
                self.continue_run()          # CONTINUE: resume the suspended run, else fresh
```

In `quit`, refresh the block from the live world so an explicit quit captures the latest state. Change (line ~593):

```python
    def quit(self):
        if self.world is not None:
            self.world.remember_map()
        self.codex.save()
        pygame.quit()
        sys.exit(0)
```
to:
```python
    def quit(self):
        if self.world is not None:
            self.world.remember_map()
            if not self.world.dead:
                self.codex.run = self.world.to_dict()
        self.codex.save()
        pygame.quit()
        sys.exit(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSuspendResumeLifecycle -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green, including `TestKnowledgeIsNotPower`.

- [ ] **Step 6: Commit**

```bash
git add deathward/game.py deathward/tests.py
git commit -m "Continue resumes the suspended run; death clears it; new run stamps it"
```

---

## Self-Review Notes (for the executor)

- **The whole feature is now live.** After Task 3, quitting (window close, title Escape, or the OS killing the process — the last completed turn is on disk) and relaunching → **Continue** returns to the exact floor/position/gear/dungeon-state. A death clears the block; **New Game** wipes it; a fresh-dungeon victory-respawn (`new_dungeon`) clears it.
- **Manual playtest owed by the user** (per project convention): descend a couple of floors, kill some monsters, take some loot, quit, relaunch, Continue — confirm you resume exactly; then die and confirm Continue starts fresh; then New Game and confirm a clean slate.
- **Autosave cadence is the known tunable** (spec's "Open tunables"): every turn serializes all visited floors (the `seen` grids dominate the size). If held-key auto-walk hitches on deep runs, debounce `_autosave` to every-N-turns — an implementation change, not a design change. Flag it after playtest.
- **Do not touch the Phase 1 serialization layer** — this phase is wiring only.
