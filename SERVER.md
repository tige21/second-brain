# Server Access

> **Consolidated 2026-06-12 → single production host `185.214.108.29` (NL).**
> The PWA used to run on two divergent deploys (83.x + 185.x); split-brain
> sessions/data forced a consolidation. `185.x` is now the **sole** PWA host;
> `83.x`'s PWA is decommissioned (see bottom). Geo note: ipinfo puts `83.x` in
> **Moscow/RU** (earlier docs wrongly said NL) and `185.x` in **Amsterdam/NL**.

## Production VPS — PWA + CouchDB (`second-braintige.online`)

```
Host:     185.214.108.29
User:     root
Password: 8zgsro6V
Provider: Amsterdam / NL
Domains:  second-braintige.online (apex + www)  → PWA
          sync.second-braintige.online          → CouchDB (Obsidian LiveSync)
```

This is the **only** PWA production host. nginx serves the frontend at
`/var/www/second-brain-pwa/` and reverse-proxies `/api/*` to `127.0.0.1:8766`
(uvicorn, systemd unit `second-brain-pwa`). One local CouchDB on `127.0.0.1:5984`
serves BOTH the PWA (`personal_vault` + per-user provisioned vaults) AND the
public Obsidian LiveSync at `sync.second-braintige.online`.

DNS `second-braintige.online` (apex + www) → `185.214.108.29`.

## Auth — server-side Google OAuth + HttpOnly session cookie

Login is a **server-side authorization-code flow** (not client GIS tokens — that
broke in iOS standalone PWAs). Flow: `GET /api/auth/google/start` → 302 to Google
→ `GET /api/auth/google/callback` exchanges the code, creates a `Session` row, and
sets an HttpOnly `sb_session` cookie. `GET /api/auth/me` hydrates the user (incl.
`is_admin`); `POST /api/auth/logout` clears it. `get_current_user` reads the cookie
first (Bearer/API-key fallback). The Google Console must list the callback
redirect URI `https://second-braintige.online/api/auth/google/callback`.

## SSH

```bash
# Production (PWA + CouchDB)
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29
```

## Services on 185.214.108.29 (production)

| Service | Systemd unit / path |
|---------|---------------------|
| PWA Frontend (static) | nginx → `/var/www/second-brain-pwa/` |
| PWA Backend (FastAPI/uvicorn `:8766`) | `second-brain-pwa` → `/root/second-brain-pwa/backend/` |
| CouchDB (personal_vault + per-user + public LiveSync) | Docker, `/root/obsidian-livesync/`, `127.0.0.1:5984` |
| nginx (`second-braintige.online` + `sync.…`) | `/etc/nginx/` |

⚠️ Backend `WorkingDirectory` is `/root/second-brain-pwa/backend/`. Backend DB is
SQLite at `backend/data/brain.db`. After any backend deploy: `systemctl restart
second-brain-pwa` then tail `journalctl -u second-brain-pwa -n 30 --no-pager` to
confirm clean startup before claiming done.

## Deploy cheatsheet (production = 185.x)

### Frontend (Vite build → static)

```bash
cd frontend && npm run build
sshpass -p '8zgsro6V' rsync -avz --delete \
  -e 'ssh -o StrictHostKeyChecking=no' \
  dist/ root@185.214.108.29:/var/www/second-brain-pwa/
```

### Backend (FastAPI)

```bash
sshpass -p '8zgsro6V' rsync -avz \
  -e 'ssh -o StrictHostKeyChecking=no' \
  backend/ root@185.214.108.29:/root/second-brain-pwa/backend/ \
  --exclude='__pycache__' --exclude='.venv' --exclude='*.pyc' \
  --exclude='.pytest_cache' --exclude='data' --exclude='*.db' \
  --exclude='*.db-journal' --exclude='.env' --exclude='*.egg-info'

sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 \
  'systemctl restart second-brain-pwa && journalctl -u second-brain-pwa -n 30 --no-pager'
```

🚨 **NEVER use `--delete` for the backend rsync** — it would wipe `data/brain.db`
(the SQLite production DB). The excludes above are the safe path.

## CouchDB admin users (on 185.x)

| User | Purpose |
|---|---|
| `admin` | PWA backend via `COUCHDB_ADMIN_USER` env (drop-in below). Loopback only. |
| `livesync` | Owner's Obsidian LiveSync devices, public via `sync.second-braintige.online`. |
| `pwa_provisioner` | Provisions per-user E2E vaults. |

## Vault provisioning env vars (185.x systemd drop-in)

`/etc/systemd/system/second-brain-pwa.service.d/vault-env.conf`:

```
[Service]
Environment="COUCHDB_ADMIN_USER=<admin user>"
Environment="COUCHDB_ADMIN_PASS=<password>"
Environment="ADMIN_EMAILS=mregoryt@gmail.com"
```

`ADMIN_EMAILS` lives in this drop-in, NOT `.env` — an ad-hoc python that reads
only `.env` sees it empty. After editing: `systemctl daemon-reload && systemctl
restart second-brain-pwa`.

## Decommissioned — 83.217.215.66 (was PWA prod, RU/Moscow, VDSINA)

```
Host: 83.217.215.66   User: root   Password: REDACTED
```

PWA **stopped + disabled** here on 2026-06-12 (`systemctl disable second-brain-pwa`),
its nginx site moved to `/root/second-brain-pwa.nginx.disabled-20260612`. `brain.db`
backups are kept on the box. Do NOT re-enable — it would re-create the split-brain.
(Outbound TCP 83→185 is firewall-blocked by VDSINA, which is why the original
data migration was relayed through the Mac.)

## Notes

- SSH standard port `22`. `sshpass` required (`brew install hudochenkov/sshpass/sshpass`).
- Debian 12 (Bookworm). Backend DB SQLite `backend/data/brain.db` — **backup before risky ops**.
- Live features (deployed): server-side cookie OAuth; "workout/food/weight for all
  users" + body-profile onboarding (English/knowledge-graph stay admin-only,
  vault-dependent); English mistake capture — full lesson transcript → LLM extracts
  every mistake with a category → «Где я косячу» patterns screen.

## Multi-user vault model (decided 2026-05-27 — Option B: E2E for all)

Two tiers of vault coexist by design:

- **Owner vault** (`personal_vault`, plaintext): the admin's. Stored unencrypted
  on 185.x so the PWA backend can READ it → powers graph, semantic search,
  raw→wiki processing, English lesson ingest, and the chat vault tools. Admin-only
  (gated by `require_admin` / `user.email in admin_emails_list`).
- **Per-user vaults** (provisioned, E2E-encrypted): any authenticated PWA user
  can `POST /api/vault/provision` → gets their own CouchDB user + DB + a one-time
  passphrase + a Setup URI (QR). These are **E2E-encrypted**, so the server CANNOT
  read them. Users get cross-device Obsidian SYNC only — NOT graph / search / AI
  processing (those require server-readable content).

This is intentional: privacy for users, full features for the owner.

Setup URI crypto (`backend/app/services/setup_uri.py`) matches obsidian-livesync
V2 (`encrypt3`/`decryptV2`): `PBKDF2(SHA256(passphrase), randomSalt, 100k)` →
AES-256-GCM, token `%<hex iv><hex salt><b64 ct>`, URL-encoded.
