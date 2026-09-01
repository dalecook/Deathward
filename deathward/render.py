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

"""Drawing the dungeon.

This is the only place (with ui.py) that reads the Kodex. What you know does not
change the dungeon -- it changes how much of the dungeon is drawn:

    monster, unknown    -> a featureless silhouette. no name, no health, no intent.
    monster, rule known -> its actual sprite: a rat looks like a rat.
    monster, tell known -> its health bar and its INTENT: the brute's wind-up, the
                           spitter's firing line, the kobold's break for the door.
    trap,   not found   -> clean floor. invisible. it still fires.
    trap,   found once  -> THAT trap, drawn forever. never the others of its kind.
    mimic,  tell known  -> the chest that is not a chest is marked.
"""

import math

import pygame

from . import config, fontcache, sprites
from .items import CONSUMABLES


def font(size, bold=False):
    return fontcache.get_font(size, bold)


def glyph(surf, ch, cx, cy, color, size=20, bold=True):
    img = font(size, bold).render(ch, True, color)
    surf.blit(img, img.get_rect(center=(cx, cy)))


def _dim(c, k):
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k))


class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0

    def center_on(self, px, py):
        self.x = px - config.VIEW_W // 2
        self.y = py - config.VIEW_H // 2
        self.x = max(0, min(config.MAP_W - config.VIEW_W, self.x))
        self.y = max(0, min(config.MAP_H - config.VIEW_H, self.y))

    def to_screen(self, x, y):
        return ((x - self.x) * config.TILE, (y - self.y) * config.TILE)

    def on_screen(self, x, y):
        return (self.x <= x < self.x + config.VIEW_W and
                self.y <= y < self.y + config.VIEW_H)


