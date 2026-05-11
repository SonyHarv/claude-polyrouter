# claude-polyrouter — Project Instructions (v1.6.2)

Contexto permanente para chats de Claude.ai. Este documento resume el estado, la arquitectura y la filosofía del plugin `claude-polyrouter`. Si algo contradice lo que veas en el repo, **confía en el repo** y anota la discrepancia.

---

## 1. Estado actual (v1.6.2)

- **Versión publicada:** `1.6.2` (hotfix sobre 1.6.1 que arregla el string `[poly v1.6]` → `[poly v1.6.2]` en el HUD). Fuente: `plugin.json:3`, `hud/polyrouter-hud.mjs:227`, `CHANGELOG.md` entrada `[1.6.2]`.
- **Tests:** `613 tests collected` vía `pytest tests/ --collect-only` (confirmado en vivo). El badge del README dice `613 passed` (coincide).
- **Precisión (v1.6.1 corpus, `tests/fixtures/accuracy_corpus.json` v1.6.1, 214 prompts):**
  - Routing accuracy global: **98.1 %** (210/214).
  - Effort accuracy: **100.0 %** (97/97 prompts `deep` con `expected_effort`).
  - Per-language accuracy ≥ 97 % en los 10 idiomas.
  - **Nota:** la memoria previa decía 95.9 % effort / 98.1 % overall; el repo registra **100 % effort** en `CHANGELOG.md` para 1.6.1 y el README muestra el badge "effort accuracy 100%". Se actualiza la cifra.
- **Reducción de tokens:** 82 % sobre el `additionalContext` (vs v1.3), medida en ~27 tokens por query.
- **Idiomas soportados (10):** `en, es, pt, fr, de, ru, zh, ja, ko, ar` + detección Spanglish (en+es).
- **Tiers (3) + sub-effort dinámico:**
  - `fast` → Haiku 4.5 (`claude-haiku-4-5`) · effort `low`
  - `standard` → Sonnet 4.6 (`claude-sonnet-4-6`) · effort `medium`
  - `deep` → Opus 4.7 (`claude-opus-4-7`) · effort `medium` / `high` / `xhigh`
- **Agents incluidos (4):** `fast-executor`, `standard-executor`, `deep-executor`, `opus-orchestrator` (ver `plugin.json:14-19`).
- **Slash commands (10):** `/polyrouter:route`, `stats`, `dashboard`, `config`, `learn`, `learn-on`, `learn-off`, `knowledge`, `learn-reset`, `retry`.
- **Latencia de clasificación:** < 5 ms objetivo (pure-rules, regex precompiladas).

---

## 2. Arquitectura y archivos clave

### Pipeline del router (8 etapas)

`prompt (stdin JSON)` → `classify-prompt.py`:

1. **Exception check** (`_stage_exception_check`) — slash commands, queries vacías, meta-queries (`polyrouter`, `routing`, `router`), continuation tokens (`ok`, `dale`, `sí`, `go`, …).
2. **Intent override** (`lib/intent_override.py`) — "use opus", "usa haiku" → tier forzado, prioridad máxima.
3. **Cache lookup** — fingerprint SHA → L1 LRU (50 entradas) + L2 file (`~/.claude/polyrouter-cache.json`, 100 entradas, TTL 30 d). Cache hits reproducen `effort` + `advisor` desde 1.5.
4. **Language detection** (`lib/detector.py`) — scoring por stopwords con "sticky language" si coincide con la última detectada.
5. **Pattern extraction** (`lib/classifier.py`) — conteo crudo de signals por idioma, sin decidir tier.
6. **Multi-signal scoring** (`lib/scorer.py`) — combina `patterns` (0.70 max), `structural` (0.25), `universal` (0.20), `context` (0.10) en un score 0.0-1.0+. Umbrales: `fast < 0.35`, `standard < 0.65`, `deep ≥ 0.65`.
7. **Architectural promotion** (`effort.maybe_promote_to_deep_xhigh`) — si hay match en `arch_patterns` + ≥1 signal std/tool/orch, **promueve a `deep`** (luego stage 9 lo marcará `xhigh`).
7b. **Multi-file refactor promotion** (`effort.maybe_promote_multifile_refactor`) — verbo refactor + ≥2 archivos **o** cuantificador multi-archivo ("across 3 files", "em vários módulos") → promueve `standard → deep+high`.
8. **Context boost** — follow-up detection (`lib/context.py`) sube confianza en queries encadenados.
9. **Learned adjustments** — KB opcional por proyecto (`learnings/`) aplica ajustes de keyword.
10. **Dynamic deep effort** (`effort.compute_deep_effort`) — para tier `deep` calcula `medium` / `high` / `xhigh` según score, deep/std/tool/orch signals, archivos y code blocks, **usando `arch_patterns` del idioma detectado**.
11. **Advisor flag** — `xhigh` → `requires_advisor=true` (surface `adv` en HUD).

