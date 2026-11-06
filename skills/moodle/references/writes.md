# Writes

Writes reach real people: teachers see submissions, and everyone in a course sees forum posts.
Most of them cannot be taken back. So `moodle.py` gates every write three times:

1. **Off by default, per site.** Only a person at an interactive terminal can run `writes on`,
   and they must type the site's name to confirm. Agents usually run without a terminal, so they
   cannot switch it on by accident.
2. **Preview first.** Without `--confirm`, a write command checks everything it can, prints what
   it would do and a confirmation code, and sends nothing.
3. **A code for that exact action.** `--confirm CODE` sends only if the code matches a hash of
   the site, the user, the action and its content, including the SHA-256 of each file. If
   anything changed since the preview, the code no longer matches and nothing is sent.

## The protocol for agents

1. Run the write command without `--confirm`.
2. Show the user the whole preview. Do not summarise away the warnings.
3. Ask whether to send exactly that. Wait for an explicit yes. Approval to "submit my essay"
   given earlier does not cover a preview you have not shown.
4. Run the identical command with `--confirm <code>` and report the result line.

If the user wants a change, change the command and preview again. Never reuse a code for
another action. If writes are disabled, tell the user they can run `writes on` themselves. Do not
look for another way.

## `submit`: assignments

```bash
moodle.py submit <cmid> --file report.pdf [--file data.zip]
moodle.py submit <cmid> --text "…" | --text-file answer.md
moodle.py submit <cmid> --final          # submit the draft for grading
```

- **Drafts.** If the assignment wants a final click, a save stays a draft that the teacher does
  not see as submitted. Add `--final` (in the same command, or later) to submit it for grading.
  After that, the submission usually cannot be changed.
- **No drafts.** Some assignments have none, and saving submits immediately. The preview says
  which kind this one is. `--final` is refused there, because it is not needed.
- **Files replace files.** Uploading sends the new set; files submitted before are dropped. The
  preview lists them.
- **Text and files are independent.** A files-only save keeps the current online text, and a
  text-only save keeps the current files. Moodle needs the text re-sent on every save, so
  `moodle.py` re-sends it unchanged. Images embedded in that text may not survive; the preview
  warns about it.
- **Checked before sending:** accepted submission types, number of files, size limit, file types
  (a warning only, since Moodle also accepts type groups), the word limit, and whether Moodle
  still lets you edit. `--force` sends despite the warnings it can override.
- Plain text is sent as HTML paragraphs. `--html` sends the text as it is.
- If the assignment requires a submission statement, `--final` accepts it, and the preview shows
  its text.

## `post` and `reply`: forums

```bash
moodle.py post <forum cmid> --subject "…" --message "…" [--group <id>]
moodle.py reply <post id> --message "…" [--subject "…"]
```

Everyone who can see the forum sees the post, and subscribers get it by email, usually after the
site's editing window (often 30 minutes). Students usually cannot post in the Announcements
forum; `post` checks that first. `reply` takes a post id, or a `discuss.php` link ending in
`#p<id>`, and the preview quotes the post being answered.

## `choose`: choice activities

```bash
moodle.py choose <cmid> "Graph search"      # option text, part of it, or the option id
```

The preview says whether the answer can be changed later. Full options and choices that cannot
be changed are refused.

## `complete`: manual completion

```bash
moodle.py complete <cmid> [--undo]
```

This works only for activities with manual completion. Teachers can see completion state.

## What there is no command for

Starting or answering quiz attempts, sending messages, deleting anything, enrolling, and marking
notifications read. These are out of scope on purpose, and `call` refuses them too.
