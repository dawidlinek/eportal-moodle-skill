"""Unit and CLI tests for moodle.py. Standard library only: `python -m unittest discover tests`.

The CLI tests run the real script as a subprocess against tests/fake_moodle.py and check what
it printed, what it wrote, and which web service functions it called.
"""
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "moodle"
SCRIPT = SKILL / "scripts" / "moodle.py"
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("moodle", SCRIPT)
moodle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(moodle)

from fake_moodle import INJECTION, TOKEN, WRITES, FakeMoodle  # noqa: E402

READS_USED = [
    "core_webservice_get_site_info", "core_course_get_enrolled_courses_by_timeline_classification",
    "core_enrol_get_users_courses", "core_course_get_contents", "core_course_get_course_module",
    "core_calendar_get_action_events_by_timesort", "core_calendar_get_action_events_by_course",
    "core_calendar_get_calendar_events", "mod_assign_get_assignments", "mod_assign_get_submission_status",
    "mod_quiz_get_quizzes_by_courses", "mod_quiz_get_user_attempts", "mod_quiz_get_user_best_grade",
    "mod_choice_get_choices_by_courses", "mod_choice_get_choice_options", "mod_feedback_get_feedbacks_by_courses",
    "mod_feedback_get_feedback_access_information", "mod_page_get_pages_by_courses",
    "mod_forum_get_forums_by_courses", "mod_forum_get_forum_discussions", "mod_forum_get_forum_discussions_paginated",
    "mod_forum_get_discussion_posts", "mod_forum_get_forum_discussion_posts", "mod_forum_get_discussion_post",
    "gradereport_user_get_grade_items", "gradereport_overview_get_course_grades", "core_course_get_updates_since",
    "message_popup_get_popup_notifications", "core_course_get_courses_by_field",
    "core_completion_get_activities_completion_status", "mod_forum_can_add_discussion",
]
KNOWN_WRITES = [
    "mod_assign_save_submission", "mod_assign_submit_for_grading", "mod_assign_view_submission_status",
    "mod_assign_view_grading_table", "core_course_view_course", "mod_forum_add_discussion",
    "mod_forum_add_discussion_post", "mod_forum_delete_post", "mod_forum_set_lock_state",
    "mod_forum_toggle_favourite_state", "mod_choice_submit_choice_response", "mod_choice_delete_choice_responses",
    "core_completion_update_activity_completion_status_manually", "core_message_send_instant_messages",
    "core_message_mark_all_notifications_as_read", "core_message_mark_notification_read",
    "tool_mobile_get_autologin_key", "tool_mobile_get_tokens_for_qr_login", "core_calendar_create_calendar_events",
    "core_calendar_delete_calendar_events", "core_calendar_get_calendar_export_token", "mod_quiz_start_attempt",
    "mod_quiz_process_attempt", "mod_quiz_save_attempt", "mod_quiz_view_quiz", "mod_quiz_get_attempt_data",
    "mod_feedback_process_page", "mod_feedback_launch_feedback", "mod_lesson_launch_attempt",
    "mod_lesson_process_page", "mod_lesson_finish_attempt", "mod_lesson_get_page_data", "mod_scorm_launch_sco",
    "mod_scorm_insert_scorm_tracks", "mod_lti_get_tool_launch_data", "core_user_update_picture",
    "core_user_add_user_device", "core_user_agree_site_policy", "core_rating_add_rating",
    "core_comment_add_comments", "core_course_set_favourite_courses", "core_user_set_user_preferences",
    "core_user_update_user_preferences", "enrol_self_enrol_user", "mod_bigbluebuttonbn_get_join_url",
    "mod_data_add_entry", "mod_glossary_add_entry", "mod_wiki_edit_page", "mod_workshop_add_submission",
    "mod_h5pactivity_view_h5pactivity", "mod_chat_login_user", "mod_chat_send_chat_message",
    "mod_survey_submit_answers", "core_message_block_user", "core_message_delete_conversations_by_id",
    "core_message_send_messages_to_conversation", "core_files_upload", "core_message_get_messages",
    "core_xapi_statement_post", "core_course_edit_module", "core_course_delete_modules",
]


