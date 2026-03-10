<div align="center">

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&size=22&duration=3000&pause=1000&color=4CBB17&center=true&vCenter=true&random=false&width=600&lines=Building+ISTINA;Conflict+Intelligence+Engine;Truth+Through+Data)](https://github.com/mufferio/istina)

# Istina

**Conflict-tracking and bias-aware news aggregator.**  
Ingest articles · Detect AI-powered bias · Surface conflicting narratives

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red)
![Tests](https://img.shields.io/badge/tests-626%20passing-brightgreen)

</div>

---

Istina is a CLI-first prototype that ingests news articles, analyzes them for bias using external AI services (e.g. Google Gemini), and surfaces conflicting narratives across sources. Built with a clean Model-View-Controller (MVC) architecture and extensible design patterns (Command, Factory, Visitor), Istina is designed to grow into a full web + mobile platform.

## Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Requirements](#-requirements)
- [Configuration](#-configuration)
- [CLI Commands](#-cli-commands)
- [AI Providers](#-ai-providers)
- [Architecture](#-architecture)
- [Storage Format](#-storage-format-cli-v0)
- [Running Tests](#-running-tests)
- [RSS Feeds](#-rss-feeds)
- [Gemini Live Tests](#-gemini-live-smoke-tests-optional)
- [License](#license)

---

## 🚀 Features

- 📰 Ingest articles from RSS feeds
- 🤖 Analyze articles using AI-based bias detection
- ⚖️ Track conflicting narratives across multiple sources
- 📊 Summarize or export bias/conflict reports
- 🧩 Swappable AI provider integration via factory pattern
- 💾 JSONL file persistence with schema versioning
- 💻 CLI-first design, built for eventual web + mobile expansion

---

## ⚡ Quick Start

> No API key required — the built-in `mock` provider works out of the box.

```bash
# 1. Clone the repository
git clone https://github.com/mufferio/istina.git
cd istina

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies and the package in editable mode
pip install -r requirements.txt
pip install -e .

# 4. Run a full pipeline
python main.py ingest --feeds "http://feeds.bbci.co.uk/news/rss.xml"
python main.py analyze --limit 5
python main.py summarize
```

> Articles are stored in `data/articles.jsonl` by default. To use in-memory storage only (no disk writes), set `ISTINA_REPO_TYPE=memory`.

---

## 📦 Requirements

| Requirement      | Version            |
|:-----------------|:-------------------|
| Python           | ≥ 3.11             |
| pip dependencies | `requirements.txt` |

All Python dependencies are installed with:

```bash
pip install -r requirements.txt
pip install -e .
```

---

## ⚙️ Configuration

All settings are controlled by **environment variables** or a `.env` file placed in the project root.

| Variable                | Default            | Description                                                        |
|:------------------------|:-------------------|:-------------------------------------------------------------------|
| `ISTINA_REPO_TYPE`      | `file`             | `file` — persist to disk; `memory` — in-process only              |
| `ISTINA_DATA_DIR`       | `./data`           | Directory for JSONL files (only when `ISTINA_REPO_TYPE=file`)      |
| `ISTINA_PROVIDER`       | `mock`             | AI provider: `mock`, `gemini`                                      |
| `ISTINA_ENV`            | `dev`              | Runtime environment: `dev`, `test`, `prod`                         |
| `ISTINA_LOG_LEVEL`      | `INFO`             | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`                    |
| `ISTINA_RATE_LIMIT_RPM` | `60`               | Max AI provider calls per minute                                   |
| `ISTINA_GEMINI_API_KEY` | *(empty)*          | Required only when `ISTINA_PROVIDER=gemini`                        |
| `ISTINA_GEMINI_MODEL`   | `gemini-2.5-flash` | Gemini model name                                                  |

**Example `.env` file:**

```dotenv
ISTINA_REPO_TYPE=file
ISTINA_DATA_DIR=./data
ISTINA_PROVIDER=mock
ISTINA_LOG_LEVEL=INFO
```

---

## 🖥️ CLI Commands

All commands follow the pattern: `python main.py <command> [options]`

---

### `ingest` — Fetch RSS feeds and store articles

```bash
python main.py ingest --feeds <URL> [<URL> ...]
```

| Flag      | Description                           |
|:----------|:--------------------------------------|
| `--feeds` | One or more RSS feed URLs (required)  |

**Examples**

```bash
# Single feed
python main.py ingest --feeds "http://feeds.bbci.co.uk/news/rss.xml"

# Multiple feeds
python main.py ingest \
  --feeds "http://feeds.bbci.co.uk/news/rss.xml" \
          "https://www.aljazeera.com/xml/rss/all.xml"
```

---

### `analyze` — Run bias analysis on stored articles

```bash
python main.py analyze [--limit N] [--source SOURCE] [--since ISO_DATE]
```

| Flag             | Description                                            |
|:-----------------|:-------------------------------------------------------|
| `--limit N`      | Cap the number of articles to analyze                  |
| `--source SOURCE`| Filter by source name (e.g. `"BBC News"`)              |
| `--since DATE`   | Only analyze articles published after this date        |

**Examples**

```bash
python main.py analyze                         # all unscored articles
python main.py analyze --limit 10              # cap at 10
python main.py analyze --source "BBC News"     # BBC only
python main.py analyze --since 2026-03-01      # published after 2026-03-01
```

---

### `summarize` — Print a bias report

```bash
python main.py summarize [--report summary|full] [--source SOURCE] [--limit N] [--article-id ID]
```

| Flag               | Description                                          |
|:-------------------|:-----------------------------------------------------|
| `--report`         | Report style: `summary` (default) or `full`          |
| `--source SOURCE`  | Filter report by source name                         |
| `--limit N`        | Number of articles to include                        |
| `--article-id ID`  | Show report for a single article                     |

**Examples**

```bash
python main.py summarize                            # default summary
python main.py summarize --report full              # per-article detail
python main.py summarize --report full --limit 5    # top 5 in full detail
```

---

### Global flags

| Flag            | Effect                                                        |
|:----------------|:--------------------------------------------------------------|
| `--debug`       | Print full stack traces instead of friendly error messages    |
| `-h` / `--help` | Show usage for any command                                    |

---

## 🤖 AI Providers

Istina routes every `analyze` run through a **provider**, selected by the `ISTINA_PROVIDER` environment variable.
Providers are swappable — the rest of the application never changes when you switch between them.

### Available providers

| Provider | `ISTINA_PROVIDER` value | API key required | Notes |
|:---------|:------------------------|:-----------------|:------|
| **Mock** | `mock` | No | Deterministic offline analysis — identical input always produces identical output. Use for development and CI. |
| **Gemini** | `gemini` | Yes (`ISTINA_GEMINI_API_KEY`) | Calls Google Gemini API for real bias detection and claim checking. |

---

### Mock provider (default)

No configuration required — works immediately after install.

```bash
# ISTINA_PROVIDER defaults to mock, so this is all you need:
python main.py ingest --feeds "http://feeds.bbci.co.uk/news/rss.xml"
python main.py analyze --limit 5
python main.py summarize
```

The mock provider uses a deterministic heuristic (keyword matching + SHA-256 of the article ID)
to produce stable `BiasScore` results — same article always gets the same label and confidence score.
There are no network calls and no rate limits to worry about.

---

### Gemini provider

**1. Get an API key**

Create a free key at [Google AI Studio](https://aistudio.google.com/app/apikey).

**2. Set the environment variables**

```dotenv
# .env (project root)
ISTINA_PROVIDER=gemini
ISTINA_GEMINI_API_KEY=your_api_key_here
ISTINA_GEMINI_MODEL=gemini-2.5-flash   # optional — this is the default
ISTINA_RATE_LIMIT_RPM=60               # optional — requests per minute cap
```

Or export them inline for a one-off run:

```bash
# Windows (PowerShell)
$env:ISTINA_PROVIDER       = "gemini"
$env:ISTINA_GEMINI_API_KEY = "your_api_key_here"

# macOS / Linux
export ISTINA_PROVIDER=gemini
export ISTINA_GEMINI_API_KEY=your_api_key_here
```

**3. Run the pipeline**

```bash
python main.py ingest --feeds "http://feeds.bbci.co.uk/news/rss.xml"
python main.py analyze --limit 10
python main.py summarize --report full
```

Each article triggers **two** Gemini API calls — one for rhetorical bias scoring and one for claim extraction. The built-in rate limiter (`ISTINA_RATE_LIMIT_RPM`) prevents exceeding the free-tier quota.

**What Gemini returns (per article):**

| Field | Description |
|:------|:------------|
| `overall_bias_label` | `left`, `center`, `right`, or `unknown` |
| `rhetorical_bias` | List of detected flags, e.g. `loaded_language`, `appeal_to_fear` |
| `claim_checks` | List of extracted claims with verdicts (`true`, `false`, `mixed`, `unverified`, `insufficient evidence`) |
| `confidence` | Float in `[0.0, 1.0]` |

---

### Adding a new provider

All providers implement the [`BaseProvider`](src/istina/model/providers/base_provider.py) interface — a single method:

```python
def analyze_article(self, article: Article) -> BiasScore:
    ...
```

To wire in a new provider:
1. Create `src/istina/model/providers/your_provider.py` implementing `BaseProvider`.
2. Add a branch in [`src/istina/model/providers/provider_factory.py`](src/istina/model/providers/provider_factory.py).
3. Add the new name to `valid_providers` in [`src/istina/config/settings.py`](src/istina/config/settings.py).

No changes to services, commands, or the CLI controller are needed.

---

## 🧱 Architecture

Istina follows a layered MVC architecture with several design patterns.

### Layers

| Layer          | Responsibility                                                         |
|:---------------|:-----------------------------------------------------------------------|
| **Model**      | Domain objects (`Article`, `BiasScore`, `Conflict`), repositories, AI providers |
| **View**       | Terminal rendering of reports and summaries                            |
| **Controller** | CLI entry point; wires commands, services, and the repository          |

### Design Patterns

| Pattern         | Where it's used                                               |
|:----------------|:--------------------------------------------------------------|
| **Command**     | Each CLI action (`ingest`, `analyze`, `summarize`) is an isolated command object |
| **Factory**     | `ProviderFactory` selects the AI backend at runtime           |
| **Visitor**     | Scoring and export logic applied to articles/conflicts        |
| **Repository**  | Pluggable persistence — swap `MemoryRepository` ↔ `FileRepository` without touching business logic |

---

## 🗄️ Storage Format (CLI v0)

Istina persists data as **newline-delimited JSON** (JSONL) in the `data/` directory.
Each line is one complete, self-contained JSON object.

### Files

| File                    | Contents                        |
|:------------------------|:--------------------------------|
| `data/articles.jsonl`   | One `Article` record per line   |
| `data/bias_scores.jsonl`| One `BiasScore` record per line |

### Article record (`schema_version = 1`)

```json
{
  "schema_version":  1,
  "id":              "a3f8c2d...",
  "title":           "Gaza ceasefire talks resume in Cairo",
  "url":             "https://bbc.co.uk/news/world-middle-east-123456",
  "source":          "BBC News",
  "published_at":    "2026-03-04T12:00:00Z",
  "summary":         "Negotiators from both sides ..."
}
```

> `published_at` and `summary` may be `null`.

### BiasScore record (`schema_version = 1`)

```json
{
  "schema_version":     1,
  "article_id":         "a3f8c2d...",
  "provider":           "gemini",
  "overall_bias_label": "center",
  "rhetorical_bias":    ["loaded_language"],
  "claim_checks": [
    {
      "claim_text": "The ceasefire was unconditional.",
      "verdict":    "contradicted",
      "evidence":   ["https://reuters.com/..."]
    }
  ],
  "confidence":   0.87,
  "timestamp":    "2026-03-04T14:05:00",
  "raw_response": null
}
```

> `raw_response` may be `null`.

### Update Policies

| Entity      | Policy                                                                                                         |
|:------------|:---------------------------------------------------------------------------------------------------------------|
| `Article`   | **First write wins** — once an `id` is stored it is never overwritten                                          |
| `BiasScore` | **Latest write wins** — new records for the same `(article_id, provider)` are appended; only the last is kept on load. Call `FileRepository.compact()` to purge superseded lines |

### Atomicity

Full-file rewrites (e.g. `compact()`) write to a temporary file, then use `os.replace()`.
A crash mid-write will never leave a half-written file.

### Implementation

- Full implementation: [`src/istina/model/repositories/file_repository.py`](src/istina/model/repositories/file_repository.py)
- Smoke tests: [`tests/test_file_repository_roundtrip.py`](tests/test_file_repository_roundtrip.py)
- Integration tests: [`tests/test_repositories/test_file_repository.py`](tests/test_repositories/test_file_repository.py)

---

## 🧪 Running Tests

```bash
# Run the full test suite
pytest

# Verbose output
pytest -v

# Run a specific test file
pytest tests/test_repositories/test_file_repository.py -v

# Skip live API tests (fast mode — no API key needed)
pytest --ignore=tests/test_providers/test_gemini_live_smoke.py
```

The suite covers unit tests, integration tests, and round-trip persistence tests.
Live Gemini API tests are **automatically skipped** unless `ISTINA_GEMINI_API_KEY` is set.

---

## 🔌 RSS Feeds

The following feeds are used as reference fixtures for integration smoke tests
([`scripts/smoke_test_rss.py`](scripts/smoke_test_rss.py)):

| Outlet     | RSS URL                                                   |
|:-----------|:----------------------------------------------------------|
| BBC News   | `http://feeds.bbci.co.uk/news/rss.xml`                    |
| Al Jazeera | `https://www.aljazeera.com/xml/rss/all.xml`               |

Both feeds are confirmed to return HTTP 200, parse to valid `Article` objects with correct
`title`, `url`, and `source` fields, and produce ISO-8601 UTC `published_at` timestamps.

Run the smoke test manually at any time:

```bash
python scripts/smoke_test_rss.py
```

---

## 🤖 Gemini Live Smoke Tests (Optional)

Istina includes gated live integration tests that call the real Google Gemini API
to verify the full analysis pipeline end-to-end.

These tests are **optional** and **automatically skipped** unless an API key is set.

See [`docs/GEMINI_LIVE_TESTS.md`](docs/GEMINI_LIVE_TESTS.md) for full setup instructions, then run:

```bash
pytest tests/test_providers/test_gemini_live_smoke.py -v
```

---

## License

This project is **not open source.**  
The code is publicly visible for transparency and learning purposes only.  
All rights reserved.
