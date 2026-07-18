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

"""The Kodex: the only thing that survives a run.

DEATHWARD is a permadeath roguelike. When you die you lose the floor, the gold,
the gear and the corpse-warm certainty that this run was the one. You keep
exactly one thing: what you learned.

The guarantee (enforced by `postmortem`-style tests in tests.py):

    every death reveals a fact the player has never seen. every time.

The ladder:
    1. the first death explains what death itself does in this dungeon
    2/3/4. the rule, tell and counter of the thing that killed you
    5. the nearest unlearned fact about anything else on that floor
    6. the true name of an item you are carrying but have not identified
    7. a secret about yourself or the dungeon
    8. intel on something you have not met yet
    9. telemetry synthesised from your own corpse-strewn history -- computed at
       the moment of death, and therefore inexhaustible

And the design rule the whole thing rests on:

    KNOWLEDGE IS INFORMATION, NEVER POWER.

Learning a monster's rule does not weaken it. Learning a trap does not disarm it.
The dungeon simulates identically for an ignorant hero and an omniscient one --
what changes is how much of it you are permitted to SEE. An un-codexed monster is
a '?' with no health bar and no readable intent. An un-codexed trap is invisible
floor. An unidentified potion is just a colour.
"""

import json
import os

from . import config


class Fact:
    def __init__(self, key, subject, tier, title, text):
        self.key = key
        self.subject = subject        # monster/trap/item family, or self/dungeon
        self.tier = tier              # rule | tell | counter | identity | secret | telemetry
        self.title = title
        self.text = text


def _f(key, subject, tier, title, text):
    return Fact(key, subject, tier, title, text)


