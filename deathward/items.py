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

from . import config


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

    def __init__(self, key, name, tier, defense, speed_mod=0, trait=None, note="",
                 bonus=0):
        self.key, self.name, self.tier = key, name, tier
        self.defense, self.speed_mod, self.trait, self.note = defense, speed_mod, trait, note
        self.bonus = bonus                # masterwork + scroll enchant, per-instance

    def copy(self, bonus=None):
        return Armour(self.key, self.name, self.tier, self.defense, self.speed_mod,
                      self.trait, self.note,
                      self.bonus if bonus is None else bonus)

    def desc(self, bonus=None):
        b = self.bonus if bonus is None else bonus
        s = "%d def" % (self.defense + b)
        if self.speed_mod:
            s += ", %+d spd" % self.speed_mod
        return s + ("  |  " + self.note if self.note else "")


class Boots:
    slot = "boots"

    def __init__(self, key, name, tier, speed, trait=None, note="", defense=0,
                 wake_radius=0):
        self.key, self.name, self.tier = key, name, tier
        self.speed, self.trait, self.note = speed, trait, note
        self.defense = defense            # armoured boots (mail/plate); 0 for the rest
        self.wake_radius = wake_radius    # stealth boots: tiles a monster wakes within; 0 = normal

    def desc(self):
        s = "%+d spd" % self.speed
        if self.defense:
            s += ", %+d def" % self.defense
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
    # A clean four-rung leather/mail/plate ladder sharing the material vocabulary of
    # ordinary boots. A sidegrade tradeoff, not a power ladder: more defense costs more
    # speed, and armour + boots spend from the SAME speed budget. No traits -- thorns and
    # wraithsilk graduate to the magical roster.
    "rags":    Armour("rags", "Padded Rags", 0, 0),
    "leather": Armour("leather", "Leather Jerkin", 1, 2, 0),
    "mail":    Armour("mail", "Mail Shirt", 2, 3, -10),
    "plate":   Armour("plate", "Full Plate", 3, 4, -20),
    # --- magical (floors 8+): found unenhanced, DWEN-enchantable. Each a survival
    # identity, not a bigger number. thorn + silk return from the graduated ordinary
    # pieces. Reactive pieces trigger on being struck, gated by player.armour_cd.
    "thorn":   Armour("thorn", "Thorned Cuirass", 4, 3, -5, "thorns",
                      "returns 2 damage to anything that hits you"),
    "silk":    Armour("silk", "Wraithsilk", 4, 2, 10, "wraithsilk",
                      "a wraith's touch cannot find you -- light, fast, ethereal"),
    "venom":   Armour("venom", "Venomweave", 4, 3, -5, "venom",
                      "an attacker is envenomed"),
    "cinder":  Armour("cinder", "Cinderplate", 4, 3, -5, "cinder",
                      "an attacker is set alight"),
    "glacial": Armour("glacial", "Glacial Mail", 4, 3, -5, "glacial",
                      "an attacker freezes solid"),
    "lifeweave": Armour("lifeweave", "Lifeweaver", 4, 3, -5, "lifeweave",
                        "it knits your wounds, turn after turn"),
    "bastion": Armour("bastion", "Bastion", 5, 4, -15, "bastion",
                      "no single blow lands harder than it allows"),
    "lastbreath": Armour("lastbreath", "Last Breath", 5, 4, -10, "lastbreath",
                         "the first killing blow is refused, once"),
    "blinding": Armour("blinding", "Blinding Light", 5, 3, -5, "blinding",
                       "struck, it flares -- everything near you reels"),
    "stonegolem": Armour("stonegolem", "Stone Golem's Chest", 5, 5, 0, None,
                         "heavy as stone, yet it never slows you"),
    "hades":   Armour("hades", "Robe of Hades", 5, 3, 0, "hades",
                      "struck, it answers in fire that will not touch you"),
    "fade":    Armour("fade", "Fadecloak", 4, 2, 10, "fade",
                      "every fourth blow, you are simply not there"),
    "nightcloak": Armour("nightcloak", "Nightcloak", 5, 3, 0, "nightcloak",
                         "the dark keeps you until you break it"),
    # --- boss-reserved (never drops from the floor; see FINDABLE_MAGICAL_ARMOUR) ---
    "shade":   Armour("shade", "Shademail", 4, 3, 0, "shade",
                      "the stone parts for you -- for a while"),
}

