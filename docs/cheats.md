# Cheat codes

For reaching the deep floors in a few minutes instead of a few hours. These exist for
testing and playtesting; nothing here is reachable by accident.

**Hold CTRL** (CMD on a Mac) and type the digits in order, keeping the modifier down the
whole way. Let go, or press anything not in the sequence, and it starts over. Nothing in
the game binds CTRL, and none of these sequences is one a hand produces by mistake.

Source of truth is `deathward/game.py` (where the codes are wired) and
`deathward/cheats.py` (the matcher).

## The codes

| Code | What it does |
|---|---|
| **CTRL + 0 9 8 7** | Instant kit — the Vampiric Kris, the best armour, the best boots, and up to nine healing potions. |
| **CTRL + 7 8** | Warp down one floor, from anywhere. |
| **CTRL + 8 7** | Arsenal — the top three weapons, armours and boots; your pick drops beside you. |
| **CTRL + 6 7** | Scroll picker — any uncommon or rare scroll, into your pack, identified. |
| **CTRL + 7 6** | Potion picker — same, for potions. |
| **CTRL + 1 2** | Weapon bench — nine ordinary weapons plus all thirteen magical ones. |
| **CTRL + 2 1** | Magic bench — the thirteen magical weapons only, skipping the ordinary page. |
| **CTRL + 5 6** | Boots bench — every boot, ordinary and magical. |
| **CTRL + 3 4** | Armour bench — every armour, ordinary and magical. |

## Using the benches

The four benches (`12`, `21`, `56`, `34`) all share one picker:

- **TAB** cycles pages — *Ordinary* → *Magical — Tier 4* → *Magical — Tier 5*.
  (The magic bench has no ordinary page.)
- **1**–**9** equips the item on that row. Pages hold at most nine, so every digit key
  stays reachable.
- **SHIFT + digit** gives you the **+2 masterwork** version instead. Weapon benches only.

What you were wearing **drops at your feet**. Benches are swaps.

## Worth knowing

**`0987` does not drop your old gear.** Unlike the benches, it overwrites your weapon,
armour and boots outright — it is a debug grant, not a swap, and littering the floor with
your old rags would just be noise. It also marks the granted gear as seen in your Kodex.

**`78` obeys every rule except the stairs.** It drops you on the next floor's entrance
tile, but the floor is still cached if you have been there this run, the vendor odds still
step, and it will not take you past the Warden on floor 20. It is a shortcut through the
walking, not through the game.

**The pickers give you identified items.** The scroll and potion pickers put the real,
known item in your pack — so they bypass the identification game entirely. That is the
point when you are testing a deep consumable, and worth remembering when you are trying to
judge how the *unidentified* experience feels.

## Reaching the mini-boss

Floor 8 is Syrinx's sealed arena. `CTRL + 7 8` seven times gets you to its antechamber,
which is the last place you can prepare — the mouth seals behind you when you step
through, and the way down does not open until she is dead.

Useful there:

- **`CTRL + 6 7`** for a Scroll of Teleport. In her hall it is not an escape (the sealed
  antechamber is excluded from its destinations) but a **gap-closer** — she shoves you five
  tiles with every blow and is helpless for exactly one turn afterwards, so an aimed jump is
  how you convert that stun into damage.
- **`CTRL + 3 4`** for Shademail, the armour that walks into stone — currently the one thing
  that can cross the sealed mouth in either direction.
- **`CTRL + 5 6`** for Slipstep or Flicker boots, if you want to test how the blink
  repositioners behave against the gate.
