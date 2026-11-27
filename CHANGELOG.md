# Changelog

## 2.4.1
- Increased default chat text sizing and improved narrow-screen fit.
- Tightened secondary-page control and typography sizing while keeping descriptions hidden.
- Removed the misleading always-green storage status dot.
- Validate unsupported message categories consistently before querying storage.


## 2.4.0 — Mockup-matched mobile Saved Messages UI
- Rebuilt the primary Saved Messages screen as a full-screen dark-blue mobile interface with category tabs, search, message bubbles, composer, emoji picker and bottom Text Size / Theme / Settings controls.
- Made Saved Messages the post-login landing screen; Dashboard, Library, Trash and Settings remain accessible from the navigation drawer.
- Removed success toasts and secondary explanatory copy while preserving error feedback.
- Improved scroll-to-bottom after sending, scroll behavior during older-page loading, and `/` / Ctrl+K search focus.
- Added the Links category to the messages API and fixed `only_deleted=true` so Trash queries include deleted records even when `include_deleted` is omitted.
- Media and Files tabs remain visible but disabled because the current text-only storage schema does not store attachments.


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
