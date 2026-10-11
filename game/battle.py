"""Battle: Orion against an enemy, turn by turn, like a Pokemon fight. Each turn a side either attacks
or blocks. Nothing is ever timed; every turn waits for the player.

  select  - the player picks: a spell (1-8), Block (B, or hold a fist), or Rest (0)   } the player's turn
  player  - Attack: draw the spell's constellation; power builds star by star         }
  guard   - Block: one Grip rep (fist, hold, open wide) raises a shield               }
  result  - the attack lands, or the shield is up                                     }
  strike  - the enemy casts a constellation of its own, then it flies at Orion   } the enemy's turn
  brace   - the enemy blocks instead: the player's next spell does half          }
  heal    - on Hard the enemy sometimes heals                                    }
  pause   - a beat to read the outcome                                           }
  won / lost - over; then the check-in (how do you feel?) and the report
See turns.py for the strict turn rules: stars count only in "player", a block only in "guard".

A full Grip rep gives a full shield (the enemy's attacks that turn do nothing); opening early gives a
cracked shield (half damage). Choosing to attack means the enemy's answer lands in full.

Power per star = the spell's damage range, shared between its stars, by reach quality x form:
  reach quality: 0 for stars within 80% of the calibrated reach, rising to 1 at the full reach
                 and beyond, so the far stars do the most damage
  form:          x0.5 if a lean warning fired since the previous star
Nothing hurts the enemy until the last star is lit: then the power is added up and lands at once.
Each player turn plus the enemy's answer is one Round (report.py).
"""
import random

import numpy as np

import events
from game import difficulty as levels
from game import spells as magic
from game import turns
from game import report
from game.report import Round
from sessions.grip import CLOSED, Grip, openness
from sessions.reach import Reach, load_constellation

PLAYER_HEALTH = 100
QUALITY_FROM = 0.8        # stars past this share of the calibrated reach start to do extra damage
LEAN_PENALTY = 0.5        # damage multiplier when the player leaned on that star
CAST_SECONDS = 2.0        # the enemy traces its constellation star by star...
FLIGHT_SECONDS = 1.0      # ...then the strike flies at Orion
STRIKE_SECONDS = CAST_SECONDS + FLIGHT_SECONDS
RESULT_SECONDS = 1.6      # time to see the damage land before the turn passes
REPORT_DELAY = 2.5        # a win or a fall is shown this long before the check-in
FIST_CHOOSES_BLOCK = 1.0  # holding a fist this long on the select screen chooses Block
GUARD_FACTOR = 0.5        # the share of damage that gets through a cracked shield, or the enemy's guard
HEAL_SECONDS = 1.6        # length of the enemy's heal
BRACE_SECONDS = 1.6       # length of the enemy raising its guard
PAUSE_SECONDS = 1.5       # a beat to read "Blocked!" or the damage before the next turn
WON_SECONDS = 6.0         # how long the win is shown before moving on
RED = (107, 107, 255)     # #FF6B6B in BGR: Scorpius is drawn in the warning red
SHIELD_BLUE = (255, 190, 120)  # #78BEFF: the colour of a block
AMBER, VIOLET, TEAL, ROSE = (80, 170, 255), (220, 120, 200), (200, 200, 90), (150, 120, 255)

ATTACK_SCALE = (0.45, 0.85)  # the enemy's attack damage runs from this to that share of its strike, by star count.
# Tuned with tools/simulate.py: with attack-or-block turns the enemy's answer lands in full on every attack turn,
# so higher values made the last battles unwinnable for every simulated patient.


def attack_damage(base, stars):
    """Damage of an enemy attack: its strike damage, scaled by the size of the constellation it cast."""
    low, high = ATTACK_SCALE
    return max(1, round(base * (low + (high - low) * min(1.0, max(0.0, (stars - 4) / 6)))))


