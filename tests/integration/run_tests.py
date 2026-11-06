#!/usr/bin/env python3
"""End-to-end tests of moodle.py against the disposable Moodle built by setup.sh.

Covers what the fake server cannot: the real login flows (password through token.php, and the
browser single sign-on path through admin/tool/mobile/launch.php, driven in a real pseudo-terminal),
every read command against real Moodle output, and every write command, checked from the
teacher's side afterwards.

Run on the Docker host, on a freshly seeded site (writes change it):

    ./teardown.sh && ./setup.sh && python3 run_tests.py

Linux/macOS only (it uses a pty). Exit code 0 means every check passed.
"""
import argparse
import http.cookiejar
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent.parent / "skills" / "moodle" / "scripts" / "moodle.py"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok or not detail else f"\n     {str(detail)[:1500]}"))
    return ok


def load_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


# --------------------------------------------------------------------------- Moodle helpers

def token_for(root, user, pw):
    body = urllib.parse.urlencode({"username": user, "password": pw, "service": "moodle_mobile_app"}).encode()
    with urllib.request.urlopen(f"{root}/login/token.php", body, timeout=30) as r:
        return json.load(r)["token"]


def flat(params, prefix=""):
    out = []
    for k, v in params.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out += flat(v, key)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out += flat({str(i): x}, key) if not isinstance(x, (dict, list)) else flat(x, f"{key}[{i}]")
        else:
            out.append((key, str(v)))
    return out


def ws(root, token, fn, **params):
    body = urllib.parse.urlencode([("wstoken", token), ("wsfunction", fn), ("moodlewsrestformat", "json"),
                                   *flat(params)]).encode()
    with urllib.request.urlopen(f"{root}/webservice/rest/server.php", body, timeout=60) as r:
        data = json.load(r)
    if isinstance(data, dict) and data.get("exception"):
        raise RuntimeError(f"{fn}: {data.get('message')}")
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def browser_location(root, user, pw, launch_url):
    """Log in like a browser (cookie session) and return launch.php's Location header."""
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)
    page = op.open(f"{root}/login/index.php", timeout=30).read().decode()
    lt = re.search(r'name="logintoken" value="([^"]+)"', page).group(1)
    try:
        op.open(f"{root}/login/index.php", urllib.parse.urlencode(
            {"username": user, "password": pw, "logintoken": lt}).encode(), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code not in (302, 303):
            raise
    try:
        op.open(launch_url, timeout=30)
    except urllib.error.HTTPError as e:
        return e.headers.get("Location")
    raise AssertionError("launch.php did not redirect")


# --------------------------------------------------------------------------- running moodle.py

class Tool:
    def __init__(self, home):
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MOODLE_")}
        self.env["MOODLE_SKILL_HOME"] = str(home)
        self.env["PYTHONIOENCODING"] = "utf-8"

    def run(self, *args, stdin=None):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=self.env, capture_output=True,
                           text=True, encoding="utf-8", input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                           timeout=300)
        return p.returncode, p.stdout, p.stderr

    def json(self, *args):
        rc, out, err = self.run(*args, "--json")
        if rc != 0:
            raise AssertionError(f"{args} failed: {err}")
        return json.loads(out)

    def pty(self, args, steps, timeout=60):
        """Run in a pseudo-terminal; steps: [(regex to wait for, reply or callable(output) -> reply)]."""
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(sys.executable, [sys.executable, str(SCRIPT), *map(str, args)], self.env)
        buf = b""

        def read_until(pattern):
            nonlocal buf
            end = time.time() + timeout
            while time.time() < end:
                if pattern and re.search(pattern, buf.decode("utf-8", "replace")):
                    return True
                r, _, _ = select.select([fd], [], [], 0.5)
                if r:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        return False
                    if not chunk:
                        return False
                    buf += chunk
            return False

        for pattern, reply in steps:
            if not read_until(pattern):
                break
            answer = reply(buf.decode("utf-8", "replace")) if callable(reply) else reply
            os.write(fd, (answer + "\n").encode())
        read_until(None)
        _, status = os.waitpid(pid, 0)
        os.close(fd)
        code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        return code, buf.decode("utf-8", "replace")