### Mapa de archivos clave

| Archivo | Propósito |
|---|---|
| `plugin.json` | Manifiesto (version, agents, metadata). |
| `hooks/hooks.json` | Registra `UserPromptSubmit`, `PostToolUse`, `SessionStart`, `SubagentStop`. |
| `hooks/classify-prompt.py` | Orquestador del pipeline (631 líneas). |
| `hooks/cache-keepalive.py` | PostToolUse — detecta expiración del prompt cache (50 min). |
| `hooks/subagent-stop.py` | Limpia `subagent_active=false`. |
| `hooks/check-update.py` | SessionStart — notificación de updates. |
| `hooks/lib/classifier.py` | `extract_signals()`, `compile_patterns()`. |
| `hooks/lib/scorer.py` | Motor multi-signal: `compute_score`, `score_to_tier`. |
| `hooks/lib/effort.py` | `compute_effort`, `compute_deep_effort`, promotion helpers, carga de `arch_patterns` con fallback EN. |
| `hooks/lib/detector.py` | Stopword language detection. |
| `hooks/lib/intent_override.py` | "use opus" / "force haiku" — prioridad máxima. |
| `hooks/lib/cache.py` | LRU + file cache con fingerprinting. |
| `hooks/lib/context.py` | `SessionState` (persistencia en `~/.claude/polyrouter-session.json`). |
| `hooks/lib/compact.py` | Advisory para `/compact`. |
| `hooks/lib/limits.py` | Lectura opcional de `ccusage`. |
| `hooks/lib/learner.py` | KB de aprendizaje por proyecto. |
| `hooks/lib/stats.py` | Stats + savings cumulativo. |
| `hud/polyrouter-hud.mjs` | **HUD** (429 líneas). Parsea stdin CC, fallback OMC cache, renderiza. |
| `languages/<code>.json` | Stopwords + `patterns.fast/standard/deep` + `arch_patterns` + `follow_up_patterns`. |
| `languages/schema.json` | Esquema JSON para validación. |
| `tests/fixtures/accuracy_corpus.json` | Corpus v1.6.1 (214 prompts) con `expected_tier` + `expected_effort`. |
| `scripts/poly-accuracy.py` | Runner del corpus → matriz de confusión. |
| `scripts/post-install.sh` | Auto-inyecta hook en `settings.json`. |
| `agents/*.md`, `commands/*.md` | 4 executors + 10 slash commands. |

### Data-flow del HUD

```
Claude Code → stdin JSON (statusLine event)
             ├─ context_window.used_percentage      → ctx:%
             ├─ rate_limits.five_hour               → 5h:%(rem)
             ├─ rate_limits.seven_day               → wk:%(rem)
             └─ exceeds_200k_tokens                 → ⚠compact

polyrouter-hud.mjs
   ├─ readStdin() + parseStdinJson()                 (PRIMARY)
   ├─ readJson(SESSION_PATH) [polyrouter-session]    (FALLBACK 1)
   ├─ readJson(OMC_USAGE_CACHE)                      (FALLBACK 2, sólo snt)
   │       .data.sonnetWeeklyPercent / resetsAt
   ├─ readJson(STATS_PATH)     → $savings↓
   ├─ readJson(COMPACT_PATH)   → advisory_active
   └─ execSync(OMC_HUD)        → prepend output
       → rendered statusline a stdout
```

Tiered hiding según ancho de terminal:
- `cols < 80`: sólo mascot + modelSeg + cache.
- `80 ≤ cols < 120`: añade `ctx`, `5h`, `wk`.
- `cols ≥ 120`: añade `snt`.

---

## 3. Decisiones técnicas importantes

