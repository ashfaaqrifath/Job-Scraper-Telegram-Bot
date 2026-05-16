# QA Job Daily Scraper

Runs every weekday at **10:07 WAT (09:07 UTC)** via GitHub Actions.
Searches remote QA / QA Automation job sources, filters them, and sends a
Telegram digest to your configured chat.

## What It Does

| Step | Detail |
|------|--------|
| **Sources** | Indeed, ZipRecruiter, We Work Remotely, Remotive, RemoteOK, Greenhouse, Lever, Jobright, Jobicy, Working Nomads |
| **Roles** | QA Engineer, QA Automation Engineer, SDET, Test Automation Engineer, Performance Test Engineer, Security Test Engineer |
| **Timezone filter** | Roles in UTC-1 to UTC+3, plus worldwide/global roles |
| **Salary gate** | At least NGN 2,000,000/month equivalent; undisclosed salaries are included |
| **Company signals** | Priority companies are sorted to the top |
| **Resume keywords** | Each job includes matched skills from the job description |
| **Deduplication** | Cross-source duplicates are removed |

## One-Time Setup

### 1. Create a Telegram bot

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`.
3. Follow the prompts.
4. Copy the bot token. It will look similar to:

```text
123456789:ABCdefYourBotTokenHere
```

### 2. Get your Telegram chat ID

1. Send any message to your new bot.
2. Open this URL in your browser, replacing `<BOT_TOKEN>`:

```text
https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
```

3. Look for:

```json
"chat":{"id":123456789}
```

4. Copy that `id`. That is your `TELEGRAM_CHAT_ID`.

For a group chat, add the bot to the group, send a message in the group, then use the same `getUpdates` URL.

### 3. Push this repo to GitHub

```bash
git remote add origin https://github.com/<YOUR_USERNAME>/QA-job-website-daily-scraping.git
git push -u origin main
```

### 4. Add repository secrets

Go to **Settings -> Secrets and variables -> Actions -> New repository secret** and add:

| Secret name | Value |
|-------------|-------|
| `TELEGRAM_BOT_TOKEN` | Bot token from `@BotFather` |
| `TELEGRAM_CHAT_ID` | Your Telegram user, group, or channel chat ID |
| `EXCHANGE_RATE_API_KEY` | Optional free key from exchangerate-api.com |

### 5. Test immediately

Go to **Actions -> Daily QA Job Telegram Digest -> Run workflow** to trigger a manual run.

## Run Locally

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r scripts\requirements.txt
$env:TELEGRAM_BOT_TOKEN="your_bot_token"
$env:TELEGRAM_CHAT_ID="your_chat_id"
python scripts\job_scraper.py
```

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── daily_job_scraper.yml
└── scripts/
    ├── job_scraper.py
    └── requirements.txt
```

## Customisation

| What to change | Where |
|----------------|-------|
| Add or remove job titles | `JOBSPY_QUERIES` list in `scripts/job_scraper.py` |
| Adjust timezone window | `ACCEPTED_TZ_TOKENS` and `is_timezone_ok()` |
| Change minimum salary | `MIN_NGN_MONTHLY` constant |
| Add priority companies | `PRIORITY_COMPANIES` set |
| Add skill keywords | `SKILL_KEYWORDS` list |
| Run on weekends too | Change `1-5` to `*` in the cron expression |

## Telegram Digest

Each job message includes:

- Job title, company, location, source, and date posted
- Type labels such as UI Automation, Performance, Security, API Testing, or Mobile
- Salary estimate in NGN/month
- Resume keyword matches
- Direct apply link
