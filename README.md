# Personal Vault Web 2.3.0

**একটি আধুনিক, ব্যক্তিগত ও searchable knowledge workspace — Telegram Bot-এর পরিবর্তে সম্পূর্ণ ওয়েব UI।** কোনো Telegram command টাইপ করতে হবে না। Note, Search, Import, Export, Trash, Backup ও Security—সবকিছু ওয়েবসাইটের UI এবং Settings-এর ভেতর থেকে পরিচালিত হয়।

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

> Render-এ Deploy করার আগে GitHub-এ এই Source Repository upload করো এবং Render-কে সেটি access করার অনুমতি দাও। উপরের বাটনটি Render-এর Blueprint deployment খুলবে; Render যদি browser referrer থেকে source repo চিনতে না পারে, তাহলে এই Source Repository নির্বাচন করবে।

## একবার Deploy করার পর কী করতে হবে?

Render Blueprint-এর জন্য নিচের **৪টি Environment Variable** দিতে হবে:

| Variable | কী দিতে হবে |
|---|---|
| `VAULT_SETUP_KEY` | আলাদা, একবারের Setup Key (কমপক্ষে ৩২ অক্ষর) |
| `GITHUB_TOKEN` | GitHub Fine-grained Personal Access Token (PAT) |
| `GITHUB_OWNER` | GitHub username অথবা organization name |
| `GITHUB_REPO` | Vault data রাখার private repository name |

বাকি সবকিছু `render.yaml`-এ আগেই সেট করা আছে। `SECRET_KEY` Render নিজে generate করবে; `APP_PASSWORD`, Google credentials, database URL বা Redis প্রয়োজন নেই। `VAULT_SETUP_KEY`-এর জন্য আলাদা random value তৈরি করে Render Environment-এ রাখবে। Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Deploy শেষ হলে প্রথমবারের **Create your private workspace** Wizard-এ `VAULT_SETUP_KEY` দিয়ে ownership প্রমাণ করবে, তারপর কমপক্ষে ১৬ অক্ষরের Workspace Password তৈরি করবে। ওয়েবসাইট কখনো GitHub PAT চাইবে না; `GITHUB_TOKEN` কেবল Render server-side ব্যবহার করবে। Password-এর plaintext কোথাও রাখা হয় না; salted PBKDF2-SHA256 verifier তোমার private GitHub data repository-তে `.personal-vault-web/auth.json` ফাইলে থাকবে।

এই একবারের Setup Key verification জরুরি: প্রথমবারের password setup যদি সবার জন্য খোলা থাকত, তাহলে URL আগে পাওয়া যে কেউ নিজের password বসিয়ে তোমাকে Vault থেকে Lock Out করতে পারত। তাই আলাদা একটি দীর্ঘ random secret দিয়ে প্রথম setup অনুমোদিত হবে। Setup শেষ হওয়ার পর Render Environment থেকে `VAULT_SETUP_KEY` মুছে দেবে; এরপর Workspace Password দিয়েই login হবে।

**অর্থাৎ: Deploy → ৩টি GitHub value + ১টি random Setup Key → Deploy → Website-এ Setup Key দিয়ে ১৬+ character password তৈরি → Setup Key মুছে ব্যবহার শুরু।**

---

## What changed in 2.3.0

- Telegram-inspired Saved Messages chat with message bubbles, search, send/edit/delete, chronological date dividers and older-message pagination that retains scroll position.
- Mobile-first chat layout with safe-area support, a pinned composer and mobile-sized touch controls.
- Separate Dashboard and Chat interface/text size controls, persisted locally; Android/browser system UI fonts are the default.
- First-run setup no longer collects a GitHub PAT in the browser. It uses a separate one-time `VAULT_SETUP_KEY` and validates its minimum length.
- No external font, image, analytics or UI-CDN dependencies were added; the chat wallpaper is CSS-only.

## Build fix in 2.2.1

The frontend build fixes the two TypeScript errors reported by the previous Render build:
- Replaced the removed `Github` brand export from `lucide-react` with the supported `Database` icon for the GitHub storage provider.
- Added `frontend/src/vite-env.d.ts` with the Vite client reference and an explicit `*.css` module declaration so TypeScript 7 accepts the stylesheet side-effect import.

## 1. আগে GitHub প্রস্তুত করো

তোমার একটি GitHub repository দরকার যেখানে Vault-এর ডেটা রাখা হবে। দুইটি পথ আছে:

- **পুরোনো Telegram Bot-এর ডেটা চালিয়ে যেতে চাইলে:** আগের Bot যে GitHub repository, branch ও `vault-data` directory ব্যবহার করত, সেই repository-ই `GITHUB_OWNER` ও `GITHUB_REPO`-তে দেবে। এতে আগের JSONL ডেটা সরাসরি পড়া যাবে।
- **একেবারে নতুন Vault শুরু করলে:** একটি Private Repository তৈরি করো এবং `Add a README file` চালু রাখো, যাতে `main` branch তৈরি হয়।

