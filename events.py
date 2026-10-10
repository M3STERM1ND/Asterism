"""Events: the one place game moments become sound and screen effects.

Game code only calls emit("STAR", n), emit("WIN"), etc.
Sounds are generated with NumPy, so no audio files are needed.
If the audio device fails, the game keeps running silently.
"""
import os
import time

import numpy as np

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402  (must come after the env var above)

RATE = 44100
EFFECT_SECONDS = 1.5  # how long render.py keeps showing an effect

_audio_ok = False
_recent = []  # list of (event, n, pos, time_fired)


def init_audio():
    """Start pygame's mixer; on failure, remember to stay silent."""
    global _audio_ok
    try:
        pygame.mixer.init(frequency=RATE, size=-16, channels=2)
        _audio_ok = True
    except pygame.error as err:
        print(f"Audio unavailable, running silently: {err}")
        _audio_ok = False


def tone(freq, seconds, volume=0.4, fade=0.05):
    """A sine wave with a soft attack and fade-out, as float samples from -1 to 1."""
    t = np.linspace(0, seconds, int(RATE * seconds), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t) * volume
    envelope = np.minimum(1, np.minimum(t / 0.01, (seconds - t) / fade))
    return wave * envelope


def chime(n):
    """Bell-like chime; each star n climbs one step up a pentatonic scale."""
    steps = [0, 2, 4, 7, 9]
    semitones = steps[n % 5] + 12 * (n // 5)
    freq = 523.25 * 2 ** (semitones / 12)  # starts at C5
    return tone(freq, 0.6, 0.35, fade=0.5) + tone(freq * 2, 0.6, 0.1, fade=0.4)


def melody():
    """Short rising win tune: C E G C."""
    notes = [523.25, 659.25, 783.99, 1046.5]
    return np.concatenate([tone(f, 0.18, 0.35) for f in notes[:-1]] + [tone(notes[-1], 0.6, 0.35, fade=0.4)])


def rumble():
    """Deep rumble: a low tone with a slow wobble and some noise."""
    seconds = 0.9
    t = np.linspace(0, seconds, int(RATE * seconds), endpoint=False)
    wobble = 1 + 0.5 * np.sin(2 * np.pi * 6 * t)
    noise = np.random.uniform(-1, 1, t.size) * 0.08
    return (tone(55, seconds, 0.5, fade=0.4) + tone(82, seconds, 0.25, fade=0.4)) * wobble + noise * (1 - t / seconds)


SOUNDS = {
    "WIN": melody,
    "WARN LEAN": lambda: tone(180, 0.45, 0.4, fade=0.2),
    "ATTACK": rumble,
    "SHIELD": lambda: tone(1760, 0.25, 0.3, fade=0.2),
}


def play(samples):
    """Turn float samples into a stereo 16-bit pygame Sound and play it."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    stereo = np.ascontiguousarray(np.column_stack([pcm, pcm]))
    pygame.sndarray.make_sound(stereo).play()


def emit(event, n=None, pos=None):
    """Fire a game event: play its sound (if audio works) and record it for render.py.
    pos (optional, in pixels) is where the screen effect should appear, such as the star that was hit."""
    _recent.append((event, n, pos, time.monotonic()))
    if not _audio_ok:
        return
    try:
        samples = chime((n or 1) - 1) if event == "STAR" else SOUNDS[event]()  # star 1 plays the lowest note
        play(samples)
    except KeyError:
        print(f"Unknown event: {event}")
    except pygame.error as err:
        print(f"Sound failed for {event}: {err}")


def active_effects():
    """Events from the last EFFECT_SECONDS, as (event, n, pos, age_in_seconds), for render.py to draw."""
    now = time.monotonic()
    _recent[:] = [e for e in _recent if now - e[3] < EFFECT_SECONDS]
    return [(event, n, pos, now - fired) for event, n, pos, fired in _recent]
