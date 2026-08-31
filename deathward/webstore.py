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

"""Where the save actually lives, split by platform.

Native CPython has a real filesystem: the save is JSON at config.SAVE_PATH.
Under pygbag's Pyodide/emscripten runtime there is no such disk -- a page
reload starts a fresh virtual filesystem -- so the web build persists through
the browser's window.localStorage instead, which pygbag exposes synchronously
to Python via `from platform import window`.

Both branches share the same silent-degradation contract: if persistence is
unavailable for any reason (a read-only disk, a full or disabled localStorage
in private browsing), reads return None and writes are no-ops. No exception
reaches the caller either way -- the game just doesn't remember, exactly as it
already didn't on native if the save file couldn't be written.
"""

import json
import os
import sys

from . import config

_WEB_KEY = "deathward_save"


def _is_web():
    return sys.platform == "emscripten"


def load_save():
    """The saved dict, or None if there is nothing to load (or it can't be read)."""
    if _is_web():
        try:
            from platform import window
            raw = window.localStorage.getItem(_WEB_KEY)
        except Exception:
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None
    if not os.path.exists(config.SAVE_PATH):
        return None
    try:
        with open(config.SAVE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_save(data):
    """Persist data (a JSON-able dict). Failures are swallowed."""
    if _is_web():
        try:
            from platform import window
            window.localStorage.setItem(_WEB_KEY, json.dumps(data))
        except Exception:
            pass
        return
    try:
        with open(config.SAVE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass


def delete_save():
    """Forget the save entirely. Failures are swallowed."""
    if _is_web():
        try:
            from platform import window
            window.localStorage.removeItem(_WEB_KEY)
        except Exception:
            pass
        return
    try:
        if os.path.exists(config.SAVE_PATH):
            os.remove(config.SAVE_PATH)
    except OSError:
        pass
