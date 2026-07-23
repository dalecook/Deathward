# Magical Armour — Roster & Survival Identities (Plan B)

**Date:** 2026-07-23
**Status:** design, pending review
**Scope:** the magical armour tier (tiers 4–5, floors 8+) — the second of the armour passes,
after the merged ordinary tier ([[rebalance-gear-triad]] Plan A). Fourteen pieces, each a
distinct *survival identity*, mirroring what the magical weapon and boots rosters did. Covers
the roster and its mechanics; the **deep economy** (rarity, one-per-game uniqueness,
death-persistence, a collection gold star) is a deliberate follow-up (Plan C). Also folds in
one small coupled fix: the Firestorm scroll no longer burns its own caster.

## Problem

Armour has no magical tier at all — the ordinary rework deliberately left the four-rung
leather/mail/plate ladder as the whole armour slot, and **graduated two ideas out** (thorns,
wraithsilk) with the promise they return here. Weapons and boots each answer their slot's
question with a rich exotic roster; armour's question — *what you survive* — has none. The
magical tier is where distinct survival powers should live.

## Goals

- Every magical armour is a **distinct survival identity**, not a bigger defense number,
  across families: **retaliation** (hurt what hits you), **ethereal** (beat the
  armour-ignoring threat and the geometry), **stealth/escape** (invisibility), **bulwark**
  (cap a big hit), **sustain** (regen), and **last-stand** (refuse death).
- A **T4 = bounded → T5 = unbound** axis. The retaliation family shows it cleanest: T4 afflicts
  *the one attacker*; the T5 capstones (Blinding Light, Robe of Hades) blast *the whole ring*.
- **Re-home thorns + wraithsilk** as promised, and give wraithsilk its own light-and-fast
  identity so it's a real "wear it for this fight" tradeoff, not dead weight.
- **Reuse existing engine plumbing**: monster status (`burning`/`poisoned`/`stunned`), the
  intent/windup clear, `player.invisible`, the phoenix death-refusal, the VORN fire effect.
- Preserve **determinism**: reactive triggers are deterministic counters (no RNG); any combat
  RNG (Robe damage) draws the world RNG only, never the Kodex. Blind-vs-omniscient stays green.

## Non-goals

- The **deep economy** — rarity gating, one-per-game uniqueness, death-persistence, a
  collection gold star (Plan C). This pass places magical armour through the same
  generation-placed path the ordinary tier uses, ungated by rarity.
- **Ordinary armour, weapons, boots** — untouched (except the shared per-instance bonus model,
  already merged, which magical armour inherits: found unenhanced, DWEN-enchantable).
- **Building the mini-bosses.** Two pieces (Shademail, Nightcloak) are *reserved* for the
  floor-8 and floor-15 mini-bosses exactly as Windfang and the Void Scimitar are: defined and
  cheat-reachable now, excluded from floor drops, their actual drop wired by the future
  mini-boss task ([[add-minibosses-floors-8-15]]).
- **Poltergeists.** Wraithsilk's immunity covers the whole armour-ignoring class; poltergeists
  don't exist yet, so today it only bites wraiths — the poltergeist half activates when that
  monster is added ([[wraithsilk-poltergeist-defense]]).

## Design

### Tier philosophy

Weapons: T4 focused → T5 unleashed (cleave). Boots: T4 bounded trick → T5 unbound. Armour
answers *what you survive*, so **T4 = a bounded/conditional protection → T5 = a survival power
that reshapes the fight**. Bare stat is an accepted identity (Stone Golem's Chest is armour's
Windwalkers — high defense with the speed tax removed, "because it's magical").

### The roster (14 pieces: 7 found-T4, 5 found-T5, 2 boss-reserved)

Defense is modest and mostly costs a little speed (it *is* armour); the mechanic is the draw.
The two lightest pieces are cloth and *give* speed. Names are working names, the user's to
punch up.

**T4 — bounded survival (found, floors 8+)**

