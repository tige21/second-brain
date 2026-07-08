# Разморозка цепочки vault → CouchDB → PWA на ферме 194

**Created:** 2026-07-04
**Type:** fix / ops-runbook
**Branch:** main (конвенция репо — планы без веток; код этого репозитория не меняется)
**Mode:** full

## Проблема (диагностировано 2026-07-04)

Сквозная синхронизация занятий заморожена с момента миграции 185→194 (~1 июля). Цепочка:
Lesson Scribe → `~/Documents/SecondBrain/raw/…md` → **Obsidian LiveSync** → CouchDB(`personal_vault`) на 194 → **PWA** `vault_process.py` генерит `wiki/…md` («граф») → приложение/телефон.

**Где рвётся:** при восстановлении `personal_vault` из бэкапа потерялся `_local/…milestone` (сейчас HTTP 404). Для LiveSync это «remote пересоздан» → плагин на Mac встаёт в mismatch/lock и не реплицирует. Итог: `personal_vault` заморожен на seq=1879 (снимок 30 июня), новые уроки не уезжают, PWA видит старьё.

**Факты:**
- CouchDB на 194 жив (HTTPS/TLS/auth ок). PWA (`pwa_provisioner`) активно читает `personal_vault`.
- Две базы: `personal_vault` (1879 доков, plaintext, источник PWA — **живая**) и `obsidian` (22 дока, старый обфусцированный формат, milestone от 25 мая — **мусор**).
- Последний урок в vault — **1 июля** (подтверждено владельцем). Lesson Scribe НЕ сломан — новых занятий после 1 июля не было. Задача (c) = проверка готовности, не починка.
- Контейнер `obsidian-couchdb` = `unhealthy` (healthcheck curl без кред → 401), косметика.

## Settings

- **Testing:** ручная верификация по логам/curl (автотесты неприменимы — ops). Ключевой критерий T3: `personal_vault` update_seq > 1879 + milestone восстановлен.
- **Logging:** наблюдение за `docker logs obsidian-couchdb` и `journalctl -u second-brain-pwa` на 194.
- **Docs:** yes — по завершении обновить SERVER.md + память (T9).

## Границы ответственности

- **Я (сервер/Mac-CLI):** T1, T3, T5, T6, T7, T8, T9 + наблюдение в T2/T4.
- **Владелец (GUI Obsidian, я кликать не могу):** T2 (Mac), T4 (телефон).
- 🚨 Нигде не жать **rebuild/overwrite remote** в LiveSync (→ 401/потеря данных, `feedback_livesync_config_mismatch`). Только «Apply settings to this device, and fetch again».
- 🚨 Любой `docker compose` на ферме — строго с `-p`, без `--remove-orphans` (co-host с Dify, `feedback_compose_project_collision`).

## Tasks

### Фаза 1 — Разморозить Mac ↔ сервер (главное)
- **T1** ✅ Baseline снят (15:09Z): personal_vault seq=1879/milestone=404, obsidian=22 доков, внешних записей 0. *(server, я)*
- **T2** Mac → Obsidian LiveSync: проверить remote DB = `personal_vault`, выполнить «Apply settings + fetch again» (НЕ rebuild). *(GUI, владелец; я слежу за логом)* — blockedBy T1
- **T3** Верификация: personal_vault seq > 1879, появился `raw/…/2026-07-01-lesson.md`, milestone восстановлен (был 404). *(server, я)* — blockedBy T2

### Фаза 2 — Телефон + «граф» PWA
- **T4** Телефон: «Apply settings + fetch again», проверить приём свежих заметок. *(GUI, владелец; я слежу)* — blockedBy T3
- **T5** PWA: убедиться, что `vault_process` переработал новые raw→wiki (journalctl, CHANGELOG/INDEX, новый wiki-урок), подтвердить отображение в приложении. *(server, я)* — blockedBy T3

### Фаза 3 — Housekeeping + фиксация
- **T6** Бэкап (дамп в /root/backups) + `DELETE` базы `obsidian`. *(server, я)*
- **T7** Починить healthcheck `obsidian-couchdb`. Диагноз: `/_up` даёт 401 (глоб. `require_valid_user=true`). Фикс: `require_valid_user_except_for_up = true` в local.ini → пересоздать контейнер. **Применение отложено на ПОСЛЕ T3/T4** (пересоздание оборвёт переподключку). *(server, я)*
- **T8** ✅ Lesson Scribe найден: код `/Users/macbook/lesson-scribe`, данные `/Users/macbook/lesson-scribe-data/`, пишет в `~/SecondBrain/raw/learning/english/`. Ключ+модель заданы, транскрипция ок. Урок 1 июля = `structuring-failed` (LLM-вызов упал, вероятно квота OpenAI 429) — можно переструктурировать из `transcript.txt`. Память обновить в T9. *(local, я)*
- **T9** Обновить SERVER.md (две базы, obsidian удалена, грабля milestone-loss, healthcheck) + память project_vault_couch_pipeline; коммит в main. *(docs, я)* — blockedBy T5, T6, T7, T8

## Commit Plan

Код этого репозитория не меняется — единственный коммит в конце (T9): изменения в `SERVER.md` (+ при необходимости `second-brain-web`). Прочие задачи — операции на сервере/GUI, без коммитов сюда.

- **Commit 1 (после T9):** `docs(no-ref): livesync personal_vault sole live DB, obsidian removed, migration milestone-loss caveat`

## Порядок исполнения

Критический путь: **T1 → T2 → T3 → (T4 ∥ T5)**. T6/T7/T8 независимы — можно параллельно в любой момент. T9 — финал.
Старт: T1 (я снимаю baseline и включаю лог), затем ты жмёшь «fetch again» на Mac (T2).
