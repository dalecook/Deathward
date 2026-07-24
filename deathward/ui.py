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

"""HUD, title, autopsy, kodex browser, victory."""

import math

import pygame

from . import config
from .codex import CAUSE_NAME, FACT_LIST, KODEX_TABS, TOTAL_FACTS, fact_title, facts_in
from .items import CONSUMABLES, gear_catalog
from .render import font, glyph

KODEX_TAB_LABELS = ["Monsters", "Traps", "Scrolls", "Potions", "Gear", "Lore"]


def text(surf, s, pos, size=15, color=config.INK, bold=False, center=False, right=False):
    img = font(size, bold).render(s, True, color)
    r = img.get_rect()
    if center:
        r.center = pos
    elif right:
        r.midright = pos
    else:
        r.topleft = pos
    surf.blit(img, r)
    return r


def wrap(s, size, width):
    f = font(size)
    words, lines, cur = s.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        if f.size(probe)[0] <= width:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _pulse(t, sp=1.0):
    return 0.5 + 0.5 * math.sin(t * sp * math.tau)


def draw_hud(surf, world, codex):
    y0 = config.H - config.HUD_H
    pygame.draw.rect(surf, (7, 8, 12), (0, y0, config.W, config.HUD_H))
    pygame.draw.line(surf, config.FAINT, (0, y0), (config.W, y0), 1)
    p = world.player

    # --- health ---------------------------------------------------------
    text(surf, "HP", (16, y0 + 12), 13, config.DIM)
    bw = 190
    pygame.draw.rect(surf, (34, 18, 22), (44, y0 + 12, bw, 14), border_radius=3)
    frac = max(0.0, p.hp / p.max_hp)
    col = config.HEAL if frac > 0.5 else (config.GOLD if frac > 0.25 else config.BLOOD)
    if frac > 0:
        pygame.draw.rect(surf, col, (44, y0 + 12, int(bw * frac), 14), border_radius=3)
    text(surf, "%d/%d" % (max(0, p.hp), p.max_hp), (44 + bw + 10, y0 + 11), 14, config.INK)

    # --- gear -----------------------------------------------------------
    rows = [
        ("WEAPON",) + p.gear_display("weapon"),
        ("ARMOUR",) + p.gear_display("armour"),
        ("BOOTS",) + p.gear_display("boots"),
    ]
    yy = y0 + 38
    for label, name, desc in rows:
        text(surf, label, (16, yy), 11, config.FAINT)
        text(surf, name, (80, yy - 2), 14, config.INK)
        text(surf, desc, (250, yy - 1), 12, config.DIM)
        yy += 21

    # --- status ---------------------------------------------------------
    sx = 560
    text(surf, "FLOOR", (sx, y0 + 10), 11, config.FAINT)
    text(surf, "%d/%d" % (world.depth, config.DEPTH_MAX), (sx, y0 + 24), 17,
         config.INK, bold=True)
    text(surf, "GOLD", (sx + 80, y0 + 10), 11, config.FAINT)
    text(surf, str(p.gold), (sx + 80, y0 + 24), 17, config.GOLD, bold=True)
    text(surf, "SPEED", (sx + 170, y0 + 10), 11, config.FAINT)
    text(surf, str(p.speed()), (sx + 170, y0 + 24), 17,
         config.MANA if p.speed() > 100 else config.INK, bold=True)
    text(surf, "DEATHS", (sx + 250, y0 + 10), 11, config.FAINT)
    text(surf, str(codex.deaths), (sx + 250, y0 + 24), 17, config.INK, bold=True)

    known, total = codex.progress()
    text(surf, "KODEX", (sx + 340, y0 + 10), 11, config.FAINT)
    pw = 150
    pygame.draw.rect(surf, (26, 30, 40), (sx + 340, y0 + 27, pw, 8), border_radius=3)
    if known:
        pygame.draw.rect(surf, config.PLAYER,
                         (sx + 340, y0 + 27, int(pw * known / total), 8), border_radius=3)
    text(surf, "%d/%d" % (known, total), (sx + 340 + pw + 8, y0 + 22), 12, config.DIM)

    # status effects
    eff = []
    if p.poison:
        eff.append(("POISONED %d" % p.poison, (140, 220, 120)))
    if p.haste:
        eff.append(("HASTE %d" % p.haste, config.MANA))
    if p.might:
        eff.append(("MIGHT %d" % p.might, config.GOLD))
    if p.stoneskin:
        eff.append(("STONESKIN %d" % p.stoneskin, (180, 184, 194)))
    if p.regen:
        eff.append(("REGEN %d" % p.regen, config.HEAL))
    if p.vigor:
        eff.append(("VIGOR %d" % p.vigor, (200, 214, 234)))
    if p.weak:
        eff.append(("WEAKENED %d" % p.weak, (170, 160, 100)))
    if p.berserk:
        eff.append(("RAGE %d" % p.berserk, (232, 92, 52)))
    if p.resist:
        eff.append(("WARDED %d" % p.resist, (60, 190, 176)))
    if p.levitate:
        eff.append(("AFLOAT %d" % p.levitate, (130, 206, 220)))
    if p.invisible:
        eff.append(("UNSEEN %d" % p.invisible, (190, 200, 220)))
    if p.heroism:
        eff.append(("HEROISM %d" % p.heroism, config.GOLD))
    if p.sanctuary:
        eff.append(("SANCTUARY %d" % p.sanctuary, (150, 210, 255)))
    if p.phoenix:
        eff.append(("PHOENIX", (255, 170, 70)))
    if p.confused:
        eff.append(("CONFUSED %d" % p.confused, (196, 130, 150)))
    if p.blade_coat == "poison":
        eff.append(("VENOMED BLADE", (150, 220, 130)))
    elif p.blade_coat == "weak":
        eff.append(("SAPPING BLADE", (200, 190, 120)))
    if p.frozen:
        eff.append(("FROZEN %d" % p.frozen, (150, 210, 255)))
    if p.stuck:
        eff.append(("IN A PIT", config.TRAP))
    ex = sx
    for s, c in eff:
        r = text(surf, s, (ex, y0 + 52), 12, c, bold=True)
        ex = r.right + 12

    # --- pack -----------------------------------------------------------
    # six FIXED slots. an empty slot is drawn as an empty slot, because the slot
    # number is the key you press, and it must not move under your fingers.
    text(surf, "PACK", (sx, y0 + 74), 11, config.FAINT)
    free = p.free_slots()
    text(surf, "%d/%d slots" % (config.PACK_SLOTS - free, config.PACK_SLOTS),
         (sx + 44, y0 + 74), 11,
         config.BLOOD if p.pack_is_full else config.FAINT, bold=p.pack_is_full)
    yy = y0 + 88
    for i in range(config.PACK_SLOTS):
        slot = p.slot_of(i)
        x = sx + (i % 2) * 250
        y = yy + (i // 2) * 16
        if slot is None:
            text(surf, "%d) --" % (i + 1), (x, y), 12, (52, 56, 70))
            continue
        flavor, n = slot
        c = CONSUMABLES[flavor]
        col = config.ITEM if codex.identified(flavor) else config.DIM
        label = "%d) %s%s" % (i + 1, c.name(codex),
                              "  x%d" % n if n > 1 else "")
        text(surf, label, (x, y), 12, col)

    text(surf, "I  pack", (config.W - 16, y0 + 76), 11, config.FAINT, right=True)
    text(surf, "?  help", (config.W - 16, y0 + 92), 11, config.FAINT, right=True)
    text(surf, "K  kodex", (config.W - 16, y0 + 108), 11, config.FAINT, right=True)


def draw_log_line(surf, world):
    """The single most recent log line, in its own strip just below the map -- roomy
    and readable, with a hint that L opens the whole thing."""
    top = config.TILE * config.VIEW_H
    pygame.draw.rect(surf, (12, 13, 18), (0, top, config.W, config.LOG_H))
    pygame.draw.line(surf, config.FAINT, (0, top), (config.W, top), 1)
    my = top + config.LOG_H // 2
    if world.messages:
        msg, mcol = world.messages[-1]
        text(surf, msg, (16, my - 9), 18, mcol)
    text(surf, "L  log", (config.W - 16, my - 8), 12, config.FAINT, right=True)


# --- the full-game log popup ---------------------------------------------
_LOG_TOP = 96
_LOG_LINE_H = 22


def _log_view_h():
    return (config.H - 40) - _LOG_TOP


def log_max_scroll(messages):
    """The furthest you can scroll: everything below the visible window, in pixels.
    Shared by the drawer and by open_log so the view opens at the newest line."""
    return max(0, len(messages) * _LOG_LINE_H - _log_view_h())


def draw_log(surf, messages, scroll, t):
    """The whole log for this game, scrollable. Newest at the bottom. Returns the max
    scroll offset so the caller can clamp."""
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 242))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "LOG", (cx, 34), 30, config.GOLD, bold=True, center=True)
    text(surf, "everything that has happened this game", (cx, 66), 13,
         config.DIM, center=True)

    max_scroll = log_max_scroll(messages)
    scroll = max(0, min(scroll, max_scroll))
    view_h = _log_view_h()
    surf.set_clip((0, _LOG_TOP, config.W, view_h))
    y = _LOG_TOP - scroll
    for msg, mcol in reversed(messages):        # most recent first, at the top
        if -_LOG_LINE_H <= (y - _LOG_TOP) <= view_h:
            text(surf, msg, (60, y), 15, mcol)
        y += _LOG_LINE_H
    surf.set_clip(None)

    if not messages:
        text(surf, "nothing has happened yet", (cx, _LOG_TOP + 40), 16,
             config.FAINT, center=True)
    text(surf, "UP / DOWN / PGUP / PGDN to scroll     L or ESC to close",
         (cx, config.H - 22), 12, config.FAINT, center=True)
    return max_scroll