| key | Name | Def | Spd | Effect |
|---|---|---|---|---|
| `thorn` | Thorned Cuirass | +3 | −5 | returns **2** damage to anything that hits you |
| `silk` | Wraithsilk | +2 | **+10** | a wraith/poltergeist's touch cannot find you; light, fast, ethereal |
| `venom` | Venomweave | +3 | −5 | an attacker is **poisoned 3 turns** (lower dmg); 3-turn recharge |
| `cinder` | Cinderplate | +3 | −5 | an attacker **burns 2 turns** (higher dmg); 3-turn recharge |
| `glacial` | Glacial Mail | +3 | −5 | an attacker is **frozen** (as Winter's Edge); 3-turn recharge |
| `fade` | Fadecloak | +2 | **+10** | every **4th** hit taken: you vanish 2 turns, all aggroed monsters de-aggro, and any that had not yet attacked lose their windups |
| `lifeweave` | Lifeweaver | +3 | −5 | knits **2 hp** every turn while worn |

**T5 — unbound survival (found, floors 8+)**

| key | Name | Def | Spd | Effect |
|---|---|---|---|---|
| `bastion` | Bastion | +4 | −15 | **caps any single hit** at N damage — the boss/big-hit answer to flat def's swarm answer |
| `lastbreath` | Last Breath | +4 | −10 | **refuses one killing blow per life** — you survive at 1 hp **and are untouchable for 1 turn** (a mob can't finish you the same beat), then it is spent |
| `blinding` | Blinding Light | +3 | −5 | on struck: **stun every monster** within 2 tiles and wipe their windups; 4-turn recharge |
| `stonegolem` | Stone Golem's Chest | +5 | 0 | **pure defense, no speed cost** — the tank pick, for players who want no gimmick |
| `hades` | Robe of Hades | +3 | 0 | on struck: a **firestorm that spares you**, burning everything near you; 4-turn recharge |

**Mini-boss reserved (excluded from floor drops; cheat-only until the boss task wires them)**

| key | Name | Tier | Def | Spd | Effect | Boss |
|---|---|---|---|---|---|---|
| `shade` | Shademail | T4 | +3 | 0 | **walk into walls** (never off the map); 5-turn cooldown after you leave the stone | floor 8 |
| `nightcloak` | Nightcloak | T5 | +3 | 0 | **permanent invisibility** — breaks when you attack, re-cloaks a set number of turns after your last strike | floor 15 |

### Mechanics

Only ONE armour is worn at a time, so all the reactive state (recharge timers, hit counters,
the last-stand spent-flag, the wall-walk cooldown) is a small amount of **player** state, not
per-piece — one cooldown, one counter — serialized with the run (save is `RUN_SAVE_VERSION=2`).

**1. Retaliation — Thorned Cuirass, Venomweave, Cinderplate, Glacial Mail (T4).** All hook the
existing on-struck point in `monster_attacks_player` (world.py:774; thorns already fires there
at ~816). Thorns returns raw damage (existing, unchanged). The three elementals apply the
*same monster statuses weapons already apply* (player_attack, world.py:555–568): `m.burning`
(Cinderplate, higher on-hit dmg), `m.poisoned` (Venomweave, 3 turns, lower dmg), `m.stunned =
FREEZE_TURNS` (Glacial Mail, the Winter's Edge freeze). Those statuses already tick and
serialize (monsters.py:186–240, `_MONSTER_STATE`). The one new part is a **3-turn recharge**:
the elemental fires only when the wearer's armour cooldown is 0, then resets — a deterministic
counter, no RNG.

**2. Retaliation capstones — Blinding Light, Robe of Hades (T5).** Same on-struck trigger, same
recharge model but **4 turns**, and they hit *everything near you* instead of the one attacker:
- **Blinding Light** — every monster within 2 tiles gets `m.stunned` and its telegraphed
  `intent` cleared (the same intent-clear knockback uses), so a whole wind-up crowd is
  interrupted. No RNG.
- **Robe of Hades** — a firestorm centred on the wearer that **spares the wearer**. See §7.

**3. Ethereal immunity — Wraithsilk (T4).** Re-homes the dormant `wraithsilk` trait
(monsters.py:603): the wraith/poltergeist "ignore armour" touch does nothing to the wearer.
Given its own identity here: **+2 def / +10 spd** — the only magical armour that *gives* speed
(wraith-cloth is light and fast), so it's an appealing light-and-mobile option whose real
value is the situational immunity.

**4. Bastion — the hit-cap (T5).** In the incoming-damage path (world.py:788, `dmg = max(0,
dmg - p.defense)`), also clamp the post-reduction hit to a **cap N**. Flat def thins a swarm;
the cap answers the single big hit (a brute, a boss). No RNG.

**5. Last Breath (T5).** Mirrors the **phoenix** death-refusal already in `kill_player`
(world.py:851–861, `p.phoenix`): once per life the fatal blow is refused and the wearer is left
at 1 hp **and untouchable for 1 turn** — reuse `p.sanctuary` (the Scroll of Sanctuary's
"nothing can lay a blow on you"), so a mob can't finish the job the same beat; a spent-flag on
the player marks it used until the next life. Distinct from the Phoenix potion (which is a
consumable, not a worn slot).

**6. Lifeweaver — regen (T4).** A passive heal-while-worn: **2 hp every turn**, ticked in the
per-turn advance (near `tick_effects`, player.py:188 / world.py). Distinct from the
Regeneration potion's timed burst — this is constant and permanent while worn.

**7. Robe of Hades + the Firestorm scroll fix.** The VORN scroll effect today (world.py:1655)
burns every visible monster **and the caster** (line 1670, `hurt_player(2–5, "glyph")`). That
self-burn is the "dumb" part. **Fix:** factor the fire into one routine — *burn everything in
range, spare the caster* — drop the `hurt_player` line, and keep everything else about the
scroll the same (still "everything you can see", 8–14 each). The **Robe of Hades** calls that
same routine on-struck (4-turn recharge), so the scroll and the robe share one implementation
and neither cooks its own user. Damage draws the world RNG (deterministic per seed).

**8. Fadecloak — reactive invisibility (T4).** A counter of hits *taken* (styled after Slipstep
boots / the hammer cadence, no RNG): on **every 4th** hit, set `player.invisible` for 2 turns,
**de-aggro** every currently-awake monster (the wake/aggro system), and clear the `intent` of
any that had not yet landed a blow (windup-wipe). Reuses `player.invisible` (world.py aggro /
`monster_can_see_player`) and the intent-clear. **+2 def / +10 spd** — it's a cloak.

**9. Nightcloak — permanent invisibility (T5, boss-reserved).** `player.invisible` held
**continuously** while worn, so monsters neither see nor aggro the wearer — until the wearer
**attacks**, which breaks it; it **re-cloaks a set number of turns after the last strike**
(turn-tuned, deterministic — no aggro-set tracking). Reuses the invisibility path. Its drop is
reserved for the floor-15 mini-boss; until then it is cheat-only and excluded from floor drops.

**10. Shademail — wall-walk (T4, boss-reserved).** The wearer may step **onto wall (stone)
tiles**, but never off the map / into the void — `walkable()` (or the player-move check) treats
in-bounds stone as passable for the wearer. Monsters cannot follow into stone (except wraiths,
who already move through walls). A **5-turn cooldown** starts when the wearer **leaves** the
stone, so wall-walking is a periodic escape, not a permanent state. FOV inside stone shows the
immediate surroundings. Its drop is reserved for the floor-8 mini-boss; cheat-only until then.

### Data model

`Armour` (items.py) carries `key, name, tier, defense, speed_mod, trait, note, bonus`. The new
identities need a few parameters the single `trait` string can't hold — the **retaliation
element + on-hit magnitude + recharge**, the **Fadecloak hit cadence + invis duration**, the
**Bastion's cap N**, the **Lifeweaver regen amount**, the **Blinding/Robe radius + recharge**, the
**Nightcloak re-cloak delay**, the **Shademail cooldown**. These become either fields on
`Armour` or **config constants keyed by the identity** (as the boots roster did); the
implementation plan settles the exact shape. Parameterless identities (thorns, wraithsilk,
last-breath, stone-golem, wall-walk) stay a `trait` flag. The one-armour-at-a-time invariant
means the reactive *runtime* state lives on the Player as a couple of scalars, serialized.

### Retiring / redefining

- `thorn` (Thorned Cuirass) and `silk` (Wraithsilk) return from the graduated ordinary pieces —
  same keys, re-tiered to T4, wraithsilk restatted to +2/+10. Their dormant engine hooks
  (world.py:816 thorns, monsters.py:603 wraithsilk) reactivate.
- Twelve new pieces, each needs a distinct **sprite** in `sprites.gear()` (the dead
  `scale`/`chain` sprite branches left by Plan A can be repurposed).
- **Distribution:** magical armour joins the `FINDABLE_MAGICAL_*` pattern the weapons/boots use
  — a `FINDABLE_MAGICAL_ARMOUR` set (the 12 non-boss pieces) placed on floors 8+ via the
  generation path; Shademail/Nightcloak are **excluded** (boss-reserved), like Windfang/Void.

## Surfaces touched

- **`items.py`** — the `ARMOURS` table (12 new + 2 re-homed magical entries); `Armour` gains the
  identity parameters; `FINDABLE_MAGICAL_ARMOUR` + the floor-8+ magical-armour roll.
- **`world.py`** — retaliation + capstones in the on-struck path; Bulwark cap in the damage
  calc; Last Breath in `kill_player`; the shared spares-the-caster firestorm (Robe + VORN fix);
  Fadecloak reactive invis + de-aggro + windup-wipe; Nightcloak continuous invis + re-cloak;
  Shademail wall passability + cooldown.
- **`monsters.py`** — reactivate the dormant wraithsilk immunity branch; confirm de-aggro and
  monster pathing respect wall-walk.
- **`player.py`** — the reactive armour state (cooldown, hit counter, last-stand flag, wall-walk
  cooldown) + serialization; the Lifeweaver regen tick; freeze/immunity plumbing as needed.
- **`config.py`** — constants for recharges, radii, caps, regen cadence, re-cloak delay.
- **`sprites.py`** — a distinct sprite per new magical armour.
- **`tests.py`** — per-mechanic tests; the Firestorm-no-self-burn test; determinism/bit-identical
  stays green.

## Phased implementation (decompose in writing-plans)

Too large for one plan. Proposed phases, each shippable and testable:

1. **Roster + reused-mechanic pieces + the Firestorm fix.** The `ARMOURS` table, the
   parameter-carrying data model, sprites, distribution (`FINDABLE_MAGICAL_ARMOUR`, floor-8+
   roll), and every identity that reuses existing systems — thorns, wraithsilk, the retaliation
   trio, Lifeweaver regen, Bastion's cap, Last Breath (phoenix pattern), Blinding Light, Robe of
   Hades + the VORN self-burn fix.
2. **The novel subsystems.** Invisibility (Fadecloak reactive + Nightcloak continuous) and
   wall-walk (Shademail) — the higher-risk pieces touching aggro/FOV/pathing. Its own plan.
   Nightcloak/Shademail ship cheat-reachable + boss-reserved (drop wiring deferred to the
   mini-boss task).
3. **Deep economy (Plan C, later).** Rarity, one-per-game uniqueness, death-persistence, a
   collection gold star — mirroring the boots economy.

## Open tunables (settle in playtest)

- All defense/speed numbers, esp. Stone Golem's Chest (+5/0) and the two +10-speed cloths.
- Retaliation recharge (3 turns) and the fire-vs-poison damage/duration split; capstone recharge
  (4 turns) and Blinding radius (2).
- Bastion's cap N; Lifeweaver regen (2 hp/turn); Last Breath's 1-turn untouchable window.
- Fadecloak cadence (every 4th) and invis duration (2); Nightcloak re-cloak delay.
- Shademail cooldown (5) and whether FOV inside stone reveals anything beyond the adjacent.