Website Source Code যে repository-তে upload করবে, সেটি এবং Vault Data Repository একইও হতে পারে, আলাদাও হতে পারে। পুরোনো Bot-এর data reuse করতে চাইলে `GITHUB_REPO`-তে পুরোনো Bot-এর data repository দেবে।

### GitHub PAT তৈরি

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token:

1. Resource owner-এ সঠিক GitHub user/organization বেছে নাও।
2. Repository access-এ শুধু Vault Data Repository নির্বাচন করো।
3. Repository permissions-এ **Contents: Read and write** দাও।
4. Token তৈরি করে কপি করো। এটি `GITHUB_TOKEN`-এ দেবে।

এই permission দরকার, কারণ অ্যাপকে আগের JSONL পড়তে এবং নতুন/পরিবর্তিত JSONL ও password verifier লিখতে হয়। GitHub Contents API-তে read-এর জন্য Contents read এবং file create/update-এর জন্য Contents write লাগে।

**গুরুত্বপূর্ণ:** PAT কখনো Source Code, README, `.env` বা ZIP-এ লিখবে না। শুধু Render-এর secret field-এ দেবে। PAT-টি কেবল নির্দিষ্ট Private Repository-তে সীমাবদ্ধ রাখবে।

---

## 2. Source Repository-তে Upload

1. ZIP Extract করো।
2. ভেতরের সব ফাইল ও ফোল্ডার একটি GitHub repository-এর root-এ upload করো।
3. নিশ্চিত করো default branch `main` এবং root-এ `render.yaml` ও `Dockerfile` আছে।
4. Source Repository private হলে Render-এর GitHub App-কে এই repository access দাও। Public repository হলে অতিরিক্ত source access approval লাগবে না।

## 3. One-click Render Deployment

1. Source Repository-এর README থেকে **Deploy to Render** বাটনে চাপ দাও; অথবা Render Dashboard-এ **New → Blueprint** নির্বাচন করে Source Repository connect করো।
2. Render `render.yaml` detect করে `personal-vault-web` Web Service তৈরি করবে।
3. Environment Variable prompt-এ এই চারটি value বসাও:
   - `VAULT_SETUP_KEY` → random setup secret (কমপক্ষে ৩২ অক্ষর)
   - `GITHUB_TOKEN` → তোমার Fine-grained PAT
   - `GITHUB_OWNER` → GitHub username বা organization
   - `GITHUB_REPO` → Vault Data Repository-এর নাম (`.git` ছাড়া)
4. Blueprint review করে Apply/Deploy করো।
5. Deploy সম্পন্ন হলে Render-এর দেওয়া HTTPS URL খুলে `VAULT_SETUP_KEY` দিয়ে প্রথমবারের ownership verification করো, তারপর Workspace Password তৈরি করো। সফল হলে Render Environment থেকে `VAULT_SETUP_KEY` মুছে দাও।

Render Blueprint-এ আগে থেকেই configured:

- Docker runtime এবং Free Web Service plan
- `APP_ENV=production`, `COOKIE_SECURE=true`
- Session lifetime: ২৪ ঘণ্টা
- Stable `SECRET_KEY` automatic generation
- `GITHUB_BRANCH=main`, `VAULT_DATA_DIR=vault-data`
- Health check: `/health`
- Upload limit: ২৫ MB
- Render auto-deploy disabled; নতুন deployment Render Dashboard থেকে হাতে trigger করা যাবে

### Render source access বনাম data access

Render-এর GitHub App Source Repository clone/build করার জন্য ব্যবহৃত হয়। `GITHUB_TOKEN` Website-কে Vault Data Repository পড়তে/লিখতে দেয়। Source Repository ও Data Repository আলাদা হলে দুইটির access আলাদা করে অনুমোদন করতে হবে।

### Browser phishing / unsafe-site warning

এই Source Code-এ GitHub PAT browser-এ চাওয়া হয় না, third-party font/CDN/analytics নেই, এবং CSP, HTTPS-only secure cookies ও security headers ব্যবহার করা হয়। তবে Chrome Safe Browsing বা Microsoft SmartScreen-এর URL reputation তালিকা hosting provider-এর বাইরে নিয়ন্ত্রিত; নতুন/কম-পরিচিত domain বা আগের false-positive classification থাকলে code deploy করলেই warning সঙ্গে সঙ্গে সরে যায় না।

