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

A consumable's identity (what it does) holds for the whole game, but the LOOK it
wears while unidentified -- a potion's colour, a scroll's rune -- is dealt fresh
every new game (see Codex.roll_appearances). So the murky ochre potion that healed
you last game may be something else entirely in this one. Until you identify it the
game shows you only that look, and identity is learned by drinking it, or by dying
with it unopened in your pack.
"""

import random


class Weapon:
    slot = "weapon"

    def __init__(self, key, name, tier, lo, hi, traits=(), note="",
                 speed_mod=0, bonus=0):
        self.key, self.name, self.tier = key, name, tier
        self.lo, self.hi, self.note = lo, hi, note
        self.traits = tuple(traits)       # e.g. ("cleave", "burn"); () for a plain blade
        self.speed_mod = speed_mod        # a swing tax (or, negative, a quickening)
        self.bonus = bonus                # masterwork + scroll enchant, per-instance

    @property
    def trait(self):
        """Back-compat: the primary trait, or None. New code reads self.traits."""
        return self.traits[0] if self.traits else None

    def has(self, t):
        return t in self.traits

    def roll(self, rng):
        return rng.randint(self.lo, self.hi) + self.bonus

    def copy(self, bonus=None):
        return Weapon(self.key, self.name, self.tier, self.lo, self.hi, self.traits,
                      self.note, self.speed_mod,
                      self.bonus if bonus is None else bonus)

    def desc(self):
        lo, hi = self.lo + self.bonus, self.hi + self.bonus
        s = "%d dmg" % lo if lo == hi else "%d-%d dmg" % (lo, hi)
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


# Ordinary weapons: TYPE sets the attack shape and a speed tax, MATERIAL raises the
# damage floor (holding the ceiling at 5, so a better material means fewer whiffs, not
# a bigger top end). Tier encodes the power ordering used to keep the better of two
# weapons on a corpse: shiv < bone < bronze < steel < magical.
def _ordinary(mat, mat_tier, mat_lo):
    out = {}
    for typ, tax, trait, note in (
            ("sword", 0, None, ""),
            ("axe", -15, "cleave", "cleaves every adjacent enemy"),
            ("hammer", -25, "stun", "staggers the first blow, then every third")):
        key = "%s_%s" % (mat, typ)
        name = "%s %s" % (mat.capitalize(), typ.capitalize())
        out[key] = Weapon(key, name, mat_tier, mat_lo, 5,
                          traits=(trait,) if trait else (), note=note, speed_mod=tax)
    return out

WEAPONS = {"shiv": Weapon("shiv", "Rusted Shiv", 0, 1, 3)}
WEAPONS.update(_ordinary("bone", 1, 1))
WEAPONS.update(_ordinary("bronze", 2, 2))
WEAPONS.update(_ordinary("steel", 3, 3))
# --- magical (floors 8+): found unenhanced, enchantable by scroll ------------
# Tier 4 = the effect FOCUSED (single target / fast). Tier 5 = the effect UNLEASHED
# (borrows an ordinary attack shape -- usually cleave -- so it lands on a crowd).
WEAPONS.update({
    # Tier 4 -----------------------------------------------------------------
    "rapier": Weapon("rapier", "Razor Sharp Rapier", 4, 4, 6, traits=("crit",),
                     note="1 in 4 strikes doubles"),
    "brand":  Weapon("brand", "Flame Brand", 4, 4, 8, traits=("burn",),
                     note="sets the struck thing alight"),
    "betrayers_edge": Weapon("betrayers_edge", "Betrayer's Edge", 4, 4, 6,
                             traits=("enrage",),
                             note="the struck thing turns on its own"),
    "fulgurite": Weapon("fulgurite", "Fulgurite", 4, 4, 6, traits=("cleave", "shock"),
                        note="cleaves; scours the incorporeal"),
    "winters_edge": Weapon("winters_edge", "Winter's Edge", 4, 3, 6, traits=("freeze",),
                           note="a chance to freeze where it cuts"),
    "sacrificial_dagger": Weapon("sacrificial_dagger", "Sacrificial Dagger", 4, 3, 5,
                                 traits=("lifesteal",),
                                 note="you heal for half of what you deal"),
    "windfang": Weapon("windfang", "Windfang", 4, 5, 5, traits=(),
                       note="so light it quickens you", speed_mod=20),
    # Tier 5 -----------------------------------------------------------------
    "basilisk_maul": Weapon("basilisk_maul", "Basilisk Maul", 5, 5, 9,
                            traits=("poison", "stun"),
                            note="venom that stiffens the blood"),
    "pyroclast": Weapon("pyroclast", "Pyroclast", 5, 5, 8, traits=("cleave", "burn"),
                        note="cleaves and ignites all it touches"),
    "reapers_whisper": Weapon("reapers_whisper", "Reaper's Whisper", 5, 5, 8,
                             traits=("cleave", "fear"),
                             note="the reaped scatter in terror"),
    "kris": Weapon("kris", "Vampiric Kris", 5, 4, 7, traits=("cleave", "lifesteal"),
                   note="light enough to carry through, and it drinks from each"),
    "glacial_flail": Weapon("glacial_flail", "Glacial Flail", 5, 4, 7,
                            traits=("cleave", "freeze"),
                            note="freezes every adjacent foe"),
    "void_scimitar": Weapon("void_scimitar", "Scimitar of the Void", 5, 7, 7,
                            traits=("void",),
                            note="a chance to unmake what it strikes"),
})

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
    highest first; ties keep roster order (which runs plain -> exotic). The magical
    trio (rapier/brand/kris) fills all three weapon slots outright; armour and boots
    have only two top-tier pieces each, so their third slot is the best of the next
    tier down."""
    def top(d):
        return sorted(d.values(), key=lambda g: g.tier, reverse=True)[:n]
    return {"weapon": top(WEAPONS), "armour": top(ARMOURS), "boots": top(BOOTS)}


