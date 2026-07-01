# Аварийная миграция VDS 185.214.108.29 → 194.5.65.182

**Created:** 2026-06-30
**Mode:** emergency (диск источника умирает — ext4 aborted journal, циклический read-only)
**Source (умирает):** 185.214.108.29 (Debian 12), root/8zgsro6V
**Target:** 194.5.65.182 (svr_146835, Франкфурт, Debian 12, 4 CPU, **8GB RAM**, 150GB NVMe), root/Aic5TKex — ⚠️ это ТОТ ЖЕ хост, где уже работает Dify-ферма

## ⚠️ Главный риск
Target **уже несёт Dify-ферму** (Dify+litellm+postgres+redis+weaviate+skills-api+tg-bridge+couchdb-фермы) — RAM 8GB почти выбрана. Доселение PWA + 2-й CouchDB + cards-game (postgres+api+grafana+prometheus) + mtproxy может вызвать OOM. **Рекомендация:** взять отдельный новый VDS под мигрируемый стек. По умолчанию (как просил владелец) — селим на 194, но с урезанием (Grafana/Prometheus/лишние .bak — не тащить) и контролем RAM/портов.

## Settings
- Testing: реальная проверка каждого сервиса (curl/SSH), без юнит-тестов.
- Logging: verbose (все реальные команды).
- Docs: обновить память + SERVER.md после миграции.

## Уже спасено (Mac `/Users/macbook/Documents/projects/_rescue-185-20260630/`)
- `brain.db.fresh` (PWA SQLite, integrity ok)
- `obsidian-livesync.tgz` (CouchDB-vault data+etc+configs+admin_password)
- `cards_game_staging.sql` (Postgres дамп, 21 таблица)

## Что переносим (инвентарь источника)
| Сервис | Что это | Данные | Домен |
|---|---|---|---|
| second-brain-pwa | FastAPI :8766 + фронт + SQLite | brain.db ✅ | PWA-домен |
| obsidian-couchdb | Obsidian LiveSync | /root/obsidian-livesync ✅ | sync.second-braintige.online |
| cards-game-staging | api+postgres+grafana+prometheus | pg dump ✅ | (sparkcards?) |
| mtproxy / mtproxy-2053 | Telegram MTProto proxy | конфиг/secret | — |
| /var/www | marketbox, sparkcards.space, sparkcards-play, cards-staging, html, _assistant_graphs | ? | sparkcards.space и др. |
| /opt | assistant, claude-office, spark | ? код/данные | — |

## СТАТУС 2026-06-30 (после Фаз 0–1)
**Спасено всё незаменимое** (базы/секреты/конфиги/TLS/исходник cards) на Mac. **Поднято на ферме 194** (HTTP, ждёт DNS): Obsidian-vault (1879 док.), PWA (backend :8766 + фронт), cards-game (postgres 20 таблиц + api :8080, изолирован под проект `cards-staging`), статика sparkcards.space/sparkcards-play/cards-staging, nginx-vhosts всех доменов + acme-challenge. TLS-скрипт готов: `/root/issue-tls.sh` (запустить ПОСЛЕ DNS).
**Инцидент (исправлен):** cards-compose делил проект «docker» с Dify → ферма легла на ~15 мин → восстановлено (Dify 200, healthy), cards переведён на `-p cards-staging`. Урок → память `feedback_compose_project_collision`.
**Осталось (требует DNS от владельца):** переключить A-записи на 194 → `bash /root/issue-tls.sh` → проверить HTTPS/синк; тикет 62yun по диску 185; вывод 185.

## Tasks

### Фаза 0 — ДОЗАБРАТЬ ВСЁ с умирающего диска (СРОЧНО, пока читается)
- [ ] **M0.1** Снять полный инвентарь источника → файл на Mac: `docker ps -a`, `docker volume ls`, все `docker-compose.yml`/`.env`, `systemctl list-units`, `/etc/nginx/sites-*`, `crontab -l`, список доменов/секретов, `du -sh` ключевых каталогов.
- [ ] **M0.2** Спасти все docker-стеки (compose+env+Dockerfile) каждого проекта.
- [x] **M0.3** Базы: CouchDB-vault ✅, Postgres cards_game ✅, brain.db ✅.
- [ ] **M0.4** Tar+pull код/данные не из git: `/opt/{assistant,claude-office,spark}`, `/root/second-brain`, `/var/www/{marketbox,sparkcards.space,sparkcards-play,cards-staging,html,_assistant_graphs}` — **исключая** десятки `*.bak*`/`*.tar.gz`.
- [ ] **M0.5** Конфиги: `/etc/nginx`, systemd-юниты приложений, `/root/cert` (TLS) или план пере-выпуска acme, crontab, `/root/.*` секреты, mtproxy secret.

### Фаза 1 — Поднять стек на 194.5.65.182
- [ ] **M1.1** Проверить ресурсы/порты target (free RAM, занятые порты vs нужные: 80/443 nginx, couchdb 5984/5985, postgres, grafana 3000, prometheus 9090, mtproxy). Решить co-host vs новый VDS; при co-host — сдвинуть порты, отключить лишнее (grafana/prometheus опц.).
- [ ] **M1.2** CouchDB Obsidian: распаковать `obsidian-livesync` → docker compose up (порт без конфликта с couchdb фермы).
- [ ] **M1.3** cards-game: compose up postgres → восстановить `cards_game_staging.sql` → api (+опц. grafana/prometheus).
- [ ] **M1.4** PWA: код из git + venv + `python-multipart` + brain.db в `data/` + systemd unit + фронт в nginx.
- [ ] **M1.5** mtproxy: compose up + secret.
- [ ] **M1.6** nginx vhosts всех доменов + TLS (acme.sh пере-выпуск на target).

### Фаза 2 — DNS-переключение + проверка
- [ ] **M2.1** Переключить A-записи доменов (sync.second-braintige.online, PWA, sparkcards.space, …) на 194.5.65.182; дождаться TLS.
- [ ] **M2.2** Проверить каждый сервис вживую: PWA логин+запись БД, Obsidian LiveSync с устройства, cards-game, mtproxy, прочие сайты.

### Фаза 3 — Завершение
- [ ] **M3.1** Обновить память (SERVER.md/reference) — новый хост, порты, как восстановлено.
- [ ] **M3.2** Тикет в 62yun: диск 185 неисправен — снапшот/замена/возврат средств; после подтверждённой миграции — вывод 185 из эксплуатации.

→ **Checkpoint после Фазы 0:** все данные спасены — дальше можно не торопиться даже если 185 умрёт.
