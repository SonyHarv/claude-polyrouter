# Contributing to claude-polyrouter

Thank you for your interest in contributing to claude-polyrouter! This guide will help you get started.

## Getting Started

### Prerequisites

- Python 3.8+
- Claude Code CLI installed
- Git

### Local Setup

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/claude-polyrouter.git
cd claude-polyrouter

# 2. Install as a Claude Code plugin (for local testing)
claude plugin install --local .

# 3. Run the test suite
python -m pytest tests/ -v
```

### Project Structure

```
claude-polyrouter/
├── hooks/          # UserPromptSubmit routing hook
├── commands/       # Slash command implementations
├── skills/         # Skill definitions (stats, dashboard, etc.)
├── agents/         # Agent tier definitions (fast, standard, deep)
├── languages/      # Language pattern files (JSON)
├── hud/            # Status line HUD integration
├── tests/          # Test suite (pytest)
├── docs/           # Documentation
└── plugin.json     # Plugin manifest
```

## Reporting Bugs

Open an issue on GitHub with:

1. **Description** — What happened vs. what you expected
2. **Steps to reproduce** — Minimal query or sequence that triggers the bug
3. **Routing context** — Output of `/claude-polyrouter:config` and `/claude-polyrouter:stats`
4. **Environment** — OS, Python version, Claude Code version

Label the issue with `bug`.

## Suggesting New Languages

claude-polyrouter supports 10 languages via JSON pattern files. To add a new one:

1. Create `languages/<code>.json` following the existing format (e.g., `languages/es.json`)
2. Include:
   - `stopwords` — Common words for language detection scoring
   - `patterns` — Regex patterns grouped by tier (`fast`, `standard`, `deep`)
3. Add tests in `tests/` covering routing accuracy for the new language
4. The language is auto-discovered at runtime — no code changes needed

Open an issue first with the `language` label to discuss before starting work.

## Suggesting New Patterns

Routing patterns determine how queries map to model tiers. To improve or add patterns:

1. Identify misrouted queries (include examples in your issue or PR)
2. Add or modify regex patterns in the relevant `languages/<code>.json`
3. Ensure patterns don't regress existing routing — run the full test suite
4. Keep classification latency under 5ms

## Making a Pull Request

### Workflow

```bash
# 1. Create a feature branch from master
git checkout -b feat/my-feature

# 2. Make your changes
# 3. Add or update tests in tests/
# 4. Run the test suite
python -m pytest tests/ -v

# 5. Commit with conventional commit style
git commit -m "feat: add Hindi language support"

# 6. Push and open a PR against master
git push origin feat/my-feature
```

### PR Checklist

- [ ] Tests added or updated for all changes
- [ ] All existing tests pass (`python -m pytest tests/ -v`)
- [ ] Classification latency stays under 5ms
- [ ] PR description explains **why**, not just **what**
- [ ] One logical change per PR

### Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feat/<description>` | `feat/add-hindi-language` |
| Bug fix | `fix/<description>` | `fix/cjk-word-counting` |
| Refactor | `refactor/<description>` | `refactor/cache-layer` |
| Docs | `docs/<description>` | `docs/update-config-examples` |
| Tests | `test/<description>` | `test/arabic-routing-coverage` |

## Code Style & Conventions

### Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat:     New feature or capability
fix:      Bug fix
refactor: Code restructuring without behavior change
test:     Adding or updating tests
docs:     Documentation only
chore:    Maintenance, dependencies, CI
perf:     Performance improvement
```

### Python

- Follow PEP 8
- Use type hints for function signatures
- Keep functions focused — one responsibility per function
- Prefer `pathlib` over `os.path` for file operations
- Use `f-strings` for string formatting

### JSON Pattern Files

- Keep patterns readable — one pattern per line where possible
- Comment complex regex with a `_comment` field if needed
- Group patterns by tier: `fast`, `standard`, `deep`
- Test edge cases: short queries, mixed-language input, CJK characters

### Performance

- Routing must complete in under 5ms — this is a hard constraint
- Use pre-compiled regex (`re.compile`) for all patterns
- Leverage the two-level cache (memory + file) before classification
- Profile before optimizing — measure with `python -m pytest tests/ -v --durations=10`

## Questions?

Open a [Discussion](https://github.com/SonyHarv/claude-polyrouter/discussions) or reach out via an issue. All contributions are welcome — from typo fixes to new language support.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
