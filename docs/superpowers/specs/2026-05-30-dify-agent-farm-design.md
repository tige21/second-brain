# Dify AI Farm — Design Spec

**Date:** 2026-05-30
**Owner:** mregoryt@gmail.com
**Status:** Approved (design) → next: implementation plan via AI Factory (`/aif-plan`)

## 1. Goal

Stand up a **personal, self-hosted Dify "agent farm"**: multiple specialized AI agents,
each doing a different job, fully configurable through the Dify web portal (Studio),
reachable via Telegram. This is a **new, standalone sandbox** — the existing Second Brain
Telegram bot and the production VPS (83.x) are **not touched**.

Visualization (graph/game-style) is explicitly **out of scope for this phase** — revisit
after the farm works.

## 2. Scope

### In scope (5 agents)
| # | Agent | Job | Model (start) | Skills / tools |
|---|-------|-----|---------------|----------------|
| 1 | 🧭 Orchestrator / Classifier | Understand request, route to the right agent | Gemini Flash (cheap) | Question Classifier → routing |
| 2 | 🔎 Research | Web search, read pages, cited summaries | Gemini Flash | Web search (Tavily or SearXNG) + page reader |
| 3 | ✍️ Content / Email | Write posts, emails, summaries, translations in user's style | Claude Sonnet (quality) | Pure LLM + style variables |
| 4 | 🖼 Image / Poster | Generate images and basic posters | `gpt-image-1` (OpenAI) | Image-gen tool |
| 5 | 📊 Presentation | Build slide decks | GPT/Claude for content | Marp markdown → PPTX custom HTTP tool |

### Out of scope (YAGNI for this phase)
- Vault-RAG agent (not selected by user).
- 3D / game-style visualization (deferred).
- Multi-user / sharing (personal use only).
- Touching the existing Second Brain bot or prod 83.x.

## 3. Architecture decisions (approved)

- **Farm orchestration:** Dify **Workflow + Question Classifier** node routes intent into
  the correct agent branch. This *is* the visual farm graph; deterministic and cheap.
  (Rejected: agent-as-tool — more tokens, less predictable; external router — more moving parts.)
- **Presentations:** **Marp** (agent emits Marp markdown → custom HTTP tool renders PPTX/PDF).
  Free, self-hosted. (Rejected: python-pptx — more dev now; Gamma/SlidesGPT — paid + data leaves.)
- **Telegram topology:** **one bot per agent** (5 bots). A "main" orchestrator bot runs the
  classifier workflow and routes; each specialist also has its own direct bot. Each bot wired
  via the Dify **Telegram Trigger** plugin (auto webhook).
- **Models:** OpenAI (existing API key) + Gemini (new Google AI key) + Claude (new Anthropic
  API key, ~$5 starter). Cheap models for routine agents, Claude for quality.
  Note: the consumer claude.ai subscription (Pro/Max) **cannot** be used — Dify needs an
  Anthropic **API key**, billed per token, separate from the subscription.

## 4. Infrastructure

- **Host:** new dedicated VPS, **4–8 GB RAM**, always-on (user provisions and sends creds;
  add to `SERVER.md`). Existing VPS rejected: prod 83.x = 1.9 GB / 1 vCPU / no Docker / production;
  aux 185.x = 1.9 GB, already loaded (CouchDB + cards-game staging stack + mtproxy). Dify needs ~4 GB+.
- **Stack:** official Dify `docker compose` (API, worker, web, PostgreSQL, Redis, vector DB, sandbox)
  + **Langfuse** container (per-agent token/cost tracing) in the same compose project.
- **Networking:** nginx reverse proxy + TLS (Let's Encrypt) on a subdomain
  (e.g. `farm.second-braintige.online` or a new domain). HTTPS is required for Telegram webhooks.
- **Isolation:** entirely separate from prod 83.x; no shared services.

## 5. Data flow

```
Telegram user ──> [agent bot] ──(Telegram Trigger webhook)──> Dify
   main bot ───> Orchestrator Workflow ──(Question Classifier)──> branch:
                                                       ├─ Research agent ── web search tool
                                                       ├─ Content agent ── LLM + style vars
                                                       ├─ Image agent ──── gpt-image-1 tool
                                                       └─ Presentation ─── Marp→PPTX HTTP tool
   specialist bots ───> their agent directly
All invocations traced in Langfuse (tokens, latency, cost per agent).
```

## 6. Cost & controls

- Platform cost: **$0** (open-source, self-hosted). Pay only per-token API usage.
- Personal-use estimate: **a few $/month** on cheap models (Gemini Flash / GPT mini),
  more if Claude Sonnet is used heavily.
- Controls: Langfuse per-agent dashboard; default to cheap models; cap context/history length;
  Claude reserved for quality-critical steps.

## 7. Success criteria

1. Dify portal reachable over HTTPS on the VPS; admin workspace created.
2. All 3 model providers (OpenAI, Gemini, Claude) connected and tested.
3. 5 agents created and individually working in the Dify preview chat.
4. Orchestrator workflow correctly routes at least the 4 specialist intents.
5. Each agent reachable from its own Telegram bot end-to-end.
6. Marp→PPTX tool produces a downloadable deck from a prompt.
7. Image agent returns a generated image from a prompt.
8. Langfuse shows per-agent token/cost traces.

## 8. Open implementation questions (for the plan)

- Exact VPS provider/specs (pending user; likely VDSINA upgrade or new box).
- Domain/subdomain choice + DNS.
- Web-search tool: Tavily (API key, easy) vs SearXNG (self-host, free) — decide in plan.
- Marp render tool: containerized `marp-cli` behind a tiny HTTP wrapper (recommended) vs library.