1. **stdin JSON como fuente primaria de `ctx%` y `rate_limits`** (v1.6.1, commit `83ec4d3`). Antes todo venía de `polyrouter-session.json`; ahora Claude Code inyecta JSON en statusLine y el HUD lo parsea con `parseStdinJson()`. Sesión queda como fallback. Ver `hud/polyrouter-hud.mjs:221-267`.
2. **OMC Anthropic-API cache como fuente para `snt%`** (v1.6.1, commit `89116a1`). Claude Code stdin **no expone** `sonnet_weekly`; el HUD lee `~/.claude/plugins/oh-my-claudecode/.usage-cache-anthropic.json` → `data.sonnetWeeklyPercent` / `sonnetWeeklyResetsAt`.
3. **`arch_patterns` separados de `deep_patterns`** (v1.6.1, commit `3ab77d6`). Habilita `xhigh` en los 10 idiomas (JA/KO/ZH/AR/RU recibieron el parche). Todos tienen 4-6 patterns; carga lazy con `@lru_cache(32)` en `effort.py:_load_arch_re` y `_FALLBACK_ARCH_RE` EN para idiomas sin definir.
4. **Opus 4.7 pricing fix** (v1.6, commit `2e132d7`). Antes `$0.005/$0.025` (3× understated); ahora `$0.015/$0.075` por 1k tokens ($15/$75 por 1M, vigente abril 2026). Inflaba artificialmente el `$savings↓`.
5. **Savings calc per-token** (v1.6). `1 000 input + 500 output` tokens por prompt. Reemplaza `input + 2×output`.
6. **Threshold-based ANSI coloring** (v1.6.1, commit `ce09e3b`). Verde `<70%`, amarillo `70-89%`, rojo `≥90%`. Respeta `NO_COLOR` (`hud/polyrouter-hud.mjs:101-123`).
7. **xhigh es display-only.** `normalize_effort_for_env()` hace `xhigh → high` para `CLAUDE_CODE_EFFORT_LEVEL`; el HUD y la session sí muestran `xhigh`.
8. **Promoción arquitectural bidireccional.** Stage 7 eleva `standard → deep`; stage 10 marca ese deep como `xhigh`. Evita que "redesign the auth architecture" caiga en standard.
9. **Cache replay persiste effort + advisor** (v1.5, commit `a4868a6`).
10. **Idle fallback** (v1.6). Sesiones > 30 min emiten `[poly v1.6.2] [^.^]~ idle`.
11. **Hook auto-injection** (v1.3+). `scripts/post-install.sh` inyecta el hook en `~/.claude/settings.json` con `matcher` + nested `hooks`.
12. **Multi-file refactor promotion** (v1.6). Refactor verb (ES/EN/FR/DE/PT) + ≥2 archivos **o** qualifier multi-archivo → `deep+high` (nunca `xhigh`, que se reserva a scope arquitectural).

---

## 4. Formato HUD aprobado (con ejemplo)

### Formato canónico (v1.6.2)

```
[poly v1.6.2] <mascot> <model>·<tier>[·<effort>][·adv][ ⚠compact] │ [🤖N ]cache:<bar> [ctx:N%] │ [5h:N%(T)] [wk:N%(T)] [snt:N%(T)] │ [$X.XX↓] [<lang>]
```

Con subagent activo, el segmento de modelo se divide:

```
[poly v1.6.2] <mascot> prompt:<model>·<tier>[·<effort>] ⚙ exec:<execModel>·<execEffort>[·adv] │ 🤖N cache:<bar> ctx:N% │ ... │ $X.XX↓ <lang>
```

### Separadores

- Entre segmentos: ` │ ` (U+2502 "Box Drawings Light Vertical" + espacios, `SEP` en `hud/polyrouter-hud.mjs:31`).
- Dentro del model segment: `·` (U+00B7 middle dot) entre model, tier, effort, adv.
- Entre mascot y model: espacio simple.

### Orden de labels (izquierda → derecha)

1. **Prefix + mascot:** `[poly v1.6.2] <frame>` (color animado según estado).
2. **Model segment:** `prompt:haiku·fast` / `haiku·fast` / `opus·deep·xhigh·adv`. `medium` se elide.
3. **Exec segment** (solo si `subagent_active`): ` ⚙ exec:opus·xhigh·adv`.
4. **Compact advisory:** ` ⚠compact` inline cuando `ctx ≥ 70%` o `exceeds_200k_tokens`.
5. **Middle group:** `🤖N` (si hay subagents) → `cache:bar` → `ctx:N%`.
6. **Limits group:** `5h:N%(T)` `wk:N%(T)` `snt:N%(T)` (tiered por ancho de terminal).
7. **Tail:** `$X.XX↓` `<lang>`.

