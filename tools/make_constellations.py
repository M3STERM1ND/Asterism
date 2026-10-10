"""Builds constellations/*.json from real star positions, so every file can be checked against a star chart.

Each star is (name, right ascension in degrees, declination in degrees), J2000, listed in the order the
player draws them. Positions are projected as you see the sky (east on the left, north up), keep their
true proportions, and are scaled so the longer side spans 0 to 1. Run from the project folder:
    .venv\Scripts\python tools\make_constellations.py
"""
import json
import math

# For Pisces the right ascension wraps past 0/360, so stars just west of 0 are written as negative degrees.
CONSTELLATIONS = {
    "aries": ("Aries", [("Mesarthim", 28.38, 19.29), ("Sheratan", 28.66, 20.81), ("Hamal", 31.79, 23.46),
                        ("Bharani (41 Ari)", 42.50, 27.26)]),
    "taurus": ("Taurus", [("Elnath", 81.57, 28.61), ("Ain", 67.15, 19.18), ("Prima Hyadum", 64.95, 15.63),
                          ("Aldebaran", 68.98, 16.51), ("Tianguan", 84.41, 21.14)]),
    "gemini": ("Gemini", [("Tejat", 95.74, 22.51), ("Mebsuta", 100.98, 25.13), ("Castor", 113.65, 31.89),
                          ("Pollux", 116.33, 28.03), ("Wasat", 110.03, 21.98), ("Alhena", 99.43, 16.40)]),
    "cancer": ("Cancer", [("Iota Cancri", 131.67, 28.76), ("Asellus Borealis", 130.82, 21.47),
                          ("Asellus Australis", 131.17, 18.15), ("Altarf", 124.13, 9.19)]),
    "leo": ("Leo", [("Ras Elased Australis", 146.46, 23.77), ("Rasalas", 148.19, 26.01), ("Adhafera", 154.17, 23.42),
                    ("Algieba", 154.99, 19.84), ("Zosma", 168.53, 20.52), ("Denebola", 177.26, 14.57),
                    ("Chertan", 168.56, 15.43), ("Regulus", 152.09, 11.97)]),
    "virgo": ("Virgo", [("Vindemiatrix", 195.54, 10.96), ("Minelauva", 193.90, 3.40), ("Porrima", 190.42, -1.45),
                        ("Spica", 201.30, -11.16)]),
    "libra": ("Libra", [("Brachium", 226.02, -25.28), ("Zubenelgenubi", 222.72, -16.04),
                        ("Zubeneschamali", 229.25, -9.38), ("Zubenelhakrabi", 233.88, -14.79),
                        ("Upsilon Librae", 234.26, -28.13)]),
    "scorpius": ("Scorpius", [("Acrab", 241.36, -19.81), ("Dschubba", 240.08, -22.62), ("Antares", 247.35, -26.43),
                              ("Paikauhale", 248.97, -28.22), ("Larawag", 252.54, -34.29), ("Xamidimura", 252.97, -38.05),
                              ("Eta Scorpii", 258.04, -43.24), ("Sargas", 264.33, -43.00), ("Girtab", 265.62, -39.03),
                              ("Shaula", 263.40, -37.10)]),
    "sagittarius": ("Sagittarius", [("Alnasl", 271.45, -30.42), ("Kaus Australis", 276.04, -34.38),
                                    ("Ascella", 285.65, -29.88), ("Tau Sagittarii", 286.74, -27.67),
                                    ("Nunki", 283.82, -26.30), ("Phi Sagittarii", 281.41, -26.99),
                                    ("Kaus Borealis", 276.99, -25.42), ("Kaus Media", 275.25, -29.83)]),
    "capricornus": ("Capricornus", [("Algedi", 304.51, -12.54), ("Dabih", 305.25, -14.78),
                                    ("Omega Capricorni", 312.96, -26.92), ("Zeta Capricorni", 321.67, -22.41),
                                    ("Deneb Algedi", 326.76, -16.13), ("Theta Capricorni", 316.49, -17.23)]),
    "aquarius": ("Aquarius", [("Albali", 311.92, -9.50), ("Sadalsuud", 322.89, -5.57), ("Sadalmelik", 331.45, -0.32),
                              ("Ancha", 334.21, -7.78), ("Lambda Aquarii", 343.15, -7.58), ("Skat", 343.66, -15.82)]),
    "pisces": ("Pisces", [("Fumalsamakah", 345.97 - 360, 3.82), ("Gamma Piscium", 349.29 - 360, 3.28),
                          ("Omega Piscium", 359.83 - 360, 6.86), ("Delta Piscium", 12.17, 7.59),
                          ("Epsilon Piscium", 15.74, 7.89), ("Alrescha", 30.51, 2.76), ("Alpherg", 22.87, 15.35)]),
    "orion": ("Orion", [("Meissa", 83.78, 9.93), ("Betelgeuse", 88.79, 7.41), ("Bellatrix", 81.28, 6.35),
                        ("Mintaka", 83.00, -0.30), ("Alnitak", 85.19, -1.94), ("Saiph", 86.94, -9.67),
                        ("Rigel", 78.63, -8.20)]),
}


def project(stars):
    """Flatten (RA, Dec) onto the page as seen from Earth and scale the longer side to 0..1."""
    mid_dec = math.radians(sum(dec for _, _, dec in stars) / len(stars))
    xs = [-ra * math.cos(mid_dec) for _, ra, _ in stars]  # east (bigger RA) on the left
    ys = [-dec for _, _, dec in stars]                     # north up (screen y grows downward)
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    ox = min(xs) - (span - (max(xs) - min(xs))) / 2       # center the shorter side
    oy = min(ys) - (span - (max(ys) - min(ys))) / 2
    return [[round((x - ox) / span, 3), round((y - oy) / span, 3)] for x, y in zip(xs, ys)]


def main():
    for key, (name, stars) in CONSTELLATIONS.items():
        data = {"name": name, "order": "sequential", "stars": project(stars), "star_names": [s[0] for s in stars]}
        with open(f"constellations/{key}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"{name:12s} {len(stars)} stars")


if __name__ == "__main__":
    main()
