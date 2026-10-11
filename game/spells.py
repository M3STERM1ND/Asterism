"""Spells: each spell is a constellation the player draws on their turn.

A spell has a mana cost, a damage range (the total for the whole constellation, from a short reach to
the full reach) and a cooldown in turns: after casting, it can't be cast again until that many player
turns have passed (1 = never twice in a row). Bigger constellations cost more and hit harder.
Some spells start unlocked; the rest unlock when the player has won enough battles.
"""
from dataclasses import dataclass

MAX_MANA = 100
REST_MANA = 15   # extra mana from resting (skipping the attack)


@dataclass(frozen=True)
class Spell:
    name: str
    constellation: str   # the file in constellations/ (also the key shown on screen)
    stars: int
    cost: int
    damage: tuple        # (lowest, highest) total damage for the whole constellation
    cooldown: int        # player turns before it can be cast again
    unlock_wins: int     # battles won needed to use it


SPELLS = (
    Spell("Aries", "aries", 4, 10, (16, 32), 1, 0),
    Spell("Taurus", "taurus", 5, 15, (28, 50), 1, 0),
    Spell("Gemini", "gemini", 6, 20, (42, 72), 1, 0),
    Spell("Pisces", "pisces", 7, 25, (56, 98), 1, 1),
    Spell("Leo", "leo", 8, 30, (70, 120), 2, 2),
    Spell("Orion", "orion", 7, 28, (62, 108), 1, 3),
    Spell("Sagittarius", "sagittarius", 8, 34, (80, 136), 2, 4),
    Spell("Scorpius", "scorpius", 10, 42, (110, 180), 2, 6),
)


def unlocked(wins):
    """The spells available after winning this many battles."""
    return [s for s in SPELLS if s.unlock_wins <= wins]


def newly_unlocked(wins):
    """The spells that the win which brought the total to `wins` just unlocked."""
    return [s for s in SPELLS if s.unlock_wins == wins]


def star_damage(spell, quality, leaned, lean_penalty=0.5):
    """Damage for one star of a spell. quality is 0 (a short reach) to 1 (the full reach or beyond);
    it picks a point in the spell's damage range, shared evenly between its stars."""
    low, high = spell.damage
    damage = (low + (high - low) * min(1.0, max(0.0, quality))) / spell.stars
    return max(1, round(damage * (lean_penalty if leaned else 1.0)))


class SpellBook:
    """Mana and cooldowns for one battle."""

    def __init__(self, spells):
        self.spells = list(spells)
        self.mana = MAX_MANA
        self.cooldowns = {}      # spell name -> player turns still to wait

    def reason_unavailable(self, spell):
        """None if the spell can be cast now, otherwise a short reason."""
        if spell not in self.spells:
            return "Locked"
        if self.cooldowns.get(spell.name, 0) > 0:
            return f"Cooldown {self.cooldowns[spell.name]}"
        if spell.cost > self.mana:
            return "Not enough mana"
        return None

    def can_cast(self, spell):
        return self.reason_unavailable(spell) is None

    def any_castable(self):
        return any(self.can_cast(s) for s in self.spells)

    def cast(self, spell):
        """Pay for the spell and start its cooldown. Returns False (and changes nothing) if it can't be cast."""
        if not self.can_cast(spell):
            return False
        self.mana -= spell.cost
        self.cooldowns[spell.name] = spell.cooldown + 1  # ticked once at the end of this very turn
        return True

    def rest(self):
        """Skip the attack to recover a little extra mana."""
        self.mana = min(MAX_MANA, self.mana + REST_MANA)

    def end_turn(self, refill):
        """Between turns: cooldowns count down and mana refills a little."""
        self.cooldowns = {n: c - 1 for n, c in self.cooldowns.items() if c > 1}
        self.mana = min(MAX_MANA, self.mana + refill)
