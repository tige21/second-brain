# Project Rules for /aif-plan

> Конвенция personal-assistant: «план → сразу aif-implement в боте».

## Rules

### План коммитится и пушится сразу после сохранения
**Source**: конвенция personal-assistant (план, составленный на компьютере, должен быть мгновенно доступен боту на VPS — его pre-run pull подтягивает клон перед каждым раном)
**Rule**: Сразу после записи plan-файла (fast: `.ai-factory/PLAN.md`, full: `.ai-factory/plans/<stem>.md`) ОБЯЗАТЕЛЬНО зафиксируй его в git:
1. `git add <только сам plan-файл>` — никогда `git add -A`, чтобы не подхватить чужие незакоммиченные правки;
2. `git commit -m "plan: <slug фичи>"`;
3. `git push origin <текущая ветка>`; если push отклонён — `git pull --rebase` и повтори push ровно один раз.
Best-effort: нет origin — только commit без push; нет git-репо — пропусти шаг без ошибки. После пуша можно сразу писать боту «aif-implement» — он выполнит готовый план.