def loot_rows(world, codex):
    """The menu, as (key, label, colour) rows. Split out from the drawing so the shape
    of the menu can be tested without a screen."""
    opts = world.loot_options()
    if not opts:
        return []
    rows = [(str(i + 1), o["label"], _loot_color(o, codex)) for i, o in enumerate(opts)]
    # G is ALWAYS offered, even for a single item. A key that means "take everything"
    # should not disappear just because "everything" happens to be one coin -- a menu
    # that changes shape under your fingers is a menu you have to re-read every time.
    rows.append(("G", "all", config.HEAL))
    return rows


def draw_loot_panel(surf, world, codex):
    """What is under your feet, and how to take it.

    Shown automatically the moment you step onto anything lootable -- a chest, a
    drop, your own body. Numbered, because a hoard is a decision: you should be able
    to take the gold and leave the potion you do not trust.
    """
    opts = world.loot_options()
    if not opts:
        return None
    rows = loot_rows(world, codex)

    hint = "press a number to take one thing"
    f = font(15)
    wid = max(f.size(lbl)[0] for _, lbl, _ in rows) + 70
    wid = max(wid, font(12).size(hint)[0] + 32)      # the footer must fit too
    wid = max(300, min(560, wid))
    h = 40 + len(rows) * 22 + 22
    x = 18
    y = config.H - config.HUD_H - h - 14

    card = pygame.Surface((wid, h), pygame.SRCALPHA)
    pygame.draw.rect(card, (14, 17, 24, 242), (0, 0, wid, h), border_radius=7)
    pygame.draw.rect(card, config.GOLD, (0, 0, wid, h), 2, border_radius=7)
    head = pygame.Surface((wid - 4, 24), pygame.SRCALPHA)
    head.fill((*config.GOLD, 28))
    card.blit(head, (2, 2))
    text(card, world.loot_source_name(), (14, 5), 13, config.GOLD, bold=True)

    yy = 34
    for num, label, col in rows:
        text(card, num + ".", (16, yy), 15, config.DIM, bold=True)
        text(card, label, (44, yy), 15, col)
        yy += 22

    text(card, hint, (16, h - 20), 12, config.FAINT)
    surf.blit(card, (x, y))
    return len(opts)


