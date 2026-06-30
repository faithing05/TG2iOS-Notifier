# AGENTS.md

## Project Summary

This project is a Windows Telegram-to-iPhone notifier.

It has two parts:

1. Desktop app on `PyQt5` + `Telethon`
2. PWA files used on iPhone for iOS WebPush

High-level flow:

1. User authorizes a Telegram account in the desktop app
2. Desktop app listens for incoming private messages from contacts
3. Desktop app sends WebPush via `pywebpush`
4. iPhone PWA receives the push in `serviceworker.js`
5. iOS shows the notification on the lock screen

## Important Repos

There are effectively two code locations involved:

1. This repo: main source of truth for desktop code and PWA source files
2. Separate GitHub Pages repo: `faithing05/TG-notification`

Do not assume changing PWA files in this repo updates the live site.

After changing any PWA file, sync them to the site repo.

## Files That Matter Most

Desktop / Python:

- `desktop_app.py`: main PyQt5 GUI entry point
- `bot_core.py`: Telegram service, message handling, WebPush payload formatting
- `app_config.py`: config model, VAPID generation, config load/save, subscription validation
- `tg_to_ios_userbot.py`: console mode entry point

PWA / Website:

- `index.html`: PWA page shown on iPhone
- `frontend.js`: subscription flow in Safari/PWA
- `manifest.json`: PWA name, icon, install metadata
- `serviceworker.js`: push handling and notification display
- `telegram-icon.svg`: icon for PWA / push

Other:

- `README.md`: user-facing setup instructions
- `deploy_pwa.ps1`: syncs PWA files into the separate Pages repo
- `deploy_pwa.bat`: Windows wrapper for the sync script

## Notification Behavior

Current intended notification format:

- notification title: sender name
- notification body: message text
- app/PWA name: `Telegram`
- icon: `telegram-icon.svg`

Relevant implementation:

- `bot_core.py` builds the WebPush payload
- `serviceworker.js` decides what iOS actually displays

If notification text looks wrong on iPhone, inspect both files.

## PWA Sync Rule

This is critical.

If you edit any of these files:

- `index.html`
- `frontend.js`
- `manifest.json`
- `serviceworker.js`
- `telegram-icon.svg`

you must sync them to the Pages repo, otherwise the live iPhone site stays stale.

Default local assumption:

- main repo: `F:\Desktop\tg2iOS`
- Pages repo clone: `F:\Desktop\TG-notification`

Use:

```bat
deploy_pwa.bat
```

Useful modes:

```bat
deploy_pwa.bat -DryRun
deploy_pwa.bat -NoCommit
deploy_pwa.bat -NoPush
deploy_pwa.bat -TargetRepoPath "F:\Desktop\TG-notification"
```

The live Pages repo is:

- `https://github.com/faithing05/TG-notification`

## Common Change Map

If the task is about Telegram auth, tray behavior, settings UI, QR login, logs:

- start with `desktop_app.py`
- then inspect `bot_core.py`

If the task is about notification text, sender name, message preview, icon:

- inspect `bot_core.py`
- inspect `serviceworker.js`
- possibly inspect `manifest.json`

If the task is about subscription JSON, VAPID keys, config persistence:

- inspect `app_config.py`
- inspect `frontend.js`

If the task is about the iPhone install experience or PWA title/icon:

- inspect `index.html`
- inspect `manifest.json`
- inspect `serviceworker.js`

## Behavior Constraints

- This app intentionally only forwards incoming private messages.
- It only forwards messages from contacts or mutual contacts.
- Config is stored under `%AppData%\TgIosNotifier\`.
- Telegram session is stored under `%AppData%\TgIosNotifier\session\`.
- There is migration logic for legacy app directories in `app_config.py`.

Do not casually break any of the above.

## Testing / Verification

For Python syntax:

```bash
python -m py_compile bot_core.py desktop_app.py tg_to_ios_userbot.py app_config.py
```

For service worker syntax:

```bash
node --check serviceworker.js
```

For PWA sync sanity check:

```bash
deploy_pwa.bat -DryRun
```

Manual end-to-end checks usually matter for these changes:

1. Update desktop code if payload format changed
2. Sync PWA files if site files changed
3. Re-open iPhone PWA
4. Sometimes remove and reinstall the PWA from Home Screen if manifest/icon/title changed
5. Send a test notification

## Known iOS / PWA Gotchas

- iOS WebPush works only when opened as a PWA from the Home Screen.
- iOS may cache manifest, service worker, title, and icon aggressively.
- If icon/title/name changes do not appear, remove the old PWA and install it again.
- Notification appearance can depend on both push payload and the installed PWA metadata.

## Editing Guidance For Future Agents

- Prefer minimal changes.
- Avoid introducing new abstraction unless it clearly reduces duplication.
- Keep notification formatting logic easy to trace.
- When changing displayed notification text, do not fix only one side unless you are sure:
  both payload generation and service worker display may need updates.
- If PWA files were changed, mention explicitly that `deploy_pwa.bat` must be run.
- If desktop payload format changed, mention that the desktop app must be rebuilt/restarted.

## Do Not Forget

Before finishing a task, quickly check:

1. Did I change desktop Python only?
2. Did I change PWA files only?
3. Did I change both?
4. If PWA changed, did I run or at least mention `deploy_pwa.bat`?
5. If notification behavior changed, did I validate both `bot_core.py` and `serviceworker.js`?
