"""Spells: costs, mana, cooldowns, unlocks. Run: .venv/bin/python -m unittest"""
import unittest

from game import spells as magic
from sessions.reach import load_constellation


class SpellTest(unittest.TestCase):
    def test_star_counts_match_the_constellation_files(self):
        for s in magic.SPELLS:
            self.assertEqual(len(load_constellation(f"constellations/{s.constellation}.json")["stars"]), s.stars, s.name)

    def test_bigger_constellations_cost_more_and_hit_harder(self):
        by_size = sorted(magic.SPELLS, key=lambda s: (s.stars, s.cost))
        self.assertLess(by_size[0].cost, by_size[-1].cost)
        self.assertLess(by_size[0].damage[1], by_size[-1].damage[1])
        for a in magic.SPELLS:
            for b in magic.SPELLS:
                if a.stars < b.stars:
                    self.assertLessEqual(a.cost, b.cost)
                    self.assertLessEqual(a.damage[1], b.damage[1])

    def test_damage_runs_from_the_low_to_the_high_end_of_the_range(self):
        s = magic.SPELLS[0]
        total = lambda q, leaned=False: s.stars * magic.star_damage(s, q, leaned)
        self.assertAlmostEqual(total(0.0), s.damage[0], delta=s.stars)
        self.assertAlmostEqual(total(1.0), s.damage[1], delta=s.stars)
        self.assertLess(total(1.0, leaned=True), total(1.0))

    def test_some_spells_start_unlocked_and_wins_unlock_the_rest(self):
        self.assertGreaterEqual(len(magic.unlocked(0)), 3)
        self.assertLess(len(magic.unlocked(0)), len(magic.SPELLS))
        self.assertEqual(magic.unlocked(99), list(magic.SPELLS))
        self.assertEqual([s.name for s in magic.newly_unlocked(1)], ["Pisces"])

    def test_casting_costs_mana_and_starts_the_cooldown(self):
        book = magic.SpellBook(magic.unlocked(0))
        aries = magic.SPELLS[0]
        self.assertTrue(book.cast(aries))
        self.assertEqual(book.mana, magic.MAX_MANA - aries.cost)
        self.assertFalse(book.can_cast(aries))  # never twice in a row
        self.assertIn("Cooldown", book.reason_unavailable(aries))
        book.end_turn(refill=0)
        self.assertFalse(book.can_cast(aries))  # the next turn is still on cooldown
        book.end_turn(refill=0)
        self.assertTrue(book.can_cast(aries))

    def test_longer_cooldowns_last_longer(self):
        leo = next(s for s in magic.SPELLS if s.name == "Leo")
        book = magic.SpellBook(magic.unlocked(9))
        book.cast(leo)
        book.end_turn(0)  # the turn it was cast on ends
        for _ in range(leo.cooldown):  # then it sits out this many whole turns
            self.assertFalse(book.can_cast(leo))
            book.end_turn(0)
        self.assertTrue(book.can_cast(leo))

    def test_not_enough_mana_and_locked_spells_cannot_be_cast(self):
        book = magic.SpellBook(magic.unlocked(0))
        book.mana = 5
        self.assertEqual(book.reason_unavailable(magic.SPELLS[0]), "Not enough mana")
        self.assertEqual(book.reason_unavailable(magic.SPELLS[-1]), "Locked")
        self.assertFalse(book.cast(magic.SPELLS[0]))
        self.assertEqual(book.mana, 5)

    def test_mana_refills_each_turn_but_never_past_the_maximum(self):
        book = magic.SpellBook(magic.unlocked(0))
        book.cast(magic.SPELLS[2])
        book.end_turn(refill=15)
        self.assertEqual(book.mana, magic.MAX_MANA - magic.SPELLS[2].cost + 15)
        book.end_turn(refill=500)
        self.assertEqual(book.mana, magic.MAX_MANA)


if __name__ == "__main__":
    unittest.main()