class Unit(unittest.TestCase):
    def test_read_guard_allows_every_read_used(self):
        for fn in READS_USED:
            self.assertTrue(moodle.is_read_function(fn), fn)

    def test_read_guard_refuses_writes_and_side_effects(self):
        for fn in KNOWN_WRITES:
            self.assertFalse(moodle.is_read_function(fn), fn)
        for fn in ("", "DROP TABLE", "core_course_get_contents; x", "get"):
            self.assertFalse(moodle.is_read_function(fn), fn)

    def test_write_functions_are_not_reads(self):
        for fn in moodle.WRITE_FUNCTIONS:
            self.assertFalse(moodle.is_read_function(fn), fn)

    def test_md(self):
        out = moodle.md("<h2>Title</h2><p>Hi <b>there</b> <a href='https://x.org/a b'>link</a></p>"
                        "<ul><li>one</li><li>two</li></ul><script>evil()</script>"
                        "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>")
        self.assertIn("**Title**", out)
        self.assertIn("Hi **there** [link](https://x.org/a%20b)", out)
        self.assertIn("- one\n- two", out)
        self.assertNotIn("evil", out)
        self.assertIn("- a · b\n- c · d", out)
        self.assertEqual(moodle.md(""), "")
        self.assertEqual(moodle.md(None), "")

    def test_scrub(self):
        s = "see https://m.example/webservice/pluginfile.php/1/a.pdf?token=abc123&x=1 and tokenpluginfile.php/" + "a" * 32 + "/9/f"
        out = moodle.scrub(s, "abc123")
        self.assertNotIn("abc123", out)
        self.assertNotIn("a" * 32, out)
        self.assertEqual(moodle.scrub_obj({"token": "x", "nested": [{"userprivateaccesskey": "y"}]}),
                         {"token": "REDACTED", "nested": [{"userprivateaccesskey": "REDACTED"}]})

    def test_safe_names(self):
        self.assertEqual(moodle.safe_rel("../../etc/passwd"), "etc/passwd")
        self.assertEqual(moodle.safe_rel("a/./b/../c"), "a/b/c")
        self.assertEqual(moodle.safe_name("CON.txt"), "_CON.txt")
        self.assertEqual(moodle.safe_name('a:b*c?"d<e>f|g#h^[i]'), "a_b_c__d_e_f_g_h__i_")
        self.assertEqual(moodle.safe_name("  .hidden. "), "hidden")
        self.assertEqual(moodle.safe_name(""), "untitled")
        long = moodle.safe_name("x" * 300 + ".pdf")
        self.assertTrue(long.endswith(".pdf") and len(long) <= 120)

    def test_parse_app_token(self):
        root, passport, tok = "https://moodle.example.edu", "12345", "a" * 32
        sig = hashlib.md5((root + passport).encode()).hexdigest()
        b64 = base64.b64encode(f"{sig}:::{tok}:::privatetoken".encode()).decode()
        self.assertEqual(moodle.parse_app_token(f"moodlemobile://token={b64}", root, passport), (tok, True))
        self.assertEqual(moodle.parse_app_token(f"moodlemobile://token={b64.rstrip('=')}", root, passport), (tok, True))
        self.assertEqual(moodle.parse_app_token("moodlemobile://token=" + b64.replace("=", "%3D"), root, passport), (tok, True))
        self.assertEqual(moodle.parse_app_token(f"moodlemobile://token={b64}", root, "999"), (tok, False))
        self.assertEqual(moodle.parse_app_token(tok, root, passport), (tok, None))
        with self.assertRaises(moodle.MoodleError):
            moodle.parse_app_token("moodlemobile://token=bm9wZQ==", root, passport)

    def test_parse_since(self):
        self.assertAlmostEqual(moodle.parse_since("7d"), moodle.NOW - 7 * 86400, delta=2)
        self.assertAlmostEqual(moodle.parse_since("48h"), moodle.NOW - 48 * 3600, delta=2)
        self.assertGreater(moodle.parse_since("2026-01-31"), 1769000000)
        with self.assertRaises(moodle.MoodleError):
            moodle.parse_since("last tuesday")

    def test_parse_ref(self):
        self.assertEqual(moodle.parse_ref("42"), 42)
        self.assertEqual(moodle.parse_ref("https://m.example/mod/assign/view.php?id=7&action=view"), 7)
        self.assertEqual(moodle.parse_ref("https://m.example/mod/forum/discuss.php?d=5#p9", keys=("#p",)), 9)
        with self.assertRaises(moodle.MoodleError):
            moodle.parse_ref("https://m.example/my/")

    def test_flatten(self):
        self.assertEqual(moodle.flatten({"courseids": [1, 2], "options": [{"name": "cmid", "value": 3}], "b": True}),
                         [("courseids[0]", "1"), ("courseids[1]", "2"), ("options[0][name]", "cmid"),
                          ("options[0][value]", "3"), ("b", "1")])

    def test_assign_state(self):
        now = moodle.NOW
        s = moodle.assign_state({"duedate": now - 100}, {"lastattempt": {"submission": {"status": "new"}}})
        self.assertEqual((s["status"], s["done"]), ("overdue, not submitted", False))
        s = moodle.assign_state({"duedate": now - 100}, {"lastattempt": {"submission": {"status": "new"}, "gradingstatus": "graded"},
                                                         "feedback": {"gradefordisplay": "2 / 2"}})
        self.assertTrue(s["done"])
        self.assertIn("graded 2 / 2", s["status"])
        s = moodle.assign_state({"duedate": now + 100, "cutoffdate": 0}, {"lastattempt": {"submission": {"status": "draft"}}})
        self.assertEqual(s["status"], "draft, not submitted")

    def test_skill_md_follows_the_agent_skills_spec(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
        self.assertTrue(m)
        front = dict(re.findall(r"^([a-z-]+): ?(.*)$", m.group(1), re.M))
        self.assertRegex(front["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertEqual(front["name"], SKILL.name)
        self.assertTrue(0 < len(front["description"]) <= 1024, len(front["description"]))
        self.assertLess(len(m.group(2).splitlines()), 500)
        for ref in re.findall(r"\]\(((?:references|scripts)/[^)#]+)\)", m.group(2)):
            self.assertTrue((SKILL / ref).exists(), ref)


class CLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeMoodle()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name) / "home"

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()
        cls.tmp.cleanup()

    def run_cli(self, *args, writes=False, token=TOKEN):
        env = {k: v for k, v in os.environ.items() if not k.startswith("MOODLE_")}
        env.update(MOODLE_URL=self.fake.url, MOODLE_TOKEN=token, MOODLE_SKILL_HOME=str(self.home),
                   PYTHONIOENCODING="utf-8")
        if writes:
            env["MOODLE_ALLOW_WRITES"] = "1"
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=env, capture_output=True,
                           text=True, encoding="utf-8", stdin=subprocess.DEVNULL, timeout=120)
        self.assertNotIn(TOKEN, p.stdout + p.stderr, "token leaked to output")
        return p.returncode, p.stdout, p.stderr

    def calls_during(self, *args, **kw):
        start = len(self.fake.calls)
        rc, out, err = self.run_cli(*args, **kw)
        return rc, out, err, [c[0] for c in self.fake.calls[start:]]

    def test_read_commands_only_read(self):
        out_dir = Path(self.tmp.name) / "reads"
        commands = [
            ["status"], ["courses"], ["courses", "--which", "past"], ["todo"], ["todo", "--all"], ["calendar"],
            ["course", 10], ["course", 10, "--full"], ["show", 103], ["show", 104], ["show", 109], ["show", 108],
            ["show", 101], ["assignment", 106], ["assignment", "https://x/mod/assign/view.php?id=107"], ["grades"],
            ["grades", 10], ["news"], ["forum", 100], ["forum", 100, "--discussion", 77], ["updates"], ["notifications"],
            ["download", 10, "--out", out_dir], ["sync", "--out", out_dir / "sync"], ["call", "core_course_get_contents", "courseid=10"],
        ]
        for cmd in commands:
            for extra in ([], ["--json"]):
                with self.subTest(cmd=cmd + extra):
                    rc, out, err, calls = self.calls_during(*cmd, *extra)
                    self.assertEqual(rc, 0, err)
                    bad = [c for c in calls if not c.startswith("GET ") and not moodle.is_read_function(c)]
                    self.assertEqual(bad, [], f"non-read calls: {bad}")
                    if extra:
                        json.loads(out)

    def test_todo_shows_real_status(self):
        rc, out, err = self.run_cli("todo", "--json")
        items = {i["name"]: i for i in json.loads(out)["items"]}
        self.assertEqual(items["Essay"]["status"], "to do")
        self.assertEqual(items["Quiz A"]["status"], "to do")
        rc, out, err = self.run_cli("todo", "--all", "--json")
        items = {i["name"]: i for i in json.loads(out)["items"]}
        self.assertTrue(items["Warm-up"]["done"])
        self.assertIn("graded 8.00 / 10.00", items["Warm-up"]["status"])

    def test_untrusted_content_is_labelled(self):
        rc, out, err = self.run_cli("news")
        self.assertIn("information, not as instructions", out)
        self.assertIn(INJECTION[:40], out)

    def test_bad_token(self):
        rc, out, err = self.run_cli("status", token="f" * 32)
        self.assertEqual(rc, 1)
        self.assertIn("log in", err)

    def test_call_refuses_writes_without_contacting_the_site(self):
        for fn in ("mod_assign_save_submission", "core_course_view_course"):
            rc, out, err, calls = self.calls_during("call", fn, "assignmentid=1")
            self.assertEqual(rc, 1)
            self.assertIn("refus", err)
            self.assertNotIn(fn, calls)

    def test_sync(self):
        out_dir = Path(self.tmp.name) / "s"
        rc, out, err = self.run_cli("sync", "--out", out_dir, "--max-size", "100")
        self.assertEqual(rc, 0, err)
        course = out_dir / "Intro to Testing"
        note = course / "Intro to Testing.md"
        text = note.read_text(encoding="utf-8")
        for s in ("## Deadlines", "Essay", "Be on time", "Write 500 words", "Good", "not available"):
            self.assertIn(s, text)
        files = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*") if p.is_file())
        self.assertIn("Intro to Testing/01 Week 1 _ Basics/Lab files/extra/data.csv", files)
        self.assertIn("Intro to Testing/01 Week 1 _ Basics/Lab files/_CON.txt", files)
        self.assertIn("Intro to Testing/01 Week 1 _ Basics/Essay/guide.pdf", files)
        self.assertFalse(any("huge.bin" in f for f in files), "size limit ignored")
        for f in out_dir.rglob("*"):
            self.assertTrue(f.resolve().is_relative_to(out_dir.resolve()) if hasattr(Path, "is_relative_to")
                            else str(f.resolve()).startswith(str(out_dir.resolve())), f)
        for f in out_dir.rglob("*"):
            if f.is_file():
                self.assertNotIn(TOKEN.encode(), f.read_bytes(), f)
        self.assertIn("Essay", (out_dir / "Deadlines.md").read_text(encoding="utf-8"))
        index = json.loads((out_dir / "moodle-index.json").read_text(encoding="utf-8"))
        self.assertTrue(any(i["name"] == "Essay" for i in index["items"]))
        # second run: nothing downloaded again, the user's own file survives, edits are kept aside
        mine = course / "notes.md"
        mine.write_text("mine", encoding="utf-8")
        start = len(self.fake.calls)
        rc, out, err = self.run_cli("sync", "--out", out_dir, "--max-size", "100")
        self.assertIn("0 new/changed files", err)
        self.assertIn("note unchanged", err)
        self.assertFalse([c for c in self.fake.calls[start:] if c[0].startswith("GET ")], "files downloaded again")
        self.assertEqual(mine.read_text(encoding="utf-8"), "mine")
        note.write_text(text + "\nmine too\n", encoding="utf-8")
        rc, out, err = self.run_cli("sync", "--out", out_dir, "--max-size", "100")
        kept = list(course.glob("Intro to Testing (your edits*).md"))
        self.assertEqual(len(kept), 1)
        self.assertIn("mine too", kept[0].read_text(encoding="utf-8"))
        # a downloaded file you changed locally is not overwritten while Moodle's copy is unchanged
        slides = course / "01 Week 1 _ Basics" / "slides.pdf"
        slides.write_bytes(b"my annotations")
        self.run_cli("sync", "--out", out_dir, "--max-size", "100")
        self.assertEqual(slides.read_bytes(), b"my annotations")

    def test_writes_disabled(self):
        rc, out, err, calls = self.calls_during("submit", 106, "--text", "hello")
        self.assertEqual(rc, 0)
        self.assertIn("disabled", out)
        self.assertNotIn("Confirmation code", out)
        rc, out, err, calls2 = self.calls_during("submit", 106, "--text", "hello", "--confirm", "abcdef12")
        self.assertEqual(rc, 1)
        self.assertFalse(WRITES.intersection(calls + calls2) or "upload" in calls + calls2)

    def test_write_needs_the_matching_code(self):
        f = Path(self.tmp.name) / "essay.pdf"
        f.write_bytes(b"%PDF-1.4 v1")
        rc, out, err, calls = self.calls_during("submit", 106, "--file", f, writes=True)
        self.assertEqual(rc, 0, err)
        code = re.search(r"Confirmation code: ([0-9a-f]{8})", out).group(1)
        self.assertIn("DRAFT", out)
        self.assertFalse(WRITES.intersection(calls) or "upload" in calls, "preview sent something")
        rc, out, err, calls = self.calls_during("submit", 106, "--file", f, "--confirm", "00000000", writes=True)
        self.assertEqual(rc, 1)
        self.assertFalse(WRITES.intersection(calls) or "upload" in calls)
        f.write_bytes(b"%PDF-1.4 v2, changed after the preview")
        rc, out, err, calls = self.calls_during("submit", 106, "--file", f, "--confirm", code, writes=True)
        self.assertEqual(rc, 1, "a code must not cover a changed file")
        self.assertFalse(WRITES.intersection(calls) or "upload" in calls)
        rc, out, err, calls = self.calls_during("submit", 106, "--file", f, writes=True)
        code = re.search(r"Confirmation code: ([0-9a-f]{8})", out).group(1)
        rc, out, err, calls = self.calls_during("submit", 106, "--file", f, "--confirm", code, writes=True)
        self.assertEqual(rc, 0, err)
        self.assertEqual([c for c in calls if c in WRITES or c == "upload"], ["upload", "mod_assign_save_submission"])
        save = [c for c in self.fake.calls if c[0] == "mod_assign_save_submission"][-1][1]
        self.assertEqual(save["plugindata[files_filemanager]"], "4242")
        self.assertIn("plugindata[onlinetext_editor][format]", save, "online text must be re-sent with files")

    def test_submit_checks_limits_before_sending(self):
        big = Path(self.tmp.name) / "big.pdf"
        big.write_bytes(b"x" * (2 * 1024 * 1024))
        rc, out, err, calls = self.calls_during("submit", 106, "--file", big, writes=True)
        self.assertEqual(rc, 1)
        self.assertIn("larger than the limit", err)
        rc, out, err, calls = self.calls_during("submit", 107, "--final", writes=True)
        self.assertEqual(rc, 1)
        self.assertFalse(WRITES.intersection(calls))

    def test_other_writes_preview_then_send(self):
        for cmd, fn in ((["choose", 109, "trees"], "mod_choice_submit_choice_response"),
                        (["post", 100, "--subject", "Hi", "--message", "Hello all"], "mod_forum_add_discussion"),
                        (["reply", 770, "--message", "Thanks"], "mod_forum_add_discussion_post"),
                        (["complete", 103], "core_completion_update_activity_completion_status_manually")):
            with self.subTest(cmd=cmd):
                rc, out, err, calls = self.calls_during(*cmd, writes=True)
                self.assertEqual(rc, 0, err)
                self.assertNotIn(fn, calls)
                code = re.search(r"Confirmation code: ([0-9a-f]{8})", out).group(1)
                rc, out, err, calls = self.calls_during(*cmd, "--confirm", code, writes=True)
                self.assertEqual(rc, 0, err)
                self.assertEqual([c for c in calls if c in WRITES], [fn])

    def test_login_needs_a_terminal(self):
        rc, out, err = self.run_cli("login", self.fake.url, "--password")
        self.assertEqual(rc, 1)
        self.assertIn("interactive terminal", err)

    def test_login_with_token_file_and_sites(self):
        home = Path(self.tmp.name) / "login-home"
        tf = Path(self.tmp.name) / "tok"
        tf.write_text(TOKEN + "\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith("MOODLE_")}
        env.update(MOODLE_SKILL_HOME=str(home), PYTHONIOENCODING="utf-8")

        def run(*a):
            return subprocess.run([sys.executable, str(SCRIPT), *map(str, a)], env=env, capture_output=True, text=True,
                                  encoding="utf-8", stdin=subprocess.DEVNULL, timeout=60)

        p = run("login", self.fake.url, "--token-file", tf)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Logged in", p.stdout)
        p = run("status", "--json")
        self.assertEqual(json.loads(p.stdout)["username"], "student")
        p = run("sites", "--json")
        self.assertEqual(len(json.loads(p.stdout)["sites"]), 1)
        p = run("writes", "on")
        self.assertEqual(p.returncode, 1)
        self.assertIn("interactive terminal", p.stderr)
        p = run("logout")
        self.assertEqual(p.returncode, 0)
        self.assertFalse(list((home / "tokens").glob("*.token")))
        p = run("status")
        self.assertEqual(p.returncode, 1)
        self.assertIn("log in", p.stderr)


if __name__ == "__main__":
    unittest.main()
