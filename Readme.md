# AI-Powered Website Uptime Monitor

Real-time website monitoring that checks if sites are up or down, classifies the failure, and automatically fires a Claude AI agent to diagnose the root cause and generate a fix runbook — all saved to a SQLite database.

---

## What's Inside

| File | Purpose |
|---|---|
| `uptime_monitor.py` | Checks websites live, classifies errors, triggers AI on failures |
| `db_manager.py` | Query and manage your database in plain English |
| `code_manager.py` | Edit Python files in plain English with auto-backup |
| `logger.py` | Shared logging across all modules (file + database) |
| `log_analyzer.py` | AI-powered log reader and auto bug detector |

---

## Setup

```bash
git clone https://github.com/yourusername/uptime-monitor.git
cd uptime-monitor

python3 -m venv venv
source venv/bin/activate

pip install requests anthropic python-dotenv

cp .env.example .env
# Add your Anthropic API key to .env
```

Get a free API key at [console.anthropic.com](https://console.anthropic.com)

---

## Usage

**Monitor websites**
```bash
python3 uptime_monitor.py
# Enter URLs when prompted — AI analysis fires automatically on any failure
```

**Query your database**
```bash
python3 db_manager.py
# Ask anything: "show all DOWN incidents", "which site is slowest?", "add a notes column"
```

**Edit your code**
```bash
python3 code_manager.py
# Say what you want changed — see the diff, confirm, and it applies with auto-backup
```

**Analyze logs**
```bash
python3 log_analyzer.py
# Type "auto debug" — Claude reads logs + source code and finds bugs automatically
```

---

## How the AI Analysis Works

Every DOWN incident sends the full error context to Claude — not just the status code. Claude returns:

- **Root cause** — distinguishes bot blocking from a real outage
- **Severity** — LOW / MEDIUM / HIGH
- **User impact** — are real users affected?
- **Fix steps** — step-by-step runbook
- **Escalate?** — yes or no with reasoning

---

## Tech Stack

Python · SQLite · REST APIs · Claude AI API · python-dotenv · requests

