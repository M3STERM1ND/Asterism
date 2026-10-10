"""Placement: decides where a constellation's stars go on screen (all positions in pixels).

With calibration, the constellation is centered near the reaching shoulder and scaled so its
outer stars sit at the edge of the player's measured reach. Without calibration, it is fitted
into a default comfortable seated box. Either way it stays inside what the camera can see and
clear of on-screen text, and consecutive stars are kept far enough apart to tell apart.
"""
import numpy as np

EDGE = 0.95  # outer stars sit at 95% of the calibrated reach: at the edge of the range, not beyond it
# Without calibration: a comfortable seated reach around the middle of the shoulders, in shoulder widths.
REACH_SIDE, REACH_UP, REACH_DOWN = 2.0, 1.6, 1.0
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 130, 110, 60  # keep targets clear of the on-screen text


CAMERA_EDGE = 0.08  # keep stars this far inside the camera's view (fraction of it), so the whole hand fits


def safe_bounds(camera_rect, size, margin):
    """The screen area (left, top, right, bottom) where a target is reachable and visible:
    inside what the camera sees (by at least margin, or CAMERA_EDGE of its view) and clear of the text."""
    w, h = size
    margin = max(margin, CAMERA_EDGE * (camera_rect[2] - camera_rect[0]) * w)
    return (max(camera_rect[0] * w + margin, SAFE_SIDE), max(camera_rect[1] * h + margin, SAFE_TOP),
            min(camera_rect[2] * w - margin, w - SAFE_SIDE), min(camera_rect[3] * h - margin, h - SAFE_BOTTOM))


def comfortable_box(figure, bounds, size):
    """Default reach area before calibration: a box around the shoulders, clipped to the bounds."""
    w, h = size
    (lx, ly), (rx, ry) = figure.stars["Betelgeuse"], figure.stars["Bellatrix"]
    shoulder = np.hypot((rx - lx) * w, (ry - ly) * h)
    cx, cy = (lx + rx) / 2 * w, (ly + ry) / 2 * h
    return (max(cx - REACH_SIDE * shoulder, bounds[0]), max(cy - REACH_UP * shoulder, bounds[1]),
            min(cx + REACH_SIDE * shoulder, bounds[2]), min(cy + REACH_DOWN * shoulder, bounds[3]))


def fit_stars(stars, box):
    """Scale and center the constellation's own outline inside the box, keeping its true shape."""
    pts = np.array(stars, dtype=float)
    lo, span = pts.min(axis=0), np.maximum(pts.max(axis=0) - pts.min(axis=0), 1e-6)
    box_w, box_h = box[2] - box[0], box[3] - box[1]
    k = min(box_w / span[0], box_h / span[1])
    offset = np.array([box[0] + (box_w - span[0] * k) / 2, box[1] + (box_h - span[1] * k) / 2])
    return [tuple(p) for p in (pts - lo) * k + offset]


def largest_scale(rel, center, shoulder, reach, bounds):
    """The biggest scale for a constellation centered here: every star inside the bounds and
    within the reach distance of the shoulder."""
    far = np.max(np.hypot(rel[:, 0], rel[:, 1]))
    limits = [(reach - np.hypot(*(center - shoulder))) / far]
    for axis, (lo, hi) in enumerate(((bounds[0], bounds[2]), (bounds[1], bounds[3]))):
        if rel[:, axis].max() > 0:
            limits.append((hi - center[axis]) / rel[:, axis].max())
        if rel[:, axis].min() < 0:
            limits.append((lo - center[axis]) / rel[:, axis].min())
    return min(limits)


def place_calibrated(stars, cal, bounds, tries=15):
    """Center the constellation near the reaching shoulder and scale it so its outer stars reach the
    edge of the calibrated range. If the screen or camera cuts that range off, try nearby centers
    and keep the one that allows the biggest constellation."""
    pts = np.array(stars, dtype=float)
    rel = pts - (pts.min(axis=0) + pts.max(axis=0)) / 2
    shoulder = np.array(cal.shoulder)
    reach = cal.reach * cal.width * EDGE
    best_scale, best_center = 0.0, shoulder
    for dx in np.linspace(-reach, reach, tries):
        for dy in np.linspace(-reach, reach, tries):
            center = shoulder + (dx, dy)
            if not (bounds[0] <= center[0] <= bounds[2] and bounds[1] <= center[1] <= bounds[3]):
                continue
            scale = largest_scale(rel, center, shoulder, reach, bounds)
            if scale > best_scale:
                best_scale, best_center = scale, center
    return [tuple(p) for p in best_center + rel * best_scale]


def spread_out(points, bounds, min_gap, rounds=60):
    """Push apart consecutive stars (the ones touched one after another) that are closer than
    min_gap, along the line between them, keeping them inside the bounds. Spread-out shapes don't
    change; tight runs like Aries's three close stars just stretch a little."""
    pts = np.array(points, dtype=float)
    for _ in range(rounds):
        moved = False
        for i in range(len(pts) - 1):
            gap = pts[i + 1] - pts[i]
            dist = np.hypot(*gap)
            if dist >= min_gap:
                continue
            direction = gap / dist if dist > 1e-6 else np.array([1.0, 0.0])
            push = direction * (min_gap - dist) / 2
            pts[i] -= push
            pts[i + 1] += push
            moved = True
        pts[:, 0] = np.clip(pts[:, 0], bounds[0], bounds[2])
        pts[:, 1] = np.clip(pts[:, 1], bounds[1], bounds[3])
        if not moved:
            break
    return [tuple(p) for p in pts]


def closest_gap(points):
    """Distance in pixels between the two closest stars."""
    pts = np.array(points)
    return min(np.hypot(*(pts[i] - pts[j])) for i in range(len(pts)) for j in range(i + 1, len(pts)))
