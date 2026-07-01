# Обновление доков → актуальный сервер 194.5.65.182 (после миграции с 185)

**Created:** 2026-07-01
**Type:** docs
**Mode:** full
**Branch:** main везде (repos коммитятся в main напрямую)

## Цель
Во всех **живых** доках 3 репозиториев указать актуальный сервер `194.5.65.182` (ферма, вместо умершего `185.214.108.29`) и отразить новую архитектуру co-host + грабли миграции. Исторические планы/спеки/эволюции НЕ переписываем (это записи «как было»).

## Settings
- Testing: N/A (документация).
- Logging: N/A (документация).
- Docs: это и есть docs-задача.

## Факты, которые доки должны знать
- Сервер: **185.214.108.29 УМЕР** (сбой диска ext4). Всё переехало на **194.5.65.182** (ферма, Франкфурт/NL, co-host рядом с Dify).
- Работает по HTTPS: PWA (`second-braintige.online` + www + `second-brain-pwa.duckdns.org`, uvicorn :8766, systemd `second-brain-pwa`, brain.db `/root/second-brain-pwa/backend/data/brain.db`, фронт `/var/www/second-brain-pwa`); Obsidian-vault CouchDB (`sync.second-braintige.online`, `/root/obsidian-livesync`, :5984); cards-game (postgres+api, проект `cards-staging`, `/opt/spark/docker`, :8080); статика `sparkcards.space` (ждёт реактивации Bunny DNS).
- TLS: **certbot** (не acme.sh), автопродление. Хост-nginx: `/etc/nginx/conf.d/*.conf`.
- НЕ переносили: TG-бот second-brain, VPN xray/x-ui, marketbox, claude-office, mtproxy, openai-proxy (`openai.second-braintige.online` остался на 185 → умрёт).
- Грабли: (a) **compose project-name collision** — cards под `-p cards-staging`, никогда `--remove-orphans`, dir «docker» коллизится с Dify; (b) Dify nginx = `EXPOSE_NGINX_PORT=127.0.0.1:8088`, поднимать `docker compose -f docker-compose.yaml -f docker-compose.override.yml`; (c) фронты собирать на Mac (RAM 8ГБ впритык), grafana/prometheus не поднимали; (d) sparkcards DNS в Bunny (GEO NL+Москва 83.217.215.66), приостановлен из-за $0.

## Tasks

- [ ] **D1** `second-brain/SERVER.md` — переписать: актуальный прод = ферма `194.5.65.182`; таблица доменов→сервис→путь; 185 помечен как «decommissioned (диск умер)»; TLS certbot; nginx conf.d; ссылка на грабли миграции.
- [ ] **D2** `dify-farm/infra/SERVER.md` — добавить раздел «Co-hosted сервисы на ферме» (PWA/vault/cards/sparkcards), список доменов + порты (:8766/:5984/:8080), правило compose-collision (`-p`, не `--remove-orphans`), Dify nginx 127.0.0.1:8088.
- [ ] **D3** `second-brain-web/DEPLOYMENT_LOG.md` — новая запись «2026-07-01: аварийная миграция 185→194»: что, куда, деплой-пути, certbot, co-host, что осталось (sparkcards DNS).
- [ ] **D4** `second-brain-web/CLAUDE.md` — деплой-раздел: сервер = ферма 194, certbot вместо acme, co-host рядом с Dify; предупреждение про compose `-p`.
- [ ] **D5** `second-brain/CLAUDE.md` (hard-won rules) — пометка что PWA-сервер теперь `194.5.65.182`, TLS certbot; ссылка на `feedback_compose_project_collision`.
- [ ] **D6** `dify-farm/.ai-factory/DESCRIPTION.md` — одна строка про co-host (если уместно).

→ **Commit:** по репо: `docs(no-ref): point docs to 194 farm after 185 disk failure` (second-brain, second-brain-web, dify-farm — каждый свой).
