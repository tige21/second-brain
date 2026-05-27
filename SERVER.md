# Server Access

## Production VPS (PWA — `second-braintige.online`)

```
Host:     83.217.215.66
Hostname: v3107684.hosted-by-vdsina.ru
User:     root
Password: REDACTED
Provider: VDSINA (NL)
Domains:  second-braintige.online (apex + www)
          83.217.215.66 (raw IP)
```

This is the **only** PWA production host. nginx serves the frontend at `/var/www/second-brain-pwa/` and reverse-proxies `/api/*` to `127.0.0.1:8766` (uvicorn).

## Auxiliary VPS (CouchDB for personal Obsidian vault — `sync.second-braintige.online`)

```
Host:     185.214.108.29
User:     root
Password: 8zgsro6V
Purpose:  Self-hosted CouchDB for owner's personal Obsidian vault via LiveSync.
          Public over HTTPS at sync.second-braintige.online.
```

Used by Obsidian LiveSync plugin on owner's Mac/iPhone. **Not used by the PWA backend** — PWA-provisioned user vaults live on a separate CouchDB on the prod host (see below).

⚠️ Note: outbound TCP from 83.x to 185.x is blocked by VDSINA's egress firewall (ICMP works, TCP doesn't). PWA backend cannot reach this CouchDB. PWA uses its own local CouchDB instead.

## SSH

```bash
# Production
sshpass -p 'REDACTED' ssh -o StrictHostKeyChecking=no root@83.217.215.66

# Auxiliary CouchDB host
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29
```

## Services on 83.217.215.66 (production)

| Service | Systemd unit | Path |
|---------|-------------|------|
| PWA Frontend (static) | served by nginx | `/var/www/second-brain-pwa/` |
| PWA Backend (FastAPI/uvicorn) | `second-brain-pwa` | `/root/second-brain-pwa/backend/` |
| Nginx | `nginx` | `/etc/nginx/` |
| CouchDB 3.5 (local, for PWA user vaults) | `couchdb` | `/opt/couchdb/`, data in `/var/lib/couchdb/` |

CouchDB listens only on `127.0.0.1:5984` (loopback) — accessed by the PWA backend in-process.

## Services on 185.214.108.29 (auxiliary)

| Service | Path |
|---------|------|
| CouchDB 3.4 (Docker) — personal vault | `/root/obsidian-livesync/` |
| nginx reverse-proxy `sync.second-braintige.online` → `127.0.0.1:5984` | `/etc/nginx/sites-enabled/sync.second-braintige.online` |

## Deploy cheatsheet (production = 83.x)

### Frontend (Vite build → static files)

```bash
cd frontend && npm run build
sshpass -p 'REDACTED' rsync -avz --delete \
  -e 'ssh -o StrictHostKeyChecking=no' \
  dist/ root@83.217.215.66:/var/www/second-brain-pwa/
```

### Backend (FastAPI)

```bash
sshpass -p 'REDACTED' rsync -avz \
  -e 'ssh -o StrictHostKeyChecking=no' \
  backend/ root@83.217.215.66:/root/second-brain-pwa/backend/ \
  --exclude='__pycache__' --exclude='__pycache__/' \
  --exclude='.venv' --exclude='.venv/' \
  --exclude='*.pyc' --exclude='.pytest_cache' \
  --exclude='data' --exclude='data/' \
  --exclude='*.db' --exclude='*.db-journal' \
  --exclude='.env'

sshpass -p 'REDACTED' ssh -o StrictHostKeyChecking=no root@83.217.215.66 \
  'systemctl restart second-brain-pwa && journalctl -u second-brain-pwa -n 30 --no-pager'
```

🚨 **NEVER use `--delete` for backend rsync** — it will wipe `data/brain.db` (the SQLite production DB). The excludes above are the safe path. Always verify `data/brain.db` mtime/md5 before AND after rsync to confirm preservation.

## CouchDB admin users

### On 83.x (production, for PWA-provisioned vaults)

| User | Purpose |
|---|---|
| `admin` | Backend uses this via `COUCHDB_ADMIN_USER` env. Listens only on `127.0.0.1:5984`. |

To rotate `admin` password:
1. Generate new: `openssl rand -base64 60 | tr -d '/+=\n' | head -c 40`
2. PUT to `/_node/_local/_config/admins/admin` with new value
3. Update `COUCHDB_ADMIN_PASS=` in `/etc/systemd/system/second-brain-pwa.service.d/vault-env.conf`
4. `systemctl daemon-reload && systemctl restart second-brain-pwa`

### On 185.x (auxiliary, for personal vault)

| User | Purpose |
|---|---|
| `livesync` | Used by Obsidian LiveSync plugin on owner's devices. Public via `sync.second-braintige.online`. |
| `pwa_provisioner` | Created during initial Phase 1 setup but **unused** — outbound block prevents 83.x from reaching this CouchDB. Kept for completeness. |

## Vault provisioning env vars (83.x systemd drop-in)

`/etc/systemd/system/second-brain-pwa.service.d/vault-env.conf`:

```
[Service]
Environment="COUCHDB_BASE_URL=http://127.0.0.1:5984"
Environment="COUCHDB_ADMIN_USER=admin"
Environment="COUCHDB_ADMIN_PASS=<the random 40-char password>"
Environment="ADMIN_EMAILS=mregoryt@gmail.com"
```

After editing: `systemctl daemon-reload && systemctl restart second-brain-pwa`.

## Notes

- SSH uses standard port `22` on both hosts.
- `sshpass` required (`brew install hudochenkov/sshpass/sshpass` on macOS).
- Both hosts: Debian 12 (Bookworm).
- Backend DB is SQLite at `backend/data/brain.db`. **Always backup before risky operations.**

## Multi-user vault model (decided 2026-05-27 — Option B: E2E for all)

Two tiers of vault coexist by design:

- **Owner vault** (`personal_vault`, plaintext): the admin's. Stored unencrypted
  on 83.x so the PWA backend can READ it → powers graph, semantic search,
  raw→wiki processing, and the chat vault tools. Admin-only (gated by
  `require_admin` / `user.email in admin_emails_list`).
- **Per-user vaults** (provisioned, E2E-encrypted): any authenticated PWA user
  can `POST /api/vault/provision` → gets their own CouchDB user + DB + a
  one-time passphrase + a Setup URI (QR). These are **E2E-encrypted**, so the
  server CANNOT read them. Users get cross-device Obsidian SYNC only — NOT
  graph / search / AI processing (those require server-readable content).

This is intentional: privacy for users, full features for the owner. Making
per-user vaults feature-rich would require storing them plaintext (server can
read everyone's notes) — explicitly rejected for now. Revisit only if building
a product where users opt into plaintext.

Setup URI crypto (`backend/app/services/setup_uri.py`) matches obsidian-livesync
V2 (`encrypt3`/`decryptV2`): `PBKDF2(SHA256(passphrase), randomSalt, 100k)` →
AES-256-GCM, token `%<hex iv><hex salt><b64 ct>`, URL-encoded. Verified against
the real plugin's decrypt in Node.
