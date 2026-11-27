# Personal Vault Web 2.5.0

A lightweight, mobile-first chat page for saving plain-text notes and messages. The home page is only the chat room. Its Settings sheet contains exactly three controls: **Text Scaling**, **Export**, and **Import**.

- AMOLED black background (`#000000`) with grayscale controls and message bubbles.
- All UI text follows one Text Scaling setting (80%–150%); the preference is saved in the browser.
- Messages appear immediately using an optimistic bubble while the server saves them.
- The page loads recent messages first and automatically loads older messages when you scroll to the top.
- Export downloads one JSONL file compatible with the Telegram Personal Vault Bot's shard format.
- Import accepts Telegram Desktop Saved Messages JSON and Personal Vault JSON/JSONL exports.
- No sidebar, dashboard, search panel, theme switcher, attachment controls, third-party fonts, analytics, or UI framework is included.

## Storage modes

The existing backend and data format are retained. Configure **one** backend or **both**:

| Mode | GitHub variables | Google Drive variables |
|---|---|---|
| GitHub only | `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` | Leave both blank |
| Google Drive only | Leave all three blank | `GOOGLE_OAUTH_CLIENT_B64`, `GOOGLE_OAUTH_TOKEN_B64` |
| Both | Configure all three | Configure both |

`GITHUB_BRANCH` defaults to `main`; `VAULT_DATA_DIR` defaults to `vault-data`. Keep the same branch and data directory as the Telegram bot to reuse the same vault. The Drive adapter uses the existing `Telegram Personal Vault` folder and the same `vaultPath` JSONL objects as the bot.

**Dual mode behavior:** GitHub is the primary store and Google Drive is its mirror. New writes are committed to GitHub first; Drive mirror failures are tracked and retried by the existing storage layer. In Drive-only mode, Drive is the primary store. The app refuses to start with no valid backend or a partial set of credentials.

### Google Drive OAuth setup

Use the provided helper on your local computer after downloading a Desktop OAuth client JSON from Google Cloud:

```bash
python -m pip install -r requirements.txt
python scripts/google_auth.py --credentials credentials.json
```

Complete Google's consent screen. The script prints `GOOGLE_OAUTH_CLIENT_B64` and `GOOGLE_OAUTH_TOKEN_B64`. Add both values as private environment variables in the hosting dashboard. Never put them in source code or share them in chat. You can optionally set `GOOGLE_DRIVE_FOLDER_ID` to use an existing folder; otherwise the app finds or creates `Telegram Personal Vault`.

For a **Drive-only** installation, also set `APP_PASSWORD` to a strong password of at least 16 characters. Because no GitHub repository is available to store the website password verifier, this password is read from the hosting environment. For GitHub or dual mode, leave `APP_PASSWORD` blank and complete the one-time setup using `VAULT_SETUP_KEY`; the salted password verifier is stored in the private GitHub data repository.

### GitHub setup

Create a private data repository and a fine-grained GitHub token limited to that repository, with **Contents: Read and write** permission. Set all three GitHub variables. The website only uses the token server-side.

Do not point the website at a different `VAULT_DATA_DIR` if you want to reuse the Telegram bot's existing records. The default is `vault-data` in both projects.

## Render deployment

The included `render.yaml` is the simple GitHub-first Blueprint. It asks for the GitHub token, owner, repository, and one-time setup key; Render generates `SECRET_KEY`.

1. Upload this project to a GitHub repository.
2. In Render, create a Blueprint from that source repository.
3. Supply the GitHub data-repository values and a random `VAULT_SETUP_KEY` of at least 32 characters.
4. Deploy, open the generated site, enter the setup key, and create a password of at least 16 characters.
5. After setup succeeds, remove `VAULT_SETUP_KEY` from Render's environment and redeploy.

To use **both** stores on Render, add `GOOGLE_OAUTH_CLIENT_B64` and `GOOGLE_OAUTH_TOKEN_B64` in the service Environment settings. GitHub remains primary and Drive becomes the mirror.

To use **Drive only** on Render, set the two Google OAuth variables and `APP_PASSWORD` (at least 16 characters), then remove/clear `GITHUB_TOKEN`, `GITHUB_OWNER`, and `GITHUB_REPO` together. Do not leave only part of the GitHub group configured. The service must have a complete valid storage group before it can start.

The local filesystem is not used for persistent vault records. Render Free services may sleep when idle and the next request may have a cold start; instant always-on hosting is not guaranteed.

## Local development

Copy `.env.example` to `.env`, configure one storage mode, then run:

```bash
cd frontend
npm install
npm run build
cd ..
python -m pip install -r requirements.txt
python -m app.main
```

Open `http://localhost:8000`. For local HTTP, set `COOKIE_SECURE=false`. Set a stable `SECRET_KEY` of at least 32 characters. GitHub/dual mode can use the one-time setup flow with `VAULT_SETUP_KEY`. Drive-only mode should use `APP_PASSWORD`.

## Existing data and compatibility

- The vault remains newline-delimited JSON (JSONL), partitioned by UTC date under `vault-data/YYYY/MM/DD/part-XXXX.jsonl`.
- Existing Telegram bot records are read without conversion when branch, repository, and data directory match.
- Import uses record IDs to merge rather than blindly replacing the complete vault. Existing records not present in an import are retained.
- Export is JSONL, which is the compact, lossless format used by both app storage adapters. Telegram Desktop JSON remains an accepted import format.
- The schema is text-only: message text, IDs, dates, edit/deletion metadata, hashtags, and links. The web UI does not claim to upload images, videos, documents, or voice messages.

**Concurrent writers:** the Telegram bot and website share the same shard files. Avoid sending or editing from both services at the exact same time; simultaneous commits to one GitHub shard may conflict. For a safe migration, stop the bot while testing website writes, then restart only after the test is complete.

## Security and limitations

- GitHub and Google OAuth secrets remain server-side and are never returned to the browser.
- State-changing requests use the existing session CSRF token.
- The website uses the existing password/session middleware and security headers.
- A deployment restart invalidates in-memory active sessions; users may need to sign in again.
- Google Drive API availability, OAuth consent, provider quotas, and hosting cold starts are external dependencies.
- The send bubble appears immediately, but final persistence still depends on the selected storage provider responding.

## Project layout

- `app/` — FastAPI authentication, JSONL storage adapters, APIs, and import/export.
- `frontend/` — small React + TypeScript + Vite chat interface.
- `scripts/google_auth.py` — local Google Drive OAuth token helper.
- `render.yaml` — GitHub-first Render Blueprint.
- `Dockerfile` — frontend build and Python runtime.
- `tests/` — backend storage, configuration, import, API, and deployment tests.