def _loot_color(o, codex):
    if o["kind"] == "gold":
        return config.GOLD
    if o["kind"] == "gear":
        return config.ITEM
    return config.ITEM if codex.identified(o["payload"]) else config.DIM


def draw_trade(surf, world, codex, t):
    """It buys potions and scrolls. It sells you whatever it has. It does not haggle,
    and it does not care whether you live."""
    from .vendor import price_of, sell_price_of

    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 232))
    surf.blit(layer, (0, 0))
    v = world.level.vendor
    p = world.player
    cx = config.W // 2

    text(surf, "IT OPENS ITS HANDS", (cx, 44), 34, config.VENDOR_COLOR,
         bold=True, center=True)
    text(surf, "your gold: %d" % p.gold, (cx, 88), 17, config.GOLD, center=True)

    # ---- left: what it sells ----
    lx = 100
    text(surf, "IT SELLS", (lx, 128), 15, config.INK, bold=True)
    text(surf, "press the number", (lx, 148), 12, config.FAINT)
    y = 176
    if not v or not v.stock:
        text(surf, "its hands are empty", (lx, y), 14, config.FAINT)
    for i, (kind, payload) in enumerate((v.stock if v else [])[:9]):
        cost = price_of(kind, payload, world.depth)
        afford = p.gold >= cost
        row = pygame.Rect(lx - 12, y - 6, 400, 40)
        pygame.draw.rect(surf, (16, 18, 24), row, border_radius=5)
        pygame.draw.rect(surf, config.VENDOR_COLOR if afford else (54, 50, 44),
                         row, 1, border_radius=5)
        text(surf, str(i + 1), (lx, y + 6), 17,
             config.INK if afford else config.FAINT, bold=True)
        label = world.loot_label(kind, payload)
        if len(label) > 32:                      # keep clear of the price column
            label = label[:31] + "…"
        text(surf, label, (lx + 28, y + 2), 14,
             config.ITEM if afford else config.FAINT)
        text(surf, "%dg" % cost, (lx + 372, y + 12), 15,
             config.GOLD if afford else config.FAINT, bold=True, right=True)
        y += 44

    # ---- right: what it will take ----
    rx = config.W - 500
    text(surf, "IT BUYS", (rx, 128), 15, config.INK, bold=True)
    text(surf, "potions and scrolls only     SHIFT + slot number", (rx, 148), 12,
         config.FAINT)
    y = 176
    empty = True
    for i in range(config.PACK_SLOTS):
        slot = p.slot_of(i)
        if not slot:
            continue
        empty = False
        flavor, n = slot
        paid = sell_price_of(flavor, world.depth)
        row = pygame.Rect(rx - 12, y - 6, 400, 40)
        pygame.draw.rect(surf, (16, 18, 24), row, border_radius=5)
        pygame.draw.rect(surf, (60, 66, 82), row, 1, border_radius=5)
        text(surf, "SHIFT+%d" % (i + 1), (rx, y + 8), 13, config.DIM, bold=True)
        text(surf, "%s%s" % (CONSUMABLES[flavor].name(codex),
                             "  x%d" % n if n > 1 else ""),
             (rx + 78, y + 2), 14,
             config.ITEM if codex.identified(flavor) else config.DIM)
        text(surf, "+%dg" % paid, (rx + 372, y + 12), 15, config.HEAL,
             bold=True, right=True)
        y += 44
    if empty:
        text(surf, "you have nothing it wants", (rx, y), 14, config.FAINT)

    text(surf, "ESC  walk away", (cx, config.H - 40), 16, config.PLAYER,
         center=True, bold=True)


def draw_sealed(surf, t):
    """You tried to walk out of the front door."""
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 5, 8, 232))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "THE PORTCULLIS HAS COME DOWN", (cx, 210), 34, config.BLOOD,
         bold=True, center=True)
    y = 274
    for ln in ["You came in through this gate. It is not a door any more.",
               "",
               "There is no way out of the Deathward but through it.",
               "The only way is down."]:
        text(surf, ln, (cx, y), 17, config.DIM if ln else config.DIM, center=True)
        y += 28

    g = _pulse(t, 0.9)
    text(surf, "any key", (cx, y + 34), 15,
         (int(90 + 60 * g), int(100 + 60 * g), int(120 + 60 * g)), center=True)


