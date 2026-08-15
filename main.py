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

"""DEATHWARD -- the WEB entry point.

pygbag requires the file it packages to be called `main.py`, to sit at the root of
the folder it is given, and to end in `asyncio.run(main())`. That is the whole reason
this file exists next to run_deathward.py: desktop players use that one, browsers get
this one, and both drive the identical coroutine in deathward.game.
"""

import asyncio

# pygbag decides which packages to fetch by SCANNING THIS FILE for imports. It does not
# follow them into the package, so without this line pygame is never installed and every
# `deathward` module fails on import against an empty stub. It is load-bearing, not tidy.
import pygame  # noqa: F401

from deathward.game import amain


async def main():
    await amain()


asyncio.run(main())