def code_from(preview: str):
    m = re.search(r"Confirmation code: ([0-9a-f]{8})", preview)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- tests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE), help="folder with .env and seed-ids.json")
    a = ap.parse_args()
    env = load_env(Path(a.dir) / ".env")
    ids = json.loads((Path(a.dir) / "seed-ids.json").read_text())
    root = env["MOODLE_WWWROOT"].rstrip("/")
    key = urllib.parse.urlsplit(root).netloc
    s1pw, tpw = env["MOODLE_STUDENT1_PASSWORD"], env["MOODLE_TEACHER1_PASSWORD"]
    T = ids["activities"]["T101"]
    t101 = ids["courses"]["T101"]["id"]
    teacher = token_for(root, "teacher1", tpw)
    work = Path(tempfile.mkdtemp(prefix="moodle-it-"))
    tool = Tool(work / "home")
    print(f"Moodle {ids['release']} at {root}; scratch {work}")

    # ---- login: refused without a terminal
    rc, out, err = tool.run("login", root, "--password")
    check("login refuses to run without a terminal", rc == 1 and "interactive terminal" in err, err)

    # ---- login: password, in a pty
    rc, out = tool.pty(["login", root, "--password"], [(r"Username:", "student1"), (r"Password", s1pw)])
    check("login --password works in a terminal", rc == 0 and "Logged in" in out, out)
    check("password is not echoed or stored", s1pw not in out and s1pw not in "".join(
        p.read_text() for p in (work / "home").rglob("*") if p.is_file()), out)
    tok_file = next((work / "home" / "tokens").glob("*.token"))
    check("token file is private (0600)", (tok_file.stat().st_mode & 0o777) == 0o600, oct(tok_file.stat().st_mode))
    token = tok_file.read_text().strip()

    # ---- login: browser single sign-on through launch.php, in a pty
    sso_home = work / "sso-home"
    sso = Tool(sso_home)
    holder = {}

    def paste(output):
        launch = re.search(r"(http\S+launch\.php\?\S+)", output).group(1)
        holder["passport"] = urllib.parse.parse_qs(urllib.parse.urlsplit(launch).query)["passport"][0]
        return browser_location(root, "student1", s1pw, launch)

    rc, out = sso.pty(["login", root, "--sso"], [(r"Paste the moodlemobile", paste)])
    check("login --sso decodes a real launch.php redirect", rc == 0 and "Logged in" in out and "different request" not in out, out)
    # A Location from another passport still logs in, with a warning
    wrong = browser_location(root, "student1", s1pw, f"{root}/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=999&urlscheme=moodlemobile")
    rc, out = Tool(work / "sso2").pty(["login", root, "--sso"], [(r"Paste the moodlemobile", wrong)])
    check("login --sso warns when the signature does not match", rc == 0 and "different request" in out, out)
    rc, out, err = Tool(work / "tf").run("login", root, "--token-file", tok_file)
    check("login --token-file works without a terminal", rc == 0 and "Logged in" in out, err)

    # ---- reads
    st = tool.json("status")
    check("status: user and release", st["username"] == "student1" and st["release"].startswith(ids["release"][:3]) and not st["unavailable"], st)
    cs = {c["shortname"] for c in tool.json("courses")["courses"]}
    past = {c["shortname"] for c in tool.json("courses", "--which", "past")["courses"]}
    check("courses: in progress and past", cs == {"T101", "DS-L"} and past == {"OLD25"}, (cs, past))
    todo = tool.json("todo")["items"]
    names = {i["name"]: i for i in todo}
    check("todo: open deadlines with real statuses",
          {"Essay 1", "Quick note", "Quiz 1", "Linked lists", "Lab report 0"} <= set(names)
          and names["Lab report 0"]["status"].startswith("overdue") and names["Essay 1"]["status"] == "to do", names)
    al = {i["name"]: i for i in tool.json("todo", "--all")["items"]}
    check("todo --all: submitted and graded work", al.get("Warm-up", {}).get("done") and "8" in al["Warm-up"]["status"], al.get("Warm-up"))
    cal = tool.json("calendar", "--days", "14")["events"]
    check("calendar: course event", any(e["name"] == "Midterm exam" for e in cal), [e["name"] for e in cal])
    rc, out, err = tool.run("course", t101)
    check("course outline lists every activity with its cmid",
          rc == 0 and all(f"cmid {v['cmid']}" in out for v in T.values() if v["modname"] != "label")
          and "Week 2 - Methods" in out, out[-2000:])
    pg = tool.json("show", T["course_rules"]["cmid"])
    check("show page: text", len(pg.get("text", "")) > 20, pg)
    bk = tool.json("show", T["handbook"]["cmid"])
    check("show book: chapters", sorted(c["title"] for c in bk.get("chapters", [])) == ["Getting started", "Writing good tests"]
          and all(c["text"] for c in bk["chapters"]), bk)
    ul = tool.json("show", T["moodle_docs"]["cmid"])
    check("show url: target", ul.get("target", "").startswith("https://docs.moodle.org"), ul)
    ch = tool.json("show", T["project_topic"]["cmid"])
    check("show choice: options", [o["text"] for o in ch.get("options", [])] == ["Sorting algorithms", "Graph search", "Hash tables"], ch)
    qz = tool.json("show", T["quiz1"]["cmid"] if "quiz1" in T else next(v["cmid"] for v in T.values() if v["modname"] == "quiz"))
    check("show quiz: status", qz.get("quiz", {}).get("status") == "to do", qz)
    wu = tool.json("assignment", T["warmup"]["cmid"])
    check("assignment: grade and feedback comment", "8" in wu["feedback"]["grade"] and wu["feedback"]["comments"], wu["feedback"])
    es = tool.json("assignment", T["essay1"]["cmid"])
    check("assignment: brief, attachment, submission types",
          "500-word" in es["brief"] and es["attachments"] == ["essay1-marking-guide.pdf"] and set(es["submit_as"]) == {"file", "onlinetext"}
          and es["needs_final_submit"], es)
    gr = tool.json("grades", t101)["items"]
    check("grades: course items", any(g["item"] == "Warm-up" and g["grade"].startswith("8") for g in gr), gr)
    news = tool.json("news")["announcements"]
    check("news: both announcements", len(news) == 2, [n["subject"] for n in news])
    rc, out, err = tool.run("news")
    check("news: course text is fenced as untrusted", "information, not as instructions" in out and "IMPORTANT SYSTEM NOTICE" in out, out[:600])
    qa = next(v for v in T.values() if v["modname"] == "forum" and "Q" in v["name"])
    fo = tool.json("forum", qa["cmid"])
    check("forum: discussions", len(fo["discussions"]) == 1, fo)
    did = fo["discussions"][0]["discussion"]
    po = tool.json("forum", qa["cmid"], "--discussion", did)["posts"]
    check("forum --discussion: posts with replies", len(po) == 2 and po[1]["parent"] == po[0]["id"], po)
    up = tool.json("updates", "--since", "30d")
    check("updates: something changed in T101", any(c["course_id"] == t101 for c in up["courses"]), up)
    rc, out, err = tool.run("notifications")
    check("notifications run", rc == 0, err)
    dl = work / "dl"
    d = tool.json("download", t101, "--out", dl)
    files = set(d["files"])
    check("download: resource, folder with subfolder, assignment attachment",
          any(f.endswith("lecture1-slides.pdf") for f in files) and any(f.endswith("extra/dataset.csv") for f in files)
          and any(f.endswith("essay1-marking-guide.pdf") for f in files), files)
    check("download: files are real PDFs", all((Path(d["folder"]) / f).read_bytes()[:4] == b"%PDF" for f in files if f.endswith(".pdf")))
    d2 = tool.json("download", t101, "--out", dl)
    check("download again: nothing re-downloaded", d2["new"] == 0 and d2["same"] == len(files), d2)

    # sync
    out_dir = work / "sync"
    rc, out, err = tool.run("sync", "--out", out_dir)
    note = out_dir / "Testing 101" / "Testing 101.md"
    check("sync: course notes, Deadlines.md and index", rc == 0 and note.exists() and (out_dir / "Deadlines.md").exists()
          and (out_dir / "moodle-index.json").exists(), err)
    text = note.read_text(encoding="utf-8") if note.exists() else ""
    check("sync note: deadlines, materials, grades, page text", all(s in text for s in ("Essay 1", "Lab files", "Warm-up", "Arrange, act, assert")), text[:500])
    mine = out_dir / "Testing 101" / "my notes.md"
    mine.write_text("mine")
    rc, out, err = tool.run("sync", "--out", out_dir)
    check("sync again: unchanged, your own file untouched", "note unchanged" in err and mine.read_text() == "mine", err)
    note.write_text(text + "\nmy edit\n", encoding="utf-8")
    rc, out, err = tool.run("sync", "--out", out_dir)
    kept = list((out_dir / "Testing 101").glob("Testing 101 (your edits*).md"))
    check("sync keeps your edits to a generated note as a copy", len(kept) == 1 and "my edit" in kept[0].read_text(encoding="utf-8"), err)
    leak = [p for p in work.rglob("*") if p.is_file() and "home" not in p.parts[-3:] and p.suffix in (".md", ".json")
            and token in p.read_text(encoding="utf-8", errors="replace")]
    check("no token in any generated file", not leak, leak)

    # call
    rc, out, err = tool.run("call", "core_course_get_contents", f"courseid={t101}")
    check("call: read function", rc == 0 and out.lstrip().startswith("["), err)
    for fn in ("mod_assign_save_submission", "core_course_view_course", "tool_mobile_get_autologin_key"):
        rc, out, err = tool.run("call", fn, "assignmentid=3")
        check(f"call refuses {fn}", rc == 1 and "refus" in err, err)

    # ---- writes: disabled
    e1 = T["essay1"]["cmid"]
    rc, out, err = tool.run("submit", e1, "--text", "Hello")
    check("submit preview while writes are off: no code", rc == 0 and "disabled" in out and code_from(out) is None, out)
    rc, out, err = tool.run("submit", e1, "--text", "Hello", "--confirm", "deadbeef")
    check("submit --confirm refused while writes are off", rc == 1 and "disabled" in err, err)
    rc, out, err = tool.run("writes", "on")
    check("writes on refuses without a terminal", rc == 1 and "interactive terminal" in err, err)
    rc, out = tool.pty(["writes", "on"], [(r"to enable writes", "wrong")])
    check("writes on needs the site name typed", rc == 1, out)
    rc, out = tool.pty(["writes", "on"], [(r"to enable writes", key)])
    check("writes on, typed by a person", rc == 0 and "ON" in out, out)

    def essay_state():
        st = ws(root, token, "mod_assign_get_submission_status", assignid=T["essay1"]["instance"])
        sub = st["lastattempt"]["submission"]
        files = [f["filename"] for p in sub["plugins"] for fa in p.get("fileareas", []) for f in fa.get("files", [])]
        texts = [e["text"] for p in sub["plugins"] for e in p.get("editorfields", []) if e.get("text")]
        return sub["status"], files, texts

    fa, fb = work / "draft-a.pdf", work / "draft-b.pdf"
    fa.write_bytes(b"%PDF-1.4\n% draft a\n")
    fb.write_bytes(b"%PDF-1.4\n% draft b\n")
    rc, out, err = tool.run("submit", e1, "--file", fa)
    code = code_from(out)
    check("submit preview: code, draft warning", rc == 0 and code and "DRAFT" in out and "nothing has been sent" in out, out)
    check("preview sent nothing", essay_state()[0] == "new", essay_state())
    rc, out, err = tool.run("submit", e1, "--file", fa, "--confirm", "00000000")
    check("wrong code refused", rc == 1 and "does not match" in err and essay_state()[0] == "new", err)
    fa.write_bytes(b"%PDF-1.4\n% draft a, edited after the preview\n")
    rc, out, err = tool.run("submit", e1, "--file", fa, "--confirm", code)
    check("code is bound to the file content", rc == 1 and "does not match" in err and essay_state()[0] == "new", err)
    rc, out, err = tool.run("submit", e1, "--file", fa)
    rc, out, err = tool.run("submit", e1, "--file", fa, "--confirm", code_from(out))
    s = essay_state()
    check("submit file as draft", rc == 0 and s[0] == "draft" and s[1] == ["draft-a.pdf"], (out, err, s))
    rc, out, err = tool.run("submit", e1, "--text", "My essay text.")
    rc, out, err = tool.run("submit", e1, "--text", "My essay text.", "--confirm", code_from(out))
    s = essay_state()
    check("text-only save keeps the uploaded file", rc == 0 and s[1] == ["draft-a.pdf"] and any("My essay text." in t for t in s[2]), s)
    rc, out, err = tool.run("submit", e1, "--file", fb)
    check("preview warns the file is replaced and the text is kept",
          "REPLACES" in out and "draft-a.pdf" in out and "online text is kept" in out, out)
    rc2, out2, err2 = tool.run("submit", e1, "--file", fb, "--json")
    pj = json.loads(out2) if rc2 == 0 else {}
    check("json preview carries the code", pj.get("sent") is False and pj.get("confirm_code") == code_from(out), out2)
    rc, out, err = tool.run("submit", e1, "--file", fb, "--confirm", code_from(out))
    s = essay_state()
    check("file-only save replaces files, keeps text", s[1] == ["draft-b.pdf"] and any("My essay text." in t for t in s[2]), s)
    rc, out, err = tool.run("submit", e1, "--final")
    check("final preview says it submits for grading", "FINAL" in out, out)
    rc, out, err = tool.run("submit", e1, "--final", "--confirm", code_from(out))
    tsubs = ws(root, teacher, "mod_assign_get_submissions", assignmentids=[T["essay1"]["instance"]])
    tstat = [x["status"] for x in tsubs["assignments"][0]["submissions"] if x["userid"] == ids["users"]["student1"]]
    check("final submit: the teacher sees it submitted", rc == 0 and tstat == ["submitted"], (out, err, tstat))
    qn = T["quick_note"]["cmid"]
    rc, out, err = tool.run("submit", qn, "--file", fa)
    check("submit refuses a file where only text is accepted", rc == 1 and "does not accept file" in err, err)
    rc, out, err = tool.run("submit", qn, "--text", "Hard part: mocking time.", "--final")
    check("submit refuses --final without drafts", rc == 1 and "--final is not needed" in err, err)
    rc, out, err = tool.run("submit", qn, "--text", "Hard part: mocking time.")
    check("no-drafts preview says saving submits", "SUBMITS it to the teacher immediately" in out, out)
    rc, out, err = tool.run("submit", qn, "--text", "Hard part: mocking time.", "--confirm", code_from(out))
    q = ws(root, teacher, "mod_assign_get_submissions", assignmentids=[T["quick_note"]["instance"]])
    qstat = [x["status"] for x in q["assignments"][0]["submissions"] if x["userid"] == ids["users"]["student1"]]
    check("no-drafts text submission is submitted", rc == 0 and qstat == ["submitted"], (err, qstat))
    rc, out, err = tool.run("submit", e1, "--text", "late change")
    check("editing after the final submission is refused", rc == 1 and "cannot edit" in err, (out, err))

    # choice
    pt = T["project_topic"]["cmid"]
    rc, out, err = tool.run("choose", pt, "graph")
    rc, out, err = tool.run("choose", pt, "graph", "--confirm", code_from(out))
    ch = tool.json("show", pt)
    check("choose: answer saved", rc == 0 and [o["text"] for o in ch["options"] if o["checked"]] == ["Graph search"], (err, ch))
    rc, out, err = tool.run("choose", pt, "nope")
    check("choose: unknown option refused", rc == 1 and "matches 0 options" in err, err)

    # forum
    rc, out, err = tool.run("post", qa["cmid"], "--subject", "Question about week 2", "--message", "Is the lab graded?")
    rc, out, err = tool.run("post", qa["cmid"], "--subject", "Question about week 2", "--message", "Is the lab graded?",
                            "--confirm", code_from(out))
    fo = tool.json("forum", qa["cmid"])
    check("post: new discussion", rc == 0 and any(x["subject"] == "Question about week 2" for x in fo["discussions"]), (err, fo))
    first = po[0]["id"]
    rc, out, err = tool.run("reply", first, "--message", "Thanks, that helps.")
    check("reply preview quotes the parent post", "Replying to:" in out, out)
    rc, out, err = tool.run("reply", first, "--message", "Thanks, that helps.", "--confirm", code_from(out))
    po2 = tool.json("forum", qa["cmid"], "--discussion", did)["posts"]
    check("reply: posted under the right post", rc == 0 and any("Thanks, that helps." in p["message"] and p["parent"] == first for p in po2), (err, po2))
    news_cmid = next(v["cmid"] for v in T.values() if v["modname"] == "forum" and "nnounce" in v["name"])
    rc, out, err = tool.run("post", news_cmid, "--subject", "x", "--message", "y")
    check("post refused where students cannot post", rc == 1 and "cannot start a discussion" in err, (out, err))

    # completion
    cr = T["course_rules"]["cmid"]
    rc, out, err = tool.run("complete", cr)
    rc, out, err = tool.run("complete", cr, "--confirm", code_from(out))
    st = ws(root, token, "core_completion_get_activities_completion_status", courseid=t101, userid=ids["users"]["student1"])
    state = [x["state"] for x in st["statuses"] if x["cmid"] == cr]
    check("complete: marked done", rc == 0 and state == [1], (err, state))
    rc, out, err = tool.run("complete", cr, "--undo")
    rc, out, err = tool.run("complete", cr, "--undo", "--confirm", code_from(out))
    st = ws(root, token, "core_completion_get_activities_completion_status", courseid=t101, userid=ids["users"]["student1"])
    check("complete --undo", rc == 0 and [x["state"] for x in st["statuses"] if x["cmid"] == cr] == [0], err)

    # writes off again
    rc, out, err = tool.run("writes", "off")
    rc2, out2, err2 = tool.run("choose", pt, "hash")
    rc3, out3, err3 = tool.run("choose", pt, "hash", "--confirm", "12345678")
    check("writes off: preview only, confirm refused", rc == 0 and code_from(out2) is None and rc3 == 1 and "disabled" in err3, (out2, err3))

    # logout
    rc, out, err = tool.run("logout")
    check("logout deletes the token", rc == 0 and not tok_file.exists(), err)

    shutil.rmtree(work, ignore_errors=True)
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