- Chrome/Google warning হলে Search Console-এর Security Issues report পরীক্ষা করো; কোনো deceptive content শনাক্ত হলে ঠিক করে review request করো। ভুল classification হলে [Google Safe Browsing false-positive report](https://www.google.com/safebrowsing/report_error/) জমা দাও।
- Edge/SmartScreen warning হলে warning page-এর **More information → Report that this site doesn't contain threats** ব্যবহার করে site owner হিসেবে report করো।

Warning বন্ধ হয়েছে কি না যাচাই না করা পর্যন্ত browser-এর safety protection বন্ধ করে site-এ প্রবেশ করার পরামর্শ দেওয়া হচ্ছে না।

---

## 4. Website-এ কী কী করা যাবে?

কোনো Telegram-style manual command বা slash command নেই। সব কাজ modern UI controls, search, menu, dialog ও Settings থেকে হবে।

- **Dashboard:** মোট saved item, active note, Trash, recent activity ও popular hashtags।
- **Modern Search:** Keyword, exact phrase, hashtag, URL/domain এবং date/date range filter। `/` অথবা `Ctrl/Cmd + K` দিয়ে দ্রুত search-এ focus করা যায়।
- **Saved Messages:** Telegram Saved Messages-এর মতো chat view; message bubble, search, quick save composer, edit/delete এবং older-message loading।
- **Library:** সব note/message browse, filter, sort, preview ও edit।
- **Create / Edit:** নতুন note তৈরি এবং পুরোনো message edit।
- **Trash:** Soft-delete, restore এবং trashed item আলাদা করে দেখা।
- **Telegram Import:** Telegram Desktop-এর Saved Messages → Export Chat History → Machine-readable JSON।
- **Vault Import:** পূর্বে Export করা Vault JSON অথবা JSONL Import।
- **Export:** সম্পূর্ণ Vault JSON, JSONL অথবা CSV হিসেবে download। Trash-এর item-ও পূর্ণ backup-এ অন্তর্ভুক্ত।
- **Merge logic:** নতুন record যোগ; একই ID-এর newer `edited_at` থাকলে সংশ্লিষ্ট record update; Duplicate বা পুরোনো export skip; অন্য record অক্ষত।
- **Settings:** Storage Status, Import, Export, Backup, Workspace Password/Security, Appearance, density এবং আলাদা Dashboard/Chat size controls।
- **Google Drive:** Render-এর quick-deploy flow-এ ডিফল্টভাবে প্রয়োজন নেই। পরে advanced configuration হিসেবে Drive OAuth যোগ করে GitHub primary + Drive mirror করা যাবে।

এই সংস্করণের data format আগের Telegram Personal Vault Bot-এর JSONL shard format-এর সঙ্গে compatible। একই Vault-এ Bot এবং Website একসঙ্গে চালাবে না; concurrent write conflict এড়াতে Website চালুর আগে Bot service বন্ধ করবে।

**বর্তমান data scope:** text message ও note। ছবি, ভিডিও, document এবং voice file এখনো storage/import scope-এর বাইরে। Telegram Desktop export-এর original timestamp, edited timestamp, hashtag, link এবং text data সংরক্ষিত হয়।

---


## 4.1 Security model (important)

- **Server-side authentication:** every private page and every private API endpoint checks authentication on the server. Hiding React screens is not treated as security.
- **First-run ownership proof:** before anyone can claim the first password, the setup endpoint requires the separate `VAULT_SETUP_KEY` configured in the host environment. The key is compared server-side, is never stored with the password verifier, and should be removed from the host after the first setup.
- **GitHub credential isolation:** `GITHUB_TOKEN` is only used by the backend for repository storage. The React page never asks for it or receives it.
- **Password protection:** minimum 16 characters (maximum 1,024); salted PBKDF2-HMAC-SHA256 with 600,000 iterations; only the verifier is stored in the private data repository. Use a unique passphrase that you do not reuse elsewhere.
- **Server-side session allowlist:** after login the server creates a random session ID and records its expiry in server memory. A signed, HttpOnly, Secure-in-production, SameSite=Lax cookie is not sufficient by itself; every private request also checks the server-side active-session registry.
- **Session lifetime:** 24 hours by default. Server restarts invalidate active sessions, so sign in again after a restart. Run one application instance; multi-replica deployments need a shared session backend and are not enabled by this lightweight free-hosting build.
- **CSRF and browser protections:** session-bound CSRF token on state-changing actions; Content Security Policy, frame denial, MIME sniffing protection, referrer policy, no-store for private responses and HTTPS Secure cookies in production.
- **Login/setup throttling:** five failed attempts per IP in a 15-minute window. The limiter is in-memory and resets on process restart; use the hosting provider's edge protection for stronger distributed throttling.
- **Secret handling:** GitHub PAT is only used server-side for GitHub storage. `VAULT_SETUP_KEY` is a separate one-time setup secret; remove it from the hosting environment after first-run setup. Neither secret is returned by the API or written to logs. Never paste them into chat or source code.

## 5. Render ছাড়াও অন্যান্য hosting

প্রজেক্টটি একই multi-stage Dockerfile ব্যবহার করে। Render, Railway, Koyeb অথবা Dockerfile সমর্থিত অন্য provider-এ Website চালানো যায়। অন্য provider-এ একই তিনটি GitHub environment variable দিতে হবে এবং session স্থায়ী রাখতে একটি স্থায়ী `SECRET_KEY` configure করতে হবে। সেখানে `SECRET_KEY` auto-generated না হলে নিজের random value দিতে হবে।

| Hosting | Deployment | Free-tier সম্পর্কে |
|---|---|---|
| Render | Blueprint / Dockerfile | Blueprint-এ Free plan নির্বাচন করা আছে; inactivity-তে sleep হতে পারে |
| Railway | Dockerfile | Free allowance/credit ও usage limits প্রযোজ্য |
| Koyeb | Dockerfile | Free instance-এর resource ও scale-to-zero সীমাবদ্ধতা প্রযোজ্য |
| Other Docker hosts | Dockerfile / Compose | Provider-এর নিজস্ব pricing ও limits প্রযোজ্য |

Docker-compatible মানেই ২৪/৭ Free Hosting নিশ্চিত নয়। Free plan-এর quota, sleep, cold start ও availability provider যেকোনো সময় পরিবর্তন করতে পারে। App-এর persistent data GitHub-এ থাকে; Render-এর local disk-এ নির্ভর করে না।

---

## 6. Advanced / local configuration

Render-এর one-click GitHub-only mode-এ উপরের ৩টি input ছাড়া আর কিছু লাগে না। Google Drive বা local development-এর জন্য advanced environment variables প্রয়োজন হতে পারে। `.env.example`-এ তাদের তালিকা আছে।

### Local run

প্রথমে আধুনিক React UI build করো; এরপর FastAPI চালালে browser-এ একই first-run password setup wizard পাওয়া যাবে।

```bash
cd frontend
npm install
npm run build
cd ..
python -m pip install -r requirements.txt
python scripts/generate_secret.py
python -m app.main
```

Local `.env`-এ অন্তত GitHub-এর তিনটি variable এবং একটি stable `SECRET_KEY` বসাও। Drive-only local configuration ব্যবহার করলে `APP_PASSWORD` environment variable প্রয়োজন, কারণ first-run password verifier-এর persistent store হিসেবে GitHub নেই।

### Optional Google Drive mirror

Advanced deployment-এ Google Drive যুক্ত করতে `GOOGLE_OAUTH_CLIENT_B64` ও `GOOGLE_OAUTH_TOKEN_B64` configure করতে হবে। GitHub + Drive হলে GitHub primary এবং Drive mirror; GitHub-only হলে ডেটা শুধু GitHub-এ; Drive-only advanced mode-ও supported, তবে Render one-click Blueprint ইচ্ছাকৃতভাবে GitHub-only রাখা হয়েছে যেন first-time setup মাত্র তিনটি input-এ শেষ হয়।

---

## 7. Security & reliability

- GitHub token server-side; frontend-এ পাঠানো হয় না।
- Workspace password plaintext নয়; salted PBKDF2-SHA256 verifier private data repo-তে রাখা হয়।
- Signed session cookie, CSRF validation, login rate limit এবং security headers ব্যবহৃত হয়।
- Message content application log-এ লেখা হয় না।
- App local filesystem-এ Vault data রাখে না; GitHub হলো persistent store।
- অন্তত একটি persistent storage backend required; invalid/partial GitHub config হলে startup fail হবে।
- Workspace password Settings → Security থেকে পরিবর্তন করা যায়।
- GitHub repository ও PAT private এবং least-privilege রাখো; PAT revoke করলে নতুন credential দিয়ে redeploy করতে হবে।

### গুরুত্বপূর্ণ Render Free সীমাবদ্ধতা

Render Free Web Service ১৫ মিনিট incoming traffic না পেলে spin down করতে পারে; পরের request-এ cold start হতে পারে। Free service-এর local filesystem ephemeral, তাই website-এর durable data GitHub repository-তে থাকে। এটি personal vault-এর জন্য উপযোগী, তবে instant always-on response-এর নিশ্চয়তা নয়।

---

## Project files

- `app/` — FastAPI API, authentication, GitHub/Drive storage এবং import/export logic
- `frontend/` — React + TypeScript + Vite + Tailwind UI
- `render.yaml` — one-click Render Blueprint; prompts for one-time setup key and three GitHub values
- `Dockerfile` — frontend build + Python runtime in one image
- `railway.json` — Railway Docker deployment configuration
- `docker-compose.yml` — local/container deployment
- `.env.example` — optional advanced/local configuration reference
- `tests/` — backend, API, import, merge and storage tests

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