def draw_pack(surf, world, codex):
    """The pack, laid out as its six real slots, with a way to dump what you do not
    want. A carry limit is only fair if you can choose WHAT you are carrying."""
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 8, 12, 226))
    surf.blit(layer, (0, 0))
    p = world.player
    cx = config.W // 2

    text(surf, "THE PACK", (cx, 60), 38, config.INK, bold=True, center=True)
    free = p.free_slots()
    text(surf, "%d of %d slots used   |   a slot holds %d of one thing"
         % (config.PACK_SLOTS - free, config.PACK_SLOTS, config.STACK_MAX),
         (cx, 106), 15, config.DIM, center=True)

    sink = world.container_here()
    where = ("it goes into the chest you are standing on" if sink is not None
             else "it goes on the floor at your feet")
    text(surf, "nothing is destroyed -- %s" % where, (cx, 130), 14,
         config.FAINT, center=True)

    w = 560
    x0 = cx - w // 2
    y = 172
    for i in range(config.PACK_SLOTS):
        slot = p.slot_of(i)
        row = pygame.Rect(x0, y, w, 46)
        pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
        pygame.draw.rect(surf, (40, 46, 60) if slot is None else config.PLAYER,
                         row, 1, border_radius=6)
        text(surf, str(i + 1), (x0 + 18, y + 13), 20,
             config.DIM if slot is None else config.INK, bold=True)
        if slot is None:
            text(surf, "empty", (x0 + 54, y + 15), 15, (60, 66, 82))
        else:
            flavor, n = slot
            c = CONSUMABLES[flavor]
            col = config.ITEM if codex.identified(flavor) else config.DIM
            text(surf, c.name(codex), (x0 + 54, y + 8), 16, col)
            text(surf, "x%d" % n, (x0 + w - 24, y + 16), 16, config.INK,
                 bold=True, right=True)
            hint = "%d  drop one" % (i + 1)
            if n > 1:
                hint += "        SHIFT+%d  drop all %d" % (i + 1, n)
            text(surf, hint, (x0 + 54, y + 27), 12, config.FAINT)
        y += 52

    text(surf, "1-6  drop one        SHIFT + 1-6  drop the whole stack",
         (cx, y + 14), 15, config.PLAYER, center=True, bold=True)
    text(surf, "ESC / I / TAB  close", (cx, y + 40), 13, config.FAINT, center=True)


def draw_learned_banner(surf, fact, age, codex):
    """A fact discovered mid-run: over a corpse, on a sprung trap, in a drained flask.

    It slides in and then it STAYS. Nothing takes it away on a timer -- it clears when
    the player MOVES, which is to say when they have finished reading it. A lesson
    bought with blood should not evaporate while you are still on the second line.
    """
    if not fact:
        return
    slide = min(1.0, age / 0.28)                 # ease in, then hold
    fade = 1.0

    # never truncate a lesson mid-sentence -- the card grows to fit it
    lines = wrap(fact.text, 14, 560)
    h = 96 + len(lines) * 19
    w = 620
    x = (config.W - w) // 2
    y = int(-h + (18 + h) * slide)

    card = pygame.Surface((w, h), pygame.SRCALPHA)
    a = int(240 * fade)
    pygame.draw.rect(card, (16, 19, 26, a), (0, 0, w, h), border_radius=8)
    pygame.draw.rect(card, (*config.GOLD, int(220 * fade)), (0, 0, w, h), 2,
                     border_radius=8)
    head = pygame.Surface((w - 4, 24), pygame.SRCALPHA)
    head.fill((*config.GOLD, int(30 * fade)))
    card.blit(head, (2, 2))

    known, total = codex.progress()
    text(card, "KODEX  +1", (16, 5), 13, config.GOLD, bold=True)
    text(card, "%d/%d" % (known, total), (w - 16, 12), 12, config.DIM, right=True)
    text(card, fact_title(fact, codex), (16, 34), 19, config.INK, bold=True)
    text(card, "move on when you have read it", (16, h - 22), 12, config.FAINT)
    yy = 60
    for ln in lines:
        text(card, ln, (16, yy), 14, config.DIM)
        yy += 19
    surf.blit(card, (x, y))


def draw_help(surf):
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 7, 11, 236))
    surf.blit(layer, (0, 0))
    cx = config.W // 2
    text(surf, "DEATHWARD", (cx, 60), 40, config.INK, bold=True, center=True)
    rows = [
        ("move / attack", "WASD, arrows, or QEZC for diagonals -- HOLD to keep walking"),
        ("wait a turn", "SPACE or ."),
        ("standing on loot", "a menu appears: press its NUMBER to take one thing"),
        ("take everything", "G  (chests, drops, your own corpse)"),
        ("drink / read", "1-6  from the pack -- when you are NOT standing on loot"),
        ("the pack", "I or TAB -- six slots, three of one thing per slot"),
        ("drop something", "in the pack: 1-6 drops one, SHIFT+1-6 drops the stack"),
        ("descend", "> or ENTER, standing on the down stairs"),
        ("climb back up", "< or ENTER, standing on the up stairs (floors 2+)"),
        ("floor 1's gate", "shut. the only way out of the Deathward is through it"),
        ("leap 3 tiles", "SHIFT + direction  (needs Boots of Blinking)"),
        ("kodex", "K"),
        ("quit to title", "ESC"),
        ("", ""),
        ("CONTINUE (title)", "ENTER -- a new run; you keep the Kodex and your dead"),
        ("NEW GAME (title)", "N -- erases the Kodex, the dead, everything"),
    ]
    y = 140
    for k, v in rows:
        text(surf, k, (cx - 30, y), 16, config.INK, right=True)
        text(surf, v, (cx + 30, y - 9), 15, config.DIM)
        y += 34
    lines = [
        "You cannot see what you do not understand.",
        "A monster you have never been killed by is drawn as a '?' -- no name, no health,",
        "no warning of what it is about to do. A trap you have never triggered is drawn as",
        "clean floor. It still fires.",
        "",
        "Every death writes one true thing into your Kodex, and it is never something you",
        "already knew. That is the only progression in this game. There is no XP.",
    ]
    y += 16
    for ln in lines:
        text(surf, ln, (cx, y), 14, config.DIM, center=True)
        y += 21
    text(surf, "any key to go back", (cx, config.H - 40), 14, config.FAINT, center=True)


