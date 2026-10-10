"""Editor: placing stars, naming, and saving files the game can load. Run: .venv\\Scripts\\python -m unittest"""
import json
import os
import tempfile
import unittest

from editor import BACKSPACE, ENTER, ESCAPE, MAX_STARS, Editor, normalize, slug
from sessions.reach import load_constellation

CANVAS = (48, 130, 1232, 600)


def type_text(editor, text):
    for ch in text:
        editor.handle_key(ord(ch), 0.0)


def place(editor, count):
    for i in range(count):
        editor.click(100 + i * 100, 200 + (i % 2) * 100, 0.0)


class NormalizeTest(unittest.TestCase):
    def test_longer_side_spans_zero_to_one_and_shape_is_kept(self):
        self.assertEqual(normalize([(100, 200), (300, 200), (300, 300)]), [[0.0, 0.0], [1.0, 0.0], [1.0, 0.5]])

    def test_slug_makes_a_safe_file_name(self):
        self.assertEqual(slug("  Little Bear's Tail "), "little_bear_s_tail")
        self.assertEqual(slug("../../etc"), "etc")


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.editor = Editor(CANVAS, protected=["orion"], folder=self.folder)

    def test_clicks_outside_the_canvas_or_too_close_are_ignored(self):
        self.editor.click(10, 10, 0.0)
        self.editor.click(500, 300, 0.0)
        self.editor.click(510, 305, 0.0)
        self.assertEqual(self.editor.stars, [(500, 300)])

    def test_no_more_than_eight_stars(self):
        place(self.editor, MAX_STARS + 2)
        self.assertEqual(len(self.editor.stars), MAX_STARS)

    def test_backspace_and_x_remove_stars(self):
        place(self.editor, 3)
        self.editor.handle_key(BACKSPACE, 0.0)
        self.assertEqual(len(self.editor.stars), 2)
        self.editor.handle_key(ord("x"), 0.0)
        self.assertEqual(self.editor.stars, [])

    def test_naming_takes_every_letter_including_editor_keys(self):
        self.editor.handle_key(ord("n"), 0.0)
        type_text(self.editor, "Sxn  q")
        self.editor.handle_key(BACKSPACE, 0.0)
        self.editor.handle_key(ENTER, 0.0)
        self.assertEqual(self.editor.name, "Sxn")
        self.assertIsNone(self.editor.typing)

    def test_escape_cancels_naming(self):
        self.editor.name = "Lyra"
        self.editor.handle_key(ord("n"), 0.0)
        type_text(self.editor, "abc")
        self.editor.handle_key(ESCAPE, 0.0)
        self.assertEqual(self.editor.name, "Lyra")

    def test_save_needs_four_stars_and_a_name(self):
        place(self.editor, 3)
        self.assertIsNone(self.editor.save(0.0))
        place(self.editor, 1)
        self.assertIsNone(self.editor.save(0.0))
        self.assertEqual(os.listdir(self.folder), [])

    def test_built_in_constellations_are_never_overwritten(self):
        place(self.editor, 4)
        self.editor.name = "Orion"
        self.assertIsNone(self.editor.save(0.0))

    def test_saved_file_loads_like_a_built_in_one(self):
        place(self.editor, 5)
        self.editor.name = "Little Bear"
        path = self.editor.save(0.0)
        self.assertEqual(path, os.path.join(self.folder, "little_bear.json"))
        data = load_constellation(path)
        self.assertEqual(data["name"], "Little Bear")
        self.assertEqual(data["order"], "sequential")
        self.assertEqual(len(data["stars"]), 5)
        xs, ys = zip(*data["stars"])
        self.assertEqual(max(max(xs) - min(xs), max(ys) - min(ys)), 1.0)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), data)


if __name__ == "__main__":
    unittest.main()
