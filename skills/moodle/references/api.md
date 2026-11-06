# How it talks to Moodle

Everything goes through Moodle's web service for the official mobile app (`moodle_mobile_app`).
Each call is `POST <site>/webservice/rest/server.php` with `wstoken`, `wsfunction`,
`moodlewsrestformat=json`, and PHP-style parameters (`courseids[0]=12`). To download a file,
`token=` is appended to the file's `pluginfile.php` address. A site that works with the Moodle
app works with `moodle.py`.

## Functions per command

| Command | Web service functions |
|---|---|
| all | `core_webservice_get_site_info` (who you are, which functions the site offers) |
| `courses` | `core_course_get_enrolled_courses_by_timeline_classification`; older sites: `core_enrol_get_users_courses` |
| `todo` | `core_calendar_get_action_events_by_timesort` / `…_by_course`, then the activity lists below for your real status |
| activity status | `mod_assign_get_assignments`, `mod_assign_get_submission_status`, `mod_quiz_get_quizzes_by_courses`, `mod_quiz_get_user_attempts`, `mod_choice_get_choices_by_courses`, `mod_choice_get_choice_options`, `mod_feedback_get_feedbacks_by_courses`, `mod_feedback_get_feedback_access_information` |
| `course`, `show`, `download`, `sync` | `core_course_get_contents`, `core_course_get_course_module`, `mod_page_get_pages_by_courses`, `mod_quiz_get_user_best_grade` |
| `calendar` | `core_calendar_get_calendar_events` |
| `grades` | `gradereport_overview_get_course_grades`, `gradereport_user_get_grade_items` |
| `news`, `forum` | `mod_forum_get_forums_by_courses`, `mod_forum_get_forum_discussions` (older: `…_paginated`), `mod_forum_get_discussion_posts` (older: `mod_forum_get_forum_discussion_posts`) |
| `updates` | `core_course_get_updates_since` |
| `notifications` | `message_popup_get_popup_notifications` |
| `submit` | `webservice/upload.php`, `mod_assign_save_submission`, `mod_assign_submit_for_grading` |
| `post`, `reply` | `mod_forum_can_add_discussion`, `mod_forum_get_discussion_post`, `mod_forum_add_discussion`, `mod_forum_add_discussion_post` |
| `choose` | `mod_choice_submit_choice_response` |
| `complete` | `core_completion_get_activities_completion_status`, `core_completion_update_activity_completion_status_manually` |

If a site does not offer a function (because its admins restricted the app service, or the
Moodle version is old), the part that needs it is skipped with a warning and the rest still
works. `status` lists what is unavailable.

## The read-only guard

Every read goes through one function that refuses anything that is not a read:

- The name must contain the verb `get` or `search` after the component prefix
  (`mod_assign_get_…`).
- It is refused if, after the component, it also contains a word that implies a side effect:
  `view` (which marks an activity viewed or complete), `save`, `submit`, `update`, `delete`,
  `create`, `add`, `set`, `send`, `mark`, `start`, `launch`, `process`, `token`, `key`,
  `autologin`, `join`, and similar.
- A few `get` functions that change state anyway are refused by name. For example,
  `mod_quiz_get_attempt_data` can move an attempt in progress to another page.

Writes go through a second function. It accepts only the six functions behind the write
commands, and only during a confirmed preview. The tests check the guard against more than 60
real write functions, and check that no read command ever calls anything else.

## Versions

The script is built against the web service API of Moodle 3.9 to 5.x. Where newer functions are
missing, it falls back to older ones. It has been run against:

- Moodle 4.5.4 (PWr ePortal, single sign-on): every read command, read-only.
- Moodle 5.0.10 in Docker (`tests/integration/`): every command, including password and SSO
  login and every write.

## Raw calls

```bash
moodle.py call core_course_get_contents courseid=12
moodle.py call mod_assign_get_assignments 'courseids[0]=12' 'courseids[1]=13'
```

The output is JSON with tokens and private keys redacted. Only read functions are allowed. The
full list of functions is in the site's API documentation (`/admin/webservice/documentation.php`,
admins only) and in the Moodle developer docs.
