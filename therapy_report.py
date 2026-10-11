"""Therapy report: one self-contained HTML page from sessions.csv, for the patient's therapist.

It shows the overall trend of every rehab measure (progress.METRICS), what the patient said after each
battle (pain, tiredness, mood), things worth a look (flags), and the session table. The simulation
(tools/simulate.py) can add drawings of the fingertip's movements.
Everything here describes how the patient played the game at home; it is not a clinical assessment.

Run:  .venv/bin/python -m therapy_report [sessions.csv] [report.html]
In the game: G (Progress) then R writes reports/therapy-report.html and opens it.
"""
import html
import os
import sys
import webbrowser
from datetime import datetime

import numpy as np

import progress
from game import report as rehab

REPORT_PATH = os.path.join("reports", "therapy-report.html")
EDGE_SESSIONS = 3         # "first" and "latest" are the averages of this many sessions at each end
CHART_W, CHART_H, PAD = 340, 130, 26
CHART_KEYS = ("max_reach", "reach_pct", "error_sw", "straightness", "tremor_sw", "time_per_star", "slowdown",
              "lean_per_10", "open_s", "grip_hold_pct")
FEELINGS = (("pain", "#e5484d"), ("tiredness", "#d9a521"), ("mood", "#3e9b6f"))
TREND_WORDS = {"better": "Improving", "worse": "Getting worse", "same": "Steady", None: "Too few sessions"}