# The ladder of battles, each harder than the last and each with a new enemy.
# health/strike are the Normal values; the difficulty scales them. "eyes" and "color" draw the enemy.
BATTLES = [
    {"title": "Warm-up", "attacks": ["aries", "taurus"], "enemy": "The shadow", "health": 50, "strike": 10, "color": RED, "eyes": 2},
    {"title": "Scorpius", "attacks": ["scorpius", "gemini"], "enemy": "Scorpius", "health": 180, "strike": 25, "color": RED, "eyes": 0, "heart": True},
    {"title": "The Crab", "attacks": ["cancer", "libra"], "enemy": "Cancer's claw", "health": 220, "strike": 28, "color": AMBER, "eyes": 2},
    {"title": "The Twins", "attacks": ["gemini", "pisces"], "enemy": "The twin phantoms", "health": 260, "strike": 30, "color": VIOLET, "eyes": 4},
    {"title": "The Bull", "attacks": ["taurus", "capricornus"], "enemy": "The ash bull", "health": 310, "strike": 34, "color": TEAL, "eyes": 2},
    {"title": "The Serpent", "attacks": ["aquarius", "sagittarius"], "enemy": "Ophiuchus' serpent", "health": 370, "strike": 38, "color": ROSE, "eyes": 3},
    {"title": "The Void", "attacks": ["scorpius", "leo", "orion"], "enemy": "The devouring void", "health": 400, "strike": 38, "color": RED, "eyes": 5},
]


def reach_quality(star, cal):
    """0 within 80% of the calibrated reach, rising to 1 at the full reach and beyond."""
    ratio = np.hypot(*(np.array(star) - np.array(cal.shoulder))) / (cal.reach * cal.width)
    return float(np.clip((ratio - QUALITY_FROM) / (1 - QUALITY_FROM), 0.0, 1.0))


def star_damage(spell, star, cal, leaned):
    """Damage for one star of a spell."""
    return magic.star_damage(spell, reach_quality(star, cal), leaned, LEAN_PENALTY)


def load_attack(name, base):
    """An enemy attack from a constellation file: its name, its stars (0 to 1) and its damage."""
    data = load_constellation(f"constellations/{name}.json")
    return {"name": data["name"], "stars": data["stars"], "damage": attack_damage(base, len(data["stars"]))}


