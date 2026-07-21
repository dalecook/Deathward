# Boots Rebalance — Ordinary Tier & Magical Relocation (Plan 1)

**Date:** 2026-07-21
**Status:** design, pending review
**Scope:** the first of the boots passes — the middle leg of the gear triad, after
weapons. This plan builds the *ordinary* boots tier (leather/mail/plate) and performs a
mechanical *relocation* of the existing boots to the magical floors (8+). The creative
rework of the magical roster — real movement identities, capabilities beyond speed, new
boots, names and flavour — is a deliberate follow-up (Plan 2).

## Problem

Boots have no ordinary tier. Every boot except the T0 Worn Sandals starter is, in the
user's words, effectively *magical* — a big speed number (Swift +25, Windwalkers +40) or
an exotic trait (blink, softsole, kick). The early game jumps straight from the +0
starter to a +25 boot, so there is no mundane progression to descend into, and the boots
slot is out of step with weapons, which now have a full ordinary foundation (floors 1–7)
before the magical roster takes over at floor 8.

## Goals

- Give boots an **ordinary tier** on floors 1–7, mirroring how weapons were rebalanced.
- Make each ordinary boot a **genuine decision**, not a strictly-better ladder — a
  fast↔tanky tradeoff (speed vs. defense), honouring the gear-triad thesis.
- Establish **leather/mail/plate** as shared material vocabulary that will later flow
  into the armour rebalance.
- Relocate the existing boots to the magical floors (8+) so the tier structure stays
  coherent, **without reworking them yet**.
- Make magical boots **found-only** (never sold or gifted), mirroring magical weapons.

## Non-goals (this plan)

- The creative rework of the magical roster: movement identities, capabilities beyond
  raw speed, new magical boots, names and flavour (Plan 2).
- Rarity / uniqueness / deep-economy for magical boots (the equivalent of the later
  weapon plans). This plan relocates them with their **current stats and traits intact**
  and lets them drop through the existing loot pipeline on deep floors.
- Any change to armour or weapons. Leather/mail/plate as *armour* is a future task; the
  material names are chosen now with that in mind, but only boots are touched here.

## Design

### 1. Data model — boots gain defense

`Boots` gains a `defense` field (default `0`), sitting beside its existing `speed` and
`trait`. `Boots.desc()` shows `N def` when non-zero (alongside the `%+d spd`).

The single integration point is the `player.defense` property (player.py:103–104),
which today reads only armour:

```python
d = self.armour.defense + self.enchants.get(self.armour.key, 0)
```

It gains `+ self.boots.defense`. Because damage reduction funnels through the one
`p.defense` property (`dmg = max(0, dmg - p.defense)`, world.py:673), boots defense
stacks with armour defense for free, and the **wraith "ignore armour"** path — which
suppresses `p.defense` — suppresses boots defense too. That is the intended behaviour: a
wraith's touch ignores *mundane* protection, and armoured boots are mundane. The plan
must confirm the ignore path zeroes the combined property rather than only the armour
term.

**Speed needs no change.** Plate's −10 flows through the existing player-speed sum
(`BASE_SPEED + boots.speed + armour.speed_mod + weapon.speed_mod`, min 30). Boots already
contribute `speed`.

### 2. The ordinary tier — a fast↔tanky tradeoff ladder

Not a 3×3 matrix (the weapon matrix is a guide, not a bound). A linear ladder where each
rung trades speed for protection:

| tier | key | name | speed | defense | floor band |
|---|---|---|---|---|---|
| 0 | `sandals` | Worn Sandals | +0 | 0 | starter (unchanged) |
| 1 | `leather` | Leather Boots | +10 | 0 | 1+ |
| 2 | `mail` | Mail Boots | +0 | +1 | 3+ |
| 3 | `plate` | Plate Boots | −10 | +2 | 5+ |

Speed steps −10 per rung; defense +1 per rung; leather (+10) and plate (−10) are
symmetric about mail, the neutral pivot. No traits — this is the mundane tier by design,
and its plainness is what makes the magical boots feel exotic by contrast. Names are
plain; flavour notes are the user's to punch up later.

Because the tiers are a *tradeoff*, not a power ranking, a T3 plate is **not** an upgrade
over T1 leather for a speed build — which drives the auto-swap change in §5.

### 3. Magical relocation — interim, no rework

The five existing boots are re-tiered to T4/T5 and pushed to floors 8+, with **stats and
traits untouched**:

| tier | key | name | speed | trait |
|---|---|---|---|---|
| 5 | `wind` | Windwalkers | +40 | — |
| 4 | `swift` | Swift Boots | +25 | — |
| 4 | `blink` | Boots of Blinking | +15 | blink |
| 4 | `soft` | Padded Soles | +10 | softsole |
| 4 | `ironshod` | Ironshod Boots | +5 | kick |