def draw_title(surf, codex, t):
    surf.fill(config.BG)
    cx = config.W // 2
    for i in range(50):
        a = t * 0.1 + i * 0.6
        r = 60 + i * 11
        x = cx + math.cos(a) * r * 1.4
        y = 230 + math.sin(a) * r * 0.42
        pygame.draw.circle(surf, (26 + i, 30 + i, 42 + i), (int(x), int(y)), 2)

    text(surf, "DEATHWARD", (cx, 170), 76, config.INK, bold=True, center=True)
    text(surf, "the dungeon does not get easier. you get harder to kill.",
         (cx, 232), 17, config.PLAYER, center=True)

    lines = [
        "Eight floors. Permadeath. A rusted shiv, padded rags and worn sandals.",
        "",
        "What you cannot explain, you cannot see: an unknown monster is a '?', an",
        "unknown trap is clean floor, an unknown potion is just a colour.",
        "Every death teaches you one true thing -- and never the same thing twice.",
        "",
        "Your corpse keeps your gold. Go back down and take it off yourself.",
    ]
    y = 300
    for ln in lines:
        text(surf, ln, (cx, y), 15, config.DIM, center=True)
        y += 23

    known, total = codex.progress()
    g = _pulse(t, 0.7)
    glow = (int(120 + 100 * g), int(180 + 50 * g), int(200 + 40 * g))

    if codex.has_progress():
        text(surf, "run %d   %d deaths   kodex %d/%d   deepest floor %d%s"
             % (codex.runs + 1, codex.deaths, known, total, codex.best_depth,
                "   WARDEN SLAIN x%d" % codex.wins if codex.wins else ""),
             (cx, y + 16), 14, config.CORPSE, center=True)
        live = [d for d in codex.corpses]
        if live:
            text(surf, "your dead are waiting on floor %s"
                 % ", ".join(sorted(live)), (cx, y + 40), 13, config.BLOOD, center=True)

        text(surf, "ENTER   CONTINUE", (cx, config.H - 104), 22, glow,
             center=True, bold=True)
        text(surf, "a new run, a new dungeon -- you keep the Kodex and your dead",
             (cx, config.H - 80), 13, config.DIM, center=True)
        text(surf, "N   NEW GAME", (cx, config.H - 52), 17, config.BLOOD,
             center=True, bold=True)
        text(surf, "erase everything and walk back in knowing nothing",
             (cx, config.H - 32), 13, config.FAINT, center=True)
    else:
        text(surf, "ENTER   BEGIN", (cx, config.H - 92), 22, glow,
             center=True, bold=True)

    text(surf, "K  kodex        ?  help        ESC  quit",
         (cx, config.H - 12), 13, config.FAINT, center=True)


def draw_confirm_new(surf, codex, t):
    """Erasing a Kodex is irreversible. Say out loud what is about to be lost."""
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((8, 5, 7, 240))
    surf.blit(layer, (0, 0))
    cx = config.W // 2
    known, total = codex.progress()

    text(surf, "START A NEW GAME?", (cx, 140), 40, config.BLOOD, bold=True, center=True)
    y = 200
    for ln in wrap("This is not a new run -- it erases the whole game. Everything you "
                   "have learned becomes a hole in the world again, and every body you "
                   "left behind is gone, with the gold still in its hand.", 16, 660):
        text(surf, ln, (cx, y), 16, config.DIM, center=True)
        y += 24

    y += 20
    rows = [
        ("kodex", "%d of %d truths" % (known, total)),
        ("deaths", "%d" % codex.deaths),
        ("deepest floor", "%d" % codex.best_depth),
        ("bodies still down there", "%d" % len(codex.corpses)),
        ("gold on those bodies",
         "%d" % sum(c.get("gold", 0) for c in codex.corpses.values())),
    ]
    for k, v in rows:
        text(surf, k, (cx - 20, y), 15, config.DIM, right=True)
        text(surf, v, (cx + 20, y - 9), 15, config.INK, bold=True)
        y += 26

    text(surf, "Y   yes, erase it all", (cx, y + 26), 19, config.BLOOD,
         center=True, bold=True)
    text(surf, "N / ESC   no, take me back", (cx, y + 56), 17, config.PLAYER,
         center=True, bold=True)


def draw_autopsy(surf, world, codex, fact, cause, reveal_t):
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((7, 5, 8, 234))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "YOU DIED", (cx, 52), 46, config.BLOOD, bold=True, center=True)
    text(surf, "killed by %s, on floor %d, with %d gold in your pocket"
         % (CAUSE_NAME.get(cause, cause), world.depth, world.player.gold),
         (cx, 98), 15, config.INK, center=True)
    text(surf, "death no. %d   |   %d things killed this run   |   the gold stays with the body"
         % (codex.deaths, world.run_kills), (cx, 122), 13, config.DIM, center=True)

    card = pygame.Rect(150, 168, config.W - 300, 250)
    pygame.draw.rect(surf, (14, 16, 22), card, border_radius=6)
    pygame.draw.rect(surf, config.PLAYER, card, 2, border_radius=6)

    tag = "TELEMETRY RECOVERED" if fact.tier == "telemetry" else "NEW KODEX ENTRY"
    head = pygame.Surface((card.w, 26), pygame.SRCALPHA)
    head.fill((*config.PLAYER, 26))
    surf.blit(head, card.topleft)
    text(surf, tag, (card.left + 16, card.top + 6), 13, config.PLAYER, bold=True)
    known, total = codex.progress()
    text(surf, "%d/%d" % (known, total), (card.right - 16, card.top + 13), 13,
         config.DIM, right=True)

    text(surf, fact_title(fact, codex), (card.left + 22, card.top + 46), 23,
         config.INK, bold=True)
    body = fact.text
    n = int(min(len(body), reveal_t * 95))
    y = card.top + 90
    for ln in wrap(body[:n], 15, card.w - 44):
        text(surf, ln, (card.left + 22, y), 15, config.INK)
        y += 22

    if n >= len(body):
        text(surf, "the dungeon is unchanged.  you are not.",
             (cx, card.bottom + 30), 15, config.CORPSE, center=True)
        text(surf, "ENTER  go back down        K  kodex",
             (cx, card.bottom + 66), 17, config.PLAYER, center=True, bold=True)


