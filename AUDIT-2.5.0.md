# Personal Vault Web 2.5.0 — Audit

## Implemented

- The authenticated homepage now contains only the chat room, the Personal Vault title, and a top-right Settings control.
- The chat surface and message bubbles use a pure black / grayscale palette.
- Settings opens a bottom sheet with exactly three controls: Text Scaling, Export, and Import.
- Text Scaling is global (80%–150%, 5% increments), persisted in browser local storage, and applied to login and chat interface typography.
- Export downloads the existing JSONL vault format. Import accepts `.json` and `.jsonl` through the existing server-side merge endpoint.
- Message bubbles are rendered optimistically while the server persists the message; failures remove the temporary bubble and show an error.
- Recent history is fetched in 100-message pages; older pages load automatically at the top of the chat scroll area.
- No added CDN, remote font, analytics, icon library, Tailwind runtime, search UI, sidebar, dashboard, or media/file controls.
- The existing FastAPI auth, CSRF, GitHub store, Google Drive store, dual-store primary/mirror behavior, data paths, and JSONL schema were retained.

## Verification

- Backend tests: **35 passed**.
- Python compileall: passed.
- TypeScript/TSX syntax transpilation using the installed TypeScript compiler: passed for every active source file.
- CSS parse: passed.
- HTML, JSON, YAML, and version-file validation: passed.
- Archive integrity and SHA-256 validation: performed on the release files.

## Not verified in this environment

- `npm install` could not complete because the npm registry connection returned `EAI_AGAIN` / DNS resolution failure. Therefore `npm run build`, a dependency-aware TypeScript check, and the Vite production bundle were not executed here.
- No live GitHub API, Google Drive OAuth/API, Render deploy, Telegram bot, or real-browser/Android visual run was performed.
- The frontend build remains part of the supplied Dockerfile and will run during deployment when the registry is reachable.

## Operational note

Both website and bot use the same dated JSONL shard layout. Do not write from both services simultaneously: concurrent updates to the same GitHub shard can conflict. Stop the bot while verifying website writes.
