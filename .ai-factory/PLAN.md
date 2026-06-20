# Plan: Глобальная code-intelligence связка (Serena + codegraph)

- **Mode:** fast (без git-ветки — правки идут в `~/.claude` и системные тулзы, не в репо)
- **Created:** 2026-06-04
- **Scope:** вся машина (user scope) + бутстрап всех 12 git-репо в `~/Documents/projects`

## Settings

- **Testing:** встроенная верификация после каждого шага (требование пользователя: «после каждого шага проверяй результат, не переходи дальше при ошибке»)
- **Logging:** verbose — показывать полный вывод каждой install/verify команды
- **Docs:** да — секция в глобальном `~/.claude/CLAUDE.md` (задача 6)
- **Constraint:** строго последовательно, СТОП при ошибке любого шага (кроме задачи 7: ошибка в одном репо логируется, остальные продолжаются)

## Текущее состояние (разведка 2026-06-04)

| Компонент | Состояние |
|---|---|
| `uv` | ✅ 0.11.16 (Homebrew) — установка uv пропускается |
| `serena` | ❌ нет |
| `codegraph` | ❌ нет |
| `python3.13` | нет в PATH — uv скачает сам |
| `jq` | ✅ `/usr/bin/jq` |
| user-scope MCP | пусто `[]` |
| `~/.claude/settings.json` | есть `hooks.Stop[0].hooks = [afplay Glass.aiff]` → **строго merge, не перезапись** |
| `~/.claude/CLAUDE.md` | секции Code intelligence нет |

## Tasks

### Phase 1 — Serena (LSP MCP)

- [x] **1. Установить serena-agent** — `uv tool install -p 3.13 serena-agent` → verify `serena --version`. Если не в PATH: `uv tool update-shell` / проверить `~/.local/bin`.
- [x] **2. Зарегистрировать Serena MCP (user scope)** — `claude mcp add --scope user serena -- serena start-mcp-server --context claude-code --project-from-cwd` → verify `claude mcp list`. (blocked by 1)

### Phase 2 — codegraph (CLI + MCP)

- [x] **3. Установить codegraph CLI** — `curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh` → verify `codegraph --version` (бинарь в `~/.local/bin`).
- [x] **4. Зарегистрировать codegraph MCP глобально** — `codegraph install -y --target claude --location global` → verify запись MCP + auto-allow. (blocked by 3)

### Phase 3 — Конфигурация Claude Code

- [x] **5. Stop-hook авто-реиндексации** — merge в `~/.claude/settings.json` `hooks.Stop[0].hooks` элемента `{"type":"command","command":"[ -d .codegraph ] && \"$HOME/.local/bin/codegraph\" sync >/dev/null 2>&1; exit 0","async":true,"statusMessage":"codegraph sync"}` с сохранением существующего afplay-хука. Валидация: `jq -e '.hooks.Stop'` + валидный JSON. Pipe-тест после задачи 7. (blocked by 3)
- [x] **6. Секция в глобальном `~/.claude/CLAUDE.md`** — «# Code intelligence (Serena + codegraph — все проекты)»: routing (правишь символ → Serena; смысл/impact → codegraph; точечный паттерн → Grep), субагенты без MCP → codegraph CLI через Bash, тесты из `impact` (пустому `affected` не доверять), Stop-hook автоматический, проектная routing-матрица главнее.

### Phase 4 — Per-project бутстрап (по решению пользователя: ВСЕ репо)

- [x] **7. `codegraph init -i` в 12 репо** — 21crush-backend, 21crush-frontend, 7saber-front, capsula-app, dify-farm, gidweb-main, marketbox, mobile, personal-assistant, second-brain-web, second-brain, spark. Ошибка в одном репо → лог + продолжить; в конце сводка. Уточнить у пользователя: `.serena/`/`.codegraph/` в `.gitignore` или коммитить (фраза в задании обрезана). (blocked by 3)

### Phase 5 — Верификация

- [x] **8. Финальная верификация** — `claude mcp list` (serena+codegraph, user scope); `codegraph status` в second-brain; `codegraph impact run_agent`; pipe-тест Stop-hook; Explore-субагент с `codegraph callers <symbol>` через Bash; сообщить пользователю о необходимости рестарта сессии для MCP. (blocked by 2,4,5,6,7)

## Риски / заметки

- MCP-серверы покажут «Connected» только после рестарта сессии — на шагах 2/4 проверяем факт регистрации, не коннект.
- `codegraph init -i` на 12 репо может быть долгим (индексация) — гнать последовательно с логом по каждому.
- settings.json: перед правкой Read, после — jq-валидация; при битом JSON ломаются ВСЕ хуки, поэтому откат обязателен при ошибке.
- Названия URL/команд codegraph взяты из задания пользователя как есть; если install.sh недоступен (404) — СТОП и спросить пользователя.