BOOTS = {
    # --- ordinary (floors 1-7): a fast<->tanky tradeoff, no traits. Keys are
    # boots_-prefixed so leather/plate do not clobber the armour of the same name
    # in the flat ALL_GEAR namespace.
    "sandals":      Boots("sandals", "Worn Sandals", 0, 0),
    "boots_leather": Boots("boots_leather", "Leather Boots", 1, 10),
    "boots_mail":    Boots("boots_mail", "Mail Boots", 2, 0, defense=1),
    "boots_plate":   Boots("boots_plate", "Plate Boots", 3, -10, defense=2),
    # --- magical (floors 8+): the exotic five, relocated intact (Plan 2 reworks)
    "swift":    Boots("swift", "Sandals of Mercury", 4, 25),
    "soft":     Boots("soft", "Padded Soles", 4, 10,
                      note="so quiet that monsters notice you only up close", wake_radius=4),
    "blink":    Boots("blink", "Boots of Blinking", 4, 15, "blink",
                      "SHIFT+dir to leap three tiles"),
    "ironshod": Boots("ironshod", "Ironshod Boots", 4, 5, "kick",
                      "your blows knock the struck thing back"),
    "emberstride": Boots("emberstride", "Emberstride", 4, 0, "emberstride",
                         "the ice cannot take feet that smoulder", defense=2),
    "rimewalkers": Boots("rimewalkers", "Rimewalkers", 4, 0, "rimewalkers",
                         "frost-shod -- fire finds no purchase", defense=2),
    "wind":     Boots("wind", "Windwalkers", 5, 40),
    "featherfall": Boots("featherfall", "Featherfall", 5, 25, "featherfall",
                         "you drift above the floor -- no trap can find your feet"),
    "thor":     Boots("thor", "Thor's Boots", 5, 10, "thor",
                      "every blow scatters all that stands near you"),
    "slipstep": Boots("slipstep", "Slipstep", 5, 10, "slipstep",
                      "every fourth wound flings you clear and staggers the striker"),
    "whisperstep": Boots("whisperstep", "Whisperstep", 5, 10,
                         note="you pass like a rumour -- nothing wakes until you are on it",
                         wake_radius=2),
    "phantom":  Boots("phantom", "Phantom Boots", 4, 0, "phantom",
                      "sometimes the blow finds only the ghost of you"),
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


def boots_bench_pages():
    """The CTRL+56 boots bench's pages: the ordinary boots, then the magical roster split
    into tier 4 and tier 5, so every boot stays reachable through a single digit (1-9).
    Order within a page follows BOOTS' insertion order, keeping the on-screen list stable
    run to run."""
    ordinary = [key for key, g in BOOTS.items() if g.tier <= 3]
    tier4 = [key for key, g in BOOTS.items() if g.tier == 4]
    tier5 = [key for key, g in BOOTS.items() if g.tier == 5]
    return [ordinary, tier4, tier5]


def armour_bench_pages():
    """The CTRL+34 armour bench's pages: the ordinary armour, then the magical roster split
    into tier 4 and tier 5, so every piece stays reachable through a single digit (1-9).
    Order within a page follows ARMOURS' insertion order, keeping the on-screen list stable
    run to run."""
    ordinary = [key for key, g in ARMOURS.items() if g.tier <= 3]
    tier4 = [key for key, g in ARMOURS.items() if g.tier == 4]
    tier5 = [key for key, g in ARMOURS.items() if g.tier == 5]
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
    """Empty. Weapons, boots AND armour are all generation-placed now (roll_floor_weapons
    / roll_floor_boots / roll_floor_boots_magical / roll_floor_armour), scarce and
    one-per-floor. Kept as a hook so roll_loot's gear branch falls back to gold."""
    return []


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


# The magical boots a floor can DROP -- all 12 are findable (no mini-boss-reserved boots).
FINDABLE_MAGICAL_BOOTS = {
    4: ["swift", "soft", "blink", "ironshod", "emberstride", "rimewalkers", "phantom"],
    5: ["wind", "featherfall", "thor", "slipstep", "whisperstep"],
}
FINDABLE_MAGICAL_BOOT_KEYS = set(FINDABLE_MAGICAL_BOOTS[4]) | set(FINDABLE_MAGICAL_BOOTS[5])


def is_magical_boot(key):
    """A magical boot (tier 4 or 5). The single source of truth for the boots ledger."""
    return key in BOOTS and BOOTS[key].tier >= 4


def roll_floor_boots_magical(rng, depth, exclude=()):
    """The rare magical-boots slot for floors 8-20: at most one magical boot per floor,
    one-per-game unique. `exclude` (the already-generated boot keys) filters the chosen
    tier's pool; if that tier is exhausted, none drops. Draws only from (rng, depth, exclude)
    -- run-history, never the Kodex -- so blind and omniscient runs stay bit-identical.
    Returns a boot key, or None. Boots carry no enhancement, so there is no bonus."""
    if depth < 8:
        return None
    present = 0.14 if depth <= 11 else 0.12 if depth <= 15 else 0.10
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    pool = [k for k in FINDABLE_MAGICAL_BOOTS[tier] if k not in exclude]
    if not pool:
        return None
    return rng.choice(pool)


# The magical armour a floor can DROP. fade joined in Phase 2; shade/nightcloak stay
# boss-reserved, like Windfang/Void.
FINDABLE_MAGICAL_ARMOUR = {
    4: ["thorn", "silk", "venom", "cinder", "glacial", "lifeweave", "fade"],
    5: ["bastion", "lastbreath", "blinding", "stonegolem", "hades"],
}
FINDABLE_MAGICAL_ARMOUR_KEYS = (set(FINDABLE_MAGICAL_ARMOUR[4])
                                | set(FINDABLE_MAGICAL_ARMOUR[5]))


def is_magical_armour(key):
    """A magical armour (tier 4 or 5). Single source of truth for the armour ledger."""
    return key in ARMOURS and ARMOURS[key].tier >= 4


def _band_chance(bands, depth):
    """The present-chance for `depth` from a list of (lo, hi, chance) bands, or 0.0."""
    for lo, hi, chance in bands:
        if lo <= depth <= hi:
            return chance
    return 0.0


def roll_floor_armour_magical(rng, depth, exclude=()):
    """The rare magical-armour slot for floors 8-19: at most ONE piece per floor.
    T5 is rolled first (its own deep-weighted band); only if it misses is T4 rolled --
    so P(any) = p5 + (1-p5)*p4. One-per-game unique (exclude the already-generated); a
    rolled tier whose pool is exhausted falls through to the other tier. Draws only from
    (rng, depth, exclude) -- never the Kodex -- so blind and omniscient runs stay
    bit-identical. Returns an armour key, or None."""
    if depth < 8:
        return None
    for tier, bands in ((5, config.ARMOUR_MAGICAL_T5_BANDS),
                        (4, config.ARMOUR_MAGICAL_T4_BANDS)):
        chance = _band_chance(bands, depth)
        if chance <= 0.0:
            continue
        if rng.random() < chance:
            pool = [k for k in FINDABLE_MAGICAL_ARMOUR[tier] if k not in exclude]
            if pool:
                return rng.choice(pool)
            # tier present but exhausted -- fall through to the other tier
    return None


def roll_magical(rng, depth, exclude=()):
    """The rare magical slot for floors 8-20. `exclude` is the set of magical keys already
    generated this game (absolute uniqueness): the chosen tier is filtered to its still-in-
    pool weapons, and if that tier is exhausted no magical drops. Draws only from
    (rng, depth) and `exclude` -- run-history, never the Kodex -- so blind and omniscient
    runs stay bit-identical."""
    present = 0.18 if depth <= 11 else 0.15 if depth <= 15 else 0.12
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    pool = [k for k in FINDABLE_MAGICAL[tier] if k not in exclude]
    if not pool:
        return None
    return (rng.choice(pool), 0)


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
    """Floors 2-7: the one ordinary weapon a floor may hold. Floor 1 places NO random
    weapon -- its only gear is the coin-flip gift (Bone Sword or Leather Jerkin), placed
    in dungeon.py. Returns (key, bonus) or None."""
    if depth == 1:
        return None
    if rng.random() >= 0.80:
        return None
    material = "bone" if depth <= 2 else "bronze" if depth <= 4 else "steel"
    wtype = rng.choice(["sword", "axe", "hammer"])
    bonus = 0
    if rng.random() < (depth - 1) * 0.10:          # 10% on 2 ... 60% on 7
        bonus = 2 if rng.random() < 0.25 else 1
    return ("%s_%s" % (material, wtype), bonus)


def roll_floor_weapons(rng, depth, exclude=()):
    """Every weapon a floor places at generation, as a list of (key, bonus) -- 0, 1, or 2.
    Floors 1-7: the single ordinary weapon. Floors 8-14: an enhanced-Steel find AND a rare
    magical (up to two). Floors 15-20: the rare magical only (the steel slot is spent by
    15). Deterministic on (rng, depth), never the Kodex, so a seed's floors are identical
    for a blind and an omniscient hero. `exclude` is the already-generated magical set,
    threaded to the magical slot for uniqueness."""
    if depth <= 7:
        w = roll_ordinary(rng, depth)
        return [w] if w else []
    out = []
    steel = roll_deep_steel(rng, depth)            # None on floors 15+
    if steel:
        out.append(steel)
    magical = roll_magical(rng, depth, exclude=exclude)
    if magical:
        out.append(magical)
    return out


# The ordinary boots a floor may place: at most ONE, found-only, generation-placed like the
# weapons (never from the generic loot pool). Banded by depth -- lower unlocks carried from the
# ordinary tier, upper cutoffs so the deep floors are magical territory: none on floor 1 or past
# floor 15. When several are valid the choice is UNIFORM -- ordinary boots are a speed<->defense
# tradeoff, not a power ladder, so you find one of the currently-available options and decide.
ORDINARY_BOOT_BANDS = (
    ("boots_leather", 2, 10),
    ("boots_mail", 3, 15),
    ("boots_plate", 5, 15),
)


def roll_floor_boots(rng, depth):
    """The floor's single ordinary boot, or none -- a list of 0 or 1 boot keys. 50% present-
    chance on a floor with any valid boot (floors 2-15); the boot is chosen uniformly among
    those valid at this depth. Deterministic on (rng, depth); reads nothing else, so blind and
    omniscient runs of a seed stay bit-identical."""
    valid = [key for key, lo, hi in ORDINARY_BOOT_BANDS if lo <= depth <= hi]
    if not valid or rng.random() >= 0.50:
        return []
    return [rng.choice(valid)]


# The ordinary armour a floor may place: at most ONE, found-only, generation-placed like
# the weapons and boots (never from the generic loot pool). Uniform among valid pieces --
# armour is a defense<->speed tradeoff sharing the speed budget with boots, not a power
# ladder. Banded by depth: none on floor 1 (the coin-flip gift) or past 15 (magical
# territory). Deep floors (8-15) layer a MASTERWORK +1/+2 (never +3) onto the piece.
ARMOUR_BANDS = (
    ("leather", 2, 10),
    ("mail", 3, 15),
    ("plate", 5, 15),
)


def _armour_present_chance(depth):
    """A gentle upward ramp, more generous than boots' flat 50%."""
    if depth <= 4:
        return 0.55
    if depth <= 8:
        return 0.65
    if depth <= 12:
        return 0.75
    return 0.80


def _armour_masterwork_bonus(rng, depth):
    """Floors 8-15: a chance the found armour is masterwork. +1 or +2, NEVER +3 (a +3
    Full Plate plus Plate Boots is virtually invulnerable). Below floor 8, always +0, and
    NO rng is drawn (determinism: shallow floors must not consume a masterwork draw)."""
    if depth < 8:
        return 0
    if rng.random() >= 0.25 + (depth - 8) * 0.05:      # 25% at 8 ... 60% at 15
        return 0
    return 2 if rng.random() < 0.15 + (depth - 8) * 0.05 else 1   # +2 share 15%..50%


def roll_floor_armour(rng, depth):
    """The floor's single ordinary armour, or none -- a list of 0 or 1 (key, bonus) pairs.
    Present-chance ramps with depth; the piece is chosen uniformly among those valid at
    this depth; deep floors layer a masterwork bonus. Deterministic on (rng, depth); reads
    nothing else, so blind and omniscient runs of a seed stay bit-identical."""
    valid = [key for key, lo, hi in ARMOUR_BANDS if lo <= depth <= hi]
    if not valid or rng.random() >= _armour_present_chance(depth):
        return []
    key = rng.choice(valid)
    return [(key, _armour_masterwork_bonus(rng, depth))]


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
