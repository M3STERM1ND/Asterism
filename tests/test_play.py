"""Play: the start menu keys, the editor's key routing, and logging each finished session once.
Run: .venv\\Scripts\\python -m unittest"""
import unittest
from unittest import mock

import play
from play import PRACTICE, Play, practice_list


class FakeView:
    frozen = False

    def camera_rect(self):
        return (0.0, 0.0, 1.0, 1.0)


def new_play():
    return Play((1280, 720), FakeView())


class MenuTest(unittest.TestCase):
    def test_menu_keys(self):
        for key, mode in (("p", "battle"), ("r", "practice"), ("e", "editor"), ("t", "test")):
            p = new_play()
            p.handle_key(ord(key))
            self.assertEqual(p.mode, mode)

    def test_editor_skips_calibration_and_m_returns_to_the_menu(self):
        p = new_play()
        p.handle_key(ord("e"))
        self.assertIsNone(p.calibrator)
        p.handle_key(ord("m"))
        self.assertEqual(p.mode, "start")

    def test_m_while_naming_is_a_letter(self):
        p = new_play()
        p.handle_key(ord("e"))
        p.handle_key(ord("n"))
        self.assertTrue(p.typing())
        p.handle_key(ord("m"))
        self.assertEqual((p.mode, p.editor.typing), ("editor", "m"))

    def test_clicks_place_stars_only_in_the_editor(self):
        p = new_play()
        p.handle_click(400, 300, 0.0)
        p.handle_key(ord("e"))
        p.handle_click(400, 300, 0.0)
        p.handle_click(600, 300, 0.0)
        p.handle_click(0, 0, 0.0, right=True)  # right-click removes the last star
        p.handle_click(700, 300, 0.0)
        self.assertEqual(p.editor.stars, [(400, 300), (700, 300)])

    def test_crafted_constellations_follow_the_zodiac(self):
        with mock.patch("play.os.listdir", return_value=["orion.json", "lyra.json", "notes.txt", "draco.json"]):
            self.assertEqual(practice_list(), PRACTICE + ["draco", "lyra"])


class LoggingTest(unittest.TestCase):
    def test_a_completed_practice_constellation_is_logged_once(self):
        p = new_play()
        p.mode = "practice"
        p.start_reach()
        p.reach.update = lambda *args: None
        p.reach.won_at = 5.0
        with mock.patch.object(play, "append_row") as append:
            p.update_practice([], None, None, 6.0, False)
            p.update_practice([], None, None, 6.1, False)
        append.assert_called_once()
        row = append.call_args[0][0]
        self.assertEqual((row["mode"], row["constellation"], row["result"]), ("practice", "Aries", "completed"))

    def test_a_won_battle_is_logged_with_its_damage(self):
        p = new_play()
        p.mode = "battle"
        p.start_battle()
        battle = p.battle
        battle.update = lambda *args: None
        battle.phase, battle.phase_at, battle.enemy_health = "won", 0.0, 0
        with mock.patch.object(play, "append_row") as append:
            p.update_battle([], None, None, 1.0, False)
            p.update_battle([], None, None, 1.1, False)
        append.assert_called_once()
        row = append.call_args[0][0]
        self.assertEqual((row["mode"], row["result"], row["damage dealt"]), ("battle", "won", battle.enemy_max))


if __name__ == "__main__":
    unittest.main()