def _kodex_tab_count(codex, cat):
    """(known, total) for a tab, for the little count on its label."""
    if cat == "gear":
        rows = [kv for _, group in gear_catalog() for kv in group]
        return sum(1 for k, _ in rows if codex.gear_known(k)), len(rows)
    fs = facts_in(cat)
    return sum(1 for f in fs if codex.knows(f.key)), len(fs)


def _kodex_sealed_label(f, cat):
    if cat == "scrolls":
        return "a scroll you have not identified"
    if cat == "potions":
        return "a potion you have not identified"
    if cat == "traps":
        return "a trap you have not sprung"
    if cat == "lore":
        return "yourself" if f.subject == "self" else "the dungeon"
    return "the " + f.subject.replace("_", " ")       # a monster


def draw_codex(surf, codex, scroll, t, tab=0):
    surf.fill(config.BG)
    known, total = codex.progress()
    text(surf, "THE KODEX", (40, 22), 30, config.INK, bold=True)
    text(surf, "%d of %d truths, bought with %d lives"
         % (known, total, codex.deaths), (250, 30), 14, config.DIM)

    # --- tabs ----------------------------------------------------------
    tab = max(0, min(tab, len(KODEX_TAB_LABELS) - 1))
    ty = 62
    tab_w = (config.W - 80) // len(KODEX_TAB_LABELS)
    for i, lbl in enumerate(KODEX_TAB_LABELS):
        x = 40 + i * tab_w
        active = (i == tab)
        r = pygame.Rect(x + 3, ty, tab_w - 6, 32)
        if active:
            pygame.draw.rect(surf, (26, 30, 42), r, border_radius=5)
            pygame.draw.rect(surf, config.PLAYER, r, 1, border_radius=5)
        kn, tot = _kodex_tab_count(codex, KODEX_TABS[i])
        text(surf, "%s  %d/%d" % (lbl, kn, tot), (x + tab_w // 2, ty + 9), 14,
             config.INK if active else config.FAINT, bold=active, center=True)
    cat = KODEX_TABS[tab]

    # --- the entries for this tab --------------------------------------
    top = ty + 44
    view = pygame.Rect(0, top, config.W, config.H - top - 30)
    clip = surf.subsurface(view)
    y = -scroll

    def line(s, size, color, bold=False, indent=0):
        nonlocal y
        if -30 < y < view.h:
            text(clip, s, (40 + indent, y), size, color, bold=bold)
        y += size + 7

    if cat == "gear":
        for group_label, rows in gear_catalog():
            line(group_label, 12, config.FAINT)
            for key, g in rows:
                if codex.gear_known(key):
                    line(g.name, 16, config.INK, bold=True)
                    for ln in wrap("Tier %d %s.   %s" % (g.tier, g.slot, g.desc()),
                                   14, config.W - 150):
                        line(ln, 14, config.DIM, indent=18)
                else:
                    what = {"weapon": "a weapon", "armour": "armour",
                            "boots": "boots"}[g.slot]
                    line("[ SEALED ]  %s you have not found" % what, 14,
                         config.FAINT, bold=True)
                    line("this entry is written by finding it.", 13, (52, 56, 70),
                         indent=18)
                y += 6
            y += 8
    else:
        for f in facts_in(cat):
            if codex.knows(f.key):
                line(fact_title(f, codex), 16, config.INK, bold=True)
                for ln in wrap(f.text, 14, config.W - 150):
                    line(ln, 14, config.DIM, indent=18)
            else:
                line("[ SEALED ]  something about %s" % _kodex_sealed_label(f, cat),
                     14, config.FAINT, bold=True)
                line("this entry is written by dying.", 13, (52, 56, 70), indent=18)
            y += 8
        if cat == "lore":
            for tm in codex.telemetry:
                line(tm["title"], 16, config.GOLD, bold=True)
                for ln in wrap(tm["text"], 14, config.W - 150):
                    line(ln, 14, config.DIM, indent=18)
                y += 8

    total_h = y + scroll
    text(surf, "1-6 or  <-  ->  tabs      UP / DOWN scroll      ESC / K  back",
         (config.W // 2, config.H - 18), 13, config.FAINT, center=True)
    return max(0, int(total_h - view.h + 40))


def draw_win(surf, codex, world, t):
    surf.fill(config.BG)
    cx = config.W // 2
    known, total = codex.progress()
    text(surf, "THE WARDEN FALLS", (cx, 110), 54, config.GOLD, bold=True, center=True)
    text(surf, "you walked out of the deathward", (cx, 168), 18, config.INK, center=True)

    s = codex.stats
    rows = [
        ("lives spent getting here", "%d" % codex.deaths),
        ("kodex", "%d / %d" % (known, total)),
        ("gold carried out", "%d" % world.player.gold),
        ("killed this run", "%d" % world.run_kills),
        ("total kills", "%d" % s["kills"]),
        ("damage absorbed, all runs", "%d" % s["damage_taken"]),
        ("weapon at the end", world.player.weapon.name),
    ]
    y = 230
    for k, v in rows:
        text(surf, k, (cx - 24, y), 15, config.DIM, right=True)
        text(surf, v, (cx + 24, y - 9), 15, config.INK, bold=True)
        y += 28

    msg = ("Not one of those %d deaths was wasted. The Warden did not get weaker -- "
           "you simply stopped being surprised." % codex.deaths)
    y += 12
    for ln in wrap(msg, 15, 700):
        text(surf, ln, (cx, y), 15, config.CORPSE, center=True)
        y += 22

    y += 10
    text(surf, "S   START OVER", (cx, y), 20, config.GOLD, center=True, bold=True)
    text(surf, "a NEW dungeon -- you keep the Kodex, and ONE thing you are holding",
         (cx, y + 24), 14, config.DIM, center=True)
    text(surf, "W   WALK ON", (cx, y + 54), 18, config.PLAYER, center=True, bold=True)
    text(surf, "the Warden is dead. the Deathward is not.",
         (cx, y + 76), 14, config.DIM, center=True)
    text(surf, "K  kodex        ESC  title", (cx, config.H - 22), 13,
         config.FAINT, center=True)


def draw_boon(surf, gear, t):
    """The one thing in this game that lets a new run start stronger. You have to kill
    the Warden to earn it, and you may only carry ONE piece back down."""
    from .items import ALL_GEAR

    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 238))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "TAKE ONE THING WITH YOU", (cx, 96), 36, config.GOLD,
         bold=True, center=True)
    for i, ln in enumerate([
            "A DIFFERENT DEATHWARD is waiting -- new stone, new corridors, an",
            "unfamiliar map, and its traps hidden again. Your dead do not follow.",
            "",
            "But you keep the Kodex. You walk in able to READ it.",
            "And you may carry exactly one piece of what you are holding."]):
        col = config.INK if i == 3 else config.DIM
        text(surf, ln, (cx, 150 + i * 22), 15, col, center=True)

    rows = [("1", "weapon", "WEAPON"), ("2", "armour", "ARMOUR"), ("3", "boots", "BOOTS")]
    y = 278
    for key, slot, label in rows:
        g = ALL_GEAR.get((gear or {}).get(slot))
        row = pygame.Rect(cx - 310, y, 620, 68)
        pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
        pygame.draw.rect(surf, config.GOLD, row, 1, border_radius=6)
        text(surf, key, (cx - 288, y + 20), 24, config.GOLD, bold=True)
        text(surf, label, (cx - 252, y + 12), 12, config.FAINT)
        if g:
            text(surf, g.name, (cx - 252, y + 28), 18, config.INK, bold=True)
            text(surf, g.desc(), (cx + 290, y + 32), 13, config.DIM, right=True)
        y += 80

    g2 = _pulse(t, 0.8)
    text(surf, "press 1, 2 or 3", (cx, y + 14), 16,
         (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2)), center=True)
    text(surf, "ESC  back", (cx, y + 42), 13, config.FAINT, center=True)


