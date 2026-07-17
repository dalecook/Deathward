# DEATHWARD

*the dungeon does not get easier. you get harder to kill.*

A turn-based roguelike dungeon crawler in which **failure is the only progression**.
Twenty floors, permadeath, no experience points, no levelling. You start with a
Rusted Shiv, Padded Rags and Worn Sandals, and the only thing that survives your
death is what you learned by dying.

Python + Pygame, standard library only. **No asset files** — every creature, wall,
potion and trap is drawn procedurally at runtime with polygons (supersampled and
downscaled for anti-aliasing, then cached). A rat looks like a rat; the *angry* rat
and the *plague* rat look like different animals, because on floor 2 the difference
matters.

## Run

```
pip install pygame
python run_deathward.py
```

On Windows the launcher is usually `py -3.13 run_deathward.py`. Needs Python 3.11+
and nothing else outside the standard library.

## The idea

**You cannot see what you do not understand.**

- A monster you have never been killed by is drawn as a **`?`** — no name, no
  health bar, no readable intent. It still hits exactly as hard.
- A trap you have never triggered is drawn as **clean floor**. It still fires.
- A potion you have never identified is **a colour**. Crimson is always
  regeneration and viscous green is always venom — you simply do not know that yet,
  and the day you learn it is the day one of them kills you.

**Every death performs an autopsy and writes one true thing into your Kodex**, and
it is never a thing you already knew. The reveal ladder runs: what death itself
does → the *rule* of what killed you → its *tell* → its *counter* → the nearest
unlearned thing on that floor → the true name of an item you died holding → a
secret about yourself or the dungeon → intel on something you have not met → and
finally *telemetry computed from your own history at the moment of death*, which
cannot run dry.

The instant a fact lands, the dungeon renders more of itself: the brute's wind-up
appears as a red square on the tile it is about to crush, the spitter's firing line
is painted down the corridor, the kobold's break for the door is flagged, and the
chest that is not a chest starts breathing.

**Traps are found one at a time.** Springing the dart trap by the stairs marks *that*
trap on your map forever — through every death, for the rest of the game. It tells you
nothing about the dart trap in the treasury. Every trap in this dungeon is paid for
individually. (Killing also teaches, but slowly: a corpse gives you a monster's *rule*
on the 1st kill, its *tell* on the 3rd, its *counter* on the 8th. A single death gives
you the next one immediately. Dying is the fast teacher; that is the whole thesis,
stated as a number.)

**Knowledge is information, never power.** This is enforced, not asserted: the test
suite runs the same seed with the same keystrokes against an empty Kodex and a
complete one and requires the two dungeons to be *bit-identical*. Monsters do not
get weaker. You stop being surprised.

**The dungeon is a place.** Its stone is cut once per game: floor 4's rooms and
corridors are the same rooms and corridors every time you walk back in, and the map
you drew with your feet is never forgotten. What is *living* in them — the monsters,
the loot, the chests — is dealt fresh on every respawn. The map is memorised; the
danger is not.

**Your corpse keeps your gold, exactly where you fell.** Die on floor 4 with 200 gold
and a Flame Brand, and floor 4 of your next run has your body on that same tile, still
holding all of it. Every run you lose is a cache you leave for the next one.

## The gear triad

Each slot answers a different question, so an upgrade is a decision and not just a
bigger number.

| | what it changes |
|---|---|
| **weapon** | *how you kill* — spread, cleave, crit, stun, burn, lifesteal |
| **armour** | *what you survive* — a flat subtraction from **every** hit, so it is a swarm answer, not a boss answer. And it **costs you speed.** |
| **boots** | *how you move* — and speed is turns, and turns are the only real resource in a roguelike |

Warden Plate turns a plague rat's whole damage range into zero and makes you
visibly slower. Windwalkers buy you a free action every few turns. Padded Soles are
too light to depress a pressure plate. A wraith ignores armour entirely, which
means the plate you are so proud of is dead weight the moment one appears.

## Scrolls and potions

Thirty-six consumables — **18 potions and 18 scrolls** — sorted into three rarity
tiers. **Common** ones turn up from the first floor; **uncommon** ones start seeping
in around the mid floors; **rare** ones only surface deep. So the shape of what you
can find is itself a depth gauge.

A consumable's identity is fixed for the whole game but **unknown until you learn it** —
a scroll is a colour of wax, a potion is a colour of liquid, and the way you find out
what one does is to use it or to die holding it. Some potions are gifts (healing,
regeneration, vigor, heroism) and some are traps (poison, weakness, confusion). Once
you have identified a *bad* potion, you can stop drinking it and start **coating your
blade with it** — a venom potion you would never swallow becomes poison on every swing.
Scrolls bend the dungeon instead of the body: mapping, teleport, hold monster,
banishment (pick a monster type and it is gone from the floor), enchantment that
permanently upgrades a piece of gear, and more.

## The Kodex