The split is a provisional power ordering — Windwalkers is the standout, so it takes T5;
the rest sit at T4. This mapping is throwaway: Plan 2 re-tiers, reworks, and expands the
whole magical roster (T4 *focused* / T5 *unleashed*, mirroring the magical weapons).

### 4. Distribution — floors, vendor, gift

- **Floor gating:** `gear_pool(depth)` (items.py:365) grows its tier→depth map so T4 and
  T5 unlock at floor **8+**; ordinary T1/T2/T3 keep their current **1+/3+/5+** gates.
- **Found-only magical boots:** the **vendor** (`Vendor._stock_up` draws from
  `gear_pool`, vendor.py:65) filters its stocked boots to **tier ≤ 3**, so a magical
  boot can never be bought — only found on a deep floor. This is a real filter because
  vendors appear on floors 5–19 (`VENDOR_MIN_DEPTH = 5`), so a deep vendor's
  `gear_pool(depth)` would otherwise include T4/T5 boots. The **floor-1 gift** needs *no*
  change: it draws `gear_pool(1)` (dungeon.py:530), which — once magical boots are gated
  to floor 8+ — yields only T1 gear, so it is inherently ordinary. This mirrors magical
  weapons being found-only.
- **Interim commonness:** with T4/T5 boots in `gear_pool`, they drop through the generic
  deep-floor loot roll (`roll_loot` → `gear_pool`) at the same cadence as armour — i.e.
  relatively common, not rare, not unique. That is acceptable for Plan 1; rarity and
  uniqueness are Plan 2+ (the weapons got theirs in later plans).
- **Pricing:** `GEAR_PRICE` (vendor.py:32) covers tiers 1–3 only; since the vendor never
  stocks T4/T5 boots, no new price entries are needed.

### 5. Auto-swap — respect the tradeoff

The auto-pickup check leaves a found gear piece when `g.tier <= cur.tier`
(world.py:914) — it assumes higher tier means strictly better. That is now false for
boots: auto-walking over a T3 plate while wearing T1 leather would silently swap it in
and cost the player 20 speed.

**Rule:** boots auto-swap **only when the current boots are the T0 starter**
(`sandals`). Once the player is off the starter, a found boot is left on the ground for a
deliberate manual pickup, preserving the fast↔tanky choice. Weapon and armour auto-swap
behaviour is unchanged. (The starter exception means the very first boot a player finds
still gets picked up automatically, so the mechanic isn't hidden from a new player.)

## Surfaces touched

- **`items.py`** — add `defense` to `Boots` and surface it in `Boots.desc()`; retier the
  `BOOTS` table (sandals T0; leather/mail/plate T1–T3; swift/blink/soft/ironshod T4;
  wind T5); add leather/mail/plate entries with defense; extend `gear_pool`'s tier→depth
  gates for T4/T5 at floor 8+.
- **`player.py`** — `defense` property adds `self.boots.defense`.
- **`world.py`** — auto-swap check (line 914) exempts boots unless current boots are the
  starter; verify the wraith ignore-armour path suppresses the combined `p.defense`.
- **`vendor.py`** — filter stocked boots to tier ≤ 3. (The floor-1 gift in
  `dungeon.py:529` needs no change — `gear_pool(1)` is inherently T1-only.)
- **`tests.py`** — new tests (see below).

## Testing considerations

- **Defense stacks and reduces damage:** plate boots subtract 2 from every incoming hit,
  additive with armour defense; a wraith ignores boots defense as well as armour.
- **Speed:** plate's −10 lands in `player.speed`; leather's +10 likewise; the min-30
  floor still holds under stacked penalties.
- **Distribution:** ordinary boots (T1–3) appear on floors 1–7; magical boots (T4–5)
  only on floors 8+; the vendor stock and the floor-1 gift never surface a tier ≥ 4 boot.
- **Auto-swap:** a found boot is auto-equipped over the T0 starter, but never
  auto-swapped once the player wears any T1+ boot (no silent speed downgrade).
- **Integrity:** `gear_catalog` grouping and `top_tier_gear` still hold with the new
  boots and tiers; `desc()` renders both speed and defense correctly.

## Open tunables (safe to settle in playtest)

- Ordinary boot numbers (leather +10 / plate −10 / defense +1,+2) and their floor bands.
- The interim T4/T5 split (entirely provisional — Plan 2 replaces it).
- Whether ordinary boots should hard-cut-off past floor 7 (a stricter weapon-style
  banding) rather than remain droppable deep like armour — deferred; the shared
  `gear_pool` with armour makes the simple gating the low-risk Plan 1 choice.
