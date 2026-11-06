# eportal-moodle-skill

Ask your AI agent *"what do I still have to hand in this week?"* and it answers from your
Moodle. It sees deadlines, your submission status, assignment briefs, lecture materials,
announcements, forums, grades and the calendar, through the web service the official Moodle app
uses.

It works with any Moodle site from 3.9 to 5.x. It started on
[PWr ePortal](https://eportal.pwr.edu.pl) and was tested there.

It is an [Agent Skill](https://agentskills.io): a `SKILL.md` that tells the agent how and when to
use it, plus one Python script with no dependencies. The script also works on its own, as a
command line tool.

## What it is good for

- **One list of what is due.** Moodle's own timeline across all courses, with your real status
  in each item: *to do*, *draft, not submitted*, *overdue*, *submitted, graded 8/10*. No more
  clicking through every course.
- **What changed since last week:** new files, edited assignments, grades, announcements.
- **Reading without the browser:** an assignment's brief, the teacher's attachments, your
  submission and their feedback; page and book text; forum threads.
- **Study material on disk.** Download a course or a single section of it, with the files sorted
  into section folders, ready for the agent to summarise, quiz you on, or turn into exam notes.
- **An offline mirror.** `sync` writes one Markdown note per course (deadlines, announcements,
  materials with their texts, grades), a `Deadlines.md` across all courses, and the files. Re-run
  it whenever you like: it never overwrites your own files or notes. It works well as an
  [Obsidian](https://obsidian.md) vault (`--obsidian`).
- **Optional writes, with a person in the loop.** Submit an assignment, post or reply in a forum,
  answer a choice, or tick an activity done. These are off until you enable them yourself, and
  every write is previewed and needs a confirmation code (see [Safety](#safety)).

## Install

Use any tool that installs Agent Skills from GitHub, for example:

```bash
npx skills add dawidlinek/eportal-moodle-skill
```

Or copy the [`skills/moodle`](skills/moodle) folder into the folder where your agent loads skills
from. You need Python 3.9 or newer and nothing else.

## Log in once, yourself

Login asks for a password or a browser token, so you run it in your own terminal, not through
the agent:

```bash
python3 skills/moodle/scripts/moodle.py login https://your.moodle.site
```

It asks the site how the Moodle app signs in and picks the method:

- **Username and password** on normal Moodle sites. The password is used once and never stored.
- **Single sign-on** (university accounts, Google, Microsoft…). You log in in your browser,
  open one address with the developer tools open, and paste back the
  `moodlemobile://token=…` address that Moodle answers with. It takes about two minutes;
  [setup.md](skills/moodle/references/setup.md) has the steps.

```text
$ python3 moodle.py login https://eportal.pwr.edu.pl
Found ePortal PWr at https://eportal.pwr.edu.pl
Log in through the browser (single sign-on): …
Paste the moodlemobile://token=… address (hidden):
Logged in to ePortal PWr (Moodle 4.5.4) as …. Saved as 'eportal.pwr.edu.pl'.
```

Then ask your agent things like:

- *What's due this week, and what's overdue?*
- *Summarise the slides from week 3 of databases.*
- *What did the teachers announce since Monday?*
- *What feedback did I get on Etap 3?*
- *Mirror all my courses into ~/Studia.*

## What it looks like

```text
$ moodle.py todo
# To do (overdue up to 14 days, due in the next 30 days) · Moodle IT (disposable test site) · 2026-11-06 20:17

| Due | Course | Activity | Status | cmid |
|---|---|---|---|---|
| 2026-11-04 20:17 (2 days ago) | Testing 101 | Lab report 0 (assign) | overdue, not submitted | 5 |
| 2026-11-09 20:17 (in 3 days) | Testing 101 | Essay 1 (assign) | to do | 9 |
| 2026-11-11 20:17 (in 5 days) | Testing 101 | Quiz 1 (quiz) | to do | 12 |
| 2026-11-12 20:17 (in 6 days) | Data Structures (Lab) | Linked lists (assign) | to do | 17 |
| 2026-11-16 20:17 (in 10 days) | Testing 101 | Quick note (assign) | to do | 10 |

Details: `moodle.py assignment <cmid>` for assignments, `moodle.py show <cmid>` for anything else.
```

Every command prints Markdown, or JSON with `--json`:

| | |
|---|---|
| `status`, `courses`, `todo`, `calendar` | the state of things |
| `course`, `show`, `assignment`, `forum`, `news`, `grades`, `updates`, `notifications` | details |
| `download`, `sync` | files and the offline mirror |
| `call` | any other read-only web service function, as raw JSON |
| `submit`, `post`, `reply`, `choose`, `complete` | writes, opt-in and previewed |

The [command reference](skills/moodle/references/commands.md) has every option.

## Safety

A Moodle token can do anything you can do in the app, so the tool is careful with it.

- **Read-only by default.** All reads pass a guard that refuses any function that is not a pure
  read. That includes the `…_view_…` functions, which would mark activities as viewed or
  complete. `call` goes through the same guard.
- **Writes need three things.** First, you enable them per site, by typing the site's name at an
  interactive terminal; agents cannot do that. Second, a preview: the command shows exactly what
  it would send and sends nothing. Third, a confirmation code that matches that exact action,
  including a hash of every file. If anything changes after the preview, the code no longer
  works. The skill tells the agent to show you the preview and wait for your yes.
- **The token stays put.** It is stored in `~/.config/moodle-skill/tokens/`, readable only by
  you. It is never printed, never written into notes or links, and redacted from errors and
  JSON. After an SSO login, Moodle's extra *private token* is thrown away. `logout` deletes it,
  and the reference explains how to reset it on the site.
- **Course content is treated as untrusted.** Teachers and other students write it. The output
  marks such text as information, not instructions, and the skill tells the agent never to act
  on instructions found in it. One of the tests plants such an instruction in a forum post.
- **It only talks to your Moodle.** No telemetry, no third-party services, no dependencies.
- **Your files are safe.** `sync` and `download` keep a manifest and only ever replace what they
  wrote. Your own notes, annotated PDFs and edited notes are kept. Names coming from Moodle are
  sanitised, so a file can never land outside the target folder.

Reading a course updates your *last access* time in Moodle, just as opening it in the app does.

## Tests

```bash
python3 -m unittest discover tests     # unit tests and a fake Moodle; any OS, Python 3.9+
```

- [`tests/test_moodle.py`](tests/test_moodle.py) has unit tests (HTML to Markdown, file names,
  SSO token decoding and signatures, the read-only guard against 60+ real write functions,
  confirmation codes), plus every command run against a [fake Moodle](tests/fake_moodle.py).
  The CLI tests check which functions each command called, that no read command writes, that
  the token never appears in output or files, that re-syncs are idempotent and keep your edits,
  and that a write cannot be sent without the matching code.
- [`tests/integration/`](tests/integration) builds a throwaway Moodle 5.0 in Docker, seeded with
  fictional courses. `run_tests.py` drives the real logins through a terminal (password, and SSO
  through `launch.php`), runs every command, and checks every write from the teacher's side.
- It was also run read-only against PWr ePortal (Moodle 4.5.4, single sign-on). Every read
  command and a full `sync` (8 courses, 24 files) worked, the second sync changed nothing, and no
  output contained the token. Compared with an earlier ePortal-only script on the same data, it
  found the same 25 activities with the same due dates. The only difference is deliberate: two
  assignments that were graded without an online submission now count as done.

CI runs the first set on Linux, macOS and Windows.

## License

[MIT](LICENSE)
