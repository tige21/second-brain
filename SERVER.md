# Server Access

## Connection

```
Host: 185.214.108.29
Port: 22
User: root
Password: 8zgsro6V
Domain (primary): second-braintige.online
Domain (legacy fallback): second-brain-pwa.duckdns.org
```

Primary domain moved to `second-braintige.online` (reg.ru, registered 2026-04-20,
renew reminder 2027-04-06). The old DuckDNS host is still served by nginx as a
fallback for anyone on the old URL, but new deploys and docs should use the
new domain. SNI for `*.duckdns.org` is filtered by Russian DPI; the new
`.online` domain is not flagged and loads from RU without a VPN.

### SSH command

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29
```

### Run remote command

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'COMMAND_HERE'
```

### Deploy files via rsync

```bash
sshpass -p '8zgsro6V' rsync -avz --delete -e 'ssh -o StrictHostKeyChecking=no' LOCAL_PATH/ root@185.214.108.29:REMOTE_PATH/
```

## Services

| Service | Systemd unit | Path on server |
|---------|-------------|----------------|
| PWA Frontend | `second-brain-pwa` | `/var/www/second-brain-pwa/` |
| PWA Backend (FastAPI) | `second-brain-pwa` | `/root/second-brain-pwa/backend/` |
| Telegram Bot | `second-brain` | `/root/second-brain/` |
| Nginx | `nginx` | `/etc/nginx/` |

### Restart a service

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'systemctl restart second-brain-pwa'
```

### Check all services

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'systemctl is-active second-brain-pwa nginx'
```

### View logs

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'journalctl -u second-brain-pwa -n 50 --no-pager'
```

## Deploy Cheatsheet

### Frontend (Vite build -> static files)

```bash
cd frontend && npm run build
sshpass -p '8zgsro6V' rsync -avz --delete -e 'ssh -o StrictHostKeyChecking=no' dist/ root@185.214.108.29:/var/www/second-brain-pwa/
```

### Backend (FastAPI)

```bash
sshpass -p '8zgsro6V' rsync -avz -e 'ssh -o StrictHostKeyChecking=no' backend/ root@185.214.108.29:/root/second-brain-pwa/backend/ --exclude='__pycache__' --exclude='.env' --exclude='*.db' --exclude='.venv' --exclude='venv'
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'systemctl restart second-brain-pwa'
```

## Security Updates

```bash
sshpass -p '8zgsro6V' ssh -o StrictHostKeyChecking=no root@185.214.108.29 'DEBIAN_FRONTEND=noninteractive apt update && apt upgrade -y'
```

## Notes

- SSH uses standard port `22`
- `sshpass` is required (`brew install hudochenkov/sshpass/sshpass` on macOS)
- Frontend is served by Nginx as static files
- Backend runs behind Nginx as reverse proxy
- Location: Дронтен, Нидерланды
- Hosting provider: 62yun.ru (billing), DC — Netherlands

## CouchDB admin users

| User | Purpose | Where used |
|---|---|---|
| `livesync` | Personal vault (owner's vault: `obsidian` DB) | LiveSync plugin on mac/iPhone |
| `pwa_provisioner` | PWA backend uses this to create per-user vaults | env on `second-brain-pwa` service |

To rotate `pwa_provisioner` password:
1. Generate new: `openssl rand -base64 30 | tr -d '/+=' | head -c 40`
2. `curl -X PUT -u livesync:<livesync-pass> http://127.0.0.1:5984/_node/_local/_config/admins/pwa_provisioner -d '"<new-pass>"'`
3. Update `COUCHDB_ADMIN_PASS=` in `/etc/systemd/system/second-brain-pwa.service.d/vault-env.conf`.
4. `systemctl daemon-reload && systemctl restart second-brain-pwa`