class Battle:
    def __init__(self, config, size, difficulty=levels.NORMAL, assisted=True, wins=0, rng=None):
        self.config = config
        self.size = size
        self.difficulty = difficulty
        self.assisted = assisted
        self.rng = rng or random.Random()
        self.book = magic.SpellBook(magic.unlocked(wins))
        self.wins = wins
        self.enemy_health = self.enemy_max = levels.enemy_health(config["health"], difficulty)
        self.strike_base = levels.strike_damage(config["strike"], difficulty)
        self.attacks = [load_attack(n, self.strike_base) for n in config["attacks"]]
        self.attack = self.attacks[0]  # the enemy's attack in progress (or the last one)
        self.player_health = PLAYER_HEALTH
        self.popups = []       # floating numbers: (pixel position, text, color, time)
        self.message = ""      # the latest outcome, e.g. "Blocked!"
        self.spell = None      # the spell being cast (or last cast)
        self.casts = []        # every Reach drawn in this battle, for the session log
        self.grips = []        # every Grip rep done as a Block, for the session log
        self.rounds = []       # one Round per player turn, for the report
        self.round = None
        self.strikes_left = 0
        self.shield = None     # the player's shield for the enemy's next turn: "full", "cracked" or None
        self.enemy_guarding = False  # the enemy chose to block: the player's next spell does half
        self.counted = False   # the win has been recorded (it unlocks spells)
        self.new_spells = []   # spells that win unlocked
        self.outcome = None    # "won" or "lost" once it is over
        self.checkin = {}      # the patient's answers after the battle (see report.CHECKIN)
        self.history = None    # earlier sessions, loaded by play.py for the report's comparison
        self.session = None    # this battle's own row in sessions.csv, parsed (progress.Session)
        self.checkin_saved = False
        self.dismissed = False  # the player has read the report and wants to go on
        self.report_page = 0    # the report has two pages: results, then tips
        self.fist_since = None  # on the select screen: since when a fist has been held (chooses Block)
        self.clock = None
        self.reach = None
        self.grip = None
        self.start_turn(None, first=True)

    @property
    def turn(self):
        """"player", "enemy", or None once the battle is over."""
        return turns.whose_turn(self.phase)

    @property
    def power(self):
        """The damage the spell being drawn will deal when it is finished."""
        return sum(self.pending)

    @property
    def fist_progress(self):
        """0 to 1: how far a held fist is toward choosing Block (select screen)."""
        if self.fist_since is None or self.clock is None:
            return 0.0
        return min(1.0, (self.clock - self.fist_since) / FIST_CHOOSES_BLOCK)

    @property
    def question(self):
        """The check-in question being asked, or None."""
        if self.phase != "checkin":
            return None
        return next((q for q in report.CHECKIN if q[0] not in self.checkin), None)

    def start_turn(self, now, first=False):
        """The player's turn: mana refills a little (not before the first turn), then they choose."""
        if not first:
            self.book.end_turn(self.difficulty.mana_refill)
        self.phase, self.phase_at = "select", now
        self.clock = now
        self.reach = None
        self.grip = None
        self.shield = None     # a shield only lasts through the enemy's turn after it was raised
        self.pending = []      # per-star damage waiting for the constellation to be finished
        self.lit = 0
        self.leaned = 0
        self.star_started = now
        self.fist_since = None
        self.round = Round(len(self.rounds) + 1)
        self.rounds.append(self.round)
        events.clear()  # a shield or attack effect from the last turn must not linger into this one

    def choose(self, index, now):
        """Attack: cast the spell at this index of the book (the number key minus one). Returns a message if refused."""
        if self.phase != "select":
            return None
        if not 0 <= index < len(magic.SPELLS):
            return None
        spell = magic.SPELLS[index]
        reason = self.book.reason_unavailable(spell)
        if reason is not None:
            self.message = f"{spell.name}: {reason}"
            return self.message
        self.book.cast(spell)
        self.spell = spell
        constellation = load_constellation(f"constellations/{spell.constellation}.json")
        self.reach = Reach(constellation, self.size, celebrate=False, unlit_color=self.config["color"],
                           difficulty=self.difficulty, assisted=self.assisted)
        self.casts.append(self.reach)
        self.round.move, self.round.spell, self.round.total_stars = "attack", spell.name, spell.stars
        self.phase, self.phase_at = "player", now
        self.lit, self.star_started = 0, now
        self.fist_since = None
        self.message = ""
        return None

    def block(self, now):
        """Block: this turn's move is one Grip rep that raises a shield against the enemy's next attack."""
        if self.phase != "select":
            return
        self.round.move = "block"
        self.grip = Grip()
        self.grips.append(self.grip)
        self.phase, self.phase_at = "guard", now
        self.fist_since = None
        self.message = ""

    def rest(self, now):
        """Skip the move for a little extra mana; the enemy's turn follows."""
        if self.phase != "select":
            return
        self.book.rest()
        self.round.move, self.round.rested = "rest", True
        self.message = "You rest and gather mana"
        self.begin_enemy_turn(now)

    def update(self, hands, pose, figure, camera_rect, now, cal, guard, blocked):
        """Advance the battle by one frame."""
        self.clock = now
        if self.star_started is None:
            self.star_started = now
        if self.phase == "select":
            self.watch_for_fist(hands, now)
        elif self.phase == "player":
            self.player_turn(hands, pose, figure, camera_rect, now, cal, guard, blocked)
        elif self.phase == "guard":
            self.guard_turn(hands, now, figure)
        elif self.phase == "result" and now - self.phase_at >= RESULT_SECONDS:
            if self.enemy_health <= 0:
                self.end("won", now)
                events.emit("WIN")
            else:
                self.begin_enemy_turn(now)
        elif self.phase == "strike" and now - self.phase_at >= STRIKE_SECONDS:
            self.resolve_strike(now, figure)
        elif self.phase in ("heal", "brace") and now - self.phase_at >= (HEAL_SECONDS if self.phase == "heal" else BRACE_SECONDS):
            self.phase, self.phase_at = "pause", now
        elif self.phase == "pause" and now - self.phase_at >= PAUSE_SECONDS:
            self.next_after_pause(now)
        elif self.phase in ("won", "lost") and now - self.phase_at >= REPORT_DELAY:
            self.phase, self.phase_at = "checkin", now

    def watch_for_fist(self, hands, now):
        """On the select screen, a fist held for FIST_CHOOSES_BLOCK chooses Block. (Not while drawing:
        a pointing finger can read as a half-closed hand.)"""
        values = [v for v in (openness(h) for h in hands) if v is not None]
        if values and min(values) < CLOSED:
            self.fist_since = self.fist_since if self.fist_since is not None else now
            if now - self.fist_since >= FIST_CHOOSES_BLOCK:
                self.block(now)
        else:
            self.fist_since = None

    def player_turn(self, hands, pose, figure, camera_rect, now, cal, guard, blocked):
        """Draw with Reach. Each lit star adds power, but nothing hurts the enemy until the last one is lit."""
        if not turns.can_attack(self.phase):
            return
        self.reach.update(hands, pose, figure, camera_rect, now, cal, blocked)
        while self.lit < len(self.reach.lit_at):
            star = self.reach.points[self.lit]
            leaned = guard.last_warn >= self.star_started
            self.pending.append(star_damage(self.spell, star, cal, leaned))
            self.leaned += 1 if leaned else 0
            self.lit += 1
            self.star_started = now
        if self.reach.won_at is None:
            return
        self.reach.enabled = False
        self.land_damage(now)

    def land_damage(self, now):
        """The constellation is finished: add up the power and hit the enemy once (half if it is guarding)."""
        total = self.power
        guarded = self.enemy_guarding
        if guarded:
            total = max(1, round(total * GUARD_FACTOR))
            self.enemy_guarding = False
        self.enemy_health = max(0, self.enemy_health - total)
        self.round.damage, self.round.enemy_blocked = total, guarded
        self.message = f"{self.config['enemy']}'s guard takes half!" if guarded else f"{self.spell.name} hits!"
        self.popups.append((self.reach.points[-1], f"-{total}" + ("  guarded" if guarded else ""),
                            SHIELD_BLUE if guarded else None, now))
        self.finish_round_stats()
        self.phase, self.phase_at = "result", now

    def guard_turn(self, hands, now, figure):
        """The Block move: a full Grip rep raises a full shield; opening early, a cracked one."""
        if not turns.can_block(self.phase):
            return
        self.grip.update(hands, now)
        if self.grip.result == "block":
            self.raise_shield("full", now, figure, "Shield up! The next attack is blocked")
        elif self.grip.result == "early":
            self.raise_shield("cracked", now, figure, "Opened too soon: a cracked shield takes half")

    def lower_guard(self, now, figure):
        """Space during the Block: give up the rep; no shield this turn."""
        if turns.can_block(self.phase):
            self.raise_shield(None, now, figure, "No shield this turn")

    def raise_shield(self, shield, now, figure, message):
        self.shield = self.round.shield = shield
        self.round.grip_held = self.grip.result == "block"
        self.round.open_seconds = self.grip.open_seconds
        if shield is not None:
            events.emit("SHIELD", pos=self.player_point(figure))
        self.message = message
        self.phase, self.phase_at = "result", now

    def finish_round_stats(self):
        """Copy what the drawing measured into this round's record."""
        r, reach = self.round, self.reach
        r.leaned = self.leaned
        if reach is not None:
            r.stars, r.errors_px, r.errors_sw = len(reach.lit_at), list(reach.errors_px), list(reach.errors_sw)
            r.hints, r.misses = reach.hints, reach.misses
            r.straightness, r.tremor_px, r.move_seconds = (list(reach.straightness), list(reach.tremor_px),
                                                           list(reach.move_seconds))
            reach.enabled = False

    def end(self, outcome, now):
        """The battle is over: show the win or the fall, then the check-in and the report."""
        self.phase, self.phase_at, self.outcome = outcome, now, outcome

    def answer(self, value):
        """The patient's answer (1 to 5) to the current check-in question."""
        q = self.question
        if q is not None and 1 <= value <= 5:
            self.checkin[q[0]] = value
            if self.question is None:
                self.phase = "report"

    def skip_checkin(self):
        if self.phase == "checkin":
            self.phase = "report"

    def begin_enemy_turn(self, now):
        """The turn passes to the enemy: it attacks (once, or twice on Hard), blocks, or heals."""
        if self.reach is not None:
            self.reach.enabled = False  # nothing the player does with the stars counts now
        self.enemy_guarding = False     # its guard only lasts through one player turn
        action = levels.choose_enemy_action(self.rng.random(), self.difficulty)
        self.round.enemy_action = action
        if action == "heal":
            healed = min(self.enemy_max - self.enemy_health, round(self.enemy_max * levels.HEAL_FRACTION))
            self.enemy_health += healed
            self.round.healed = healed
            self.message = f"{self.config['enemy']} heals {healed}" if healed else f"{self.config['enemy']} gathers itself"
            self.phase, self.phase_at = "heal", now
            return
        if action == "guard":
            self.enemy_guarding = True
            self.message = f"{self.config['enemy']} blocks: your next spell does half"
            self.phase, self.phase_at = "brace", now
            return
        self.strikes_left = 2 if action == "double" else 1
        self.begin_strike(now)

    def begin_strike(self, now):
        """The enemy picks one of its constellations to cast at Orion."""
        self.strikes_left -= 1
        self.attack = self.rng.choice(self.attacks)
        self.round.attacks.append(self.attack["name"])
        self.phase, self.phase_at = "strike", now
        events.emit("ATTACK")

    def resolve_strike(self, now, figure):
        """The enemy's attack arrives: a full shield stops it, a cracked one halves it, otherwise it lands."""
        damage = self.attack["damage"]
        if self.shield == "full":
            damage, result, self.message = 0, "blocked", "Blocked!"
            events.emit("SHIELD", pos=self.player_point(figure))
        elif self.shield == "cracked":
            damage, result = max(1, round(damage * GUARD_FACTOR)), "half"
            self.message = f"Your cracked shield takes half: -{damage}"
        else:
            result, self.message = "hit", f"{self.attack['name']} hits you"
        self.round.results.append(result)
        if damage:
            self.player_health = max(0, self.player_health - damage)
            self.round.damage_taken += damage
            self.popups.append((self.player_point(figure), f"-{damage}", RED, now))
        if self.player_health <= 0:
            self.end("lost", now)
        else:
            self.phase, self.phase_at = "pause", now

    def next_after_pause(self, now):
        """After the outcome has been read: a second attack if the enemy has one, else the player's turn."""
        if self.strikes_left > 0:
            self.begin_strike(now)
        else:
            self.start_turn(now)

    def dismiss(self):
        """Enter or Space on the report: the tips page first, then on to the next battle (or try again)."""
        if self.phase != "report":
            return
        if self.report_page == 0:
            self.report_page = 1
        else:
            self.dismissed = True

    def player_point(self, figure):
        """Middle of Orion's shoulders on screen (where the shield and hits appear), in pixels."""
        if figure is None:
            return (self.size[0] / 2, self.size[1] / 2)
        (lx, ly), (rx, ry) = figure.stars["Betelgeuse"], figure.stars["Bellatrix"]
        return ((lx + rx) / 2 * self.size[0], (ly + ry) / 2 * self.size[1])

    def finished(self, now):
        """True once a win's report has been read."""
        return self.phase == "report" and self.outcome == "won" and self.dismissed
