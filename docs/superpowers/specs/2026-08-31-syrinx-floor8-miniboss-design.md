# Syrinx — Floor 8 Mini-Boss — Design

**Date:** 2026-08-31
**Status:** Approved for planning
**Predecessors:** Deep magical weapon roster (Windfang/Void Scimitar reserved, merged
2026-07-20); Magical Armour Economy Plan C (`shade`/`nightcloak` reserved, merged 2026-07-24,
explicitly deferring "boss-drop wiring" to this task).

## Goal

Add the first of the two depth-milestone mini-bosses (floors 8 and 15) that sit between the
early roster and the floor-20 Warden. This spec covers **floor 8 only** — floor 15 (the
Void Scimitar boss) is a separate follow-up brainstorm/spec, not designed here.

## Context: what already exists (do not rebuild)

- `items.WEAPONS["windfang"]` (T4, "so light it quickens you", `speed_mod=20`) and
  `items.WEAPONS["void_scimitar"]` (T5, "a chance to unmake what it strikes") already exist
  and are excluded from `FINDABLE_MAGICAL` — reachable only via a mini-boss or the CTRL+12
  cheat.
- `items.ARMOURS["shade"]` (Shademail, T4, "the stone parts for you — for a while") and
  `items.ARMOURS["nightcloak"]` (T5, "the dark keeps you until you break it") already exist
  and are excluded from `FINDABLE_MAGICAL_ARMOUR`, with an explicit comment marking them
  boss-reserved. The Magical Armour Economy (Plan C) spec explicitly deferred their boss-drop
  wiring to "a future mini-boss task" — this spec is that task, for the floor-8 half.
- `world.BOSS_KEYS = {"warden"}` carries the comment *"the mini-boss task adds its keys
  here"* — the exact intended extension point for void-immunity.
- `codex.py`'s `magical_collector` Kodex fact already anticipates two mini-bosses: *"a
  second [gold star] waits for the day you also wrest the two blades the deep's guardians
  still keep."* The armour-collector facts do **not** have an equivalent second-star variant,
  and per the Plan C spec, the collection star is over the *findable* set only — it does not
  depend on boss drops. No change needed there.
- `world.py`'s `_ai_beholder` is the existing precedent for a telegraphed, two-beat
  commit-then-vulnerable monster pattern (gaze → freeze → armed ray → recharge).
- `_populate_boss` in `dungeon.py` is the existing precedent for a boss arena room with
  pillars, including the "never let the boss's own tile get walled in" safety check.
- `monsters.damage_multiplier(monster_key, source)` + `FIRE_SOURCES` is the existing
  elemental-weakness mechanism (currently used by `golem`: 2× from fire, 0.25× from
  physical).
- `Monster._step_toward` / `_step_away` are the existing movement primitives every monster's
  AI already builds on.

## Scope

**In scope:**
1. A new monster, **Syrinx**, and her AI (hide/telegraph/emerge/hunt/blow/stun/retreat loop).
2. A dedicated floor-8 arena room with six pillars.
3. Wiring her death to drop both Windfang and Shademail.
4. Void-immunity (`BOSS_KEYS`) and exclusion from normal floor spawns.
5. Fire vulnerability and immunity to other status effects.

**Out of scope (tracked separately):**
- The floor-15 / Void Scimitar / Nightcloak mini-boss — its own future spec.
- Exact balance numbers (HP, push distance, chip damage, hidden-turn cap, fire multiplier
  value) — tuned during implementation/playtesting, consistent with how the rest of the
  game's balance constants are handled (see `[[balance-tunables-deliberately-untested]]`).
- Whether her arena also spawns ambient regular monsters/chests — decided **no** for this
  version (a clean 1-on-1 room), explicitly revisitable after playtesting.

## Identity & theme

Syrinx is drawn from the Pan/Syrinx myth: a corporeal reed-nymph, not a god or spirit. She's
deliberately unassuming rather than conventionally frightening — nothing about her invites
the "boss" read on sight. Wind and sound are her whole nature; nothing supernatural is
required to justify either her attack or her fragility. In place of the myth's reeds (which
don't exist as terrain in this game), her other escape is hiding inside solid stone — giving
both reserved reward items a shared origin in the same story rather than being two arbitrarily
paired drops:

- **Windfang** — her lightness/hollowness. A blade forged from understanding something that
  weighs almost nothing is correspondingly quick.
- **Shademail** — her stone-hiding escape. Armour that lets you do what she did.

Both item names stay as they are; the mythological reference stays oblique, matching how the
rest of the roster is named (Fadecloak, Nightcloak, Robe of Hades — evocative, not literal).

## Arena

A dedicated room on floor 8, selected the same way as the Warden's arena (biggest room that
isn't the entrance/gate room). Six pillars, scattered through the room rather than
corner-only like the Warden's four. The pillars do three jobs at once:
- Her hiding spots (enter/exit).
- The surface her emergence telegraph appears on.
- Line-of-sight cover the player can use against her blow.

No extra regular monsters or chests spawn in this room for this version — an ambient monster
showing up mid-telegraph would muddy a timing-read mistake with plain bad luck, which cuts
against the skill test rather than adding to it. Revisit after playtesting if the room feels
too empty.

## The encounter loop

1. **Hidden.** She occupies a pillar and is off the grid entirely — not present in
   `level.monsters` for targeting/collision purposes, so nothing (player attacks, void
   effects, area effects) can reach her.
2. **Forced emergence.** She cannot hide indefinitely — a turn budget caps how long she stays
   hidden before she's forced to begin the emerge sequence regardless of anything else. This
   is the guard against a permanent-turtle stalemate.
