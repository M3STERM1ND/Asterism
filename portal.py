"""Portal: the Asterism website for coaches and patients, served on this computer only.

Run:  .venv/bin/python -m portal        then open http://localhost:8765
      (--data demo_data to try it with the demo accounts from tools/demo_accounts.py)

  Everyone   - sign up as a patient or a coach, log in, log out
  Coaches    - set their status (open: taking new patients, closed: not), edit their profile, see their
               linked patients, each patient's runs, recorded session videos and the therapy report
               (trends across sessions), and write feedback the patient sees here and in the game
  Patients   - browse the coach catalog and link to a coach whose status is open (one coach at a time),
               see their own runs, reports and videos, and read their coach's feedback
A coach only ever sees patients linked to them (accounts.Store.can_view guards every page and file).
Only the standard library: no installs. Listens on 127.0.0.1, so nothing outside this computer can reach it.
"""
import csv
import html
import os
import sys
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import progress
import therapy_report
from accounts import AccountError, Store

HOST, PORT = "127.0.0.1", 8765
COOKIE = "asterism_session"
MAX_BODY = 20_000
CHUNK = 1 << 20
e = html.escape

CSS = therapy_report.CSS + """
nav{display:flex;gap:14px;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--line);background:var(--card)}
nav a{color:var(--accent);text-decoration:none;margin-left:14px}nav b{font-size:18px}
form.inline{display:inline}input,textarea,select{font:inherit;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--ink);width:100%;margin:4px 0 10px}textarea{min-height:90px}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--accent)}button:disabled{opacity:.45;cursor:not-allowed}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.open{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.closed{background:color-mix(in srgb,var(--muted) 18%,transparent);color:var(--muted)}
.msg{padding:10px 12px;border-radius:8px;margin:12px 0;background:var(--card);border:1px solid var(--line)}
.msg.bad{border-left:4px solid var(--alert)}.msg.good{border-left:4px solid var(--good)}
video{width:100%;border-radius:8px;background:#000}iframe.report{width:100%;height:1100px;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 8px}
.note small{color:var(--muted)}.runs a{margin-right:10px}
"""


def page(title, body, user=None, message="", ok=True):
    links = ""
    if user is not None:
        home = "/coach" if user.role == "coach" else "/me"
        links = (f'<span class="muted">{e(user.display_name)} · {e(user.role)}</span>'
                 f'<span><a href="{home}">Home</a><form class="inline" method="post" action="/logout">'
                 f'<button class="ghost" style="margin-left:14px">Log out</button></form></span>')
    note = f'<div class="msg {"good" if ok else "bad"}">{e(message)}</div>' if message else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{CSS}</style></head>'
            f'<body><nav><b>Asterism</b>{links}</nav><main>{note}{body}</main></body></html>')


def login_page():
    return """
<h1>Asterism portal</h1><p class="sub">Patients play the game at home; coaches watch their sessions, follow their
progress and leave feedback.</p><div class="two">
<form class="panel" method="post" action="/login"><h2>Log in</h2>
<label>Username<input name="username" autocomplete="username" required></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required></label>
<button>Log in</button></form>
<form class="panel" method="post" action="/register"><h2>Create an account</h2>
<label>I am a<select name="role"><option value="patient">Patient</option><option value="coach">Coach</option></select></label>
<label>Username (3-20 letters, numbers or _)<input name="username" required></label>
<label>Your name<input name="display_name"></label>
<label>Password (6 or more characters)<input name="password" type="password" autocomplete="new-password" required></label>
<p class="muted">Coaches only:</p>
<label>Specialty<input name="specialty" placeholder="e.g. Stroke rehabilitation, upper limb"></label>
<label>About you<textarea name="bio"></textarea></label>
<button>Create account</button></form></div>"""


def run_sessions(store, run):
    return progress.load_sessions(store.run_paths(run)[0])


