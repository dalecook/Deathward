"""The hero. Fragile, ignorant, and extremely persistent."""

from . import config
from .items import ARMOURS, BOOTS, CONSUMABLES, STARTING, WEAPONS


class Player:
    def __init__(self):
        self.x = self.y = 0
        self.max_hp = config.BASE_HP
        self.hp = self.max_hp
        self.gold = 0
        # you start the run ready to move. otherwise the first action costs two
        # ticks and the dungeon gets a free swing before you have taken a step.
        self.energy = config.ACT_COST
        self.weapon = WEAPONS[STARTING[0]]
        self.armour = ARMOURS[STARTING[1]]
        self.boots = BOOTS[STARTING[2]]
        # six slots; each is None or [flavor, count] with count <= STACK_MAX
        self.slots = [None] * config.PACK_SLOTS
        self.poison = 0
        self.stuck = 0            # turns spent climbing out of a pit
        self.haste = 0
        self.might = 0
        self.stoneskin = 0        # turns of hardened hide: extra defence
        self.regen = 0            # turns of knitting flesh: a little healing each turn
        self.vigor = 0            # temporary hit points that soak blows before real hp
        self.vigor_t = 0          # turns the vigour lasts before it fades unused
        self.weak = 0             # turns of sapped strength: your blows land softer
        self.berserk = 0          # turns of rage: harder and faster, but reckless
        self.resist = 0           # turns of warding: incoming damage is halved
        self.levitate = 0         # turns afloat: pressure traps and pits ignore you
        self.invisible = 0        # turns unseen: nothing can track you (breaks on attack)
        self.confused = 0         # turns your steps go where they please, not where you point
        self.heroism = 0          # turns of the hero's draught: harder, faster, tougher
        self.sanctuary = 0        # turns nothing can lay a blow on you
        self.phoenix = False      # a Phoenix draught: the next death is refused, once
        self.enchants = {}        # gear-key -> permanent +bonus (enchant scrolls)
        self.frozen = 0           # beholder: turns you cannot act while the world does
        # a NEGATIVE potion, once identified, is not swallowed -- it is wiped down the
        # blade and spent on the very next strike you land. one coat, one strike, and
        # you have to decide which enemy gets it. None, or the potion's effect string
        # ("poison" | "weak"): the same mechanism for every bad flask.
        self.blade_coat = None
        self.depth = 1
        self.kills = 0
        # the gear key of the once-per-game gift, while you are carrying it. it goes
        # onto your corpse when you die, because it is the only one that exists.
        self.gift = None

    # --- derived --------------------------------------------------------
    def speed(self):
        s = config.BASE_SPEED + self.boots.speed + self.armour.speed_mod
        if self.haste > 0:
            s += 50
        if self.berserk > 0:
            s += 40
        if self.heroism > 0:
            s += 40
        return max(30, s)

    STONESKIN_DEF = 4         # how much the grey potion hardens you

    @property
    def defense(self):
        d = self.armour.defense + self.enchants.get(self.armour.key, 0)
        if self.stoneskin > 0:
            d += self.STONESKIN_DEF
        if self.heroism > 0:
            d += 3
        return d

    def damage_roll(self, rng):
        d = self.weapon.roll(rng) + self.enchants.get(self.weapon.key, 0)
        if self.might > 0:
            d += 3
        if self.berserk > 0:
            d += 6               # rage hits appreciably harder than might
        if self.heroism > 0:
            d += 5
        if self.weak > 0:
            d = max(1, d - 3)     # sapped, but a blow always lands for at least 1
        return d

    def equip(self, gear):
        old = None
        if gear.slot == "weapon":
            old, self.weapon = self.weapon, gear
        elif gear.slot == "armour":
            old, self.armour = self.armour, gear
        elif gear.slot == "boots":
            old, self.boots = self.boots, gear
        return old

    def gear_key(self, slot):
        return {"weapon": self.weapon, "armour": self.armour,
                "boots": self.boots}[slot].key

    def gear_display(self, slot):
        """(name, desc) for an equipped slot, with any enchantment folded into BOTH.
        A Bronze Sword enchanted twice reads 'Bronze Sword +2' with '4-7 dmg'."""
        g = {"weapon": self.weapon, "armour": self.armour, "boots": self.boots}[slot]
        n = self.enchants.get(g.key, 0)
        name = "%s +%d" % (g.name, n) if n else g.name
        desc = g.desc(n) if slot in ("weapon", "armour") else g.desc()
        return name, desc

    # --- per-turn -------------------------------------------------------
    def tick_effects(self, world):
        if self.poison > 0:
            self.poison -= 1
            world.hurt_player(1, "poison", silent=True)
            if self.poison == 0 and self.hp > 0:
                world.log("The poison burns itself out.", config.DIM)
        if self.haste > 0:
            self.haste -= 1
            if self.haste == 0:
                world.log("Your unnatural speed fades.", config.DIM)
        if self.might > 0:
            self.might -= 1
            if self.might == 0:
                world.log("The fury drains out of your arms.", config.DIM)
        if self.stoneskin > 0:
            self.stoneskin -= 1
            if self.stoneskin == 0:
                world.log("Your skin softens back to flesh.", config.DIM)
        if self.regen > 0:
            self.regen -= 1
            got = self.heal(2)
            if got and self.hp < self.max_hp:
                world.add_fx("pulse", self.x, self.y, color=config.HEAL, life=0.3)
            if self.regen == 0:
                world.log("The knitting warmth fades.", config.DIM)
        if self.vigor > 0:
            self.vigor_t -= 1
            if self.vigor_t <= 0:
                self.vigor = 0
                self.vigor_t = 0
                world.log("The last of your vigour fades unspent.", config.DIM)
        if self.weak > 0:
            self.weak -= 1
            if self.weak == 0:
                world.log("Your strength seeps back.", config.DIM)
        if self.berserk > 0:
            self.berserk -= 1
            if self.berserk == 0:
                world.log("The red mist clears. You feel the fight in your bones.",
                          config.DIM)
        if self.resist > 0:
            self.resist -= 1
            if self.resist == 0:
                world.log("The ward around you fades.", config.DIM)
        if self.levitate > 0:
            self.levitate -= 1
            if self.levitate == 0:
                world.log("Your feet settle back onto the stone.", config.DIM)
        if self.invisible > 0:
            self.invisible -= 1
            if self.invisible == 0:
                world.log("The light stops bending. You are visible again.", config.DIM)
        if self.confused > 0:
            self.confused -= 1
            if self.confused == 0:
                world.log("The floor stops swimming. Your feet obey you again.",
                          config.DIM)
        if self.heroism > 0:
            self.heroism -= 1
            if self.heroism == 0:
                world.log("The hero's fire burns down to embers. You are only you "
                          "again.", config.DIM)
        if self.sanctuary > 0:
            self.sanctuary -= 1
            if self.sanctuary == 0:
                world.log("The stillness around you breaks. They can reach you again.",
                          config.DIM)

    def heal(self, n):
        before = self.hp
        self.hp = min(self.max_hp, self.hp + n)
        return self.hp - before

    def carried_flavors(self):
        return list(self.pack)

    # --- the pack: six slots, three of one thing per slot -----------------
    @property
    def pack(self):
        """Everything you are carrying, flattened, in slot order."""
        out = []
        for s in self.slots:
            if s:
                out.extend([s[0]] * s[1])
        return out

    @pack.setter
    def pack(self, flavors):
        """Rebuild the slots from a flat list, obeying the stacking rules."""
        self.slots = [None] * config.PACK_SLOTS
        for f in flavors:
            self.pack_add(f)

    def slot_of(self, index):
        return self.slots[index] if 0 <= index < len(self.slots) else None

    def can_take(self, flavor):
        """Is there anywhere for one more of this to go?"""
        for s in self.slots:
            if s and s[0] == flavor and s[1] < config.STACK_MAX:
                return True
        return any(s is None for s in self.slots)

    def pack_add(self, flavor):
        """Top up the lowest stack of this type that has room; failing that, open the
        lowest empty slot. Returns False if there is nowhere for it to go."""
        for s in self.slots:
            if s and s[0] == flavor and s[1] < config.STACK_MAX:
                s[1] += 1
                return True
        for i, s in enumerate(self.slots):
            if s is None:
                self.slots[i] = [flavor, 1]
                return True
        return False

    def pack_remove(self, index):
        """Take one out of slot `index`, then consolidate. Returns the flavor, or
        None if that slot is empty."""
        s = self.slot_of(index)
        if not s:
            return None
        flavor = s[0]
        s[1] -= 1
        if s[1] <= 0:
            self.slots[index] = None
        self.consolidate(flavor)
        return flavor

    def consolidate(self, flavor):
        """Items slide DOWN, never up.

        Walk the slots in order; any stack of this type that is short pulls from the
        NEXT later stack of the same type -- and only takes as much as it needs. A
        later slot that gives away its last item becomes empty. Nothing of a different
        type ever moves, so slot numbers stay put.
        """
        for i, s in enumerate(self.slots):
            if not s or s[0] != flavor:
                continue
            while s[1] < config.STACK_MAX:
                donor = None
                for j in range(i + 1, len(self.slots)):
                    d = self.slots[j]
                    if d and d[0] == flavor:
                        donor = j
                        break
                if donor is None:
                    break
                need = config.STACK_MAX - s[1]
                give = min(need, self.slots[donor][1])
                s[1] += give
                self.slots[donor][1] -= give
                if self.slots[donor][1] <= 0:
                    self.slots[donor] = None

    @property
    def pack_is_full(self):
        """No empty slot -- so nothing NEW can come in.

        Note this can be true with 18 items (six maxed stacks) or with only 6 (six
        different things, one each). What matters is that there is no free slot, so a
        type you are not already carrying has nowhere to go. Whether one MORE of
        something you already hold will fit is `can_take(flavor)`, not this.
        """
        return not any(s is None for s in self.slots)

    def free_slots(self):
        return sum(1 for s in self.slots if s is None)

    def pack_counts(self):
        counts = {}
        for s in self.slots:
            if s:
                counts[s[0]] = counts.get(s[0], 0) + s[1]
        return counts
