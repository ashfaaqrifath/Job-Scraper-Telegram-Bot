# QA Job Daily Scraper

Runs every morning, including weekends, at **08:37 Sri Lanka time (03:07 UTC)** via GitHub Actions.
Searches QA / QA Automation job sources, filters them for Sri Lanka-friendly fresh graduate roles, and sends a
Telegram digest to your configured chat.

## What It Does

| Step | Detail |
|------|--------|
| **Sources** | Indeed, ZipRecruiter, We Work Remotely, Remotive, RemoteOK, Greenhouse, Lever, Jobright, Jobicy, Working Nomads, Work at a Startup, Arbeitnow, Remote First Jobs, RemoteJobs.org, WorkAnywhere, Himalayas, HireWeb3 |
| **Roles** | QA Intern, QA Internship, Software QA Internship, Quality Assurance Internship, Trainee QA, Associate QA Engineer, Junior QA Engineer, Graduate QA Engineer, QA Engineer, Software Test Engineer, Automation QA Engineer |
| **Location filter** | Sri Lanka remote/hybrid/onsite roles, plus Sri Lanka-friendly remote roles |
| **Timezone filter** | Sri Lanka/India, APAC, Singapore, Australia/NZ, Middle East, UK/EU/EMEA, and worldwide/global roles |
| **Salary gate** | Disabled by default for fresh-grad roles; set `MIN_LKR_MONTHLY` if you want a minimum |
| **Role ranking** | Internships and trainee roles are sorted first; roles with experience requirements are pushed lower |
| **Company signals** | Priority companies are sorted near the top after role fit |
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
| `EXCHANGE_RATE_API_KEY` | Optional free key from exchangerate-api.com for LKR conversion |
| `MIN_LKR_MONTHLY` | Optional minimum monthly salary in LKR; omit or set `0` to include undisclosed/low-stipend internships |

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
python scripts\main.py
```

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── daily_job_scraper.yml
└── scripts/
    ├── main.py
    └── requirements.txt
```

## Customisation

| What to change | Where |
|----------------|-------|
| Add or remove job titles | `JOBSPY_QUERIES` list in `scripts/main.py` |
| Adjust timezone window | `ACCEPTED_TZ_TOKENS` and `is_timezone_ok()` |
| Change minimum salary | `MIN_LKR_MONTHLY` env var or default in `scripts/main.py` |
| Add priority companies | `PRIORITY_COMPANIES` set |
| Add skill keywords | `SKILL_KEYWORDS` list |
| Change run schedule | Edit the cron expression in `.github/workflows/daily_job_scraper.yml` |

## Telegram Digest

Each job message includes:

- Job title, company, location, source, and date posted
- Type labels such as UI Automation, Performance, Security, API Testing, or Mobile
- Salary estimate in LKR/month when salary is disclosed
- Resume keyword matches
- Direct apply link