### Ejemplos renderizados reales (del README)

Sin subagent:
```
[poly v1.6.2] [^.^]~ haiku·fast │ cache:████░ ctx:8% │ 5h:45%(1h2m) wk:9%(6d19h) snt:3%(6d19h) │ $0.03↓ es
```

Con subagent:
```
[poly v1.6.2] [^.^]~ prompt:haiku·fast ⚙ exec:opus·xhigh·adv │ 🤖1 cache:████░ ctx:15% │ 5h:45%(1h2m) wk:9%(6d19h) snt:3%(6d19h) │ $9.50↓ es
```

Contexto alto (compact advisory):
```
[poly v1.6.2] [^.^]~ haiku·fast ⚠compact │ cache:████░ ctx:78% │ 5h:45%(1h2m) wk:9%(6d19h) │ $0.03↓ es
```

Idle (sesión > 30 min, sin OMC):
```
[poly v1.6.2] [^.^]~ idle
```

Ejemplo pedido por el usuario en formato compacto:
```
ctx 42% · snt 18% · opus · xhigh
```
— en el HUD real se rendería como `opus·deep·xhigh · cache:████░ ctx:42% · snt:18%(…)`.

### Umbrales de color ANSI (threshold-based, v1.6.1)

Aplicado a `ctx:N%`, `5h:N%`, `wk:N%`, `snt:N%` vía `colorPct()`:

| Rango | Color ANSI | Constante | Semántica |
|---|---|---|---|
| `< 70%` | Verde | `\x1b[32m` | normal |
| `70-89%` | Amarillo | `\x1b[33m` | warning |
| `≥ 90%` | Rojo | `\x1b[31m` | critical |

- La variable de entorno `NO_COLOR` (convención estándar) desactiva todo color.
- Los mascot states tienen colores truecolor independientes (hex → ANSI 38;2;R;G;B): `idle #afa9ec`, `routing #5dcaa5`, `danger #e24b4a`, `critical #e24b4a`, `ctx_high #e8853a`, etc. Ver `hud/polyrouter-hud.mjs:33-73`.

### Estados del mascot

| Estado | Frame principal | Trigger |
|---|---|---|
| `idle` | `[^.^]~` / `[^-^]` | default |
| `routing` | `[^o^]»` | últimos 3 s tras query |
| `thinking` | `[^.^]...` | 3-10 s tras query |
| `keepalive` | `[~_~]zzz` | cache elapsed > 40 min |
| `danger` | `[°O°]!!!` | cache elapsed > 50 min |
| `compact` | `[^.^]~~~` | `advisory_active` |
| `ctx_high` | `[>.^]` | `ctx ≥ 70%` |
| `critical` | `[x.x]` | `ctx ≥ 90%` ó cualquier limit `≥ 90%` |

---

## 5. Pendientes v1.7

Según `README.md` sección `Roadmap → v1.7 (planned)`, el scope declarado es:

- [ ] **Retry-escalation arrow en HUD** (ej. `fast → deep`). Mostrar visualmente cuando `/polyrouter:retry` escala tier.
- [ ] **Advisor hand-off protocol** — forma estandarizada de que los executors consulten al Advisor (Opus on-demand).
- [ ] **Effort override slash command** — `/polyrouter:effort <level>` para forzar el sub-effort desde el chat.

### Candidatos adicionales inferidos

- **Paridad `deep_patterns` por idioma.** EN/ES: 26; resto: 21-23. `arch_patterns` sí están parejos (4-6). Candidato: auditar a ~26 por idioma.
- **Corpus de tests asimétrico.** 214 prompts (v1.6.1) con EN/ES sobre-representados. Expandir a ≥120 por idioma.
- **Export CSV/JSON del dashboard.** Hoy sólo HTML Charts.js (listado en v2, candidato a adelantar).
- **Ultra tier.** Si Anthropic libera algo por encima de Opus 4.7 durante el ciclo, abrir el config.
- **Adaptive thresholds.** Hoy estáticos (`0.35` / `0.65`); `/polyrouter:learn-on` podría alimentarlos.
- **Coverage report.** 613 tests confirmados, pero no hay métrica de coverage publicada.

