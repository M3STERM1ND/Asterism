"""Shared test doubles: a fake calibration, a fake body and fake hands."""
from types import SimpleNamespace

from calibration import Calibration

SIZE = (1280, 720)
CAL = Calibration(reach=2.0, side="Bellatrix", shoulder=(700.0, 400.0), width=100.0, tilt=0.0,
                  mid=(650.0, 400.0), heights=(400.0, 400.0), nose=None)
FIGURE = SimpleNamespace(stars={"Betelgeuse": (600 / 1280, 400 / 720), "Bellatrix": (700 / 1280, 400 / 720)})
WHOLE_VIEW = (0.0, 0.0, 1.0, 1.0)


def hand_at(x, y):
    """A hand whose index fingertip (landmark 8) is at this pixel."""
    lm = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(21)]
    lm[8] = SimpleNamespace(x=x / SIZE[0], y=y / SIZE[1], visibility=1.0)
    return [lm]


class QuietGuard:
    """A lean guard that has never warned."""
    last_warn = float("-inf")
    warnings = 0
