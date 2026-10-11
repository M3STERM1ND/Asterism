"""Lobby: who is playing, and which run (save file) they play, before the start menu.

  welcome  - L log in, N create a patient account (coaches sign up in the coach portal)
  login    - email (Supabase, any computer) or username (this computer only), password
  register - email (only with Supabase), username, your name, password
With Supabase set up (.env), signing up or logging in with an email also connects the account to the cloud,
so every battle uploads by itself; there is no separate sign-up or connect step.
  runs     - the patient's runs, most recent first: 1-9 continue one, N start a new run, O log out
  new_run  - type the new run's name
A run is like a Minecraft world: continuing one adds to its progress, sessions and videos; a new run
starts fresh. Pure logic: lobby_screen.py draws it, play.py hands the chosen run to the game.
"""
from accounts import AccountError

MAX_FIELD = 30
MAX_RUNS_SHOWN = 9
ENTER, TAB, ESC = 13, 9, 27
BACKSPACE = (8, 127)
FORMS = {
    "login": (("username", "Username", False), ("password", "Password", True)),
    "register": (("username", "Username", False), ("name", "Your name", False), ("password", "Password", True)),
    "new_run": (("name", "Run name", False),),
}
CLOUD_FORMS = {  # with Supabase: an email first
    "login": (("username", "Email (or username on this computer)", False), ("password", "Password", True)),
    "register": (("email", "Email", False), ("username", "Username", False), ("name", "Your name", False),
                 ("password", "Password", True)),
}


class Lobby:
    def __init__(self, store, cloud=None):
        """cloud: something with sign_up and sign_in (cloud.GameCloud), or None to stay on this computer."""
        self.store = store
        self.cloud = cloud
        self.user = None
        self.state = "welcome"
        self.values = {}
        self.field = 0
        self.message = ""
        self.ok = True           # the message is good news (else a problem)
        self.chosen = None       # the run picked to play, for play.py to take

    def typing(self):
        """True while a form is open: every key is a character (Q doesn't quit)."""
        return self.state in FORMS

    def fields(self):
        """The current form's fields (with Supabase, login and sign-up start with an email)."""
        if self.cloud is not None and self.state in CLOUD_FORMS:
            return CLOUD_FORMS[self.state]
        return FORMS[self.state]

    def runs(self):
        return self.store.runs(self.user.id)[:MAX_RUNS_SHOWN] if self.user else []

    def open_form(self, state):
        self.state, self.values, self.field = state, {}, 0

    def say(self, text, ok=True):
        self.message, self.ok = text, ok

    def handle_key(self, key):
        if self.typing():
            self.form_key(key)
        elif self.state == "welcome":
            if key == ord("l"):
                self.open_form("login")
            elif key == ord("n"):
                self.open_form("register")
        elif self.state == "runs":
            self.runs_key(key)

    def runs_key(self, key):
        runs = self.runs()
        if ord("1") <= key <= ord("9") and key - ord("1") < len(runs):
            self.chosen = runs[key - ord("1")]
        elif key == ord("n"):
            self.open_form("new_run")
        elif key == ord("o"):
            self.user, self.state = None, "welcome"
            self.say("Logged out")

    def form_key(self, key):
        fields = self.fields()
        name = fields[self.field][0]
        if key == ESC:
            self.state = "runs" if self.user else "welcome"
            self.message = ""
        elif key in BACKSPACE:
            self.values[name] = self.values.get(name, "")[:-1]
        elif key in (ENTER, TAB):
            if self.field < len(fields) - 1:
                self.field += 1
            elif key == ENTER:
                self.submit()
        elif 32 <= key <= 126 and len(self.values.get(name, "")) < MAX_FIELD:
            self.values[name] = self.values.get(name, "") + chr(key)

    def submit(self):
        v = self.values
        try:
            if self.state == "login" and self.cloud is not None and "@" in v.get("username", ""):
                user = self.cloud.sign_in(self.store, v["username"].strip(), v.get("password", ""))
                self.signed_in(user, f"Welcome back, {user.display_name}. Your battles sync to your coach")
            elif self.state == "register" and self.cloud is not None:
                user = self.cloud.sign_up(self.store, v.get("email", "").strip(), v.get("password", ""),
                                          v.get("username", ""), v.get("name", ""))
                imported = self.store.import_legacy(user)
                self.signed_in(user, f"Welcome, {user.display_name}. Your battles sync to your coach" +
                               (f". Earlier sessions are in '{imported.name}'" if imported else ""))
            elif self.state == "login":
                user = self.store.login(v.get("username", ""), v.get("password", ""))
                if user is None:
                    raise AccountError("Wrong username or password")
                if user.role != "patient":
                    raise AccountError("Coaches use the coach portal; the game is for patients")
                self.signed_in(user, f"Welcome back, {user.display_name}")
            elif self.state == "register":
                user = self.store.register(v.get("username", ""), v.get("password", ""), "patient", v.get("name", ""))
                imported = self.store.import_legacy(user)
                self.signed_in(user, f"Welcome, {user.display_name}" +
                               (f". Your earlier sessions are in the run '{imported.name}'" if imported else ""))
            elif self.state == "new_run":
                self.chosen = self.store.create_run(self.user, v.get("name", ""))
                self.state = "runs"
        except AccountError as error:
            self.say(str(error), ok=False)
            self.field = 0 if self.state != "register" else self.field

    def signed_in(self, user, message):
        self.user, self.state = user, "runs"
        self.say(message)

    def take_choice(self):
        """The run chosen to play (once), or None."""
        run, self.chosen = self.chosen, None
        return run