def edge_averages(values):
    """The average of the first and of the latest EDGE_SESSIONS values (None if there are too few)."""
    if len(values) < 2:
        return None, None
    n = min(EDGE_SESSIONS, len(values) // 2)
    return float(np.mean(values[:n])), float(np.mean(values[-n:]))


def observations(sessions):
    """Things for the therapist to look at, most important first: (level, text), level "alert",
    "watch" or "good". Pure: tested without writing any HTML."""
    notes = []
    if not sessions:
        return [("watch", "No sessions recorded yet.")]
    recent = sessions[-EDGE_SESSIONS:]
    painful = [s for s in recent if s.pain is not None and s.pain >= rehab.PAIN_ALERT]
    if painful:
        notes.append(("alert", f"High pain reported in {len(painful)} of the last {len(recent)} sessions "
                               f"(latest {painful[-1].date[:10]}). Check in with the patient before more play."))
    for key, worse_text in (("pain", "Pain answers are rising over time."),
                            ("lean_per_10", "Leaning (trunk compensation) is increasing: review posture and difficulty."),
                            ("max_reach", "Active reach is shrinking."),
                            ("tiredness", "Tiredness after sessions is rising: consider shorter sessions.")):
        metric = progress.BY_KEY[key]
        if progress.trend(progress.series(sessions, key), metric.better) == "worse":
            notes.append(("watch", worse_text))
    tired = [s for s in recent if s.slowdown is not None and s.slowdown >= rehab.SLOWDOWN_TIRED]
    if len(tired) >= 2:
        notes.append(("watch", f"Slowed down within {len(tired)} of the last {len(recent)} sessions (fatigue)."))
    for key, good_text in (("max_reach", "Active reach is growing."), ("error_sw", "Accuracy is improving."),
                           ("straightness", "Movement paths are getting straighter (smoother)."),
                           ("tremor_sw", "Holding on a target is getting steadier."),
                           ("open_s", "The hand opens faster after a grip."),
                           ("lean_per_10", "Less leaning: the arm is doing more of the work.")):
        metric = progress.BY_KEY[key]
        if progress.trend(progress.series(sessions, key), metric.better) == "better":
            notes.append(("good", good_text))
    if not any(not s.assisted for s in sessions):
        notes.append(("watch", "No sessions with assisted learning off yet: memory practice not measured."))
    return notes


def fmt(metric, value):
    return "-" if value is None else metric.fmt.format(value)


def line_chart(values, better, metric_fmt, color="#2f6fde"):
    """A small SVG line chart: one dot per session, joined, with a dashed least-squares trend line."""
    if not values:
        return f'<svg viewBox="0 0 {CHART_W} {CHART_H}" class="chart"><text x="{CHART_W / 2}" y="{CHART_H / 2}" class="empty">No data yet</text></svg>'
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    span = hi - lo
    lo, hi = lo - span * 0.1, hi + span * 0.1
    n = len(values)

    def xy(i, v):
        x = PAD + (CHART_W - 2 * PAD) * (i / (n - 1) if n > 1 else 0.5)
        return x, CHART_H - PAD - (CHART_H - 2 * PAD) * (v - lo) / (hi - lo)

    pts = [xy(i, v) for i, v in enumerate(values)]
    parts = [f'<svg viewBox="0 0 {CHART_W} {CHART_H}" class="chart" role="img">',
             f'<line x1="{PAD}" y1="{CHART_H - PAD}" x2="{CHART_W - PAD}" y2="{CHART_H - PAD}" class="axis"/>',
             f'<text x="{PAD - 4}" y="{PAD + 4}" class="tick" text-anchor="end">{html.escape(metric_fmt.format(hi))}</text>',
             f'<text x="{PAD - 4}" y="{CHART_H - PAD}" class="tick" text-anchor="end">{html.escape(metric_fmt.format(lo))}</text>']
    if n >= 3:
        slope, icept = np.polyfit(np.arange(n), np.array(values, dtype=float), 1)
        (x0, y0), (x1, y1) = xy(0, icept), xy(n - 1, icept + slope * (n - 1))
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" class="trend"/>')
    parts.append('<polyline fill="none" stroke="{}" stroke-width="2" points="{}"/>'.format(
        color, " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)))
    for x, y in pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')
    x, y = pts[-1]
    parts.append(f'<text x="{x:.1f}" y="{y - 8:.1f}" class="last" text-anchor="end">{html.escape(metric_fmt.format(values[-1]))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def feelings_chart(sessions):
    """Pain, tiredness and mood (1 to 5) per session on one chart."""
    rows = [s for s in sessions if any(getattr(s, k) is not None for k, _ in FEELINGS)]
    if not rows:
        return '<p class="muted">No check-in answers yet.</p>'
    n = len(rows)
    w, h = 700, 170
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart wide" role="img">']
    for level in range(1, 6):
        y = h - PAD - (h - 2 * PAD) * (level - 1) / 4
        parts.append(f'<line x1="{PAD}" y1="{y:.1f}" x2="{w - PAD}" y2="{y:.1f}" class="grid"/>'
                     f'<text x="{PAD - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{level}</text>')
    for key, color in FEELINGS:
        pts = [(PAD + (w - 2 * PAD) * (i / (n - 1) if n > 1 else 0.5), h - PAD - (h - 2 * PAD) * (getattr(s, key) - 1) / 4)
               for i, s in enumerate(rows) if getattr(s, key) is not None]
        if pts:
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="'
                         + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '"/>')
            parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>' for x, y in pts]
    parts.append("</svg>")
    legend = " ".join(f'<span class="key" style="--c:{c}">{k}</span>' for k, c in FEELINGS)
    return "".join(parts) + f'<p class="legend">{legend} <span class="muted">1 = none / fresh / low, 5 = severe / exhausted / great</span></p>'


def trace_svg(points, trace, title):
    """The stars of one spell and the fingertip's path between them, with speed shown by dot spacing."""
    xs = [p[0] for p in points] + [t[1] for t in trace]
    ys = [p[1] for p in points] + [t[2] for t in trace]
    x0, x1, y0, y1 = min(xs) - 30, max(xs) + 30, min(ys) - 30, max(ys) + 30
    parts = [f'<figure><svg viewBox="{x0:.0f} {y0:.0f} {x1 - x0:.0f} {y1 - y0:.0f}" class="trace" role="img">']
    parts.append('<polyline fill="none" class="path" points="' + " ".join(f"{x:.0f},{y:.0f}" for _, x, y in trace) + '"/>')
    parts += [f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.5" class="sample"/>' for _, x, y in trace[::3]]
    parts.append('<polyline fill="none" class="shape" points="' + " ".join(f"{x:.0f},{y:.0f}" for x, y in points) + '"/>')
    for i, (x, y) in enumerate(points):
        parts.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" class="star"/><text x="{x + 12:.0f}" y="{y - 10:.0f}" class="num">{i + 1}</text>')
    parts.append(f"</svg><figcaption>{html.escape(title)}</figcaption></figure>")
    return "".join(parts)


def speed_svg(traces):
    """Fingertip speed over time for each labelled trace (smoother movement = fewer, rounder peaks)."""
    w, h = 700, 160
    colors = ("#9aa3b5", "#2f6fde")
    series = []
    for (label, trace), color in zip(traces, colors):
        t = np.array([p[0] for p in trace])
        xy = np.array([(p[1], p[2]) for p in trace])
        if len(t) < 3:
            continue
        v = np.hypot(*np.diff(xy, axis=0).T) / np.maximum(np.diff(t), 1e-3)
        series.append((label, t[1:] - t[0], np.convolve(v, np.ones(3) / 3, mode="same"), color))
    if not series:
        return ""
    t_max = max(s[1][-1] for s in series)
    v_max = max(float(np.percentile(s[2], 99)) for s in series) or 1.0
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart wide" role="img">',
             f'<line x1="{PAD}" y1="{h - PAD}" x2="{w - PAD}" y2="{h - PAD}" class="axis"/>',
             f'<text x="{w - PAD}" y="{h - 6}" class="tick" text-anchor="end">seconds</text>',
             f'<text x="{PAD}" y="{PAD - 8}" class="tick">fingertip speed</text>']
    for label, t, v, color in series:
        pts = " ".join(f"{PAD + (w - 2 * PAD) * ti / t_max:.1f},{h - PAD - (h - 2 * PAD) * min(vi, v_max) / v_max:.1f}"
                       for ti, vi in zip(t, v))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.6" points="{pts}"/>')
    parts.append("</svg>")
    legend = " ".join(f'<span class="key" style="--c:{c}">{html.escape(label)}</span>' for label, _, _, c in series)
    return "".join(parts) + f'<p class="legend">{legend}</p>'


CSS = """
:root{--bg:#f7f8fb;--card:#fff;--ink:#1b2130;--muted:#5d6678;--line:#dfe3ea;--accent:#2f6fde;
--good:#2e8b57;--watch:#b7791f;--alert:#c53030}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0d1220;--card:#151c2e;--ink:#e7ebf3;
--muted:#9aa3b5;--line:#2a3349;--accent:#7aa7ff;--good:#5cc28d;--watch:#e0b25a;--alert:#ff7b7b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1060px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:18px;margin:34px 0 10px}.muted{color:var(--muted)}.sub{color:var(--muted);margin:0 0 18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card b{display:block;font-size:22px}.card span{color:var(--muted);font-size:13px}
.notes{list-style:none;padding:0;margin:0}.notes li{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--muted);
border-radius:8px;padding:9px 12px;margin:0 0 8px}.notes .alert{border-left-color:var(--alert)}.notes .watch{border-left-color:var(--watch)}
.notes .good{border-left-color:var(--good)}table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}th{color:var(--muted);font-weight:600}
td.better{color:var(--good);font-weight:600}td.worse{color:var(--alert);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.panel h3{margin:0;font-size:15px}
.panel p{margin:0 0 4px;font-size:12px;color:var(--muted)}svg.chart{width:100%;height:auto;display:block}
svg .axis{stroke:var(--line)}svg .grid{stroke:var(--line);stroke-dasharray:2 3}svg .trend{stroke:var(--muted);stroke-dasharray:5 4}
svg text{fill:var(--muted);font-size:10px}svg .last{fill:var(--ink);font-weight:600;font-size:11px}svg .empty{text-anchor:middle;font-size:12px}
.legend{font-size:13px;margin:6px 0 0}.key{margin-right:12px}.key::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;
background:var(--c);margin-right:5px}.traces{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}figcaption{color:var(--muted);font-size:13px}
svg.trace{width:100%;height:280px;display:block}svg.trace .path{stroke:var(--accent);stroke-width:2.5}svg.trace .sample{fill:var(--accent);opacity:.6}
svg.trace .shape{stroke:var(--muted);stroke-width:1.5;stroke-dasharray:6 5}svg.trace .star{fill:#f2c94c;stroke:#8a6d1a}svg.trace .num{font-size:16px}
.scroll{overflow-x:auto}footer{margin-top:40px;color:var(--muted);font-size:13px}
"""


def build_report(sessions, title="Home rehab report", subtitle="", traces=None, extra_html=""):
    """The whole report as an HTML string. traces: [(label, star points, fingertip trace)] to draw movements."""
    sessions = list(sessions)
    e = html.escape
    first, last = (sessions[0].date[:10], sessions[-1].date[:10]) if sessions else ("-", "-")
    minutes = sum(s.minutes or 0 for s in sessions)
    reaches = sum(s.stars for s in sessions)
    grips = sum(s.grip_reps for s in sessions)
    pains = progress.series(sessions, "pain")
    days = len({s.date[:10] for s in sessions})
    cards = [(days, "days played"), (len(sessions), "battles and practice rounds"), (f"{minutes:.0f}", "minutes of exercise"),
             (reaches, "reaches (stars)"),
             (grips, "grip reps (blocks)"), ("-" if not pains else f"{pains[-1]:.0f} / 5", "latest pain")]
    out = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
           f"<h1>{e(title)}</h1><p class=\"sub\">{e(subtitle)}{' · ' if subtitle else ''}{first} to {last} · "
           f"generated {datetime.now():%Y-%m-%d %H:%M}</p>",
           '<div class="cards">' + "".join(f'<div class="card"><b>{e(str(v))}</b><span>{e(k)}</span></div>' for v, k in cards) + "</div>",
           "<h2>Worth a look</h2><ul class=\"notes\">"
           + "".join(f'<li class="{lvl}">{e(text)}</li>' for lvl, text in observations(sessions)) + "</ul>",
           "<h2>Overall trend</h2><div class=\"scroll\"><table><tr><th>Measure</th><th>What it means</th><th>First sessions</th>"
           "<th>Latest sessions</th><th>Trend</th></tr>"]
    for key in CHART_KEYS:
        m = progress.BY_KEY[key]
        values = progress.series(sessions, key)
        start, end = edge_averages(values)
        verdict = progress.trend(values, m.better)
        out.append(f"<tr><td>{e(m.label)}</td><td class=\"muted\">{e(m.unit)}, {e(m.better)} is better</td>"
                   f"<td>{e(fmt(m, start))}</td><td>{e(fmt(m, end))}</td>"
                   f"<td class=\"{verdict or ''}\">{TREND_WORDS[verdict]}</td></tr>")
    out.append("</table></div><h2>Each measure, session by session</h2><div class=\"grid\">")
    for key in CHART_KEYS:
        m = progress.BY_KEY[key]
        out.append(f'<div class="panel"><h3>{e(m.label)}</h3><p>{e(m.unit)} · {e(m.better)} is better · dashed line: trend</p>'
                   f"{line_chart(progress.series(sessions, key), m.better, m.fmt)}</div>")
    out.append("</div><h2>How the patient felt after each battle</h2><div class=\"panel\">" + feelings_chart(sessions) + "</div>")
    if traces:
        out.append("<h2>Movement: how the fingertip travelled</h2><p class=\"muted\">Dashed: the constellation's shape. "
                   "Blue: the fingertip's path, dots every 0.1 s (bunched dots = slow, spread = fast). "
                   "A direct, smooth path between stars is the goal.</p><div class=\"traces\">")
        out += [trace_svg(points, trace, label) for label, points, trace in traces]
        out.append("</div><div class=\"panel\" style=\"margin-top:12px\">" + speed_svg([(l, t) for l, _, t in traces]) + "</div>")
    out.append(extra_html)
    out.append("<h2>Sessions</h2><div class=\"scroll\"><table><tr><th>Date</th><th>Mode</th><th>Level</th><th>Assisted</th>"
               "<th>Arm</th><th>Reaches</th><th>Reach range</th><th>Error</th><th>Straightness</th><th>Leans</th>"
               "<th>Grips</th><th>Pain</th><th>Tired</th><th>Mood</th><th>Result</th></tr>")
    for s in reversed(sessions[-40:]):
        cell = lambda v, f="{:.0f}": "-" if v is None else f.format(v)
        out.append(f"<tr><td>{e(s.date[:16])}</td><td>{e(s.mode)}</td><td>{e(s.difficulty or '-')}</td>"
                   f"<td>{'on' if s.assisted else 'off'}</td><td>{e(s.arm or '-')}</td><td>{s.stars}</td>"
                   f"<td>{cell(s.reach_pct, '{:.0f}%')}</td><td>{cell(s.error_sw, '{:.2f}')}</td>"
                   f"<td>{cell(s.straightness, '{:.2f}')}</td><td>{s.lean_warnings}</td>"
                   f"<td>{s.grip_holds}/{s.grip_reps}</td><td>{cell(s.pain)}</td><td>{cell(s.tiredness)}</td>"
                   f"<td>{cell(s.mood)}</td><td>{e(s.result)}</td></tr>")
    out.append("</table></div><footer>From Asterism, a home rehab game. These numbers describe how the game was played "
               "at home with a webcam; they are not a clinical assessment. Thresholds are coaching guides for the game. "
               "The treating therapist decides what they mean.</footer></main></body></html>")
    return "".join(out)


def write_report(sessions, path=REPORT_PATH, **kwargs):
    """Write the report and return its path."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_report(sessions, **kwargs))
    return path


def generate_and_open(log_path=progress.LOG_PATH, path=REPORT_PATH):
    """From the game: write the report for sessions.csv and open it in the browser. Returns the path or None."""
    try:
        written = write_report(progress.load_sessions(log_path), path)
    except OSError as error:
        print(f"Therapy report: could not write {path}: {error}")
        return None
    webbrowser.open("file://" + os.path.abspath(written))
    print(f"Therapy report: {written}")
    return written


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else progress.LOG_PATH
    target = sys.argv[2] if len(sys.argv) > 2 else REPORT_PATH
    print(write_report(progress.load_sessions(source), target))
