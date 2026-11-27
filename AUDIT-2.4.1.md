# Personal Vault Web — 2.4.1 Audit Notes

## UI changes

- Reworked the Saved Messages screen to follow the supplied dark navy / blue mobile mockup: compact brand header, Chat / Media / Files / Links tabs, search, message bubbles, composer, emoji picker, and bottom Text Size / Theme / Settings dock.
- Made Saved Messages the post-login landing view. Dashboard, Library, Trash, and Settings remain available from the chat navigation drawer.
- Removed helper and descriptive copy from the visible dashboard, secondary pages, settings panels, and login screen. Kept actionable errors and validation messages visible.
- Removed success notifications for sending or editing chat notes. Saved messages appear directly in the thread; real errors remain visible.
- Increased the default chat scale to 120%, enlarged secondary-page controls, improved Android/system font fallbacks, and added narrow-screen rules for 320px-wide devices.
- Removed the always-green storage indicator from the navigation drawer because it did not reflect live provider state.
- Corrected the double safe-area padding between the mobile composer and bottom dock. Chat text scaling now also applies to the mobile composer.

## Feature and logic fixes

- Added the `kind=links` API filter used by the Links tab.
- Fixed `only_deleted=true` so Trash queries return deleted notes without requiring `include_deleted=true`.
- Validate unsupported `kind` values (`media`, `files`, and unknown values) consistently before reading storage.
- Fixed the `/` and Ctrl/Cmd+K search shortcut's JavaScript automatic-semicolon-insertion bug.
- Clear the file input after selection so selecting the same import file again triggers its change handler.
- Replaced the Dashboard's static storage-health label with provider/pending-sync-aware status.
- Clamped locally stored UI scale preferences to valid ranges so malformed browser values cannot collapse the interface.

## Verification performed

- Backend tests: **35 passed**.
- Python bytecode compilation: passed.
- TypeScript / TSX syntax transpilation: passed for all 6 source files.
- CSS parser: passed; 657 top-level rules parsed, including nested media/support rules.
- HTML, JSON, and YAML parsing: passed.
- API regression coverage includes Links filtering, deleted-only filtering, and unsupported category responses.
- ZIP integrity check is performed on the release archive after packaging.

## Verification limitation

The frontend dependency installation could not complete because the npm registry connection timed out in the build environment. As a result, a full `npm run build` / Vite production bundle and real-browser visual regression test were **not verified here**. The TypeScript check performed was syntax transpilation, not a complete dependency-aware typecheck. The Dockerfile still performs the full frontend build during deployment.

## Existing feature boundary

The current data schema stores text notes, hashtags, links, timestamps, and deletion state. It does not store media or file attachments. Media and Files therefore remain visible but disabled in the UI rather than acting like non-functional buttons. The composer paperclip opens Telegram archive import; it is not an attachment uploader.