3. **Telegraph.** One turn before emerging, a visual glow/rustle marks the *specific* pillar
   she's about to emerge from. This is a real, deterministic mechanical fact (not merely a
   visual flourish) — an unmet player and one who's fought her before face identical odds;
   the difference is purely whether they recognize what the glow means.
4. **Emerge.** She appears at the telegraphed pillar, now targetable, and moves at the
   player's own speed. She **never** initiates a melee attack — she has no offense besides
   the blow described below, so catching her is always safe, never a trade.
5. **Hunt.** While emerged and not yet blown, she actively seeks a line of sight on the
   player (mirroring the Warden's own alignment-seeking behavior) rather than passively
   waiting to get lucky.
6. **Blow.** Once she has a clear, aligned line to the player (`world.line_clear`, same gate
   as the Warden's `spit`), she fires — a gust that's mostly knockback/reposition with a
   small amount of real chip damage. The danger is attritional (stalling costs you over a
   fight, rather than any single blow being dangerous on its own), consistent with her being
   brittle rather than hard-hitting. If a pillar blocks the line, the blow simply doesn't
   fire that turn (matching the Warden's "the bolt shatters on a pillar" pattern).
7. **Stunned.** Immediately after blowing, she is fully vulnerable for one turn — the
   guaranteed punish window, structurally identical to the beholder's gaze → freeze → ray
   two-beat pattern.
8. **Retreat.** Once the stun turn ends, she moves toward the *nearest* pillar, excluding the
   one she just emerged from, using the existing `_step_toward` primitive. If the player's
   position blocks her path to that pillar, she re-targets to whichever of the remaining
   pillars minimizes her exposure — a per-turn re-evaluation among the six candidates, not
   full pathfinding. The exact heuristic (e.g. "the candidate whose straight-line path doesn't
   pass through or adjacent to the player's current tile") is an implementation choice, tuned
   like the other soft numbers in this spec — the requirement is that she reacts to being
   blocked rather than committing to one pillar regardless.
9. **Re-hide.** On reaching a pillar she enters it, goes off-grid again, and the hidden-turn
   budget resets. Back to step 1.

## Combat properties

- **Never melee-attacks.** Her only offense is the blow in step 6. Being adjacent to her is
  always purely advantageous for the player.
- **Brittle.** Low HP — roughly what a strong weapon kills in about 6 solid hits (exact
  number tuned during implementation, in the neighborhood of the toughest normal monsters'
  3-5 hit band, but a bit above it).
- **Fire-vulnerable.** Add a `syrinx` case to `monsters.damage_multiplier`, keyed against
  `FIRE_SOURCES` — a fire-trait weapon, a fire potion/scroll, or a fire glyph all deal bonus
  damage, the same mechanism already used for `golem`'s fire weakness (2.0×, to start, matching
  golem's existing value for consistency; revisit if it plays wrong).
- **Immune to all other area/status effects** (poison, freeze, fear, and similar) — a new
  `_status_immune(m)`-style predicate in `world.py`, modeled directly on the existing
  `_void_immune(m)`, checked at each status-application site (poison, freeze, fear). This does
  **not** cover physical damage or her own blow/knockback — those aren't "effects" in this
  sense, they resolve normally.
- **Void-immune.** Add her key to `BOSS_KEYS` so the Void Scimitar/banish scroll can't skip
  the fight, same as the Warden.

## Rewards

On death, she drops both **Windfang** and **Shademail** — see Identity & Theme above for why
both come from the same kill rather than being split across two encounters. No changes needed
to the Kodex collector facts (see Context).

## Technical wiring (for the implementation plan to work out in detail, not fully specified here)

- New monster key (`syrinx`), excluded from normal floor spawn tables like the Warden.
- New AI state beyond what `Monster.intent` alone covers — likely several instance flags in
  the spirit of the beholder's `ray_armed`/`recharge` (e.g. hidden/hidden-turn-counter,
  current pillar, telegraphed-next-pillar, blown-this-cycle) — exact field shape is an
  implementation decision.
- A new arena-population function on floor 8, adapted from `_populate_boss` — critically,
  unlike the Warden's, **this one must not clear the stairs**; floor 8 continues past this
  fight.
- **Serialization risk, called out explicitly:** her hidden/telegraph state is new and must
  survive the existing suspend/resume system (`to_dict`/`from_dict`, `RUN_SAVE_VERSION`). This
  needs deliberate design at plan time — it's more integration surface than a typical new
  monster, not just a new AI file.

## Known open items, deliberately not resolved here

- Exact tuning numbers (HP, push distance, chip damage, hidden-turn cap, fire multiplier) —
  playtest-driven.
- Whether the arena should also carry ambient monsters/chests — currently no, revisit after
  playtesting.
- The floor-15 boss and its own weapon+armour pairing — separate spec.

## Testing

Consistent with the project's existing per-monster test depth (see `TestAutosave`,
`TestEveryDeathTeaches`, the weapon/boots/armour economy suites), the implementation plan
should cover:
- Blind-vs-omniscient bit-identical behavior for the whole encounter (the core project
  invariant — knowledge changes only what's rendered, never mechanics).
- Telegraph correctness: which pillar, one-turn timing.
- Hunt behavior: she seeks line-of-sight rather than waiting passively.
- Blow resolution: fires only with a clear aligned line; fizzles against a blocking pillar.
- Forced-emergence: cannot remain hidden past the turn cap.
- Retreat/re-route: targets nearest untried pillar; re-targets if the player blocks the path.
- Fire vulnerability via `damage_multiplier`; immunity to poison/freeze/fear via the new
  status-immunity predicate.
- Void-immunity via `BOSS_KEYS`.
- Reward drop (both Windfang and Shademail) on death.
- Exclusion from normal floor spawn/loot tables (extending the existing
  `test_gear_pool_has_no_weapons`-style assertions that already cover Windfang/Void to
  Shademail as well).
