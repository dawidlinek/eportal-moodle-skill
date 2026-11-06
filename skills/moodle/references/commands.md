# Command reference

`moodle.py <command> --help` prints the same options. These options work with every command,
before or after its name:

| Option | Effect |
|---|---|
| `--site NAME` | Which configured site to use (part of the address is enough). |
| `--json` | Print JSON instead of Markdown. Tokens and private keys are always redacted. |
| `--tz Europe/Warsaw` | Time zone for dates. The default is the computer's. |
| `--debug` | Show a traceback on unexpected errors, with secrets still redacted. |

Wherever an id is expected, you can also paste a Moodle link: `course/view.php?id=…`,
`mod/…/view.php?id=…`, or `discuss.php?d=…#p…`.

## Setup

| Command | What it does |
|---|---|
| `login [URL] [--sso \| --password \| --token \| --token-file PATH] [--default]` | Sets up a site. Interactive except with `--token-file`. See [setup.md](setup.md). |
| `logout` | Deletes the site's token from this computer and says how to reset it on the site. |
| `sites` | Lists the configured sites, the default, and whether writes are on. |
| `status` | Checks the token and shows the site, the Moodle version, the user, and what this site does not offer. |
| `writes on \| off \| status` | Switches write commands for the site. `on` needs a person at a terminal. |

## Reading

| Command | Options | Output |
|---|---|---|
| `courses` | `--which inprogress\|past\|future\|all` | Course id, name, short name, progress, end date. |
| `todo` | `--days 30`, `--overdue 14`, `--course ID`, `--all` | Moodle's timeline (things that still need you), with your real status in each assignment, quiz, choice and feedback. `--all` lists every such activity in your courses, submitted ones included. |
| `calendar` | `--days 14`, `--past N`, `--course ID`, `--which` | Course, group, user and site events: exams, classes, deadlines. |
| `course ID` | `--section N`, `--full` | Sections and activities with type, dates, status, files and completion, plus the cmid of each. |
| `show CMID` | `--full` | One activity: page text, book chapters, link target, quiz settings and your attempts, choice options and your answer, files, dates, completion. Assignments and forums go to the commands below. |
| `assignment CMID` | | The brief, the teacher's attachments, what you can submit and the limits, due and cut-off dates, extensions, your submission (files and text), and grade and feedback. |
| `grades [COURSE]` | | Without a course: the total in each course. With one: each grade item with range, percentage and feedback. |
| `news` | `--since 30d`, `--limit 10`, `--full`, `--course`, `--which` | Posts in the courses' announcement forums. |
| `forum CMID` | `--discussion ID`, `--limit 20` | Discussions with their ids, or every post in one discussion, with attachments. |
| `updates` | `--since 7d`, `--course`, `--which` | Activities that changed since the given time, and how: files, settings, grades, new posts, your submission. |
| `notifications` | `--limit 20`, `--unread`, `--full` | Your Moodle notifications. They are never marked as read. |
| `call FUNCTION [key=value …]` | | Raw JSON from any read-only web service function. PHP-style array keys work: `courseids[0]=12`. |

`--since` takes `30m`, `48h`, `7d`, `2w`, or a date such as `2026-10-01`.

## Files

| Command | Options |
|---|---|
| `download COURSE` | `--out DIR` (default: the current folder), `--section N`, `--activity CMID`, `--max-size 200` (MB), `--ext pdf --ext pptx`, `--folder-name "{shortname}"`, `--dry-run` |
| `sync` | `--out DIR` (required), `--no-files`, `--max-size`, `--ext`, `--folder-name`, `--prune`, `--obsidian`, `--dry-run`, `--course ID` (repeatable), `--which` |

Both commands lay files out the same way:

```
DIR/
  Deadlines.md                 sync only: every deadline across courses, sorted
  moodle-index.json            sync only: courses and items as JSON
  <Course name>/
    <Course name>.md           sync only: deadlines, announcements, materials (with page and
                               book text, briefs, feedback), grades
    01 Week 1/slides.pdf       files, in section folders
    01 Week 1/Lab files/…      folders keep their subfolders
    02 Week 2/Essay 1/guide.pdf   an assignment's attachments
    .moodle-sync.json          what sync wrote, used for safe re-runs
```

Re-runs are safe:

- A file is downloaded again only if Moodle's copy changed (by size or time).
- A file that is in the folder but was not written by sync is never touched.
- If you changed a downloaded file and Moodle's copy changed too, yours is kept as
  `name (your copy DATE).ext`.
- If you edited a generated note, your version is kept as `name (your edits DATE).md`.
- A file that was removed from Moodle is kept, and from then on it is yours. With `--prune`, it
  is deleted instead, unless you changed it.
- Files larger than `--max-size` are listed but not downloaded.

`--folder-name` takes `{fullname}` (the default), `{shortname}` and `{id}`. Characters that are
invalid on any operating system, or in wikilinks, become `_`.

## Writing (opt-in, previewed)

| Command | Options |
|---|---|
| `submit CMID` | `--file PATH` (repeatable), `--text TEXT` or `--text-file PATH`, `--final`, `--force`, `--html`, `--confirm CODE` |
| `post FORUM_CMID` | `--subject`, `--message` or `--message-file`, `--group ID`, `--html`, `--confirm CODE` |
| `reply POST_ID` | `--message` or `--message-file`, `--subject`, `--html`, `--confirm CODE` |
| `choose CMID OPTION…` | `--confirm CODE` |
| `complete CMID` | `--undo`, `--confirm CODE` |

[writes.md](writes.md) describes what each one does and the confirmation protocol.

## Exit codes

`0` on success, and also when a preview was printed but nothing was sent. `1` on an error,
including a refused write. `2` on a usage error. `130` on interrupt. Errors go to stderr as
`error: …`.