def draw_banish(surf, types, codex, t):
    """The Banishment picker: which kind of monster (from the ones you can see) to
    unmake from the whole floor -- or ESC to keep the scroll (now identified)."""
    from .monsters import TEMPLATES
    from . import sprites

    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 238))
    surf.blit(layer, (0, 0))
    cx = config.W // 2
    accent = (200, 160, 235)

    text(surf, "BANISHMENT", (cx, 66), 34, accent, bold=True, center=True)
    text(surf, "choose a kind -- every one on the floor is unmade at once",
         (cx, 100), 14, config.DIM, center=True)

    if not types:
        text(surf, "nothing in sight to banish", (cx, 240), 20, config.FAINT,
             center=True)
        g2 = _pulse(t, 0.8)
        text(surf, "ESC  keep the scroll  (you now know what it is)", (cx, 320), 15,
             (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2)), center=True)
        return

    y = 150
    for i, (key, count) in enumerate(types):
        tmpl = TEMPLATES[key]
        known = codex.tier(key) > 0
        row = pygame.Rect(cx - 300, y, 600, 58)
        pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
        pygame.draw.rect(surf, accent, row, 1, border_radius=6)
        text(surf, str(i + 1), (cx - 282, y + 16), 24, accent, bold=True)
        icon = sprites.monster(key, tmpl.color) if known else sprites.unknown()
        surf.blit(pygame.transform.scale(icon, (42, 42)), (cx - 248, y + 8))
        name = tmpl.name if known else "an unknown kind"
        text(surf, name, (cx - 196, y + 18), 18,
             config.INK if known else config.DIM, bold=True)
        text(surf, "%d in sight" % count, (cx + 288, y + 22), 13, config.DIM, right=True)
        y += 68

    g2 = _pulse(t, 0.8)
    text(surf, "press 1-%d to unmake that kind" % len(types), (cx, y + 10), 15,
         (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2)), center=True)
    text(surf, "ESC  keep the scroll  (you now know what it is)", (cx, y + 36), 13,
         config.FAINT, center=True)