FACT_LIST = [
    # --- what death is here ---------------------------------------------
    _f("self.corpse", "self", "secret", "THE DEAD DO NOT LEAVE",
       "This dungeon does not tidy up. Where you fall, your body stays -- and it "
       "keeps what it was carrying. Descend to that depth again and your own corpse "
       "will be waiting with your gold and the weapon still in its hand. Every run "
       "you lose is a cache you leave for the next one."),
    _f("self.energy", "self", "secret", "TURNS ARE A CURRENCY",
       "Nothing here moves in real time. Everything -- you, the rats, the thing in "
       "the dark -- spends the same currency: turns. Boots are not a cosmetic. Fast "
       "boots literally buy you extra actions between a monster's swings. Heavy "
       "armour sells them back."),
    _f("self.armour", "self", "secret", "ARMOUR IS SUBTRACTION",
       "Armour does not reduce damage by a fraction. It subtracts a flat number from "
       "EVERY hit. Against one big monster it barely matters. Against six small ones "
       "it is the difference between a scratch and a grave. Plate is for swarms."),
    _f("self.stairs", "self", "secret", "DOWN IS FREE",
       "The stairs never ask for a toll. You may leave any floor at any moment, with "
       "any fraction of it explored. Greed is the only thing that keeps you on a "
       "floor -- and greed is a choice, not a rule."),

    # --- ANGRY RAT -------------------------------------------------------
    _f("angry_rat.rule", "angry_rat", "rule", "ANGRY RAT -- WHAT IT IS",
       "A rat with a grievance. It does 1 or 2, it has almost no blood in it, and it "
       "comes at you alone. It is the least dangerous thing in this entire dungeon, "
       "which should tell you something about the rest of it."),
    _f("angry_rat.tell", "angry_rat", "tell", "ANGRY RAT -- THE TELL",
       "It commits. An angry rat that has seen you does not circle and does not wait "
       "-- it comes straight in, every turn, until one of you stops moving. Its health "
       "is now drawn, and there is not much of it."),
    _f("angry_rat.counter", "angry_rat", "counter", "ANGRY RAT -- THE COUNTER",
       "Hit it. That is genuinely the whole answer, and it is worth knowing that SOME "
       "things down here can simply be hit. Learn the difference between this and its "
       "plague-ridden cousins on the floor below, who do not come at you one at a time."),

    # --- RAT -------------------------------------------------------------
    _f("rat.rule", "rat", "rule", "PLAGUE RAT -- WHAT IT IS",
       "Fast, frail, and never alone. It gets roughly three moves for every two of "
       "yours, and it dies to a stiff breeze. The danger is arithmetic: a rat does 1 "
       "to 3, and there are never fewer than four of them."),
    _f("rat.tell", "rat", "tell", "PLAGUE RAT -- THE TELL",
       "Rats do not approach in a line. They fan. If you can see two, there are more "
       "behind them, and they are already circling to your flanks. Their health is "
       "now drawn."),
    _f("rat.counter", "rat", "counter", "PLAGUE RAT -- THE COUNTER",
       "Never fight a swarm in the open, where all six reach you at once. Back into a "
       "corridor and they can only come at you one at a time. A doorway is worth more "
       "than a better sword."),

    # --- KOBOLD ----------------------------------------------------------
    _f("kobold.rule", "kobold", "rule", "KOBOLD -- WHAT IT IS",
       "A competent little soldier. It hits for 3 to 6, it has real health, and it "
       "does something almost nothing else down here does: when it is badly hurt, it "
       "runs."),
    _f("kobold.tell", "kobold", "tell", "KOBOLD -- THE TELL",
       "Watch the moment it turns. A fleeing kobold is not retreating -- it is going "
       "to fetch the others. Its health bar and its intent are now legible."),
    _f("kobold.counter", "kobold", "counter", "KOBOLD -- THE COUNTER",
       "Do not let a wounded one leave. A kobold that escapes comes back with company, "
       "and you will fight the same monster twice, the second time surrounded. Finish "
       "it, or block the door."),

    # --- SPITTER ---------------------------------------------------------
    _f("spitter.rule", "spitter", "rule", "BILE SPITTER -- WHAT IT IS",
       "It does not want to touch you. It stands off at range and spits acid down any "
       "straight line it shares with you -- four tiles, ignoring one point of your "
       "armour. In the open it will kill you without ever being in reach."),
    _f("spitter.tell", "spitter", "tell", "BILE SPITTER -- THE TELL",
       "It rears back a full turn before it spits, and it only ever fires along a "
       "straight line. The wind-up is now drawn, and so is the line it is about to "
       "fire down."),
    _f("spitter.counter", "spitter", "counter", "BILE SPITTER -- THE COUNTER",
       "Break the line. One diagonal step off its row or column and the shot has "
       "nowhere to go. Do not walk straight at a spitter -- that is the one path it "
       "is aiming at. Come at it crooked."),

    # --- BRUTE -----------------------------------------------------------
    _f("brute.rule", "brute", "rule", "BRUTE -- WHAT IT IS",
       "Enormous, slow, and capable of removing half of you in a single blow. It moves "
       "at roughly half your speed. It cannot catch you. It has never needed to."),
    _f("brute.tell", "brute", "tell", "BRUTE -- THE TELL",
       "It does not swing on arrival. It plants its feet and WINDS UP for one full "
       "turn, and only lands the blow on the next. That wind-up is now drawn above its "
       "head, in red, and it is the most useful red in this dungeon."),
    _f("brute.counter", "brute", "counter", "BRUTE -- THE COUNTER",
       "The wind-up is a free turn and it is aimed at the tile you are standing on. "
       "STEP. One tile in any direction and eight hundred pounds of arm hits stone. "
       "Then hit it while it recovers. A brute fought this way is not dangerous. A "
       "brute fought toe-to-toe is a coffin."),

    # --- WRAITH ----------------------------------------------------------
    _f("wraith.rule", "wraith", "rule", "WRAITH -- WHAT IT IS",
       "It walks through walls. Corridors do not exist to it, doors do not exist to it, "
       "and your armour does not exist to it -- a wraith's touch subtracts nothing for "
       "plate. It drains what it touches."),
    _f("wraith.tell", "wraith", "tell", "WRAITH -- THE TELL",
       "It brightens as it feeds and dims as it starves. A wraith that has not touched "
       "anything in a long while is nearly transparent -- and nearly harmless. Its "
       "health is now drawn."),
    _f("wraith.counter", "wraith", "counter", "WRAITH -- THE COUNTER",
       "You cannot outrun it and you cannot wall it out, so stop trying. It is SLOW, "
       "and it is frail, and it ignores armour -- which means the armour you are "
       "wearing is dead weight here. Kill it with speed, or leave the floor. Wraithsilk "
       "is the one cloth its touch cannot find."),

    # --- MIMIC -----------------------------------------------------------
    _f("mimic.rule", "mimic", "rule", "MIMICS EXIST",
       "Not every chest is a chest. Some of them are patient. It will sit perfectly "
       "still for the whole run, and it will open the moment you do."),
    _f("mimic.tell", "mimic", "tell", "MIMIC -- THE TELL",
       "A real chest sits square to the room. A mimic cannot quite hold the pose -- its "
       "lid breathes, very slightly, on a rhythm no hinge has. Now that you have seen "
       "it once you cannot unsee it: mimics are marked."),
    _f("mimic.counter", "mimic", "counter", "MIMIC -- THE COUNTER",
       "It has to wait for you to be adjacent, which means you choose the ground. Open "
       "the suspicious ones with a wall at your back and a corridor behind you -- or "
       "simply do not open them. No chest in this dungeon is worth a run."),

    # --- FLICKER ---------------------------------------------------------
    _f("flicker.rule", "flicker", "rule", "FLICKER -- WHAT IT IS",
       "It will not stand and fight. It blinks to a tile right beside you, cuts you, "
       "and is gone again before you can answer -- and the walls do not stop it, and "
       "neither does standing with your back to one. It appears wherever it likes."),
    _f("flicker.tell", "flicker", "tell", "FLICKER -- THE TELL",
       "Watch the beat AFTER it hits you. When a flicker blinks in and strikes, it is "
       "spent -- for one turn it cannot blink, and it just hangs there beside you. Its "
       "health is now drawn, and that helpless beat is your one chance each cycle to "
       "chip it down."),
    _f("flicker.counter", "flicker", "counter", "FLICKER -- THE COUNTER",
       "You cannot chase it and you cannot wall it out, so do not try. The turn after "
       "it cuts you it is stuck and helpless -- that window is the only time you can "
       "hit it, and it takes several such blows to bring one down, so expect to trade "
       "hits for a while. Its trick is a room with room to spare: fight it in a "
       "CORRIDOR, where there are only two tiles it can appear on, and the guessing is "
       "over."),

    # --- ORC -------------------------------------------------------------
    _f("orc.rule", "orc", "rule", "ORC -- WHAT IT IS",
       "It never comes alone -- three, four, five of them, moving as one. They have "
       "keen eyes: the instant one of them has a clear line to you, the whole pack "
       "knows exactly where you are and comes at once. They are a little faster than "
       "you, so you will not simply outrun a pack in the open."),
    _f("orc.tell", "orc", "tell", "ORC -- THE TELL",
       "Two things, once you have watched a pack. First: they are only dangerous when "
       "they can SEE you. Break the line -- a corner, a pillar, a doorway -- and they "
       "lose you at once and pull back together, milling, because they are not clever "
       "enough to remember where you went. Second: while they ARE hunting, they have "
       "no side. An orc goes for the nearest living thing and does not care whose it "
       "is; put a pack near a brute mid-hunt and they will maul the brute. Their "
       "health is now drawn."),
    _f("orc.counter", "orc", "counter", "ORC -- THE COUNTER",
       "Never fight a pack head-on in the open. Two answers, and they stack. ONE: break "
       "line of sight. Duck round a corner and the whole pack forgets you and regroups "
       "-- that is your moment to pick them off a few at a time, or just to leave. TWO: "
       "give them something else to kill. This is what that useless scroll was FOR -- "
       "read a scroll of Summoning at your feet WHILE they are on you: the things it "
       "calls up, the orcs will tear apart, and the summons will tear back. Point them "
       "at each other and walk to the stairs."),

    # --- BEHOLDER --------------------------------------------------------
    _f("beholder.rule", "beholder", "rule", "BEHOLDER -- WHAT IT IS",
       "A slow, floating eye that fights in two beats. First its gaze locks you in ice "
       "where you stand -- that does no damage; the freeze is the setup. Then, on its "
       "very next turn, it follows with a baleful ray, and THAT hurts. On its own the "
       "ray is what threatens you; in a crowd, the freeze is far worse -- you die to "
       "everything else that reaches you while you cannot move."),
    _f("beholder.tell", "beholder", "tell", "BEHOLDER -- THE TELL",
       "It winds up. For one full turn before the gaze lands its eye is drawn wide "
       "open, and the line from it to you is painted across the floor. That line is "
       "your only warning -- and it warns of both halves, because the ray only ever "
       "comes right after a freeze. No freeze, no ray."),
    _f("beholder.counter", "beholder", "counter", "BEHOLDER -- THE COUNTER",
       "Break the line of sight. Step behind a wall, a pillar, a corner -- anything "
       "solid between its eye and you -- before the gaze lands, and it freezes empty "
       "stone. Dodge the gaze and you dodge the whole combo, ray included. After it "
       "fires it must recharge, so a beholder you have just weathered is harmless for a "
       "few turns. It is slow, so close on it and cut it down between combos -- but it "
       "is no pushover; it takes several solid blows, and a freeze-and-ray or two will "
       "land while you work. Never stand in the open in its eyeline with a crowd at "
       "your back -- frozen in a mob is how it kills you."),

    # --- STONE GOLEM -----------------------------------------------------
    _f("golem.rule", "golem", "rule", "STONE GOLEM -- WHAT IT IS",
       "A brute cut from rock. It plants and swings like a brute and hits like a "
       "landslide -- but do not mistake it for one: it is FAST, faster than you are "
       "comfortable with, and once it has seen you it does not stop. But that is not "
       "the thing you need to know about it. The thing you need to know is what "
       "happened when you hit it back."),
    _f("golem.tell", "golem", "tell", "STONE GOLEM -- THE TELL",
       "Your blade rang off it and barely marked the stone. It winds up exactly like a "
       "brute -- one turn, feet planted, aimed at the tile you are on -- so step off it "
       "the same way. Its health is now drawn. And you have felt it by now: you cannot "
       "walk away from this one. It tracks you across the whole floor, a step behind "
       "and always closing."),
    _f("golem.counter", "golem", "counter", "STONE GOLEM -- THE COUNTER",
       "You do not kill this with steel -- steel is for the things that bleed. It is "
       "STONE, and stone cracks in FIRE. A fire glyph, a Flame Brand, a scroll of "
       "Firestorm -- any of them does to a golem what your sword cannot. And since you "
       "cannot outrun it, fire is not just the fast way, it is the only way that ends "
       "well: lead it onto a glyph, or set it alight, and keep moving. Everything else "
       "down here you fight. This one you cook."),

    # --- POLTERGEIST -----------------------------------------------------
    _f("poltergeist.rule", "poltergeist", "rule", "POLTERGEIST -- WHAT IT IS",
       "So THAT is what has been hitting you out of empty air. A poltergeist -- an "
       "unseen thing that walks through your walls as if they were not there. It "
       "barely rakes you, but you cannot see it, you cannot wall it out, and you "
       "cannot hit what you cannot find. Knowing its name is the first crack of "
       "light."),
    _f("poltergeist.tell", "poltergeist", "tell", "POLTERGEIST -- THE TELL",
       "You have learned to catch it in the act. The instant it strikes, it flares "
       "into view on its own tile for a single heartbeat -- and then it is gone again. "
       "It is not much. But now you know which way it came from, and roughly where it "
       "is standing, right up until it moves."),
    _f("poltergeist.counter", "poltergeist", "counter", "POLTERGEIST -- THE COUNTER",
       "Now you can SEE it -- a faint shimmer in the air, there all the time, no "
       "longer only in the half-second after it hits. That is the whole fight. Walls "
       "will not stop it and armour hardly matters, and it takes several solid blows "
       "to put down -- but none of that saved it once you could look straight at it. "
       "This monster is beaten by knowledge first; the killing is just bookkeeping "
       "after that."),

    # --- WARDEN (boss) ---------------------------------------------------
    _f("warden.rule", "warden", "rule", "THE WARDEN -- WHAT IT IS",
       "The thing at the bottom. It has the brute's wind-up, the spitter's line, and "
       "the wraith's contempt for armour, and it has more health than anything you have "
       "ever hit. It is not a new lesson. It is the exam."),
    _f("warden.tell", "warden", "tell", "THE WARDEN -- THE TELL",
       "It alternates. It never uses the same attack twice in a row, and it always "
       "telegraphs one turn early -- feet planted for the smash, head reared for the "
       "line. Its intent is now drawn."),
    _f("warden.counter", "warden", "counter", "THE WARDEN -- THE COUNTER",
       "Everything this dungeon has already taught you, in one room: step off the "
       "wind-up, break the line, keep the pillars between you and it, and never trade "
       "blows with something that hits harder than you. You knew how to kill it long "
       "before you ever saw it. Every one of those lessons was bought upstairs, from "
       "something smaller."),

    # --- TRAPS -----------------------------------------------------------
    _f("dart.rule", "dart", "rule", "DART TRAP -- WHAT IT IS",
       "A pressure plate wired to a wall. Step on it and it puts a dart through you "
       "from across the room, for 3 to 7. Armour does help."),
    _f("dart.counter", "dart", "counter", "DART TRAP -- THE COUNTER",
       "The plates you have already sprung are on your map for good -- but ONLY those. "
       "Knowing what a dart trap is does not tell you where the next one is. Walk "
       "around the ones you have found. Better: lead something with legs over them."),
    _f("spike.rule", "spike", "rule", "SPIKE PIT -- WHAT IT IS",
       "A covered hole full of rusted iron. It costs you blood on the way in and a full "
       "turn climbing out, and a turn spent in a pit with a monster beside it is worse "
       "than the spikes."),
    _f("spike.counter", "spike", "counter", "SPIKE PIT -- THE COUNTER",
       "A pit you have fallen into is a pit you will never fall into twice -- it is on "
       "your map for the rest of this game. The others are not. Never fight beside a "
       "pit you can be pushed into, and never cross one while something is chasing "
       "you: the turn you lose climbing out is the turn it catches you."),
    _f("gas.rule", "gas", "rule", "GAS VENT -- WHAT IT IS",
       "It does not hurt when you step on it. It poisons you, and the poison bleeds you "
       "for a point a turn until it burns out. It kills people who were already nearly "
       "dead -- which, down here, is everyone."),
    _f("gas.counter", "gas", "counter", "GAS VENT -- THE COUNTER",
       "The vents you have found stay found; the rest of them are still breathing "
       "quietly in the dark. Poison does not stack from one vent, but it does not stop "
       "for a fight either. Do not carry a poison into a room you have not cleared, "
       "and never descend while it is still in you."),
    _f("alarm.rule", "alarm", "rule", "ALARM RUNE -- WHAT IT IS",
       "It does no damage at all. It screams -- and every monster on the floor learns "
       "exactly where you are and starts walking. The most dangerous trap down here "
       "does not have a single sharp edge."),
    _f("alarm.counter", "alarm", "counter", "ALARM RUNE -- THE COUNTER",
       "Every rune you have set off is marked, and every rune you have not is not. If "
       "you trip a fresh one, do not stand and fight in the open -- the whole floor is "
       "coming. Take a corridor, take a doorway, or take the stairs."),
    _f("glyph.rule", "glyph", "rule", "FIRE GLYPH -- WHAT IT IS",
       "It burns everything on it and everything beside it, for 4 to 9, and it does not "
       "care who set it off. It is the only trap in this dungeon that hurts monsters "
       "exactly as much as it hurts you."),
    _f("glyph.counter", "glyph", "counter", "FIRE GLYPH -- THE COUNTER",
       "A glyph you have found is not an obstacle any more -- it is a weapon, and it is "
       "on your map for good. Stand across it from something big and slow, let it step "
       "on, and let the floor do the work. The dungeon will fight for you, in the few "
       "places where you have already learned where it keeps its teeth."),

    # --- ITEM IDENTITIES -------------------------------------------------
    _f("id.ochre", "item", "identity", "THE OCHRE POTION IS HEALING",
       "This one closes wounds -- a clean bite of health back in a single swallow, the "
       "simplest good flask in a place with very few of them. Drink it when a fight has "
       "already drawn blood and you need that blood back, not before."),
    _f("id.azure", "item", "identity", "THE AZURE POTION IS SWIFTNESS",
       "This one is speed -- twenty turns of moving like the rats do. Drink it to escape, "
       "not to fight."),
    _f("id.viscous", "item", "identity", "THE VISCOUS POTION IS VENOM",
       "This one is not medicine. Drunk in a panic it has ended more runs than any "
       "monster on the first three floors. But now that you know what it is, you will "
       "never drink it again -- you will WIPE IT DOWN YOUR BLADE, and the next thing "
       "you hit will take it instead of you. One coat, one strike, and it is gone. The "
       "flask did not change. You did. That is the entire dungeon, in one bottle."),
    _f("id.black", "item", "identity", "THE BUBBLING BLACK POTION IS MIGHT",
       "This one is fury: twenty turns of hitting appreciably harder. It is the potion "
       "you should be saving for the bottom of the dungeon."),
    _f("id.kesh", "item", "identity", "THE SCROLL 'KESH' MAPS THE FLOOR",
       "This scroll unrolls the whole level in your head -- every room, every corridor, "
       "the way down. And that is ALL it does. It is a map of the stone. It will not show "
       "you the gold, it will not show you which chest is a mimic, it will not show "
       "you a single trap, and it will not show you what is walking about in there. "
       "It tells you where you can go. It tells you nothing about what it costs."),
    _f("id.vorn", "item", "identity", "THE SCROLL 'VORN' IS FIRE",
       "This scroll sets fire to everything you can currently see. Everything you can "
       "see. Check what is standing next to you before you read it."),
    _f("id.uul", "item", "identity", "THE SCROLL 'UUL' IS ESCAPE",
       "This scroll throws you somewhere else on the floor, at random. It is not a good "
       "escape. It is, sometimes, the only one."),
    _f("id.gramm", "item", "identity", "THE SCROLL 'GRAMM' IS A MISTAKE",
       "This scroll summons. It has never once summoned anything that was pleased to see "
       "you. Read it only if you want the floor to come to you."),

    # --- WAVE 1 consumables ----------------------------------------------
    _f("id.grey", "item", "identity", "THE CLOUDY GREY POTION IS STONESKIN",
       "This one hardens your hide for a while -- blows that would have opened you slide "
       "off instead. Drink it before you wade into a crowd, not after."),
    _f("id.crimson", "item", "identity", "THE CRIMSON POTION IS REGENERATION",
       "This one does two things at once. It washes out whatever ails you -- poison, "
       "sapped strength, a swimming head -- and then it knits you closed a little at a "
       "time, turn after turn. It is not a panic heal; it is worth the most drunk "
       "EARLY, before a long fight, so the mending runs the whole way through it -- "
       "and it is your answer to a bad flask you drank by mistake."),
    _f("id.sallow", "item", "identity", "THE SALLOW YELLOW POTION IS WEAKNESS",
       "This one saps the strength out of whoever drinks it -- their blows land soft for "
       "a good while. Drunk in ignorance it is a punishment. But now that you know it, "
       "you never drink it again: you WIPE IT DOWN YOUR BLADE, exactly like venom, and "
       "the next thing you cut has ITS strength sapped instead of yours. Save it for "
       "the heavy hitter you would rather not trade blows with."),
    _f("id.silver", "item", "identity", "THE SILVERY POTION IS VIGOR",
       "This one lays a reserve of strength over your own -- temporary vitality that "
       "takes the next blows before your real health is ever touched. Drink it BEFORE "
       "you wade in, not after: it is a shield you raise, not a wound you close, and "
       "it fades if you dawdle instead of fighting."),
    _f("id.morn", "item", "identity", "THE SCROLL 'MORN' IDENTIFIES",
       "This scroll spells out the true name of the mystery you are carrying the most of. In "
       "a dungeon where every unknown flask is a coin-flip between a cure and a "
       "poison, a scroll that just TELLS you is worth saving for the thing you are "
       "most afraid to drink."),
    _f("id.yris", "item", "identity", "THE SCROLL 'YRIS' IS LIGHT",
       "This scroll floods light out around you: the nearby stone, anything lurking in it, "
       "and -- this is the point -- the traps. Read it walking blind into a new "
       "stretch of floor, and the pressure plates light up before your foot does."),
    _f("id.ghask", "item", "identity", "THE SCROLL 'GHASK' IS AGGRAVATION",
       "This scroll wakes the entire floor and points it at you. There is no good reason "
       "to read it on purpose. Learn what it is, and never read it again -- unless you have "
       "a very particular plan and a very fast pair of boots."),
    _f("id.vosh", "item", "identity", "THE SCROLL 'VOSH' DETECTS TREASURE",
       "This scroll lights up every hoard on the floor at once -- chests, dropped gear, loose "
       "coin. It shows you WHERE the treasure is and nothing about what is sitting on "
       "it, so a chest it reveals may still be a mimic. It pairs well with the way "
       "down: sweep the floor for loot, then leave."),

    # --- WAVE 2 consumables ----------------------------------------------
    _f("id.rose", "item", "identity", "THE ROSE-GOLD POTION IS GREATER HEALING",
       "This one does not just close a wound -- it closes ALL of them. From a sliver "
       "of health to full, in a single swallow. It is the flask you save for the "
       "moment a fight has gone completely wrong, not the one you sip to top up."),
    _f("id.vermilion", "item", "identity", "THE VERMILION POTION IS RAGE",
       "This one is fury in a bottle: for a good while you hit markedly harder and "
       "move faster. The price is written in the same breath -- you stop guarding "
       "yourself, and every blow that lands on you bites deeper. Drink it to END a "
       "fight fast, never to survive a losing one."),
    _f("id.teal", "item", "identity", "THE TEAL POTION IS WARDING",
       "This one halves everything that hits you for a while -- steel, fang, fire, a "
       "beholder's ray, all of it, cut in two. It is the potion for walking THROUGH "
       "something you cannot walk around."),
    _f("id.sky", "item", "identity", "THE SKY-BLUE POTION IS LEVITATION",
       "This one lifts your feet clear of the floor. Pressure plates do not click, "
       "pits do not open, and a spike pit you are already stuck in simply lets you "
       "float out. It does nothing about gas or fire in the air -- only what is "
       "underfoot."),
    _f("id.krav", "item", "identity", "THE SCROLL 'KRAV' ENCHANTS A WEAPON",
       "This scroll pours a permanent edge into the weapon in your hand -- +1 damage, and it "
       "stays. Read it over your BEST weapon, and read it again over the same one: it "
       "stacks. The enchantment lives on the weapon, so keep the weapon."),
    _f("id.dwen", "item", "identity", "THE SCROLL 'DWEN' ENCHANTS ARMOUR",
       "This scroll hardens the armour you are wearing by a permanent +1 defence, and it "
       "stacks with itself. Flat defence is a swarm answer -- every point you add is "
       "subtracted from EVERY blow -- so a stack of these turns a mob of small teeth "
       "into a nuisance."),
    _f("id.violet", "item", "identity", "THE VIOLET POTION IS INVISIBILITY",
       "This one bends the light around you: for a while, NOTHING on the floor can find "
       "you. Not the orcs' eyes, not the beholder's gaze, not a thing. You can walk "
       "straight through a room you could never have fought your way out of. It ends "
       "the instant you swing a weapon -- you cannot kill from hiding -- and it thins "
       "away on its own. "
       "This is not a fighting tool. It is an escape, a scout, a way PAST."),
    _f("id.vesh", "item", "identity", "THE SCROLL 'VESH' IS INVISIBILITY",
       "This scroll does exactly what the invisibility potion does -- wraps you in unseeing for a "
       "while -- and having it as a scroll as well is not a mistake. Down in the deep "
       "floors, being unseen is worth carrying twice. Read it to slip a pack, cross a "
       "killing floor, or reach the stairs alive. It breaks the moment you attack."),
    _f("id.puce", "item", "identity", "THE MUDDY PUCE POTION IS CONFUSION",
       "This one is the third bad flask, and it obeys the same rule as venom and weakness: "
       "drunk in ignorance it turns on YOU -- the floor swims and your feet stop going "
       "where you point them. But now that you know it, you never drink it. You WIPE "
       "IT ON THE BLADE, and the next thing you cut staggers off at random instead. "
       "Coat it onto the heavy hitter and walk away while it blunders into a wall."),
    _f("id.skarn", "item", "identity", "THE SCROLL 'SKARN' IS FEAR",
       "This scroll rolls dread out around you, and everything close enough turns and flees. "
       "It does not kill anything -- it BUYS you a stretch of floor. Read it when you "
       "are surrounded and need the room to breathe, to drink, or to run for the "
       "stairs. They come back once it fades, so spend the gap well."),
    _f("id.gorm", "item", "identity", "THE SCROLL 'GORM' IS HOLD MONSTER",
       "This scroll snags time itself: everything near you locks rigid for a good ten turns, "
       "unable to move or strike. That is a real escape window -- long enough to walk "
       "clear of a mob in a hallway, land free blows on things that cannot answer, "
       "drink, or just leave. The beholder does this to YOU; this scroll hands the trick "
       "back, and holds longer."),
    _f("id.zeph", "item", "identity", "THE SCROLL 'ZEPH' IS TELEPORT",
       "This scroll is the aimed cousin of the Escape scroll. Instead of throwing you "
       "somewhere at random, it opens a cursor and lets you CHOOSE -- any open tile "
       "you have already seen, anywhere on the floor. Jump to the stairs, out of a "
       "corner, or across a chasm you cannot walk. It only knows places you have been, "
       "so it rewards a floor you have explored."),

    # --- WAVE 3 consumables (rare) ---------------------------------------
    _f("id.vital", "item", "identity", "THE SCARLET POTION IS VITALITY",
       "This one does not heal you -- it makes you BIGGER. Your maximum life climbs, "
       "permanently, and stays climbed through every death after. It is the only "
       "potion whose worth outlives the run you drink it in, so never leave one on the "
       "floor."),
    _f("id.radiant", "item", "identity", "THE GOLDEN POTION IS HEROISM",
       "This one is every good potion at once, for a while: a heal, harder blows, more "
       "speed, and a tougher hide, all together. It is the flask you break open at the "
       "top of the fight you have to win -- a mini-boss, the Warden, a room that has "
       "gone wrong. Do not waste it topping up."),
    _f("id.luminous", "item", "identity", "THE LUMINOUS POTION IS INSIGHT",
       "This one hands you a whole lesson for nothing -- one Codex entry you had not "
       "yet earned, learned in a swallow instead of a death. In a game where knowledge "
       "is the only thing you truly keep, a potion that just GIVES you some is worth "
       "more than it looks."),
    _f("id.ember", "item", "identity", "THE SMOULDERING POTION IS THE PHOENIX",
       "This one sets an ember behind your ribs. The next time something would end you "
       "-- a swarm, a trap, the Warden's fist -- death is refused, and "
       "you come back on your feet with half your life. Once. It is the closest this "
       "dungeon comes to a second chance; carry it into the fights you are not sure "
       "you walk out of."),
    _f("id.ossk", "item", "identity", "THE SCROLL 'OSSK' IS BANISHMENT",
       "This scroll unmakes an entire kind at once: whatever there is most of on the floor "
       "simply ceases to be there. No corpses, no loot -- you did not kill them, you "
       "erased them. Read it when a pack has you outnumbered and you would rather the "
       "pack was just... gone."),
    _f("id.vrom", "item", "identity", "THE SCROLL 'VROM' IS DESCENT",
       "This scroll drops you straight onto the way down, wherever the stairs are hiding. It "
       "does not take you down -- it puts you ON them -- so you choose the moment. The "
       "fastest exit from a floor that has turned against you, short of dying."),
    _f("id.dract", "item", "identity", "THE SCROLL 'DRACT' IS THUNDERCLAP",
       "This scroll is a single, flat crack of force through everything you can see. Real "
       "damage, to every monster in sight at once, and -- unlike Firestorm -- it does "
       "not touch YOU. The scroll for a room that is too full to fight one at a time."),
    _f("id.ulm", "item", "identity", "THE SCROLL 'ULM' IS SANCTUARY",
       "This scroll wraps a stillness around you. For a while nothing can land a blow -- not a "
       "fist, not a ray, not the beholder's gaze. They can still come, you can still "
       "act, but you cannot be touched. Read it to walk out through a crowd, revive a "
       "plan, or stand on the stairs unhurried."),

    # --- DUNGEON ---------------------------------------------------------
    _f("dungeon.hoard", "dungeon", "secret", "THE HOARDS ARE GUARDED",
       "Rooms that glitter are not gifts. The dungeon puts its gold where its teeth are "
       "-- the denser the treasure, the worse the thing sleeping on it. If a room looks "
       "generous, count the exits before you take a step into it."),
    _f("dungeon.deep", "dungeon", "secret", "WHY YOU CANNOT SEE",
       "The dark down here is not a lack of torches. It is a lack of understanding. The "
       "dungeon draws exactly as much of itself as you have earned -- a thing you do not "
       "know is drawn as a hole, a trap you have never triggered is drawn as clean "
       "floor. You are not lighting this place up. You are learning it."),
]