def videos(store, run):
    """(file name, session date, title, result) for each recorded session of a run, newest first."""
    log, _, folder = store.run_paths(run)
    by_file = {}
    if os.path.exists(log):
        with open(log, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("video"):
                    by_file[row["video"]] = row
    files = sorted((n for n in os.listdir(folder) if n.endswith(".mp4")), reverse=True) if os.path.isdir(folder) else []
    out = []
    for name in files:
        row = by_file.get(name, {})
        stamp, _, slug = name[:-4].partition("-")[2].partition("-")  # 20261006-101400-scorpius.mp4
        fallback_date = f"{name[:4]}-{name[4:6]}-{name[6:8]} {name[9:11]}:{name[11:13]}" if len(name) > 15 else name
        out.append((name, row.get("date", fallback_date), row.get("constellation", slug.replace("-", " ").title()),
                    row.get("result", "")))
    return out


class Portal(BaseHTTPRequestHandler):
    store = None  # set by serve()

    # --- plumbing
    def log_message(self, fmt, *args):
        pass  # quiet: the console isn't for request logs

    def current_user(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return self.store.user_for_token(jar[COOKIE].value if COOKIE in jar else None)

    def form(self):
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        data = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        return {k: v[0] for k, v in data.items()}

    def query(self):
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def send_html(self, text, status=200, cookie=None):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, where, cookie=None, **params):
        self.send_response(303)
        self.send_header("Location", where + (("?" + urlencode(params)) if params else ""))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def deny(self):
        self.send_html(page("Not allowed", "<h1>Not allowed</h1><p>This page belongs to someone else.</p>",
                            self.current_user()), 403)

    @staticmethod
    def session_cookie(token, max_age=60 * 60 * 24 * 14):
        return f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"

    # --- routes
    def do_GET(self):
        path, q, user = urlparse(self.path).path, self.query(), self.current_user()
        msg, ok = q.get("msg", ""), q.get("ok", "1") == "1"
        if path == "/":
            if user is None:
                return self.send_html(page("Asterism portal", login_page(), None, msg, ok))
            extra = {"msg": msg, "ok": "1" if ok else "0"} if msg else {}
            return self.redirect("/coach" if user.role == "coach" else "/me", **extra)
        if user is None:
            return self.redirect("/", msg="Please log in", ok="0")
        if path == "/coach" and user.role == "coach":
            return self.send_html(page("Coach", self.coach_home(user), user, msg, ok))
        if path == "/me" and user.role == "patient":
            return self.send_html(page("Home", self.patient_home(user), user, msg, ok))
        if path == "/patient":
            patient_id = int(q.get("id", "0") or 0)
            if not self.store.can_view(user, patient_id):
                return self.deny()
            return self.send_html(page("Patient", self.patient_page(user, patient_id, q.get("run", "all")), user, msg, ok))
        if path == "/report":
            return self.report(user, q)
        if path == "/video":
            return self.video(user, q)
        self.send_html(page("Not found", "<h1>Not found</h1>", user), 404)

    def do_POST(self):
        path, f, user = urlparse(self.path).path, self.form(), self.current_user()
        try:
            if path == "/login":
                found = self.store.login(f.get("username", ""), f.get("password", ""))
                if found is None:
                    raise AccountError("Wrong username or password")
                return self.redirect("/", cookie=self.session_cookie(self.store.new_token(found)))
            if path == "/register":
                made = self.store.register(f.get("username", ""), f.get("password", ""), f.get("role", ""),
                                           f.get("display_name", ""), f.get("bio", ""), f.get("specialty", ""))
                return self.redirect("/", cookie=self.session_cookie(self.store.new_token(made)))
            if user is None:
                return self.redirect("/", msg="Please log in", ok="0")
            if path == "/logout":
                jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
                if COOKIE in jar:
                    self.store.drop_token(jar[COOKIE].value)
                return self.redirect("/", cookie=self.session_cookie("", 0), msg="Logged out")
            if path == "/coach/status":
                self.store.set_status(user, f.get("status", ""))
                return self.redirect("/coach", msg=f"Status: {f.get('status')}")
            if path == "/coach/profile":
                self.store.update_profile(user, f.get("bio", ""), f.get("specialty", ""))
                return self.redirect("/coach", msg="Profile saved")
            if path == "/link":
                coach = self.store.link(user, int(f.get("coach", "0") or 0))
                return self.redirect("/me", msg=f"Linked to {coach.display_name}")
            if path == "/unlink":
                self.store.unlink(user)
                return self.redirect("/me", msg="You no longer have a coach")
            if path == "/feedback":
                patient_id = int(f.get("patient", "0") or 0)
                run_id = int(f["run"]) if f.get("run", "").isdigit() else None
                self.store.add_feedback(user, patient_id, f.get("text", ""), run_id)
                return self.redirect("/patient", id=patient_id, run=f.get("run", "all"), msg="Feedback sent")
        except AccountError as error:
            home = "/" if user is None else ("/coach" if user.role == "coach" else "/me")
            back = home if path in ("/login", "/register", "/link", "/unlink") else self.headers.get("Referer", home)
            return self.redirect(urlparse(back).path or "/", msg=str(error), ok="0",
                                 **({"id": f["patient"]} if path == "/feedback" and "patient" in f else {}))
        self.send_html(page("Not found", "<h1>Not found</h1>", user), 404)

    # --- pages
    def coach_home(self, coach):
        status = coach.status
        other = "closed" if status == "open" else "open"
        rows = []
        for p in self.store.patients_of(coach):
            runs = self.store.runs(p.id)
            sessions = [s for r in runs for s in run_sessions(self.store, r)]
            last = max((s.date for s in sessions), default="-")
            unread = ""
            rows.append(f'<tr><td><a href="/patient?id={p.id}">{e(p.display_name)}</a> <span class="muted">@{e(p.username)}</span>'
                        f'</td><td>{len(runs)}</td><td>{len(sessions)}</td><td>{e(last[:16])}</td><td>{unread}</td></tr>')
        table = ("<table><tr><th>Patient</th><th>Runs</th><th>Sessions</th><th>Last session</th><th></th></tr>"
                 + "".join(rows) + "</table>") if rows else '<p class="muted">No patients linked yet. Patients find you in the coach catalog while your status is open.</p>'
        return (f"<h1>Coach dashboard</h1><p class=\"sub\">{e(coach.specialty or 'No specialty set')}</p>"
                f'<div class="two"><div class="panel"><h3>Status: <span class="pill {status}">{status}</span></h3>'
                f'<p>{"Open: new patients can link to you." if status == "open" else "Closed: no new patients can link to you. Current patients stay linked."}</p>'
                f'<form method="post" action="/coach/status"><input type="hidden" name="status" value="{other}">'
                f'<button>Set to {other}</button></form></div>'
                f'<form class="panel" method="post" action="/coach/profile"><h3>Profile in the catalog</h3>'
                f'<label>Specialty<input name="specialty" value="{e(coach.specialty)}"></label>'
                f'<label>About you<textarea name="bio">{e(coach.bio)}</textarea></label><button>Save</button></form></div>'
                f"<h2>Your patients</h2>{table}")

    def patient_home(self, patient):
        coach = self.store.coach_of(patient)
        mine = (f'<p>Your coach: <b>{e(coach.display_name)}</b> <span class="muted">{e(coach.specialty)}</span></p>'
                '<form method="post" action="/unlink"><button class="ghost">Leave this coach</button></form>'
                if coach else '<p class="muted">You have no coach yet. Pick one below: only coaches marked open take new patients.</p>')
        cards = []
        for c in self.store.coaches():
            is_mine = coach is not None and coach.id == c.id
            if is_mine:
                action = '<button disabled>Your coach</button>'
            elif c.status == "open":
                action = (f'<form method="post" action="/link"><input type="hidden" name="coach" value="{c.id}">'
                          f'<button>Link to {e(c.display_name)}</button></form>')
            else:
                action = '<button disabled>Not taking patients</button>'
            cards.append(f'<div class="panel"><h3>{e(c.display_name)} <span class="pill {c.status}">{c.status}</span></h3>'
                         f'<p>{e(c.specialty)}</p><p class="muted" style="font-size:14px">{e(c.bio)}</p>{action}</div>')
        notes = self.notes(patient.id)
        self.store.mark_read(patient.id)
        catalog = "".join(cards) or '<p class="muted">No coaches have signed up yet.</p>'
        return (f"<h1>Hello, {e(patient.display_name)}</h1>"
                f'<p><a href="/patient?id={patient.id}">See your runs, reports and videos →</a></p>'
                f"<h2>Your coach</h2>{mine}<h2>Feedback</h2>{notes}"
                f'<h2>Coach catalog</h2><div class="grid">{catalog}</div>')

    def notes(self, patient_id):
        items = self.store.feedback_for(patient_id)
        if not items:
            return '<p class="muted">No feedback yet.</p>'
        out = []
        for n in items:
            run = self.store.run(n.run_id) if n.run_id else None
            about = f" · about run “{e(run.name)}”" if run else ""
            new = ' <span class="pill open">new</span>' if n.read_at is None else ""
            out.append(f'<div class="note"><small>{e(n.coach_name)} · {e(n.created_at[:16])}{about}</small>{new}'
                       f'<p style="margin:6px 0 0;white-space:pre-wrap">{e(n.text)}</p></div>')
        return "".join(out)

    def patient_page(self, viewer, patient_id, run_choice):
        patient = self.store.user(patient_id)
        runs = self.store.runs(patient_id)
        chosen = next((r for r in runs if str(r.id) == run_choice), None)
        tabs = [f'<a href="/patient?id={patient_id}&run=all">{"<b>All runs</b>" if chosen is None else "All runs"}</a>']
        tabs += [f'<a href="/patient?id={patient_id}&run={r.id}">{"<b>" + e(r.name) + "</b>" if chosen and r.id == chosen.id else e(r.name)}</a>'
                 for r in runs]
        shown = [chosen] if chosen else runs
        clips = []
        for r in shown:
            for name, date, title, result in videos(self.store, r)[:12]:
                src = f"/video?run={r.id}&file={name}"
                clips.append(f'<figure><video controls preload="metadata" src="{e(src)}"></video>'
                             f'<figcaption>{e(date[:16])} · {e(title)} · {e(result)}{" · " + e(r.name) if not chosen else ""}</figcaption></figure>')
        clips_html = f'<div class="traces">{"".join(clips)}</div>' if clips else '<p class="muted">No recorded sessions yet.</p>'
        form = ""
        if viewer.role == "coach":
            options = '<option value="all">The whole programme</option>' + "".join(
                f'<option value="{r.id}"{" selected" if chosen and r.id == chosen.id else ""}>Run: {e(r.name)}</option>' for r in runs)
            form = (f'<form class="panel" method="post" action="/feedback"><h3>Write feedback for {e(patient.display_name)}</h3>'
                    f'<input type="hidden" name="patient" value="{patient_id}"><label>About<select name="run">{options}</select></label>'
                    f'<label>Message (shown in the game and here)<textarea name="text" required></textarea></label>'
                    f'<button>Send feedback</button></form>')
        report_src = f"/report?patient={patient_id}&run={chosen.id if chosen else 'all'}"
        return (f"<h1>{e(patient.display_name)}</h1><p class=\"runs\">{''.join(tabs)}</p>"
                f'<div class="two">{form}<div class="panel"><h3>Feedback so far</h3>{self.notes(patient_id)}</div></div>'
                f"<h2>Recorded sessions</h2>{clips_html}"
                f'<h2>Report and trends</h2><p><a href="{e(report_src)}" target="_blank">Open the report on its own page</a></p>'
                f'<iframe class="report" src="{e(report_src)}" title="Therapy report"></iframe>')

    def report(self, user, q):
        patient_id = int(q.get("patient", "0") or 0)
        if not self.store.can_view(user, patient_id):
            return self.deny()
        patient = self.store.user(patient_id)
        runs = self.store.runs(patient_id)
        chosen = next((r for r in runs if str(r.id) == q.get("run")), None)
        sessions = sorted((s for r in ([chosen] if chosen else runs) for s in run_sessions(self.store, r)), key=lambda s: s.date)
        scope = f"run “{chosen.name}”" if chosen else "all runs"
        self.send_html(therapy_report.build_report(sessions, title=f"Home rehab report: {patient.display_name}", subtitle=scope))

    def video(self, user, q):
        run = self.store.run(int(q.get("run", "0") or 0)) if q.get("run", "").isdigit() else None
        name = os.path.basename(q.get("file", ""))
        if run is None or not self.store.can_view(user, run.patient_id) or not name.endswith(".mp4"):
            return self.deny()
        path = os.path.join(self.store.run_paths(run)[2], name)
        if not os.path.isfile(path):
            return self.send_html(page("Not found", "<h1>Video not found</h1>", user), 404)
        size = os.path.getsize(path)
        start, end = 0, size - 1
        ranged = self.headers.get("Range", "")
        if ranged.startswith("bytes="):   # browsers fetch videos in pieces (Safari insists on it)
            first, _, last = ranged[6:].split(",")[0].partition("-")
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            elif last:
                start = max(0, size - int(last))
        self.send_response(206 if ranged else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if ranged:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def serve(store, host=HOST, port=PORT):
    Portal.store = store
    server = ThreadingHTTPServer((host, port), Portal)
    print(f"Asterism portal: http://localhost:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    args = sys.argv[1:]
    data = args[args.index("--data") + 1] if "--data" in args else "data"   # --data demo_data: the demo accounts
    serve(Store(data), port=int(args[args.index("--port") + 1]) if "--port" in args else PORT)