def draw_aim_cursor(surf, world, cam, aim, ok, t):
    """The teleport cursor: a pulsing box on the target tile -- green where you can
    land, red where you cannot -- and a thread back to where you are standing now."""
    T = config.TILE
    ax, ay = aim
    sx, sy = cam.to_screen(ax, ay)
    px, py = cam.to_screen(world.player.x, world.player.y)
    col = (110, 220, 130) if ok else (230, 90, 90)
    pulse = 0.5 + 0.5 * math.sin(t * 7)
    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    pygame.draw.line(layer, (*col, int(60 + 60 * pulse)),
                     (px + T // 2, py + T // 2), (sx + T // 2, sy + T // 2), 2)
    layer.fill((*col, int(45 + 45 * pulse)), (sx, sy, T, T))
    surf.blit(layer, (0, 0))
    pygame.draw.rect(surf, col, (sx, sy, T, T), 2)


def draw_stun_stars(surf, cx, cy, t, fade=1.0):
    """Three little gold stars spinning over a staggered thing's head, so the stun is
    something you SEE -- not just a line in the log. Feedback on YOUR blow, shown known
    or not, like the flames on a burning thing.

    Driven by a real-time 'stunstars' fx (below), NOT by reading m.stunned: the stun
    counter is set and spent inside a single turn resolution, so it is already back to 0
    by the time a frame draws. `fade` (1 -> 0) shrinks the stars as that fx gutters out."""
    for i in range(3):
        a = t * 3.4 + i * 2.0944                    # 2*pi/3 apart, orbiting slowly
        sx = cx + int(math.cos(a) * 9)
        sy = cy + int(math.sin(a) * 3.5)            # a flattened orbit reads as "overhead"
        size = int((12 + 3 * math.sin(t * 6.0 + i * 2.0)) * (0.45 + 0.55 * fade))
        if size > 2:
            glyph(surf, "*", sx, sy, config.GOLD, size)


def draw_world(surf, world, codex, cam, t):
    surf.fill(config.BG)
    lvl = world.level
    T = config.TILE

    ox = oy = 0
    if world.shake_t > 0:
        ox = int(math.sin(t * 60) * world.shake_t * 0.6)
        oy = int(math.cos(t * 71) * world.shake_t * 0.5)

    def topleft(x, y):
        sx, sy = cam.to_screen(x, y)
        return sx + ox, sy + oy

    def at(x, y):
        sx, sy = topleft(x, y)
        return sx + T // 2, sy + T // 2

    # --- terrain --------------------------------------------------------
    for vy in range(config.VIEW_H):
        for vx in range(config.VIEW_W):
            x, y = cam.x + vx, cam.y + vy
            if not lvl.in_bounds(x, y) or not lvl.explored[y][x]:
                continue
            vis = lvl.visible[y][x]
            img = (sprites.wall(x, y, vis) if lvl.grid[y][x] == 0
                   else sprites.floor(x, y, vis))
            surf.blit(img, topleft(x, y))

    # --- traps: drawn ONE AT A TIME, and only the ones you have personally found.
    # knowing what a dart trap is does not reveal the other dart traps -- every trap
    # in this dungeon is found individually, by springing it or watching it fire, and
    # once found it stays on your map through every death for the rest of the game.
    # a Scroll of Mapping never reveals one: it maps stone, not danger.
    for tr in lvl.traps:
        if not codex.trap_found(world.depth, tr.x, tr.y):
            continue                     # invisible. it will still go off.
        if not lvl.explored[tr.y][tr.x] or not cam.on_screen(tr.x, tr.y):
            continue
        vis = lvl.visible[tr.y][tr.x]
        surf.blit(sprites.trap(tr.key, tr.sprung, dim=not vis), topleft(tr.x, tr.y))
        if vis and not tr.sprung:
            pulse = 0.5 + 0.5 * math.sin(t * 2.4 + tr.x)
            layer = pygame.Surface((T, T), pygame.SRCALPHA)
            layer.fill((*config.TRAP, int(16 + 22 * pulse)))
            surf.blit(layer, topleft(tr.x, tr.y))

    # --- the way in and the way down -------------------------------------
    if lvl.entrance and lvl.explored[lvl.entrance[1]][lvl.entrance[0]]:
        ex, ey = lvl.entrance
        dim = not lvl.visible[ey][ex]
        # floor 1's entrance is a shut portcullis. every other floor's is a way back up.
        img = (sprites.entrance(dim=dim) if world.depth <= 1
               else sprites.stairs_up(dim=dim))
        surf.blit(img, topleft(ex, ey))
    if lvl.stairs and lvl.explored[lvl.stairs[1]][lvl.stairs[0]]:
        sx_, sy_ = lvl.stairs
        surf.blit(sprites.stairs(dim=not lvl.visible[sy_][sx_]), topleft(sx_, sy_))

    # --- the things you have killed --------------------------------------
    for s in lvl.slain:
        if not lvl.seen[s.y][s.x] or not cam.on_screen(s.x, s.y):
            continue
        img = sprites.slain(s.key, s.color)
        if not lvl.visible[s.y][s.x]:
            img = sprites.dimmed(img)
        surf.blit(img, topleft(s.x, s.y))

        # a body still holding something glints, or you would walk straight past it
        if s.has_loot:
            cx, cy = at(s.x, s.y)
            pulse = 0.5 + 0.5 * math.sin(t * 3.0 + s.x * 1.7 + s.y)
            halo = pygame.Surface((T, T), pygame.SRCALPHA)
            pygame.draw.circle(halo, (*config.GOLD, int(26 + 34 * pulse)),
                               (T // 2, T // 2), int(T * 0.40))
            surf.blit(halo, topleft(s.x, s.y))
            for i in range(3):
                a = t * 1.6 + i * 2.09
                gx = cx + math.cos(a) * T * 0.30
                gy = cy + math.sin(a) * T * 0.22 - T * 0.10
                r = 2 if i else 3
                pygame.draw.circle(surf, config.GOLD, (int(gx), int(gy)), r)

    # --- chests, drops, your own dead ------------------------------------
    # all gated on `seen`, not `explored`: you must have looked at the tile with your
    # own eyes. mapping the floor tells you nothing about what is lying on it.
    for ch in lvl.chests:
        if ch.opened or not lvl.seen[ch.y][ch.x] or not cam.on_screen(ch.x, ch.y):
            continue
        surf.blit(sprites.chest(dim=not lvl.visible[ch.y][ch.x]), topleft(ch.x, ch.y))

    for d in lvl.drops:
        if not lvl.seen[d.y][d.x] or not cam.on_screen(d.x, d.y):
            continue
        dim = not lvl.visible[d.y][d.x]
        if d.kind == "gold":
            img = sprites.gold(dim=dim)
        elif d.kind == "gear":
            img = sprites.gear(d.payload, dim=dim)   # one look per item, not per slot
        else:
            c = CONSUMABLES[d.payload]
            img = (sprites.potion(codex.look(d.payload), dim=dim) if c.kind == "potion"
                   else sprites.scroll(dim=dim))
        surf.blit(img, topleft(d.x, d.y))

    c = lvl.corpse
    if c and not c.taken and lvl.seen[c.y][c.x] and cam.on_screen(c.x, c.y):
        cx, cy = at(c.x, c.y)
        pulse = 0.5 + 0.5 * math.sin(t * 1.4)
        halo = pygame.Surface((T, T), pygame.SRCALPHA)
        pygame.draw.circle(halo, (*config.CORPSE, int(30 + 30 * pulse)),
                           (T // 2, T // 2), int(T * 0.42))
        surf.blit(halo, topleft(c.x, c.y))
        surf.blit(sprites.corpse(dim=not lvl.visible[c.y][c.x]), topleft(c.x, c.y))

    # --- the vendor -------------------------------------------------------
    v = lvl.vendor
    if v and lvl.seen[v.y][v.x] and cam.on_screen(v.x, v.y):
        vis = lvl.visible[v.y][v.x]
        if vis:
            cx, cy = at(v.x, v.y)
            pulse = 0.5 + 0.5 * math.sin(t * 1.5)
            halo = pygame.Surface((T, T), pygame.SRCALPHA)
            pygame.draw.circle(halo, (*config.VENDOR_COLOR, int(22 + 26 * pulse)),
                               (T // 2, T // 2), int(T * 0.46))
            surf.blit(halo, topleft(v.x, v.y))
        surf.blit(sprites.vendor(dim=not vis), topleft(v.x, v.y))

    # --- monsters --------------------------------------------------------
    for m in lvl.monsters:
        if m.hidden or not lvl.visible[m.y][m.x] or not cam.on_screen(m.x, m.y):
            continue
        cx, cy = at(m.x, m.y)
        known = codex.tier(m.key)

        if m.key == "poltergeist":
            # the one monster the knowledge ladder makes VISIBLE instead of merely
            # legible. no '?', no silhouette -- nothing at all -- right up until you
            # have learned its COUNTER, at which point it resolves into a faint,
            # wavering shimmer you can finally track and put a blade through. before
            # that, the only proof it exists is the TELL: a flash when it strikes.
            if codex.knows_tier("poltergeist", "counter"):
                a = 120 + int(70 * math.sin(t * 3.3 + m.x * 1.7))
                surf.blit(sprites.monster("poltergeist", m.t.color,
                                          max(55, min(215, a))), topleft(m.x, m.y))
                frac = max(0.0, m.hp / m.max_hp)
                bw = T - 12
                bx, by = cx - bw // 2, cy - T // 2 + 1
                pygame.draw.rect(surf, (30, 34, 44), (bx, by, bw, 3), border_radius=2)
                pygame.draw.rect(surf, (176, 202, 232),
                                 (bx, by, int(bw * frac), 3), border_radius=2)
            continue

        if m.disguised:
            # it is pretending to be a chest, and it is very good at it
            surf.blit(sprites.chest(), topleft(m.x, m.y))
            if codex.knows_tier("mimic", "tell"):
                breathe = int(2 * (0.5 + 0.5 * math.sin(t * 3.1 + m.x)))
                r = pygame.Rect(0, 0, T - 4 + breathe, T - 4 + breathe)
                r.center = (cx, cy)
                pygame.draw.rect(surf, config.BLOOD, r, 2, border_radius=3)
                glyph(surf, "!", cx + T // 2 - 5, cy - T // 2 + 6, config.BLOOD, 14)
            continue

        if known == 0:
            surf.blit(sprites.unknown(), topleft(m.x, m.y))
            continue

        col = m.t.color
        alpha = 255
        if m.key == "wraith":
            # it brightens as it feeds and fades as it starves
            alpha = int(90 + 165 * m.feed)
        surf.blit(sprites.monster(m.key, col, alpha), topleft(m.x, m.y))

        if codex.knows_tier(m.key, "tell"):
            frac = max(0.0, m.hp / m.max_hp)
            bw = T - 10
            bx, by = cx - bw // 2, cy - T // 2 + 1
            pygame.draw.rect(surf, (36, 18, 22), (bx, by, bw, 4), border_radius=2)
            pygame.draw.rect(surf, config.BLOOD if frac > 0.35 else (255, 90, 90),
                             (bx, by, int(bw * frac), 4), border_radius=2)
            if m.intent:
                kind = m.intent[0]
                if kind == "smash":
                    _, tx, ty = m.intent
                    if cam.on_screen(tx, ty):
                        pulse = 0.5 + 0.5 * math.sin(t * 9)
                        layer = pygame.Surface((T, T), pygame.SRCALPHA)
                        layer.fill((*config.BLOOD, int(55 + 70 * pulse)))
                        surf.blit(layer, topleft(tx, ty))
                        pygame.draw.rect(surf, config.BLOOD,
                                         (*topleft(tx, ty), T, T), 2)
                    glyph(surf, "!", cx, cy - T // 2 - 6, config.BLOOD, 18)
                elif kind == "spit":
                    p = world.player
                    dx = (p.x > m.x) - (p.x < m.x)
                    dy = (p.y > m.y) - (p.y < m.y)
                    lx, ly = m.x, m.y
                    for _ in range(9):
                        lx += dx
                        ly += dy
                        if not world.walkable(lx, ly) or not cam.on_screen(lx, ly):
                            break
                        layer = pygame.Surface((T, T), pygame.SRCALPHA)
                        layer.fill((170, 230, 110, 50))
                        surf.blit(layer, topleft(lx, ly))
                    glyph(surf, "!", cx, cy - T // 2 - 6, (170, 230, 110), 18)
                elif kind == "flee":
                    glyph(surf, "^", cx, cy - T // 2 - 6, config.STAIRS, 17)
                elif kind == "gaze":
                    # the beholder's eyeline -- shown so you can step OUT of it. a
                    # pulsing beam straight to you, and its wide-open eye.
                    p = world.player
                    px, py = at(p.x, p.y)
                    pulse = 0.5 + 0.5 * math.sin(t * 8)
                    layer = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
                    pygame.draw.line(layer, (150, 210, 255, int(70 + 90 * pulse)),
                                     (cx, cy), (px, py), 3)
                    surf.blit(layer, (0, 0))
                    pygame.draw.circle(surf, (200, 230, 255),
                                       (cx, cy), int(T * (0.28 + 0.06 * pulse)), 2)
                    glyph(surf, "!", cx, cy - T // 2 - 6, (150, 210, 255), 18)
                elif kind == "blow":
                    # her ranged gust -- same shape as the spitter's "spit": a
                    # line of effect toward the player that a pillar can block.
                    # pulsing (unlike spit's static fill) so it reads as active
                    # danger, not ambient scenery.
                    p = world.player
                    dx = (p.x > m.x) - (p.x < m.x)
                    dy = (p.y > m.y) - (p.y < m.y)
                    lx, ly = m.x, m.y
                    pulse = 0.5 + 0.5 * math.sin(t * 8)
                    for _ in range(9):
                        lx += dx
                        ly += dy
                        if not world.walkable(lx, ly) or not cam.on_screen(lx, ly):
                            break
                        layer = pygame.Surface((T, T), pygame.SRCALPHA)
                        layer.fill((*m.t.color, int(60 + 70 * pulse)))
                        surf.blit(layer, topleft(lx, ly))
                    glyph(surf, "!", cx, cy - T // 2 - 6, m.t.color, 18)

    # --- Syrinx's still-hidden telegraph ----------------------------------
    # her "emerge" intent fires a full turn before she leaves hidden state,
    # but the monster loop above `continue`s past her entirely while
    # m.hidden is True -- she has no sprite to draw yet. This is a second,
    # narrower pass just for that case: a persistent glow on the pillar tile
    # itself (same pulsing-highlight style as "smash"'s target-tile flash),
    # so the warning is legible for her whole telegraph turn even though
    # nothing is drawn ON her -- there is no her to draw on.
    for m in lvl.monsters:
        if not (m.hidden and m.intent and m.intent[0] == "emerge"):
            continue
        if not lvl.visible[m.y][m.x] or not cam.on_screen(m.x, m.y):
            continue
        if not codex.knows_tier(m.key, "tell"):
            continue
        pulse = 0.5 + 0.5 * math.sin(t * 9)
        layer = pygame.Surface((T, T), pygame.SRCALPHA)
        layer.fill((*m.t.color, int(55 + 70 * pulse)))
        surf.blit(layer, topleft(m.x, m.y))
        pygame.draw.rect(surf, m.t.color, (*topleft(m.x, m.y), T, T), 2)

    # --- the player -------------------------------------------------------
    p = world.player
    cx, cy = at(p.x, p.y)
    halo = pygame.Surface((T, T), pygame.SRCALPHA)
    glow = (150, 210, 255) if p.frozen > 0 else config.PLAYER
    pygame.draw.circle(halo, (*glow, 34), (T // 2, T // 2), int(T * 0.44))
    surf.blit(halo, topleft(p.x, p.y))
    hero = sprites.player(p.weapon.tier, p.armour.tier)
    if p.hidden():
        # you can still see yourself, but only just -- a ghost of a hero. ANY invisibility
        # source (Fadecloak, the untimed potion, or Nightcloak) fades the sprite, not just
        # the old timed counter.
        hero = hero.copy()
        hero.set_alpha(70)
    surf.blit(hero, topleft(p.x, p.y))
    if p.frozen > 0:
        # encased -- a pale-blue shell over the hero while the ice holds
        shell = pygame.Surface((T, T), pygame.SRCALPHA)
        pygame.draw.rect(shell, (150, 210, 255, 70), (2, 2, T - 4, T - 4),
                         border_radius=4)
        pygame.draw.rect(shell, (200, 232, 255, 200), (2, 2, T - 4, T - 4), 2,
                         border_radius=4)
        surf.blit(shell, topleft(p.x, p.y))

    # --- active-effect pips ----------------------------------------------
    # one small pip per lasting effect, at the tile corners in fill order
    # (top-left, top-right, bottom-right, bottom-left). Four corners is the cap;
    # the HUD carries the full list. A pip blinks through its final three turns;
    # untimed effects (the Phoenix) hold steady.
    effects = p.active_effects()
    if effects:
        tlx, tly = topleft(p.x, p.y)
        r = max(3, T // 9)
        m = r + 1
        corners = [(tlx + m, tly + m), (tlx + T - m, tly + m),
                   (tlx + T - m, tly + T - m), (tlx + m, tly + T - m)]
        blink_on = math.sin(t * 12) > 0
        for (_lbl, color, rem), (pcx, pcy) in zip(effects, corners):
            if rem is not None and rem <= 3 and not blink_on:
                continue
            pygame.draw.circle(surf, (10, 12, 18), (pcx, pcy), r + 1)
            pygame.draw.circle(surf, color, (pcx, pcy), r)

    # --- fire ------------------------------------------------------------
    # drawn last, over everything, because the point is that you cannot miss it
    for f in world.fx:
        prog = 1.0 - max(0.0, f["life"]) / f["max"]        # 0 -> 1
        col = f["col"]

        if f["kind"] == "burning":
            # THE FLOOR IS ON FIRE. These tiles are exactly the tiles taking damage,
            # so the animation doubles as an honest map of the blast.
            life = max(0.0, f["life"])
            fade = min(1.0, life / 0.35)                   # gutters out at the end
            grow = min(1.0, prog * 6.0)                    # catches almost at once
            for (tx, ty) in f["tiles"]:
                if not cam.on_screen(tx, ty):
                    continue
                bx, by = topleft(tx, ty)
                seed = (tx * 7 + ty * 13) % 17

                scorch = pygame.Surface((T, T), pygame.SRCALPHA)
                scorch.fill((90, 30, 18, int(120 * fade)))
                surf.blit(scorch, (bx, by))

                # three tongues per tile, each flickering on its own clock
                for i in range(3):
                    ph = t * 13.0 + seed * 1.7 + i * 2.2
                    flick = 0.55 + 0.45 * math.sin(ph)
                    h = T * (0.42 + 0.50 * flick) * grow * fade
                    w = T * (0.20 + 0.06 * math.sin(ph * 1.7))
                    fx0 = bx + T * (0.22 + 0.28 * i) + math.sin(ph * 0.9) * 2
                    base = by + T * 0.86

                    for (shrink, c) in ((1.0, (255, 108, 40)),
                                        (0.62, (255, 178, 62)),
                                        (0.30, (255, 244, 190))):
                        hh, ww = h * shrink, w * shrink
                        tongue = [(fx0 - ww / 2, base),
                                  (fx0 - ww * 0.30, base - hh * 0.55),
                                  (fx0 + math.sin(ph * 1.3) * ww * 0.30, base - hh),
                                  (fx0 + ww * 0.30, base - hh * 0.55),
                                  (fx0 + ww / 2, base)]
                        layer = pygame.Surface((T * 2, T * 2), pygame.SRCALPHA)
                        pygame.draw.polygon(
                            layer, (*c, int(210 * fade)),
                            [(px - bx + T // 2, py - by + T // 2) for px, py in tongue])
                        surf.blit(layer, (bx - T // 2, by - T // 2))

                # sparks lifting off
                if flick > 0.75:
                    sx = bx + T * (0.3 + 0.4 * ((seed % 5) / 4.0))
                    sy = by + T * 0.3 - (prog * T * 0.4)
                    pygame.draw.circle(surf, (255, 220, 140), (int(sx), int(sy)),
                                       max(1, int(2 * fade)))
            continue

        if f["kind"] == "slash":
            # your blade going through something
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            r = T * 0.5 * f["r"]
            sweep = -0.6 + prog * 1.9          # the arc travels through the target
            for k, (off, wdt) in enumerate(((0.0, 4), (0.16, 2))):
                a0 = sweep - 0.9 + off
                a1 = sweep + 0.3 + off
                pts = []
                for i in range(7):
                    a = a0 + (a1 - a0) * (i / 6.0)
                    pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
                if len(pts) > 1:
                    lay = pygame.Surface((T * 3, T * 3), pygame.SRCALPHA)
                    pygame.draw.lines(
                        lay, (*col, int(235 * fade)), False,
                        [(px - cx + T * 1.5, py - cy + T * 1.5) for px, py in pts],
                        max(1, int(wdt * fade + 1)))
                    surf.blit(lay, (cx - T * 1.5, cy - T * 1.5))
            for i in range(4):                 # a little blood
                a = sweep + i * 0.5
                d = r * (0.8 + 0.5 * prog)
                pygame.draw.circle(surf, (196, 60, 70),
                                   (int(cx + math.cos(a) * d),
                                    int(cy + math.sin(a) * d)),
                                   max(1, int(3 * fade)))
            continue

        if f["kind"] == "impact":
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            r = T * f["r"] * (0.3 + 0.85 * prog)
            pygame.draw.circle(surf, col, (cx, cy), max(1, int(r)),
                               max(1, int(3 * fade)))
            for i in range(7):
                a = i * 0.898 + f["x"]
                d = r * (0.9 + 0.5 * prog)
                pygame.draw.circle(surf, col,
                                   (int(cx + math.cos(a) * d),
                                    int(cy + math.sin(a) * d)),
                                   max(1, int(3.5 * fade)))
            continue

        if f["kind"] == "slam":
            # eight hundred pounds of arm arriving on a specific tile
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            r = T * (0.35 + 1.5 * prog)
            ring = pygame.Surface((int(r * 2) + 8, int(r * 2) + 8), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*col, int(170 * fade)),
                               (int(r) + 4, int(r) + 4), int(r),
                               max(2, int(7 * fade)))
            surf.blit(ring, (cx - int(r) - 4, cy - int(r) - 4))
            # cracks radiating out of the point of impact
            for i in range(6):
                a = i * 1.047 + f["x"] * 0.3
                d0 = T * 0.18
                d1 = T * (0.30 + 0.55 * prog)
                pygame.draw.line(surf, (250, 236, 220),
                                 (cx + math.cos(a) * d0, cy + math.sin(a) * d0),
                                 (cx + math.cos(a) * d1, cy + math.sin(a) * d1),
                                 max(1, int(3 * fade)))
            # dust
            for i in range(6):
                a = i * 1.047 + 0.4
                d = r * 0.8
                pygame.draw.circle(surf, (150, 130, 112),
                                   (int(cx + math.cos(a) * d),
                                    int(cy + math.sin(a) * d - prog * T * 0.2)),
                                   max(1, int(4 * fade)))
            continue

        if f["kind"] == "bolt":
            # something thrown across the room at you
            if not f["tiles"]:
                continue
            sxt, syt = f["tiles"][0]
            ax, ay = at(sxt, syt)
            bx, by = at(f["x"], f["y"])
            hit = min(1.0, prog / 0.7)
            px = ax + (bx - ax) * hit
            py = ay + (by - ay) * hit
            fade = 1.0 - prog
            rr = max(2, int(T * f["r"] * 0.5))
            pygame.draw.circle(surf, col, (int(px), int(py)), rr)
            pygame.draw.circle(surf, (250, 255, 230), (int(px), int(py)),
                               max(1, rr // 2))
            for i in range(3):                  # a dribbling tail
                k = hit - (i + 1) * 0.08
                if k <= 0:
                    continue
                tx2 = ax + (bx - ax) * k
                ty2 = ay + (by - ay) * k
                pygame.draw.circle(surf, col, (int(tx2), int(ty2)),
                                   max(1, rr - i - 1))
            if hit >= 1.0:                      # splash
                for i in range(8):
                    a = i * 0.785
                    d = T * 0.45 * (1.0 - fade)
                    pygame.draw.circle(surf, col,
                                       (int(bx + math.cos(a) * d),
                                        int(by + math.sin(a) * d)),
                                       max(1, int(3 * fade)))
            continue

        if f["kind"] == "beam":
            if not f["tiles"]:
                continue
            sxt, syt = f["tiles"][0]
            ax, ay = at(sxt, syt)
            bx, by = at(f["x"], f["y"])
            fade = 1.0 - prog
            pygame.draw.line(surf, col, (ax, ay), (bx, by),
                             max(1, int(9 * fade)))
            pygame.draw.line(surf, (255, 240, 245), (ax, ay), (bx, by),
                             max(1, int(3 * fade)))
            continue

        if f["kind"] == "ray":
            # the beholder's baleful ray -- a thick red lance with a hot near-white
            # core and a burst where it lands. deliberately NOT the cold blue of the
            # gaze, and deliberately not fire.
            if not f["tiles"]:
                continue
            sxt, syt = f["tiles"][0]
            ax, ay = at(sxt, syt)
            bx, by = at(f["x"], f["y"])
            fade = 1.0 - prog
            glow = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
            pygame.draw.line(glow, (*col, int(150 * fade)), (ax, ay), (bx, by),
                             max(2, int(13 * fade)))
            surf.blit(glow, (0, 0))
            pygame.draw.line(surf, col, (ax, ay), (bx, by), max(1, int(7 * fade)))
            pygame.draw.line(surf, (255, 226, 214), (ax, ay), (bx, by),
                             max(1, int(3 * fade)))
            pygame.draw.circle(surf, (255, 226, 214), (bx, by),
                               max(1, int(T * 0.34 * fade)))
            continue

        if f["kind"] == "drain":
            # a tether: life leaving one body and entering another. f["x"],f["y"] is
            # the DRAINER; tiles[0] is the victim.
            if not f["tiles"]:
                continue
            vx, vy = f["tiles"][0]
            ax, ay = at(vx, vy)
            bx, by = at(f["x"], f["y"])
            fade = 1.0 - prog
            pygame.draw.line(surf, col, (ax, ay), (bx, by), max(1, int(3 * fade)))
            for i in range(5):                  # motes travelling victim -> drainer
                k = (prog * 1.6 + i * 0.2) % 1.0
                mx = ax + (bx - ax) * k
                my = ay + (by - ay) * k + math.sin(k * 6.28 + t * 4) * 4
                pygame.draw.circle(surf, col, (int(mx), int(my)),
                                   max(1, int(4 * fade * (1 - k * 0.4))))
            continue

        if f["kind"] == "dart":
            # a dart crossing the room, from the wall it came out of to your ribs
            if not f["tiles"]:
                continue
            sx_t, sy_t = f["tiles"][0]
            if not (cam.on_screen(sx_t, sy_t) or cam.on_screen(f["x"], f["y"])):
                continue
            ax, ay = at(sx_t, sy_t)
            bx, by = at(f["x"], f["y"])
            hit = min(1.0, prog / 0.75)                # travels, then sticks
            px = ax + (bx - ax) * hit
            py = ay + (by - ay) * hit
            dx, dy = bx - ax, by - ay
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
            pygame.draw.line(surf, (255, 190, 190),
                             (px - dx * T * 0.45, py - dy * T * 0.45),
                             (px, py), 3)
            pygame.draw.circle(surf, (255, 240, 240), (int(px), int(py)), 3)
            if hit >= 1.0:                             # it lands
                fade = 1.0 - (prog - 0.75) / 0.25
                for i in range(6):
                    a = i * 1.047
                    pygame.draw.circle(
                        surf, col,
                        (int(bx + math.cos(a) * T * 0.3 * (1 - fade)),
                         int(by + math.sin(a) * T * 0.3 * (1 - fade))),
                        max(1, int(3 * fade)))
            continue

        if f["kind"] == "spikes":
            # rusted iron coming up through the floor, then sinking back
            if not cam.on_screen(f["x"], f["y"]):
                continue
            sx, sy = topleft(f["x"], f["y"])
            up = math.sin(min(1.0, prog * 1.3) * math.pi)     # out, then back in
            hole = pygame.Surface((T, T), pygame.SRCALPHA)
            pygame.draw.ellipse(hole, (14, 10, 14, 220), (2, T // 3, T - 4, T // 2))
            surf.blit(hole, (sx, sy))
            for i in range(5):
                x = sx + T * (0.16 + i * 0.17)
                h = T * (0.34 + 0.20 * ((i % 2) == 0)) * up
                base = sy + T * 0.80
                pygame.draw.polygon(surf, col,
                                    [(x - T * 0.05, base), (x + T * 0.05, base),
                                     (x, base - h)])
                pygame.draw.line(surf, (250, 236, 220), (x, base - h * 0.9),
                                 (x - T * 0.012, base - h * 0.2), 1)
                if up > 0.6:               # blood on the tips
                    pygame.draw.circle(surf, (170, 40, 46),
                                       (int(x), int(base - h)), 2)
            continue

        if f["kind"] == "gas":
            # a green cloud, billowing and lifting. it does nothing on contact, so if
            # you cannot see it you cannot connect it to the bleeding that follows.
            fade = min(1.0, max(0.0, f["life"]) / 0.5)
            for (tx, ty) in f["tiles"]:
                if not cam.on_screen(tx, ty):
                    continue
                sx, sy = topleft(tx, ty)
                seed = (tx * 5 + ty * 11) % 13
                for i in range(4):
                    a = i * 1.57 + seed + t * 1.1
                    r = T * (0.18 + 0.22 * prog + 0.05 * math.sin(t * 3 + i))
                    px = sx + T * 0.5 + math.cos(a) * T * 0.26
                    py = sy + T * 0.5 + math.sin(a) * T * 0.20 - prog * T * 0.35
                    puff = pygame.Surface((int(r * 2) + 4, int(r * 2) + 4),
                                          pygame.SRCALPHA)
                    pygame.draw.circle(puff, (*col, int(70 * fade)),
                                       (int(r) + 2, int(r) + 2), int(r))
                    surf.blit(puff, (px - r - 2, py - r - 2))
            continue

        if f["kind"] == "haunt":
            # the poltergeist, dragged into view for a single heartbeat by its own
            # strike. shown only because you have learned its tell -- and gone again
            # before you can act on it.
            if not cam.on_screen(f["x"], f["y"]):
                continue
            sx, sy = topleft(f["x"], f["y"])
            cx, cy = sx + T // 2, sy + T // 2
            fade = 1.0 - prog
            surf.blit(sprites.monster("poltergeist", col, int(205 * fade)), (sx, sy))
            r = int(T * (0.30 + 0.42 * prog))
            ring = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*col, int(150 * fade)), (r + 3, r + 3), r, 2)
            surf.blit(ring, (cx - r - 3, cy - r - 3))
            continue

        if f["kind"] == "shout":
            # THE ALARM. concentric rings racing out across the whole floor: the sound
            # is the payload, so the sound is what gets drawn.
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            for i in range(3):
                p2 = prog - i * 0.16
                if p2 <= 0:
                    continue
                r = p2 * f["r"] * T
                a = int(190 * (1.0 - p2) * fade)
                if a <= 0:
                    continue
                ring = pygame.Surface((int(r * 2) + 8, int(r * 2) + 8), pygame.SRCALPHA)
                pygame.draw.circle(ring, (*col, a), (int(r) + 4, int(r) + 4), int(r),
                                   max(2, int(5 * (1.0 - p2))))
                surf.blit(ring, (cx - int(r) - 4, cy - int(r) - 4))
            pygame.draw.circle(surf, (255, 245, 200), (cx, cy),
                               max(2, int(T * 0.3 * fade)))
            continue

        if f["kind"] == "woke":
            # everything that just heard it, marked where it stands
            fade = 1.0 - prog
            for (tx, ty) in f["tiles"]:
                if not cam.on_screen(tx, ty):
                    continue
                cx, cy = at(tx, ty)
                pygame.draw.circle(surf, col, (cx, cy),
                                   int(T * (0.30 + 0.32 * prog)),
                                   max(1, int(3 * fade)))
                glyph(surf, "!", cx, cy - T // 2 - 4, col, int(16 + 6 * fade))
            continue

        if f["kind"] == "summon":
            # GRAMM: the ground tears open and something climbs out of it. this has to
            # be LOUD -- what arrives may be a '?' the player has never seen, and if
            # they do not register that it was summoned they will think the game
            # spawned a monster on their face for no reason.
            fade = 1.0 - prog
            for (tx, ty) in f["tiles"]:
                if not cam.on_screen(tx, ty):
                    continue
                sx, sy = topleft(tx, ty)
                cx, cy = sx + T // 2, sy + T // 2

                # a red bloodlight washing the tile
                wash = pygame.Surface((T, T), pygame.SRCALPHA)
                wash.fill((*col, int(90 * fade)))
                surf.blit(wash, (sx, sy))

                # the hole itself, torn open
                hole = pygame.Surface((T, T), pygame.SRCALPHA)
                pygame.draw.ellipse(hole, (24, 4, 12, int(235 * fade)),
                                    (1, int(T * 0.30), T - 2,
                                     int(T * 0.62 * (0.35 + 0.65 * prog))))
                surf.blit(hole, (sx, sy))

                # two rings, one expanding and one contracting: it reads as a rift
                pygame.draw.circle(surf, col, (cx, cy),
                                   max(1, int(T * 0.50 * (0.25 + 0.85 * prog))),
                                   max(1, int(4 * fade)))
                pygame.draw.circle(surf, (255, 200, 200), (cx, cy),
                                   max(1, int(T * 0.42 * (1.0 - prog * 0.7))),
                                   max(1, int(2 * fade)))

                # smoke and cinders boiling up out of it
                for i in range(7):
                    a = i * 0.9 + tx * 1.3 + ty
                    px = cx + math.cos(a + t * 2.4) * T * (0.10 + 0.26 * prog)
                    py = cy - prog * T * (0.30 + 0.10 * i)
                    pygame.draw.circle(surf, (110, 26, 40),
                                       (int(px), int(py)), max(1, int(5 * fade)))
                    pygame.draw.circle(surf, (220, 90, 90),
                                       (int(px), int(py)), max(1, int(2 * fade)))
            continue

        if f["kind"] == "ripple":
            # KESH: knowledge travelling outward through the stone. the newly-mapped
            # floor lights up as the wave passes over it, so the player can watch the
            # scroll actually DO something -- most of which is off-screen.
            fade = 1.0 - prog
            wave = prog * f["r"]            # in tiles
            for (tx, ty) in f["tiles"]:
                if not cam.on_screen(tx, ty):
                    continue
                d = math.hypot(tx - f["x"], ty - f["y"])
                edge = abs(d - wave)
                if edge > 2.2:
                    continue
                a = int(150 * (1.0 - edge / 2.2) * fade)
                layer = pygame.Surface((T, T), pygame.SRCALPHA)
                layer.fill((*col, max(0, a)))
                surf.blit(layer, topleft(tx, ty))
            if cam.on_screen(f["x"], f["y"]):
                cx, cy = at(f["x"], f["y"])
                pygame.draw.circle(surf, (*col, 0), (cx, cy), 1)   # no-op guard
                pygame.draw.circle(surf, col, (cx, cy), int(wave * T),
                                   max(1, int(3 * fade)))
            continue

        if f["kind"] in ("vanish", "arrive"):
            # UUL: you left THERE, and you are now HERE
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            grow = prog if f["kind"] == "arrive" else (1.0 - prog)
            r = T * (0.15 + 0.75 * grow)
            pygame.draw.circle(surf, col, (cx, cy), int(r), max(1, int(3 * fade)))
            pygame.draw.circle(surf, (230, 245, 255), (cx, cy),
                               max(1, int(r * 0.35)), 1)
            for i in range(8):
                a = i * 0.785 + t * (3.0 if f["kind"] == "arrive" else -3.0)
                d = r * (1.15 if f["kind"] == "arrive" else 0.5 + 0.9 * fade)
                px = cx + math.cos(a) * d
                py = cy + math.sin(a) * d
                pygame.draw.circle(surf, col, (int(px), int(py)),
                                   max(1, int(3 * fade)))
            continue

        if f["kind"] == "stunstars":
            # the hammer's stagger, fired the instant it lands. A real-time fx, NOT a
            # read of m.stunned -- that counter is already spent by the time we draw.
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            draw_stun_stars(surf, cx, cy - T // 2 + 4, t, fade=1.0 - prog)
            continue

        if f["kind"] == "pulse":
            # a potion doing its work, on your own body
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            r = T * (0.35 + 0.75 * prog)
            ring = pygame.Surface((int(r * 2) + 4, int(r * 2) + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*col, int(120 * fade)),
                               (int(r) + 2, int(r) + 2), int(r))
            surf.blit(ring, (cx - int(r) - 2, cy - int(r) - 2))
            pygame.draw.circle(surf, col, (cx, cy), int(r), max(1, int(2 * fade)))
            for i in range(6):
                a = i * 1.047 - t * 2.0
                d = r * 0.9
                pygame.draw.circle(surf, col,
                                   (int(cx + math.cos(a) * d),
                                    int(cy + math.sin(a) * d - prog * T * 0.3)),
                                   max(1, int(3 * fade)))
            continue

        if f["kind"] == "freeze":
            # the beholder's gaze landing: ice crystals stabbing up around the player
            if not cam.on_screen(f["x"], f["y"]):
                continue
            cx, cy = at(f["x"], f["y"])
            fade = 1.0 - prog
            grow = min(1.0, prog * 3)
            for i in range(8):
                a = i / 8.0 * math.tau + 0.2
                d = T * (0.20 + 0.34 * grow)
                bx = cx + math.cos(a) * d
                by = cy + math.sin(a) * d
                h = T * 0.30 * grow
                pygame.draw.polygon(
                    surf, (*col, int(220 * fade)) if False else (200, 232, 255),
                    [(bx - 2, by), (bx + 2, by), (bx + math.cos(a) * 2, by - h)])
            ring = pygame.Surface((T, T), pygame.SRCALPHA)
            ring.fill((*col, int(70 * fade)))
            surf.blit(ring, topleft(f["x"], f["y"]))
            continue

        if f["kind"] == "flash":
            # VORN: the whole visible floor catches
            a = int(150 * (1.0 - prog) * (0.35 + 0.65 * min(1.0, prog * 4)))
            layer = pygame.Surface((config.W, config.H - config.HUD_H), pygame.SRCALPHA)
            layer.fill((*col, max(0, a)))
            surf.blit(layer, (0, 0))
            continue

        if not cam.on_screen(f["x"], f["y"]):
            continue
        cx, cy = at(f["x"], f["y"])
        span = (f["r"] + 0.5) * T          # the blast really is this big
        r = span * (0.25 + 0.95 * prog)
        fade = 1.0 - prog

        # the fireball: a hot core inside a cooler shell
        blob = pygame.Surface((int(r * 2) + 4, int(r * 2) + 4), pygame.SRCALPHA)
        pygame.draw.circle(blob, (*col, int(150 * fade)),
                           (int(r) + 2, int(r) + 2), int(r))
        pygame.draw.circle(blob, (255, 236, 170, int(190 * fade * fade)),
                           (int(r) + 2, int(r) + 2), int(r * 0.55))
        pygame.draw.circle(blob, (255, 255, 235, int(220 * fade ** 3)),
                           (int(r) + 2, int(r) + 2), int(r * 0.22))
        surf.blit(blob, (cx - int(r) - 2, cy - int(r) - 2))
        pygame.draw.circle(surf, (255, 220, 150), (cx, cy), int(r), max(1, int(3 * fade)))

        # embers thrown outward
        for i in range(9):
            a = i * 0.698 + f["x"] * 0.7 + f["y"]
            d = r * (0.55 + 0.5 * ((i % 3) / 2.0))
            ex = cx + math.cos(a) * d
            ey = cy + math.sin(a) * d - prog * T * 0.25       # they rise as they die
            rad = max(1, int(3 * fade * (1.0 - i / 12.0)))
            pygame.draw.circle(surf, (255, int(180 + 60 * fade), 90),
                               (int(ex), int(ey)), rad)

    badge = []
    if p.poison > 0:
        badge.append((140, 220, 120))
    if p.haste > 0:
        badge.append(config.MANA)
    if p.might > 0:
        badge.append(config.GOLD)
    if p.stoneskin > 0:
        badge.append((170, 174, 184))
    if p.regen > 0:
        badge.append(config.HEAL)
    if p.weak > 0:
        badge.append((150, 140, 90))
    if p.blade_coat == "poison":
        badge.append((150, 235, 120))
    elif p.blade_coat == "weak":
        badge.append((200, 190, 120))
    for i, bc in enumerate(badge):
        pygame.draw.circle(surf, bc, (cx - T // 2 + 5 + i * 8, cy - T // 2 + 5), 3)
