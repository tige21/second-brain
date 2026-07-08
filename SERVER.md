# Server Access

> **🚨 MIGRATED 2026-07-01 → production host is now the FARM `194.5.65.182`.**
> `185.214.108.29` **DIED** (ext4 disk failure — recurring `aborted journal` →
> root read-only). All chosen services were emergency-migrated to the Dify farm
> `194.5.65.182` (Frankfurt/NL VPS that also runs the 12-bot Dify farm — PWA is
> now **co-hosted** next to Dify). `185.x` and `83.x` are both decommissioned
> (see bottom). Data was rescued (brain.db, CouchDB vault, cards dump, configs).
> See memory `project_vds_185_migration` + `feedback_compose_project_collision`.

## Production VPS — the FARM (PWA + CouchDB + cards, co-hosted with Dify)

```
Host:     194.5.65.182
User:     root
Password: Aic5TKex
Provider: Frankfurt / NL (62yun, promo-B: 4 CPU / 8GB / 150GB NVMe)
Also runs: the whole Dify farm (docker: dify, litellm, skills-api, tg-bridge, …)
Domains:  second-braintige.online (apex + www)  → PWA
          second-brain-pwa.duckdns.org          → PWA (duckdns)
          sync.second-braintige.online          → CouchDB (Obsidian LiveSync)
          cards-staging.duckdns.org             → cards-game frontend (static)
          cards-api-staging.duckdns.org         → cards-game API (:8080)
          sparkcards.space (+ www)              → static (Bunny GEO DNS; pending)
```

The PWA nginx **vhost lives in `/etc/nginx/conf.d/second-brain-pwa.conf`** (host
nginx uses `conf.d/*.conf`, NOT `sites-enabled/`). It serves the frontend at
`/var/www/second-brain-pwa/` and reverse-proxies `/api/*` to `127.0.0.1:8766`
(uvicorn, systemd unit `second-brain-pwa`). A dedicated CouchDB (docker,
`/root/obsidian-livesync/`, `127.0.0.1:5984`) holds `personal_vault` (1879 docs)
+ per-user vaults and serves public Obsidian LiveSync at
`sync.second-braintige.online`.

**TLS = certbot** (`certbot --nginx`, NOT acme.sh), auto-renew. Re-issue helper:
`/root/issue-tls.sh`. DNS `second-braintige.online` (apex + www + sync) →
`194.5.65.182` (reg.ru zone); duckdns hosts point to `194.5.65.182` too.

