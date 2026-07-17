# DEATHWARD -- a turn-based roguelike where failure is the only progression.
# Copyright (C) 2026 Dale Cook
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.

"""Gear, treasure and consumables.

The gear triad is deliberately not three flavours of "+1 number":

    WEAPON  changes how you kill        (spread, cleave, crit, stun, burn, drain)
    ARMOUR  changes what you survive    (flat subtraction from every hit -- so it is
                                         a swarm answer, not a boss answer -- and it
                                         costs you turns)
    BOOTS   change how you move         (speed IS turns; turns are the real resource)

Consumables have FIXED identities across every run of every game. A murky ochre
potion is always healing. You simply do not know that yet -- and until you do, the
game shows you a colour and nothing else. Identity is learned by drinking it, or
by dying with it unopened in your pack.
"""

import random


class Weapon:
    slot = "weapon"

    def __init__(self, key, name, tier, lo, hi, trait=None, note=""):
        self.key, self.name, self.tier = key, name, tier
        self.lo, self.hi, self.trait, self.note = lo, hi, trait, note

    def roll(self, rng):
        return rng.randint(self.lo, self.hi)

    def desc(self, bonus=0):
        s = "%d-%d dmg" % (self.lo + bonus, self.hi + bonus)
        return s + ("  |  " + self.note if self.note else "")


class Armour:
    slot = "armour"

    def __init__(self, key, name, tier, defense, speed_mod=0, trait=None, note=""):
        self.key, self.name, self.tier = key, name, tier
        self.defense, self.speed_mod, self.trait, self.note = defense, speed_mod, trait, note

    def desc(self, bonus=0):
        s = "%d def" % (self.defense + bonus)
        if self.speed_mod:
            s += ", %+d spd" % self.speed_mod
        return s + ("  |  " + self.note if self.note else "")


class Boots:
    slot = "boots"

    def __init__(self, key, name, tier, speed, trait=None, note=""):
        self.key, self.name, self.tier = key, name, tier
        self.speed, self.trait, self.note = speed, trait, note

    def desc(self):
        s = "%+d spd" % self.speed
        return s + ("  |  " + self.note if self.note else "")


WEAPONS = {
    "shiv":     Weapon("shiv", "Rusted Shiv", 0, 1, 3),
    "sword":    Weapon("sword", "Bronze Sword", 1, 2, 5),
    "axe":      Weapon("axe", "Bone Axe", 1, 1, 7, "cleave",
                       "cleaves every adjacent enemy"),
    "rapier":   Weapon("rapier", "Steel Rapier", 2, 4, 6, "crit",
                       "1 in 4 strikes doubles"),
    "hammer":   Weapon("hammer", "Iron Warhammer", 2, 3, 9, "stun",
                       "1 in 4 strikes stuns for a turn"),
    "brand":    Weapon("brand", "Flame Brand", 3, 5, 10, "burn",
                       "sets the struck thing alight"),
    "kris":     Weapon("kris", "Vampiric Kris", 3, 3, 7, "lifesteal",
                       "you heal for half of what you deal"),
}

ARMOURS = {
    "rags":     Armour("rags", "Padded Rags", 0, 0),
    "leather":  Armour("leather", "Leather Jerkin", 1, 1),
    "scale":    Armour("scale", "Scale Vest", 1, 2, -5),
    "chain":    Armour("chain", "Chain Hauberk", 2, 3, -10),
    "thorn":    Armour("thorn", "Thorned Cuirass", 2, 2, -5, "thorns",
                       "returns 2 damage to anything that hits you"),
    "plate":    Armour("plate", "Warden Plate", 3, 5, -18),
    "silk":     Armour("silk", "Wraithsilk", 3, 2, 0, "wraithsilk",
                       "a wraith's touch cannot find you"),
}

BOOTS = {
    "sandals":  Boots("sandals", "Worn Sandals", 0, 0),
    "swift":    Boots("swift", "Swift Boots", 1, 25),
    "soft":     Boots("soft", "Padded Soles", 1, 10, "softsole",
                      "too light to set off a pressure plate"),
    "blink":    Boots("blink", "Boots of Blinking", 2, 15, "blink",
                      "SHIFT+dir to leap three tiles"),
    "ironshod": Boots("ironshod", "Ironshod Boots", 2, 5, "kick",
                      "your blows knock the struck thing back"),
    "wind":     Boots("wind", "Windwalkers", 3, 40),
}

ALL_GEAR = {}
ALL_GEAR.update(WEAPONS)
ALL_GEAR.update(ARMOURS)
ALL_GEAR.update(BOOTS)

STARTING = ("shiv", "rags", "sandals")


def gear_catalog():
    """All gear for the Kodex Gear tab, grouped by slot and ordered by tier then name:
    [("WEAPONS", [(key, gear), ...]), ("ARMOUR", ...), ("BOOTS", ...)]."""
    out = []
    for label, table in (("WEAPONS", WEAPONS), ("ARMOUR", ARMOURS), ("BOOTS", BOOTS)):
        rows = sorted(table.items(), key=lambda kv: (kv[1].tier, kv[1].name))
        out.append((label, rows))
    return out