Everything you have learned lives in the **Kodex** (`K`), now split into six tabs —
**Monsters · Traps · Scrolls · Potions · Gear · Lore** — that you flick through with
`1`–`6` or the arrow keys, each showing how much of that category you have uncovered.
Gear earns its own entries the way monsters do: a weapon, armour or boots you have
picked up or worn shows its stats and trait; one you have never held reads as a
sealed, unknown slot.

A running **message log** sits on a strip below the map; `L` opens the full,
scrollable history of the current game, newest first. The log is wiped when you start
a brand-new game.

## What is down there

**Monsters** — thirteen of them plus the boss, each built around a tactic rather than
a stat:

- **angry rats** — floor 1 only, the one thing down here you can simply hit
- **plague rats** — floor 2+, faster and sicker, and they come in numbers: arithmetic, so never fight them in the open
- **kobolds** — consequences: a wounded one *runs for help*
- **bile spitters** — geometry: break the straight line
- **brutes** — tempo: step off the wind-up
- **wraiths** — they walk through walls and ignore armour
- **mimics** — the chest opens *you*
- **orcs** — pack hunters with keen eyesight; one spotting you alerts them all, and they hunt as a group and regroup when scattered — but lose sight of you and they lose interest
- **flickers** — deep-floor blinkers, hard to pin down
- **beholders** — deep-floor: freeze you solid on one turn, then follow up with a ray on the next; weak alone, lethal when they hold you still in a crowd
- **stone golems** — deep-floor: slow to anger but once they have your scent they are almost as fast as you and never, ever stop tracking you
- **poltergeists** — deep-floor haunts
- **The Warden** — at the bottom, floor 20; not a new lesson, the exam

**Floor 1** is the tutorial the dungeon does not admit to having: angry rats, thin
spawns, a marked **entrance** you always start and restart from, and exactly one
**guaranteed gear upgrade**, placed as far from the gate as the level allows — a
reward for exploring rather than a handout at the door.

**Traps** — dart, spike pit, gas vent, alarm rune (no damage at all; it simply tells
the entire floor where you are) and the fire glyph, which hurts monsters exactly as
much as it hurts you. Once you can see a glyph, it stops being an obstacle and
becomes a weapon.

**Treasure** — gold, chests, gear upgrades, and hoard rooms that are visibly richer
and guarded in proportion. From floor 5 down a **vendor** may hold a floor, more
likely the deeper you go, willing to trade gold for gear. The dungeon puts its gold
where its teeth are.

## Controls

| key | |
|---|---|
| `WASD` / arrows | move / attack (bump) |
| `QEZC` or numpad | diagonals (`C` is down-right, **not** the kodex) |
| `SPACE` / `.` | wait a turn |
| `G` | take **all** — gold, gear, chests, **your own corpse** |
| `1`–`9` | take a numbered item when standing on loot; otherwise drink/read from the pack |
| `>` / `ENTER` | descend (standing on the stairs) |
| `SHIFT` + dir | leap (Boots of Blinking) |
| `K` | kodex (`1`–`6` / arrows switch tabs) |
| `L` | message log (scrollable, newest first) |
| `?` | help |
| `N` (title) | NEW GAME — erases the Kodex, your dead, everything (asks first) |
| `ENTER` (title) | CONTINUE — a new run; you keep the Kodex and your dead |

## Tests

```
python -m deathward.tests
```

360 tests, including the two load-bearing proofs: hundreds of consecutive deaths
never repeat a lesson (and the telemetry tier is inexhaustible), and
blind-vs-omniscient runs of the same seed produce identical dungeons. Plus: the
stairs are reachable on every floor across many seeds, the Warden is never walled
into a pillar, nothing spawns in your face, an undiscovered trap still fires, finding
one trap never reveals its twin, a Scroll of Mapping reveals stone and never loot,
plate shrugs off a rat while a wraith ignores plate, a bad potion coats your blade,
the Kodex sorts every fact into the right tab, the map survives death, and your
corpse comes back with your gold.

## Layout

```
run_deathward.py       entry point
deathward/
  game.py              main loop, state machine (death -> autopsy -> new run)
  world.py             turn economy, combat, consequences of curiosity
  dungeon.py           generation, hoards, boss arena, field of view
  monsters.py          thirteen monsters, each built around one tactic
  traps.py             five traps; invisible until YOU spring that one
  items.py             the gear triad, and the 36 fixed-identity consumables
  player.py            the hero, buffs, blade-coating, enchantments
  vendor.py            the deep-floor merchant
  codex.py             the Kodex: knowledge tree + every-death-teaches guarantee
  sprites.py           procedural polygon art (no asset files)
  keyrepeat.py         hold-to-walk
  cheats.py            Ctrl-chord test shortcuts
  render.py            drawing; what is drawn is a function of what is known
  ui.py                HUD, title, autopsy, kodex browser, log, victory
  tests.py             the proofs
  deathward_save.json  your kodex, your dead, your gold (created on first run)
```

## License

Copyright (C) 2026 Dale Cook

DEATHWARD is free software: you can redistribute it and/or modify it under the
terms of the **GNU General Public License** as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this
program (see the [LICENSE](LICENSE) file). If not, see
<https://www.gnu.org/licenses/>.
