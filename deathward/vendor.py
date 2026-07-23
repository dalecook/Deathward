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

"""The thing that trades.

It is not a shopkeeper and it is not a man. It stands very still on the deep floors,
it does not move, it cannot be attacked, and it will take your gold. It buys potions
and scrolls -- it has no interest whatsoever in your armour.

Gold in this game is otherwise only a number on a corpse. This is the one place it
becomes a decision: spend it now on something that might keep you alive, or carry it
deeper and lose it to the next thing that kills you.
"""

from . import config
from .items import CONSUMABLES, POTION_POOL, SCROLL_POOL

# what it will sell you, roughly. deeper stock costs a little more.
GEAR_PRICE = {1: 60, 2: 130, 3: 220}
POTION_PRICE = 30
SCROLL_PRICE = 40

# what it will pay you. it is not a charity.
SELL_FRACTION = 0.4


def price_of(kind, payload, depth):
    if kind == "gear":
        from .items import ALL_GEAR
        base = GEAR_PRICE.get(ALL_GEAR[payload].tier, 60)
    else:
        c = CONSUMABLES[payload]
        base = POTION_PRICE if c.kind == "potion" else SCROLL_PRICE
    return int(base + max(0, depth - config.VENDOR_MIN_DEPTH) * 6)


def sell_price_of(flavor, depth):
    """What it pays YOU. Potions and scrolls only -- it does not want your sword."""
    c = CONSUMABLES[flavor]
    base = POTION_PRICE if c.kind == "potion" else SCROLL_PRICE
    return max(5, int(base * SELL_FRACTION))


class Vendor:
    def __init__(self, x, y, depth, rng):
        self.x, self.y = x, y
        self.depth = depth
        self.stock = []          # list of (kind, payload)
        self._stock_up(rng, depth)

    def _stock_up(self, rng, depth):
        # Consumables only. Gear (weapons, boots, armour) is all found-only now -- none of
        # it enters gear_pool, so the vendor deals in potions and scrolls. (The eventual
        # richer vendor economy -- magical items at a high price -- is a later task.)
        for _ in range(rng.randint(2, 3)):
            self.stock.append(("item", rng.choice(POTION_POOL)))
        for _ in range(rng.randint(1, 2)):
            self.stock.append(("item", rng.choice(SCROLL_POOL)))

    def buys(self, flavor):
        """It takes potions and scrolls. Nothing else. Do not offer it your boots."""
        return flavor in CONSUMABLES

    def to_dict(self):
        return {"x": self.x, "y": self.y, "depth": self.depth,
                "stock": [list(s) for s in self.stock]}

    @classmethod
    def from_dict(cls, data):
        v = cls.__new__(cls)      # bypass __init__: do NOT re-roll the stock
        v.x, v.y = data["x"], data["y"]
        v.depth = data["depth"]
        v.stock = [tuple(s) for s in data["stock"]]
        return v