FACTS = {f.key: f for f in FACT_LIST}
TOTAL_FACTS = len(FACT_LIST)
TIER_ORDER = ["rule", "tell", "counter"]

# The tabs the Kodex is split into. Gear is not fact-backed (see the Gear tab in ui).
KODEX_TABS = ["monsters", "traps", "scrolls", "potions", "gear", "lore"]


def category_of(fact):
    """Which Kodex tab a fact belongs to: monsters | traps | scrolls | potions | lore.
    (Gear is handled separately -- it is not a fact.)"""
    if fact.subject == "item":
        from .items import CONSUMABLES
        flavor = fact.key.split(".", 1)[1]
        c = CONSUMABLES.get(flavor)
        return "scrolls" if (c and c.kind == "scroll") else "potions"
    if fact.subject in ("self", "dungeon"):
        return "lore"
    from .traps import TRAP_NAMES
    if fact.subject in TRAP_NAMES:
        return "traps"
    return "monsters"


def facts_in(category):
    """The static facts belonging to one tab, in Kodex order."""
    return [f for f in FACT_LIST if category_of(f) == category]


def fact_title(fact, codex):
    """The title to SHOW for a fact. For an item-identity fact this names the look the
    potion or scroll wears THIS game -- which colour/rune an effect hides behind is
    shuffled per game, so the stored title (which bakes in one fixed look) must not be
    shown verbatim. Every other fact just uses its stored title."""
    if fact.subject == "item" and fact.key.startswith("id."):
        from .items import CONSUMABLES
        flavor = fact.key.split(".", 1)[1]
        c = CONSUMABLES.get(flavor)
        if c:
            look = CONSUMABLES[codex.look(flavor)]
            effect = c.true_name.split(" of ", 1)[-1]      # "Regeneration", "Mapping"
            return "THE %s IS %s" % (look.unknown_name.upper(), effect.upper())
    return fact.title