def top_tier_gear(n=3):
    """The best `n` of each kind -- for the CTRL+87 arsenal tester. Ranked by tier,
    highest first; ties keep roster order (which runs plain -> exotic). There are only
    two top-tier weapons and armours, so the third slot is the best of the next tier."""
    def top(d):
        return sorted(d.values(), key=lambda g: g.tier, reverse=True)[:n]
    return {"weapon": top(WEAPONS), "armour": top(ARMOURS), "boots": top(BOOTS)}


# --- consumables ---------------------------------------------------------
class Consumable:
    slot = "pack"

    def __init__(self, flavor, kind, effect, unknown_name, true_name, tier="common"):
        self.flavor = flavor          # the codex key suffix: id.<flavor>
        self.kind = kind              # "potion" | "scroll"
        self.effect = effect
        self.unknown_name = unknown_name
        self.true_name = true_name
        self.tier = tier              # "common" | "uncommon" | "rare" -- spawn rarity

    def name(self, codex):
        return self.true_name if codex.identified(self.flavor) else self.unknown_name

    def known(self, codex):
        return codex.identified(self.flavor)


CONSUMABLES = {
    "ochre":   Consumable("ochre", "potion", "heal",
                          "murky ochre potion", "Potion of Healing"),
    "azure":   Consumable("azure", "potion", "haste",
                          "clear azure potion", "Potion of Swiftness"),
    "viscous": Consumable("viscous", "potion", "poison",
                          "viscous green potion", "Potion of Venom"),
    "black":   Consumable("black", "potion", "might",
                          "bubbling black potion", "Potion of Might"),
    "kesh":    Consumable("kesh", "scroll", "map",
                          "scroll etched KESH", "Scroll of Mapping"),
    "vorn":    Consumable("vorn", "scroll", "fire",
                          "scroll etched VORN", "Scroll of Firestorm"),
    "uul":     Consumable("uul", "scroll", "blink",
                          "scroll etched UUL", "Scroll of Escape"),
    "gramm":   Consumable("gramm", "scroll", "summon",
                          "scroll etched GRAMM", "Scroll of Summoning"),

    # --- WAVE 1: the rest of the common tier -----------------------------
    "grey":    Consumable("grey", "potion", "stoneskin",
                          "cloudy grey potion", "Potion of Stoneskin"),
    "crimson": Consumable("crimson", "potion", "regen",
                          "deep crimson potion", "Potion of Regeneration"),
    "sallow":  Consumable("sallow", "potion", "weak",
                          "sallow yellow potion", "Potion of Weakness"),
    "silver":  Consumable("silver", "potion", "vigor",
                          "silvery potion", "Potion of Vigor"),
    "morn":    Consumable("morn", "scroll", "identify",
                          "scroll etched MORN", "Scroll of Identify"),
    "yris":    Consumable("yris", "scroll", "light",
                          "scroll etched YRIS", "Scroll of Light"),
    "ghask":   Consumable("ghask", "scroll", "aggravate",
                          "scroll etched GHASK", "Scroll of Aggravation"),
    "vosh":    Consumable("vosh", "scroll", "detect",
                          "scroll etched VOSH", "Scroll of Detect Treasure"),

    # --- WAVE 2: the uncommon tier (floors 8+) ---------------------------
    "rose":    Consumable("rose", "potion", "greatheal",
                          "rose-gold potion", "Potion of Greater Healing", "uncommon"),
    "vermilion": Consumable("vermilion", "potion", "berserk",
                          "seething vermilion potion", "Potion of Rage", "uncommon"),
    "teal":    Consumable("teal", "potion", "resist",
                          "deep teal potion", "Potion of Warding", "uncommon"),
    "sky":     Consumable("sky", "potion", "levitate",
                          "weightless sky-blue potion", "Potion of Levitation", "uncommon"),
    "krav":    Consumable("krav", "scroll", "enchant_weapon",
                          "scroll etched KRAV", "Scroll of Enchant Weapon", "uncommon"),
    "dwen":    Consumable("dwen", "scroll", "enchant_armour",
                          "scroll etched DWEN", "Scroll of Enchant Armour", "uncommon"),
    # invisibility comes two ways, on purpose -- a real boon on the deep floors
    "violet":  Consumable("violet", "potion", "invisible",
                          "shifting violet potion", "Potion of Invisibility", "uncommon"),
    "vesh":    Consumable("vesh", "scroll", "invisible",
                          "scroll etched VESH", "Scroll of Invisibility", "uncommon"),
    "puce":    Consumable("puce", "potion", "confuse",
                          "muddy puce potion", "Potion of Confusion", "uncommon"),
    "skarn":   Consumable("skarn", "scroll", "fear",
                          "scroll etched SKARN", "Scroll of Fear", "uncommon"),
    "gorm":    Consumable("gorm", "scroll", "hold",
                          "scroll etched GORM", "Scroll of Hold Monster", "uncommon"),
    "zeph":    Consumable("zeph", "scroll", "teleport",
                          "scroll etched ZEPH", "Scroll of Teleport", "uncommon"),

    # --- WAVE 3: the rare tier (floors 12+) ------------------------------
    "vital":   Consumable("vital", "potion", "vitality",
                          "throbbing scarlet potion", "Potion of Vitality", "rare"),
    "radiant": Consumable("radiant", "potion", "heroism",
                          "radiant golden potion", "Potion of Heroism", "rare"),
    "luminous": Consumable("luminous", "potion", "insight",
                          "luminous white potion", "Potion of Insight", "rare"),
    "ember":   Consumable("ember", "potion", "phoenix",
                          "smouldering orange potion", "Potion of the Phoenix", "rare"),
    "ossk":    Consumable("ossk", "scroll", "banish",
                          "scroll etched OSSK", "Scroll of Banishment", "rare"),
    "vrom":    Consumable("vrom", "scroll", "descent",
                          "scroll etched VROM", "Scroll of Descent", "rare"),
    "dract":   Consumable("dract", "scroll", "thunderclap",
                          "scroll etched DRACT", "Scroll of Thunderclap", "rare"),
    "ulm":     Consumable("ulm", "scroll", "sanctuary",
                          "scroll etched ULM", "Scroll of Sanctuary", "rare"),
}

