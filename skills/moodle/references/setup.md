# Setting up a Moodle site

The user does this once per site, in their own terminal. Run without an agent in between,
because it asks for secrets.

```bash
python3 scripts/moodle.py login https://moodle.example.edu
```

`login` first asks the site, without logging in, how the Moodle app is meant to sign in. Then it
picks the method or asks the user to choose:

| The site | Method | What the user does |
|---|---|---|
| Normal Moodle accounts | `--password` | Types their username and password. The password is sent once to `login/token.php` and never stored. |
| Single sign-on (university account, Google, Microsoft, SAML, CAS…) | `--sso` | Logs in in the browser and copies one address back (steps below). |
| Already has a token | `--token` or `--token-file PATH` | Pastes the token, or points at a file holding it. |

At the end, `login` checks the token against the site and saves it. It says who is logged in.

## Single sign-on, step by step

Password login cannot work for an account that only signs in through SSO. Instead, `login --sso`
asks Moodle for the same token the official app receives after a browser login:

1. Log in to the site in Chrome, Edge or Firefox as usual.
2. Open the developer tools (F12, or Cmd+Option+I on a Mac) and choose the **Network** tab. Tick
   **Preserve log** (Chrome or Edge), or **Persist Logs** in the gear menu (Firefox).
3. In the same tab, open the address that `login --sso` printed. It looks like
   `https://<site>/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=…&urlscheme=moodlemobile`.
   The page will not load, or the browser offers to open an app. Cancel that; it is expected.
4. In the Network list, click the `launch.php` request and find **Location** under its
   **Response Headers**. Copy the whole value, which starts with `moodlemobile://token=`.
5. Paste it at the prompt. The input is hidden.

`login` decodes the address and checks its signature. The signature is
`md5(site address + passport)`, so it proves the token came from this request on this site. The
private token that may follow the token is discarded, never stored.

### Example: PWr ePortal

[ePortal](https://eportal.pwr.edu.pl) at Wrocław University of Science and Technology is Moodle
4.5. Logins go through USOS/AD (OpenID Connect), so a password login is impossible.

```bash
python3 scripts/moodle.py login https://eportal.pwr.edu.pl
```

The site reports browser login, so `login` goes straight to the SSO steps. Do them in a browser
where you are already logged in to ePortal. Afterwards, `status` shows your name and
`Moodle 4.5.x`.

## Problems

| Symptom | Fix |
|---|---|
| No `launch.php` in the Network list | Tick *Preserve log* first, then open the address again. |
| "has the Moodle app turned off" | The site disabled mobile web services. Only its administrators can change that. |
| `invalidlogin` on a university site | The account uses SSO. Run `login --sso`. |
| "issued for a different request" | The pasted address came from an older attempt. It still works if the site accepts it, but redoing step 3 is cleaner. |
| `invalidtoken` later on | The token expired or was reset. Run `login` again. |
| "only runs in an interactive terminal" | An agent tried to run `login`. The user must run it. |
| `CERTIFICATE_VERIFY_FAILED` / "certificate check failed" | This Python has no CA certificates. That is common with Python installed by uv, or from python.org on macOS; curl and `/usr/bin/python3` still work. `moodle.py` falls back to `certifi` or the system bundle by itself; if that still fails, `pip install certifi`, or put `export SSL_CERT_FILE=/etc/ssl/cert.pem` in your shell profile (macOS). Never turn verification off. |

## Several sites

Each `login` adds a site. The first one becomes the default; `login … --default` changes that.
Pick a site per command with `--site <name>`, which also accepts part of the address. `sites`
lists them all.

## Where things are stored

| What | Where |
|---|---|
| Settings | `~/.config/moodle-skill/config.json` (`$XDG_CONFIG_HOME` is respected) |
| Tokens | `~/.config/moodle-skill/tokens/<site>.token`, readable only by the user (mode 600) |
| Override both | the environment variable `MOODLE_SKILL_HOME=/some/dir` |

## Without a config, for scripts and servers

Set `MOODLE_URL` together with `MOODLE_TOKEN` or `MOODLE_TOKEN_FILE`, and every command uses that
site:

```bash
MOODLE_URL=https://moodle.example.edu MOODLE_TOKEN_FILE=~/.secrets/moodle python3 scripts/moodle.py todo
```

`MOODLE_ALLOW_WRITES=1` enables writes for such a site. It exists for automated tests against a
throwaway Moodle, and an agent must never set it.

## Revoking access

`logout` deletes the token from this computer. The token stays valid on the site until it is
reset there: **Preferences → Security keys** (`/user/managetoken.php`), then reset the key of the
*Moodle mobile web service*. Logging out of the official app does not reset it either.

## Notes

- On Windows, use `python` instead of `python3`. For `--tz` time zones, run `pip install tzdata`
  once; without `--tz` the computer's own time zone is used.
- A token can do everything the user can do in the app. That is why `moodle.py` only reads
  unless writes are enabled, and why each write needs a confirmed preview.
