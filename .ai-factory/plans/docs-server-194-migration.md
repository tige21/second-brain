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

- [x] **D1** `second-brain/SERVER.md` — переписан: прод = ферма `194.5.65.182`; таблица доменов→сервис→путь; 185 в «decommissioned (диск умер)»; TLS certbot; nginx conf.d; tar-деплой; грабли compose. Коммит `715cc1a`.
- [x] **D2** `dify-farm/infra/SERVER.md` — добавлен раздел co-host (PWA/vault/cards/sparkcards, домены+порты :8766/:5984/:8080), правило compose-collision (`-p cards-staging`, не `--remove-orphans`), Dify nginx 127.0.0.1:8088. Коммит `003972e`.
- [x] **D3** `second-brain-web/DEPLOYMENT_LOG.md` — баннер «2026-07-01: миграция 185→194», HTTPS-домены, деплой-пути, certbot. Коммит `bdf5114`.
- [x] **D4** `second-brain-web/CLAUDE.md` — N/A: файл 25 строк, ссылок на сервер/деплой нет → правка не требуется.
- [x] **D5** `second-brain/CLAUDE.md` (hard-won rules) — вставлена пометка: PWA-сервер теперь `194.5.65.182`, certbot, nginx conf.d, tar-деплой, ссылка на `feedback_compose_project_collision`. Коммит `715cc1a`.
- [x] **D6** `dify-farm/.ai-factory/DESCRIPTION.md` — пропущено намеренно: co-host уже покрыт в `infra/SERVER.md` (D2), дублировать в DESCRIPTION смысла нет.

→ **Commits (сделаны):** second-brain `715cc1a`, second-brain-web `bdf5114`, dify-farm `003972e` — все запушены в `main`.