# weighted spawn pools for the COMMON tier -- the bad ones are as common as the good
# ones, which is the entire reason identification is worth dying for.
POTION_POOL = ["ochre", "ochre", "ochre", "azure", "viscous", "viscous", "black",
               "grey", "crimson", "sallow", "sallow", "silver"]
SCROLL_POOL = ["kesh", "kesh", "vorn", "uul", "gramm",
               "morn", "morn", "yris", "ghask", "vosh"]

# the uncommon/rare tiers, grouped by (kind, tier), built from the table above so
# there is one source of truth. rare stays empty until Wave 3.
_TIER_POOLS = {}
for _flavor, _c in CONSUMABLES.items():
    if _c.tier != "common":
        _TIER_POOLS.setdefault((_c.kind, _c.tier), []).append(_flavor)


def _consumable_tier(rng, depth):
    """How rare a potion/scroll roll comes out. Uncommon starts on floor 8, rare on
    floor 12; the deeper you are, the better your odds at the good stuff."""
    if depth >= 12 and rng.random() < 0.10:
        return "rare"
    if depth >= 8 and rng.random() < 0.30:
        return "uncommon"
    return "common"


def roll_consumable(rng, depth, kind):
    """One potion (kind='potion') or scroll (kind='scroll'), rarity gated by depth.
    Falls back to the common pool for any tier that has nothing in it yet."""
    common = POTION_POOL if kind == "potion" else SCROLL_POOL
    tier = _consumable_tier(rng, depth)
    if tier == "common":
        return rng.choice(common)
    return rng.choice(_TIER_POOLS.get((kind, tier)) or common)


def gear_pool(depth):
    """What gear can drop at a given depth. Deeper floors unlock better tiers."""
    pool = []
    for table in (WEAPONS, ARMOURS, BOOTS):
        for key, g in table.items():
            if g.tier == 0:
                continue
            if g.tier == 1 and depth >= 1:
                pool.append(key)
            elif g.tier == 2 and depth >= 3:
                pool.append(key)
            elif g.tier == 3 and depth >= 5:
                pool.append(key)
    return pool


def roll_loot(rng, depth):
    """What a floor-drop contains: exactly one thing."""
    r = rng.random()
    if r < 0.30:
        return ("gold", rng.randint(8, 22) + depth * 6)
    if r < 0.58:
        return ("item", roll_consumable(rng, depth, "potion"))
    if r < 0.74:
        return ("item", roll_consumable(rng, depth, "scroll"))
    pool = gear_pool(depth)
    if not pool:
        return ("gold", rng.randint(10, 25))
    return ("gear", rng.choice(pool))


def roll_chest(rng, depth):
    """What a CHEST contains: a small hoard, one to three things. A chest you have
    to make a decision about is a better chest than one that just hands you a coin."""
    n = rng.choice([1, 2, 2, 3])
    return [roll_loot(rng, depth) for _ in range(n)]


# what each thing is carrying when it dies: (chance of any loot, how many things)
MONSTER_LOOT = {
    "angry_rat": (0.18, 1),
    "rat":       (0.20, 1),
    "kobold":    (0.45, 1),     # it is a soldier; it has pockets
    "spitter":   (0.35, 1),
    "brute":     (0.60, 2),     # big things guard big things
    "wraith":    (0.40, 1),
    "mimic":     (0.95, 3),     # it has been eating adventurers. all of it is theirs.
    "warden":    (1.00, 4),
}


def roll_monster_loot(rng, depth, key):
    """What is left ON THE BODY. A corpse with treasure is a container -- you have to
    walk to it, stand on it, and spend the turn -- which means the fight is never
    quite over just because the thing stopped moving."""
    chance, n = MONSTER_LOOT.get(key, (0.25, 1))
    if rng.random() >= chance:
        return []
    return [roll_loot(rng, depth) for _ in range(rng.randint(1, n))]