# --- learning by killing -------------------------------------------------
# A corpse can be read. Standing over the thing you just killed teaches you what it
# WAS -- and, if you have killed enough of them, how it moved and how it dies.
#
# But notice the price. The rule is one kill. The tell is three. The counter is
# eight. A single death hands you the same fact immediately. Killing is the slow
# way to learn and dying is the fast one, and that is the whole thesis of this game
# stated as a number: the dungeon charges you far less for a lesson you paid for
# with your life than for one you tried to grind out safely.
KILL_THRESHOLD = {"rule": 1, "tell": 3, "counter": 8}

# --- learning by springing -----------------------------------------------
# A trap you have never met is not drawn at all. Not a '?' -- nothing. Clean floor.
# You find out it exists the way everyone finds out a trap exists: it goes off.
#
# The FIRST time one fires -- under you, or under a monster while you are watching --
# you learn what it is, and from that moment every trap of that kind is drawn on your
# floor, in this run and every run after it, forever. The counter takes three.
TRAP_THRESHOLD = {"rule": 1, "counter": 3}

SELF_SECRETS = ["self.energy", "self.armour", "self.stairs"]
DUNGEON_SECRETS = ["dungeon.hoard", "dungeon.deep"]

CAUSE_NAME = {
    "angry_rat": "an angry rat",
    "rat": "a plague rat", "kobold": "a kobold", "spitter": "a bile spitter",
    "brute": "a brute", "wraith": "a wraith", "mimic": "a mimic",
    "flicker": "a flicker", "orc": "an orc", "golem": "a stone golem",
    "beholder": "a beholder", "poltergeist": "a poltergeist",
    "warden": "the Warden", "dart": "a dart trap", "spike": "a spike pit",
    "gas": "a gas vent", "alarm": "an alarm rune", "glyph": "a fire glyph",
    "poison": "poison", "starvation": "the dark",
}