⚠️ **Farm co-host landmine:** never run `docker compose up` in a dir named
`docker` without `-p <project>` — cards-game (`/opt/spark/docker`) collided with
Dify's project `docker` and took the farm down ~15 min. cards now runs under
`docker compose -p cards-staging`. Never `--remove-orphans`. Dify's nginx must
bind `127.0.0.1:8088` (`EXPOSE_NGINX_PORT` in `/opt/dify/docker/.env`); bring
Dify up with `-f docker-compose.yaml -f docker-compose.override.yml`.

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
# Production = the farm (PWA + CouchDB + cards, co-hosted with Dify)
sshpass -p 'Aic5TKex' ssh -o StrictHostKeyChecking=no root@194.5.65.182
```

## Services on 194.5.65.182 (production, co-hosted)

| Service | Systemd unit / path |
|---------|---------------------|
| PWA Frontend (static) | nginx → `/var/www/second-brain-pwa/` |
| PWA Backend (FastAPI/uvicorn `:8766`) | `second-brain-pwa` → `/root/second-brain-pwa/backend/` |
| CouchDB (personal_vault + per-user + public LiveSync) | Docker, `/root/obsidian-livesync/`, `127.0.0.1:5984` |
| cards-game (postgres + api `:8080`) | `docker compose -p cards-staging` → `/opt/spark/docker` |
| nginx vhosts (all domains) | `/etc/nginx/conf.d/*.conf` |
| Dify farm (12 bots) | Docker `/opt/dify/docker`, nginx `127.0.0.1:8088` |

⚠️ Backend `WorkingDirectory` is `/root/second-brain-pwa/backend/`. Backend DB is
SQLite at `backend/data/brain.db`. After any backend deploy: `systemctl restart
second-brain-pwa` then tail `journalctl -u second-brain-pwa -n 30 --no-pager` to
confirm clean startup before claiming done.

## Deploy cheatsheet (production = the farm 194.5.65.182)

⚠️ **`rsync` is NOT installed on the farm** — use `tar`-over-ssh (build the
frontend on the Mac; the farm's 8GB RAM is tight for a vite build).

### Frontend (Vite build on Mac → static)

```bash
cd frontend && npm run build
export COPYFILE_DISABLE=1   # avoid macOS xattr tar noise
tar czf - -C dist . | sshpass -p 'Aic5TKex' ssh -o StrictHostKeyChecking=no \
  root@194.5.65.182 'rm -rf /var/www/second-brain-pwa && mkdir -p /var/www/second-brain-pwa && tar xzf - -C /var/www/second-brain-pwa'
```

### Backend (FastAPI)

```bash
# push code (NEVER the data/ dir — brain.db is the prod SQLite DB), then restart
export COPYFILE_DISABLE=1
tar czf - -C backend --exclude='__pycache__' --exclude='.venv' --exclude='*.pyc' \
  --exclude='.pytest_cache' --exclude='data' --exclude='*.db' --exclude='.env' \
  --exclude='*.egg-info' . | sshpass -p 'Aic5TKex' ssh -o StrictHostKeyChecking=no \
  root@194.5.65.182 'tar xzf - -C /root/second-brain-pwa/backend'

sshpass -p 'Aic5TKex' ssh -o StrictHostKeyChecking=no root@194.5.65.182 \
  'systemctl restart second-brain-pwa && journalctl -u second-brain-pwa -n 30 --no-pager'
```

🚨 **NEVER push the `data/` dir** — it holds `data/brain.db` (SQLite production
DB). The `--exclude='data'` above is the safe path. TLS is certbot (`/root/issue-tls.sh`).

## CouchDB admin users (on the farm)

| User | Purpose |
|---|---|
| `admin` | PWA backend via `COUCHDB_ADMIN_USER` env (drop-in below). Loopback only. |
| `livesync` | Owner's Obsidian LiveSync devices, public via `sync.second-braintige.online`. |
| `pwa_provisioner` | Provisions per-user E2E vaults. |

## Vault provisioning env vars (farm systemd drop-in)

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

## Decommissioned — 185.214.108.29 (was PWA prod, Amsterdam/NL, 62yun)

Disk **failed** 2026-06-30/07-01 (ext4 `aborted journal` → root read-only, recurring).
All chosen services emergency-migrated to the farm `194.5.65.182`; data rescued
first (`brain.db`, CouchDB vault, cards dump, nginx/systemd/TLS configs, secrets).
NOT migrated (stay dead with 185): TG-bot `second-brain`, VPN xray/x-ui, marketbox,
claude-office, mtproxy, `openai.second-braintige.online` (openai-proxy). Open a
62yun ticket to replace the disk / refund, then retire the VDS.

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
  users" + body-profile onboarding; **English for ALL users** (2026-07-04): review/
  drills/grammar/verbs/speaking/progress open to every account; lessons arrive via
  the owner's vault ingest (still admin-only) OR the new **PDF lesson upload**
  (`POST /api/english/review/lessons/upload` — pypdf text → LLM lesson structure →
  cards; sha256 dedup; stored transcript + `/lessons/reparse` re-derive). Only the
  knowledge graph + vault ingest/seeds stay admin-only. English mistake capture —
  full lesson transcript → LLM extracts every mistake with a category → «Где я
  косячу» patterns screen. **Speaking error capture** (2026-07-04): every speaking
  analysis persists mistakes as review cards (`source_path="speaking"`); a repeated
  mistake bumps `lapses` + goes due now instead of duplicating. Speaking hub:
  `GET /speaking/mistakes` (what to fix + how), `POST /speaking/generate-session`
  (mode=mistakes — prompts targeted at YOUR recurring errors / mode=topic), plus
  the classic per-tense sets; progress has a speaking coverage block.
  **Daily speaking session** (2026-07-04): one-button `POST /speaking/daily-session`
  (3 LLM prompts for recurring mistakes + 5 vetted focus-tense prompts; focus by
  mistake-rule match → ISO-week rotation) + opt-in push (`speaking_daily` pref,
  `user_settings.speaking_daily_hour`, deep-link `/english/speaking?session=daily`).
  **Ask-tutor** (2026-07-07): `POST /english/review/ask` — «Спросить, почему так»
  in the speaking drill result + on error/grammar review cards; grounded RU
  answers about the specific attempt/card, follow-ups carry ≤4 Q/A turns.
  **Fun prompts + rule peek** (2026-07-08): shared lively style in all prompt
  generators; daily session = 12 phrases (3 mistakes + 4 vetted + 5 fresh LLM,
  best-effort); daily «Ещё» refills via the focus rule (works with an empty
  deck); «📖 Правило» peek on the drill prompt screen from the cached grammar
  handbook (zero requests).
- PWA nginx vhost: `client_max_body_size 25m`, `proxy_read_timeout 300s` (raised
  from 120s on 2026-07-04 for the PDF-lesson LLM pipeline, up to ~240s worst case).
- Server venv extras the PWA needs: `pypdf` (PDF lesson upload), `python-multipart`.

## Multi-user vault model (decided 2026-05-27 — Option B: E2E for all)

Two tiers of vault coexist by design:

- **Owner vault** (`personal_vault`, plaintext): the admin's. Stored unencrypted
  on the farm (194.x) so the PWA backend can READ it → powers graph, semantic search,
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
