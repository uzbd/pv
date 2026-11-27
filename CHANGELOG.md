# Changelog

## 2.3.0 — Saved Messages mobile-first redesign
- Added a Telegram-inspired Saved Messages chat interface with search, send, edit, delete, date separators and paged history.
- Added separate device-local Dashboard and Chat size controls.
- Set the UI font stack to native Android/browser system fonts and tuned touch targets, viewport safe areas and mobile chat sizing.
- Replaced browser-collected GitHub PAT first-run verification with a separate server-side `VAULT_SETUP_KEY`.
- Added minimum setup-key length validation and updated first-run security documentation.
- Kept chat assets CSS-only and avoided external font/CDN requests.


## 2.2.1 — Render frontend build fix
- Replaced the unavailable `Github` export from `lucide-react` with an icon that exists in the installed icon package.
- Added Vite client and CSS module declarations to resolve TypeScript 7's side-effect stylesheet import error.
- Updated frontend package and visible application version to 2.2.1.


## 2.2.0 — Security hardening
- Added GitHub PAT ownership verification to prevent first-visitor workspace takeover.
- Increased first-run and password-change minimum length to 16 characters.
- Added server-side active-session allowlist; signed cookies alone no longer grant access.
- Added server-side session revocation on logout and 24-hour session lifetime.
- Kept CSRF protection, login throttling, secure cookie settings and security headers.
- Added tests for invalid/valid bootstrap PAT and password setup.


## 2.1.0 — One-click GitHub-first deployment

- Simplified the Render Blueprint so its only manually prompted values are `GITHUB_TOKEN`, `GITHUB_OWNER`, and `GITHUB_REPO`.
- Render generates the session `SECRET_KEY` automatically and supplies production defaults for the remaining settings.
- Removed the mandatory `APP_PASSWORD` deployment variable. First visit now uses an in-browser setup wizard when GitHub storage is configured.
- The initial workspace password is stored only as a salted PBKDF2-SHA256 verifier in `.personal-vault-web/auth.json` in the configured private GitHub repository.
- Added first-run password change support in Settings → Security.
- Set Render Blueprint auto-deploy to manual so deployments are controlled from the Render dashboard.
- Updated deployment documentation for the exact three-variable setup and fine-grained GitHub PAT permissions.

## 2.0.0 — Modern React UI

- Replaced the legacy server-rendered interface with a React 19.3 + TypeScript single-page application.
- Upgraded the UI toolchain to Vite 8.4 and Tailwind CSS 4.3.
- Added reusable shadcn-inspired UI primitives, Lucide icons and TanStack Query caching.
- Added a refined, responsive workspace with collapsible sidebar, dashboard, note library, trash, global search, keyboard shortcut, theme and density preferences.
- Added a JSON API secured by the existing signed session cookie and CSRF token.
- Retained the FastAPI backend and the exact GitHub / Google Drive storage engine and JSONL record format.
- Preserved Telegram JSON import, Vault JSON / JSONL import, merge/edit deduplication, JSON / JSONL / CSV export and backup retry. Every action is now available through modern UI controls; no manual Bot commands are required.
- Added a multi-stage Docker build: Node frontend assets are bundled and served from FastAPI, so hosting needs only one web service.

## 1.0.0 — Initial website

- Password-protected FastAPI website with message library, import/export, backup and three storage modes.