class Codex:
    def __init__(self):
        self.known = []
        self.gear_seen = []     # gear keys you have picked up or worn -- the Gear tab
        # THE LOOK OF THE UNKNOWN. Which colour/rune each effect hides behind is dealt
        # fresh every NEW GAME and kept for the whole game (across respawns). identity
        # flavor -> the flavor whose look (unknown name + colour) it wears. Display
        # only: it never touches what a potion DOES, only what it looks like unidentified.
        self.appearance = {}
        self.telemetry = []
        # the running message log for the WHOLE game -- it survives death and respawn
        # (the codex does), and is wiped only by a new game (wipe() re-runs __init__).
        # runtime only: never serialised, so it does not bloat the save.
        self.messages = []
        self.deaths = 0
        self.best_depth = 0
        self.runs = 0
        self.wins = 0
        self.corpses = {}       # depth (str) -> {"x","y","gold","weapon","gift"}
        self.gifts = []         # one-time-per-GAME rewards already claimed
        self.gift_item = None   # WHICH gear the gift turned out to be, so we can
                                # still recognise it after it has been swapped out
        # WHAT YOU HAVE SEEN OF THE STONE. Kept per floor, for the whole game. The
        # map you drew with your feet does not get wiped because you died on it --
        # the corridors are still where they were, and you still remember walking
        # them. Only a new game forgets.
        self.maps = {}          # depth (str) -> "0101..." one char per tile
        # THE TRAPS YOU HAVE FOUND. Individually. A trap is a thing cut into the
        # floor at a place, and springing the one by the stairs tells you exactly
        # nothing about the one in the treasury. Knowing what a dart trap IS does not
        # tell you where they all are -- you find every single one of them the hard
        # way, once, and then you never forget that one.
        self.found_traps = {}   # depth (str) -> ["x,y", ...]
        # THE GAME'S SEED. The stone of this dungeon is cut once, when the game
        # begins, and it does not move again until a new game. Floor 4's rooms and
        # corridors are the same rooms and corridors every time you walk back into
        # them -- what changes on a respawn is what is LIVING in them.
        self.world_seed = None
        self.layout_migrated = False
        self.stats = {
            "turns": 0,
            "kills": 0,
            "kills_by": {},
            "damage_dealt": 0,
            "damage_taken": 0,
            "gold_lost": 0,
            "gold_banked": 0,
            "deaths_by": {},
            "potions_drunk": 0,
            "traps_triggered": 0,
            "traps_by": {},         # per-type: how many times you have seen it fire
            "steps": 0,
            "deepest_kill": {},
        }

    # --- persistence ----------------------------------------------------
    def load(self):
        if not os.path.exists(config.SAVE_PATH):
            return
        try:
            with open(config.SAVE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        self.known = [k for k in data.get("known", []) if k in FACTS]
        self.gear_seen = data.get("gear_seen", [])
        self.appearance = data.get("appearance", {})
        self.telemetry = data.get("telemetry", [])
        self.deaths = data.get("deaths", 0)
        self.best_depth = data.get("best_depth", 0)
        self.runs = data.get("runs", 0)
        self.wins = data.get("wins", 0)
        self.corpses = data.get("corpses", {})
        self.gifts = data.get("gifts", [])
        self.gift_item = data.get("gift_item")
        self.maps = data.get("maps", {})
        self.found_traps = data.get("found_traps", {})
        self.world_seed = data.get("world_seed")
        self.stats.update(data.get("stats", {}))

        # A save cut by an older dungeon generator remembers a map that no longer
        # matches the walls. Throw the PLACE away and keep the person.
        if data.get("layout_version", 1) != config.LAYOUT_VERSION:
            self.new_dungeon()
            self.layout_migrated = True

    def save(self):
        data = {
            "known": self.known, "gear_seen": self.gear_seen,
            "appearance": self.appearance,
            "telemetry": self.telemetry, "deaths": self.deaths,
            "best_depth": self.best_depth, "runs": self.runs, "wins": self.wins,
            "corpses": self.corpses, "gifts": self.gifts, "maps": self.maps,
            "gift_item": self.gift_item,
            "layout_version": config.LAYOUT_VERSION,
            "found_traps": self.found_traps,
            "world_seed": self.world_seed, "stats": self.stats,
        }
        try:
            with open(config.SAVE_PATH, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
        except OSError:
            pass

    def has_progress(self):
        """Is there anything here worth continuing -- or worth warning about before
        we erase it?"""
        return bool(self.known or self.telemetry or self.deaths or self.corpses
                    or self.runs or self.wins or self.gifts)

    # --- the map you drew with your feet ---------------------------------
    def remember_map(self, depth, explored):
        """Fold what this run saw into what the game already knew. Memory only ever
        grows -- dying cannot un-walk a corridor."""
        key = str(depth)
        h = len(explored)
        w = len(explored[0]) if h else 0
        old = self.maps.get(key)
        out = []
        for y in range(h):
            row = explored[y]
            for x in range(w):
                i = y * w + x
                was = old[i] == "1" if old and i < len(old) else False
                out.append("1" if (was or row[x]) else "0")
        self.maps[key] = "".join(out)

    def recall_map(self, depth, w, h):
        """The explored grid for this floor, or None if you have never been here."""
        s = self.maps.get(str(depth))
        if not s or len(s) != w * h:
            return None
        return [[s[y * w + x] == "1" for x in range(w)] for y in range(h)]

    # --- traps, one at a time --------------------------------------------
    def trap_found(self, depth, x, y):
        return "%d,%d" % (x, y) in self.found_traps.get(str(depth), [])

    def find_trap(self, depth, x, y):
        """This trap. Not this KIND of trap. This one, at this spot, forever."""
        lst = self.found_traps.setdefault(str(depth), [])
        key = "%d,%d" % (x, y)
        if key not in lst:
            lst.append(key)
            return True
        return False

    def traps_found_on(self, depth):
        return len(self.found_traps.get(str(depth), []))

    # --- the shape of the dungeon ----------------------------------------
    def layout_seed(self, depth):
        """The seed for FLOOR `depth`'s stonework. Derived from the game's seed, so
        it is stable for the whole game and unique per floor."""
        base = self.world_seed or 0
        return (base * 1000003 + depth * 2654435761) & 0x7FFFFFFF

    # --- one-time gifts --------------------------------------------------
    def gift_claimed(self, key):
        """Some rewards are once per GAME, not once per run. The guaranteed floor 1
        upgrade is the reward for exploring floor 1 -- exactly once. It must not
        regrow every time you die, or dying becomes a way to farm it."""
        return key in self.gifts

    def claim_gift(self, key):
        """Spent when the player actually PICKS IT UP -- not when it spawns. Dying
        on floor 1 before you ever found it should not quietly cost you the thing
        you never got."""
        if key not in self.gifts:
            self.gifts.append(key)

    def new_dungeon(self):
        """A NEW DUNGEON, but not a new you. Called when a victor starts over.

        Everything that describes THE PLACE is thrown away -- the stone is re-cut, the
        map you drew is forgotten, the traps you found are hidden again, your dead are
        gone with whatever they were holding, and the floor-1 gift is waiting again.

        Everything that describes WHAT YOU KNOW survives: the Kodex, the telemetry,
        every death it cost you. You walk into an unfamiliar dungeon, but you walk in
        able to read it. That is the reward for killing the Warden -- not power, but
        the one thing this game has ever given for free: not being ignorant.
        """
        self.world_seed = None       # re-cut on the next World()
        self.maps = {}
        self.found_traps = {}
        self.corpses = {}
        self.gifts = []
        self.gift_item = None

    def wipe(self):
        """A NEW GAME. Not a new run -- a new game. Everything the player ever
        learned, every body they left behind, every number: gone. They walk back in
        knowing nothing, and the monsters are '?' again.

        This is irreversible, so the only caller is behind a confirmation prompt.
        """
        try:
            if os.path.exists(config.SAVE_PATH):
                os.remove(config.SAVE_PATH)
        except OSError:
            pass
        self.__init__()

    # --- queries --------------------------------------------------------
    def knows(self, key):
        return key in self.known

    def knows_tier(self, subject, tier):
        return "%s.%s" % (subject, tier) in self.known

    def tier(self, subject):
        n = 0
        for t in TIER_ORDER:
            if "%s.%s" % (subject, t) in self.known:
                n += 1
            else:
                break
        return n

    def roll_appearances(self, seed):
        """Deal each effect the look it will wear this game. Within a kind (potions
        among potions, scrolls among scrolls) the looks are a random permutation over
        the effects, across all tiers -- a common-looking flask may be a rare potion.
        Seeded off the game's seed on its OWN rng, so it is reproducible for the game
        and cannot nudge the dungeon's stone."""
        import random as _random
        from .items import CONSUMABLES
        rng = _random.Random("appearance:%s" % seed)
        self.appearance = {}
        for kind in ("potion", "scroll"):
            flavors = [f for f, c in CONSUMABLES.items() if c.kind == kind]
            looks = flavors[:]
            rng.shuffle(looks)
            for ident, look in zip(flavors, looks):
                self.appearance[ident] = look

    def look(self, flavor):
        """The flavor whose look (unknown name + colour) `flavor` wears this game.
        Falls back to itself if appearances have not been dealt yet."""
        return self.appearance.get(flavor, flavor)

    def identified(self, flavor):
        return "id.%s" % flavor in self.known

    def identify(self, flavor):
        """Learning by using -- drinking the unknown potion also teaches you."""
        key = "id.%s" % flavor
        if key in FACTS and key not in self.known:
            self.known.append(key)
            return FACTS[key]
        return None

    def see_gear(self, key):
        """You have picked up or worn this piece of gear -- it earns its Kodex entry."""
        if key and key not in self.gear_seen:
            self.gear_seen.append(key)

    def gear_known(self, key):
        return key in self.gear_seen

    def progress(self):
        return len(self.known), TOTAL_FACTS

    # --- corpses --------------------------------------------------------
    def write_corpse(self, depth, x, y, gold, weapon_key, gift_key, loot,
                     weapon_bonus=0):
        """Overwrite the saved record of the body on this floor, exactly as it now
        stands. Called whenever the body is touched -- without this, taking gold off
        your corpse mutated only the in-memory copy, and the save still believed the
        gold was there, so you could collect it again on the next death. Forever."""
        self.corpses[str(depth)] = {
            "x": x, "y": y, "gold": gold, "weapon": weapon_key,
            "weapon_bonus": weapon_bonus, "gift": gift_key,
            "loot": [list(t) for t in loot],
        }

    def leave_corpse(self, depth, x, y, gold, weapon_key, gift_key=None,
                     weapon_bonus=0):
        """The body stays exactly where it fell, and it keeps what it was carrying.

        Your dead accumulate: dying twice on the same floor must never quietly
        destroy the cache the first body was holding. The gold piles up on the
        newest corpse, it keeps the better of the two weapons (its +n breaking the
        tie), and it never loses the gift -- the gift is once per game, so if a
        corpse is holding it, that corpse is the only place in the world it still
        exists.
        """
        from .items import ALL_GEAR

        loot = []
        old = self.corpses.get(str(depth))
        if old:
            gold += old.get("gold", 0)
            old_w = old.get("weapon")
            old_b = old.get("weapon_bonus", 0)
            if old_w in ALL_GEAR and weapon_key in ALL_GEAR:
                # keep the better weapon: higher tier wins, +n breaks the tie
                if (ALL_GEAR[old_w].tier, old_b) > (ALL_GEAR[weapon_key].tier,
                                                    weapon_bonus):
                    weapon_key, weapon_bonus = old_w, old_b
            elif old_w and not weapon_key:
                weapon_key, weapon_bonus = old_w, old_b
            gift_key = gift_key or old.get("gift")
            loot = [tuple(t) for t in old.get("loot", [])]   # never drop what it held
        self.write_corpse(depth, x, y, gold, weapon_key, gift_key, loot, weapon_bonus)

    def gift_on_a_corpse(self):
        """Which floor, if any, is holding the gift for you."""
        for depth, c in self.corpses.items():
            if c.get("gift"):
                return int(depth), c["gift"]
        return None

    def corpse_at(self, depth):
        return self.corpses.get(str(depth))

    def take_corpse(self, depth):
        return self.corpses.pop(str(depth), None)

    # --- THE GUARANTEE --------------------------------------------------
    def reveal_on_death(self, cause, floor_subjects, carried_flavors):
        """Return a Fact the player has never seen. Never returns None.

        cause           -- what killed them (monster/trap key)
        floor_subjects  -- subjects present on the floor they died on, nearest first
        carried_flavors -- unidentified item flavors in their pack when they died
        """
        # 1. the first death explains death
        if "self.corpse" not in self.known:
            return self._grant("self.corpse")

        # 2/3/4. the thing that killed you, in order
        for tier in TIER_ORDER:
            key = "%s.%s" % (cause, tier)
            if key in FACTS and key not in self.known:
                return self._grant(key)

        # 5. the nearest unlearned thing on the floor you died on
        for subject in floor_subjects:
            for tier in TIER_ORDER:
                key = "%s.%s" % (subject, tier)
                if key in FACTS and key not in self.known:
                    return self._grant(key)

        # 6. the true name of something you died holding
        for flavor in carried_flavors:
            key = "id.%s" % flavor
            if key in FACTS and key not in self.known:
                return self._grant(key)

        # 7. secrets about yourself, then the dungeon
        for key in SELF_SECRETS + DUNGEON_SECRETS:
            if key not in self.known:
                return self._grant(key)

        # 8. anything at all you have not met yet
        for f in FACT_LIST:
            if f.key not in self.known:
                return self._grant(f.key)

        # 9. inexhaustible
        return self._telemetry_fact()

    def _grant(self, key):
        self.known.append(key)
        return FACTS[key]

    def reveal_random(self, rng):
        """A Potion of Insight: learn one whole fact you did not have, for free. Any
        static Codex entry you have not yet earned. Returns the Fact, or None if you
        already know them all."""
        unknown = [k for k in FACTS if k not in self.known]
        if not unknown:
            return None
        return self._grant(rng.choice(unknown))

    def _telemetry_fact(self):
        s = self.stats
        by = s["deaths_by"]
        worst = max(by.items(), key=lambda kv: kv[1])[0] if by else "nothing"
        kills = s["kills"]
        candidates = [
            ("TELEMETRY -- YOUR NEMESIS",
             "Across %d deaths, the thing that has killed you most is %s -- %d times. "
             "You know exactly what it does. Knowing and respecting are different "
             "skills." % (self.deaths, CAUSE_NAME.get(worst, worst), by.get(worst, 0))),
            ("TELEMETRY -- THE LEDGER",
             "You have dealt %d damage and absorbed %d. You have killed %d things and "
             "died %d times. The dungeon is not beating you by a wide margin -- it is "
             "beating you by a consistent one."
             % (s["damage_dealt"], s["damage_taken"], kills, self.deaths)),
            ("TELEMETRY -- WHAT YOU LEAVE BEHIND",
             "You have lost %d gold to your own corpses and recovered %d of it. Every "
             "coin you did not go back for is still down there, in your hand."
             % (s["gold_lost"], s["gold_banked"])),
            ("TELEMETRY -- THE DEEP",
             "Your deepest descent is floor %d of %d. You have walked %d steps and "
             "spent %d turns to get there, and every one of those turns is in the "
             "Codex now." % (self.best_depth, config.DEPTH_MAX, s["steps"], s["turns"])),
            ("TELEMETRY -- THE FLOOR",
             "You have triggered %d traps and drunk %d unknown potions. Curiosity has a "
             "price down here, and you have been paying it in instalments."
             % (s["traps_triggered"], s["potions_drunk"])),
            ("TELEMETRY -- THE RATE",
             "%d runs. %d deaths. %.1f kills per run. That is not a failure rate -- it "
             "is a learning rate, and it is the only stat in this dungeon that only "
             "ever goes up."
             % (self.runs, self.deaths, kills / max(1, self.runs))),
        ]
        seen = {t["title"] + t["text"] for t in self.telemetry}
        for title, text in candidates:
            if title + text not in seen:
                self.telemetry.append({"title": title, "text": text})
                return Fact("telemetry.%d" % len(self.telemetry), "self", "telemetry",
                            title, text)

        # live numbers change with every death: this branch cannot run dry
        title = "TELEMETRY -- DEATH %d" % self.deaths
        text = ("Death %d, on floor %d. %d turns lived, %d things killed, %d damage "
                "taken, %d/%d of the Kodex written. The record grows because you keep "
                "coming back." % (self.deaths, self.best_depth, s["turns"], kills,
                                  s["damage_taken"], len(self.known), TOTAL_FACTS))
        self.telemetry.append({"title": title, "text": text})
        return Fact("telemetry.%d" % len(self.telemetry), "self", "telemetry", title, text)

    def record_death(self, cause):
        self.deaths += 1
        self.stats["deaths_by"][cause] = self.stats["deaths_by"].get(cause, 0) + 1

    # --- learning by killing --------------------------------------------
    def reveal_on_kill(self, subject):
        """Standing over a fresh corpse. Returns a Fact, or None if this one has
        nothing left to teach you yet.

        Unlike a death, a kill is NOT guaranteed to teach you anything. It teaches
        you only when you have killed enough of them to have earned the next tier,
        and it can never skip a tier. Dying to the thing is always the shorter road.
        """
        kills = self.stats["kills_by"].get(subject, 0)
        for tier in TIER_ORDER:
            key = "%s.%s" % (subject, tier)
            if key not in FACTS:
                continue
            if key in self.known:
                continue                      # already know it: look at the next tier
            if kills >= KILL_THRESHOLD[tier]:
                return self._grant(key)
            return None                       # not enough corpses yet, and no skipping
        return None

    def reveal_on_trap(self, subject):
        """A trap just went off in front of you. Returns a Fact, or None.

        Traps have no 'tell' -- there is nothing to read on a pressure plate. They
        have a rule (what it does, and from now on WHERE THEY ALL ARE) and a counter.
        """
        seen = self.stats["traps_by"].get(subject, 0)
        for tier in ("rule", "counter"):
            key = "%s.%s" % (subject, tier)
            if key not in FACTS or key in self.known:
                continue
            if seen >= TRAP_THRESHOLD[tier]:
                return self._grant(key)
            return None
        return None

    def kills_until_next_lesson(self, subject):
        """How many more of these you must kill to learn the next thing. None if
        there is nothing left to learn from killing them."""
        kills = self.stats["kills_by"].get(subject, 0)
        for tier in TIER_ORDER:
            key = "%s.%s" % (subject, tier)
            if key not in FACTS or key in self.known:
                continue
            return max(0, KILL_THRESHOLD[tier] - kills)
        return None