def weapon_bench_pages():
    """The CTRL+12 weapon bench's pages: the nine ordinary weapons, then the magical
    roster split into tier 4 (focused) and tier 5 (unleashed) so each page fits the
    bench's nine keys (1-9). Roster order within a page follows WEAPONS' insertion
    order, keeping the on-screen list stable run to run."""
    ordinary = ["%s_%s" % (mat, typ)
               for mat in ("bone", "bronze", "steel")
               for typ in ("sword", "axe", "hammer")]
    tier4 = [key for key, g in WEAPONS.items() if g.tier == 4]
    tier5 = [key for key, g in WEAPONS.items() if g.tier == 5]
    return [ordinary, tier4, tier5]


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
        if codex.identified(self.flavor):
            return self.true_name
        # unidentified: shown as the look it wears this game, not its own fixed look
        return CONSUMABLES[codex.look(self.flavor)].unknown_name

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
    # the enchant scrolls are the deep-game scaling path -- keep them reliably in reach
    # from floor 8. drawn from (rng, depth) only, so it does not break bit-identicality.
    if kind == "scroll" and depth >= 8 and rng.random() < 0.15:
        return rng.choice(["krav", "dwen"])
    tier = _consumable_tier(rng, depth)
    if tier == "common":
        return rng.choice(common)
    return rng.choice(_TIER_POOLS.get((kind, tier)) or common)


def gear_pool(depth):
    """Armour and boots that can drop at a given depth. Weapons are NOT here -- they are
    placed at generation time (see roll_floor_weapons)."""
    pool = []
    for table in (ARMOURS, BOOTS):
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


# The magical weapons a floor can actually DROP. The two mini-boss rewards -- Windfang
# (T4) and the Scimitar of the Void (T5) -- are excluded: they come only from beating a
# mini-boss, never from the floor.
FINDABLE_MAGICAL = {
    4: ["rapier", "brand", "betrayers_edge", "fulgurite", "winters_edge",
        "sacrificial_dagger"],
    5: ["basilisk_maul", "pyroclast", "reapers_whisper", "kris", "glacial_flail"],
}

FINDABLE_MAGICAL_KEYS = set(FINDABLE_MAGICAL[4]) | set(FINDABLE_MAGICAL[5])


def is_magical(key):
    """A magical weapon (tier 4 or 5). The single source of truth for the ledger."""
    return key in WEAPONS and WEAPONS[key].tier >= 4


def roll_magical(rng, depth):
    """The rare magical slot for floors 8-20. Returns (key, 0) or None. Present-chance is
    low and declines with depth (fewer adventurers died this deep); if a magical is
    present, its tier is a depth crossover -- Tier-5's share rises with depth -- and the
    specific weapon is drawn from the findable pool. Draws only from (rng, depth), never
    the Kodex, so blind and omniscient runs stay bit-identical."""
    present = 0.18 if depth <= 11 else 0.15 if depth <= 15 else 0.12
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    return (rng.choice(FINDABLE_MAGICAL[tier]), 0)


def roll_deep_steel(rng, depth):
    """The non-magical slot on floors 8-14: an ENHANCED Steel weapon (never +0), the
    masterwork a strong adventurer carried down before dying. Present-chance decays from
    70% at floor 8 to 0 at floor 15; the +3 chance climbs with depth. Returns
    ("steel_<type>", bonus) with bonus in (1, 2, 3), or None. Draws only from (rng, depth)."""
    if depth >= 15:
        return None
    present = 0.70 * (15 - depth) / 7.0          # 70% at 8 ... 10% at 14 ... 0 at 15
    if rng.random() >= present:
        return None
    wtype = rng.choice(["sword", "axe", "hammer"])
    if rng.random() < (depth - 7) * 0.05:        # +3 masterwork: 5% at 8 ... 35% at 14
        bonus = 3
    else:
        bonus = 2 if rng.random() < 0.35 else 1
    return ("steel_%s" % wtype, bonus)


def roll_ordinary(rng, depth):
    """Floors 1-7: the one ordinary weapon a floor may hold (Plan 1 of the rebalance).
    Floor 1 is a guaranteed unenhanced Bone Axe. Returns (key, bonus) or None. Unchanged
    behaviour from the original roll_floor_weapon for these floors."""
    if depth == 1:
        return ("bone_axe", 0)
    if rng.random() >= 0.80:
        return None
    material = "bone" if depth <= 2 else "bronze" if depth <= 4 else "steel"
    wtype = rng.choice(["sword", "axe", "hammer"])
    bonus = 0
    if rng.random() < (depth - 1) * 0.10:          # 10% on 2 ... 60% on 7
        bonus = 2 if rng.random() < 0.25 else 1
    return ("%s_%s" % (material, wtype), bonus)


def roll_floor_weapons(rng, depth):
    """Every weapon a floor places at generation, as a list of (key, bonus) -- 0, 1, or 2.
    Floors 1-7: the single ordinary weapon. Floors 8-14: an enhanced-Steel find AND a rare
    magical (up to two). Floors 15-20: the rare magical only (the steel slot is spent by
    15). Deterministic on (rng, depth), never the Kodex, so a seed's floors are identical
    for a blind and an omniscient hero."""
    if depth <= 7:
        w = roll_ordinary(rng, depth)
        return [w] if w else []
    out = []
    steel = roll_deep_steel(rng, depth)            # None on floors 15+
    if steel:
        out.append(steel)
    magical = roll_magical(rng, depth)
    if magical:
        out.append(magical)
    return out


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