def draw_consumable_cheat(surf, flavors, kind, t, codex):
    """CTRL+67 (scrolls) / CTRL+76 (potions) picker: any uncommon or rare one, grouped
    by tier and numbered 1-9 then 0. The chosen one goes straight into the pack."""
    from .items import CONSUMABLES
    from . import sprites

    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 238))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "SCROLLS" if kind == "scroll" else "POTIONS", (cx, 50), 32,
         config.GOLD, bold=True, center=True)
    text(surf, "[ CHEAT ]   pick one -- it goes into your pack, identified",
         (cx, 82), 14, config.DIM, center=True)

    y = 116
    last_tier = None
    for i, f in enumerate(flavors):
        c = CONSUMABLES[f]
        if c.tier != last_tier:
            last_tier = c.tier
            text(surf, c.tier.upper(), (cx - 300, y), 12, config.FAINT)
            y += 18
        num = "0" if i == 9 else str(i + 1)
        row = pygame.Rect(cx - 300, y, 600, 36)
        pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
        pygame.draw.rect(surf, config.GOLD, row, 1, border_radius=6)
        text(surf, num, (cx - 284, y + 8), 20, config.GOLD, bold=True)
        icon = sprites.potion(codex.look(f)) if kind == "potion" else sprites.scroll()
        surf.blit(pygame.transform.scale(icon, (28, 28)), (cx - 250, y + 4))
        text(surf, c.true_name, (cx - 210, y + 9), 16, config.INK, bold=True)
        y += 40

    g2 = _pulse(t, 0.8)
    text(surf, "press 1-9, 0 to take one", (cx, y + 10), 15,
         (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2)), center=True)
    text(surf, "ESC  cancel", (cx, y + 34), 13, config.FAINT, center=True)


def draw_aim_hint(surf, ok):
    """A one-line banner while you are placing the teleport cursor."""
    cx = config.W // 2
    text(surf, "move the cursor   •   ENTER jump   •   ESC cancel",
         (cx, 22), 15, config.INK, center=True, bold=True)
    text(surf, "land here" if ok else "no landing here",
         (cx, 44), 13, (110, 220, 130) if ok else (230, 90, 90), center=True)


def draw_weapon_cheat(surf, keys, t, page_label="", slot="weapon"):
    """CTRL+12/21 weapon bench and CTRL+56 boots bench: up to nine pieces per page, 1-9.
    TAB cycles pages so every piece stays reachable through a single digit. A digit equips
    the base piece; for weapons, SHIFT+digit equips its +2 masterwork. Your current piece
    drops at your feet. The instruction lives at the bottom, where the eye lands last."""
    from .items import ALL_GEAR

    is_weapon = slot not in ("boots", "armour")
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 238))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    noun = {"boots": "boots", "armour": "armour"}.get(slot, "weapon")
    title = {"boots": "BOOTS BENCH", "armour": "ARMOUR BENCH"}.get(slot, "WEAPON BENCH")
    text(surf, title, (cx, 52), 34, config.GOLD, bold=True, center=True)
    text(surf, "[ CHEAT ]   equip any %s -- your current one drops at your feet" % noun,
         (cx, 88), 14, config.DIM, center=True)
    if page_label:
        text(surf, page_label, (cx, 106), 14, config.GOLD, bold=True, center=True)

    y = 122
    for idx, key in enumerate(keys):
        g = ALL_GEAR.get(key)
        row = pygame.Rect(cx - 310, y, 620, 40)
        pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
        pygame.draw.rect(surf, config.GOLD, row, 1, border_radius=6)
        text(surf, str(idx + 1), (cx - 292, y + 9), 22, config.GOLD, bold=True)
        if g:
            text(surf, g.name, (cx - 258, y + 6), 17, config.INK, bold=True)
            text(surf, g.desc(), (cx + 292, y + 12), 12, config.DIM, right=True)
        y += 46

    g2 = _pulse(t, 0.8)
    glow = (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2))
    text(surf, "press 1-9 to equip the base %s" % noun, (cx, y + 12), 15, glow, center=True)
    if is_weapon:
        text(surf, "hold SHIFT + 1-9 for the +2 masterwork version", (cx, y + 36), 16,
             config.GOLD, bold=True, center=True)
    text(surf, "TAB  next page   •   ESC  cancel", (cx, y + (60 if is_weapon else 36)), 13,
         config.FAINT, center=True)


def draw_arsenal(surf, keys, t):
    """CTRL+87 tester: the top three of each gear kind. Pick one and it drops on an
    open tile beside you -- for trying high-end gear down in the deep floors."""
    from .items import ALL_GEAR

    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    layer.fill((6, 6, 10, 238))
    surf.blit(layer, (0, 0))
    cx = config.W // 2

    text(surf, "ARSENAL", (cx, 60), 34, config.GOLD, bold=True, center=True)
    text(surf, "[ CHEAT ]   choose one -- it drops on the floor beside you",
         (cx, 96), 14, config.DIM, center=True)

    y = 134
    for label, base in (("WEAPONS", 0), ("ARMOUR", 3), ("BOOTS", 6)):
        text(surf, label, (cx - 310, y), 12, config.FAINT)
        y += 20
        for j in range(3):
            idx = base + j
            if idx >= len(keys):
                continue
            g = ALL_GEAR.get(keys[idx])
            row = pygame.Rect(cx - 310, y, 620, 44)
            pygame.draw.rect(surf, (16, 19, 26), row, border_radius=6)
            pygame.draw.rect(surf, config.GOLD, row, 1, border_radius=6)
            text(surf, str(idx + 1), (cx - 292, y + 11), 22, config.GOLD, bold=True)
            if g:
                text(surf, g.name, (cx - 258, y + 8), 17, config.INK, bold=True)
                text(surf, g.desc(), (cx + 292, y + 14), 12, config.DIM, right=True)
            y += 52
        y += 8

    g2 = _pulse(t, 0.8)
    text(surf, "press 1-9 to drop it beside you", (cx, y + 8), 15,
         (int(150 + 60 * g2), int(150 + 60 * g2), int(160 + 60 * g2)), center=True)
    text(surf, "ESC  cancel", (cx, y + 34), 13, config.FAINT, center=True)