**Honestidad:** sólo los 3 bullets del README son scope firme de v1.7; lo demás es inferencia.

---

## 6. Filosofía del proyecto

Tagline del README:
> **Stop paying Opus prices for simple questions.** 82% less token waste, 10 languages at full parity, zero setup.

Principios fundacionales:

1. **Zero-config routing.** Prompt → router elige modelo + effort sin intervención. El hook `UserPromptSubmit` se auto-inyecta en `settings.json` al primer run.
2. **Cost-aware por defecto.** Default = `fast` (Haiku). Se escala sólo cuando signals lo justifican; `$savings↓` hace el ahorro visible por query.
3. **Paridad multilingüe.** Todos los idiomas tienen `patterns.fast/standard/deep` + `arch_patterns` + `follow_up_patterns`. Regla no-negociable: prompts equivalentes deben routear al mismo tier/effort en cualquier idioma. Cuando aparece desigualdad (ej. arch_patterns faltantes en JA/KO/ZH/AR/RU pre-1.6.1), se parche dedicado.
4. **Transparencia vía HUD.** El usuario siempre ve tier/model, effort, advisor, savings y estado de rate-limits/ctx. Cero costo de tokens: todo vive en `statusLine`, no en `additionalContext`.
5. **Rule-based, sin LLM en el hot path.** Regex pre-compilado + scoring aritmético → determinístico, auditable, gratuito, < 5 ms.
6. **Graceful degradation.** Sin `ccusage` el HUD oculta limits; sin OMC desaparece `snt%` pero `ctx/5h/wk` siguen vivos; cualquier stage que falle emite skip en lugar de romper la sesión (cada etapa envuelta en `try/except`).
7. **Separación de concerns.** `classify-prompt.py` decide; HUD refleja; session es el bus; agents ejecutan. El router nunca ejecuta; los agents nunca deciden.
8. **Configuración sin cambios de código.** Modelo nuevo → editar `levels.*.model_id` en `config.json`. HUD muestra el nombre compacto (`haiku`/`sonnet`/`opus`); el env var usa el `model_id` pinneado.

---

## 7. Contexto de desarrollo (decisiones de conversación)

### Filosofía de routing — aclaraciones clave
- **No "conservador"** — poly no limita opus, sino que lo usa **inteligentemente**. Opus cuando genuinamente lo necesita, con effort proporcional a la complejidad real.
- **Opus 4.7 adaptive thinking** usa más tokens que 4.6 — el effort que poly establece es la única señal que el modelo recibe para calibrar cuánto pensar.
- **xhigh en producción** se envía como `high` a CC (no existe nativo) pero activa `requires_advisor=true` internamente.

### Pendientes v1.7 adicionales (de conversación)
1. `snt%` nativo sin OMC — actualmente depende de OMC cache (`~/.claude/plugins/oh-my-claudecode/.usage-cache-anthropic.json`)
2. Tier `max` encima de xhigh — solo para sesión actual (Boris Cherny tip, abril 2026)
3. `sonnet·high` antes que `opus·medium` cuando tarea no es arquitectural
4. Historial routing por sesión (80% haiku, 15% sonnet, 5% opus)
5. Corpus 300+ prompts
6. Ahorro tokenizer 4.7 x1.35
7. Soul Map integración tipo SoulForge

### CC updates relevantes para poly
- v2.1.117: arregló Advisor Tool (flag `adv` ya estable)
- v2.1.118: hooks pueden invocar MCP tools directamente — usar para snt% nativo en v1.7
- v2.1.119: `/config` persiste a settings.json respetando precedencia

### Stack del desarrollador
- Linux Mint, Claude Code v2.1.119, OMC v4.12.0, Max plan
- Repo: github.com/SonyHarv/claude-polyrouter
- HUD real actual: `[poly v1.6.2] [^.^]~ prompt:haiku·fast │ cache:█████ ctx:11% │ 5h:49%(3h16m) wk:16%(6d17h) snt:12%(6d17h) │ $32.00↓ es`

Saved to `/home/sonyharv/projects/claude-polyrouter/docs/PROJECT_INSTRUCTIONS.md`.
