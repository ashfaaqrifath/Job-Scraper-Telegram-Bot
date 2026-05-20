#!/usr/bin/env python3
"""
Sources
-------
  1. Indeed + ZipRecruiter   - via python-jobspy (LinkedIn/Glassdoor blocked)
  2. We Work Remotely        - dedicated QA RSS feed (most reliable free source)
  3. Remotive API            - free JSON API, good remote-job coverage
  4. RemoteOK API            - free JSON API with tag-based search
  5. Greenhouse API          - public ATS boards for 30+ top startups
  6. Lever API               - public ATS boards for 20+ top startups
  7. Jobright (jobright.ai)  - HTML scrape of server-rendered Next.js __NEXT_DATA__
  8. Jobicy API              - free public JSON API, includes salary range
  9. Working Nomads API      - free public JSON, strong timezone-aware metadata
 10. Work at a Startup / YC   - Y Combinator startup jobs HTML
 11. Arbeitnow API            - public Europe/remote JSON API
 12. Remote First Jobs        - public remote jobs JSON API
 13. RemoteJobs.org           - public remote jobs JSON API
 14. WorkAnywhere             - public remote jobs RSS feeds
 15. Himalayas                - public remote jobs RSS feed
 16. HireWeb3                 - public web3 jobs RSS feed


"""

import os
import re
import html
import json
import logging
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
from difflib import SequenceMatcher
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup
from jobspy import scrape_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Telegram delivery ────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_API_BASE  = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
TELEGRAM_LIMIT     = 3900

# ── Date window ──────────────────────────────────────────────────────────────
# Accept jobs posted within the last 72 h (3 days).
# Job boards often index postings 24-48 h after they go live; a strict 24 h
# window silently drops many fresh roles.
MAX_AGE_HOURS = 72

# ── Salary gate ──────────────────────────────────────────────────────────────
MIN_LKR_MONTHLY = int(os.getenv("MIN_LKR_MONTHLY", "0"))
FALLBACK_USD_TO_LKR = 300.0            # fallback if live rate fetch fails

# ── Timezone acceptance ───────────────────────────────────────────────────────
# Sri Lanka is SLST/IST (UTC+5:30). Include nearby APAC, Middle East,
# Australia/NZ, UK/EU/EMEA, and worldwide/global roles.
ACCEPTED_TZ_TOKENS = {
    "SLST", "IST", "INDIA STANDARD TIME",
    "GST", "GULF STANDARD TIME", "UAE", "DUBAI", "MIDDLE EAST",
    "SGT", "SST", "HKT", "MYT", "PHT", "AWST", "AEST", "AEDT", "NZST", "NZDT",
    "GMT", "UTC", "WET", "BST", "CET", "CEST", "EET", "EEST",
    "SRI LANKA", "COLOMBO", "INDIA", "APAC", "ASIA", "SOUTH ASIA",
    "SINGAPORE", "MALAYSIA", "PHILIPPINES", "INDONESIA", "THAILAND", "VIETNAM",
    "AUSTRALIA", "NEW ZEALAND", "UK", "EUROPE", "EMEA",
    "WORLDWIDE", "GLOBAL", "ANYWHERE",
}

SRI_LANKA_LOCATION_TOKENS = {
    "SRI LANKA", "SRILANKA", "COLOMBO", "KANDY", "GALLE", "JAFFNA",
}

REMOTE_FRIENDLY_LOCATION_TOKENS = ACCEPTED_TZ_TOKENS | {
    "REMOTE", "HYBRID", "ASIA-PACIFIC", "ANZ", "OCEANIA",
    "UNITED KINGDOM", "U.K.", "UNITED ARAB EMIRATES",
}

REMOTE_LOCATION_BLOCKLIST = {
    "UNITED STATES", "USA", "U.S.", "US ONLY", "NORTH AMERICA ONLY",
    "REMOTE - US", "REMOTE, US", "REMOTE (US", "US REMOTE",
    "CANADA ONLY", "LATAM", "SOUTH AMERICA",
}

# ── JobSpy search terms ───────────────────────────────────────────────────────
# Used only for Indeed + ZipRecruiter (LinkedIn/Glassdoor actively block scraping)
JOBSPY_QUERIES = [
    "QA Intern",
    "QA Internship",
    "Software QA Internship",
    "Quality Assurance Internship",
    "Quality assurance Intern",
    "Remote QA Intern",
    "Quality Assurance Engineer",
    "Software Quality Assurance Engineer",
    "Software QA Engineer",
    "Trainee QA",
    "Associate QA Engineer",
    "Junior QA Engineer",
    "Graduate QA Engineer",
    "QA Engineer",
    "Software Test Engineer",
    "Automation QA Engineer",
]

JOBSPY_SEARCH_LOCATIONS = [
    # JobSpy/Indeed does not support Sri Lanka as a backend country. Use
    # supported backends while keeping Sri Lanka/Colombo in the location query.
    ("Sri Lanka", "worldwide"),
    ("Colombo", "worldwide"),
    ("Remote", "worldwide"),
    ("Remote", "india"),
    ("Remote", "singapore"),
    ("Remote", "australia"),
    ("Remote", "uk"),
    ("Remote", "united arab emirates"),
]

JOBSPY_VALID_COUNTRIES = {
    "argentina", "australia", "austria", "bahrain", "belgium", "bulgaria",
    "brazil", "canada", "chile", "china", "colombia", "costa rica",
    "croatia", "cyprus", "czech republic", "czechia", "denmark", "ecuador",
    "egypt", "estonia", "finland", "france", "germany", "greece",
    "hong kong", "hungary", "india", "indonesia", "ireland", "israel",
    "italy", "japan", "kuwait", "latvia", "lithuania", "luxembourg",
    "malaysia", "malta", "mexico", "morocco", "netherlands", "new zealand",
    "nigeria", "norway", "oman", "pakistan", "panama", "peru",
    "philippines", "poland", "portugal", "qatar", "romania",
    "saudi arabia", "singapore", "slovakia", "slovenia", "south africa",
    "south korea", "spain", "sweden", "switzerland", "taiwan", "thailand",
    "turkiye", "turkey", "ukraine", "united arab emirates", "uk",
    "united kingdom", "usa", "us", "united states", "uruguay", "venezuela",
    "vietnam", "usa/ca", "worldwide",
}

# ── Greenhouse / Lever company slugs ─────────────────────────────────────────
# These companies use public ATS boards — no auth required
GREENHOUSE_SLUGS = [
    "stripe", "notion", "linear", "vercel", "figma", "retool",
    "datadog", "snyk", "postman", "browserstack", "lambdatest",
    "hashicorp", "confluent", "airbyte", "dbtlabs", "mixpanel",
    "amplitude", "grafana", "pagerduty", "incident-io",
    "atlassian", "gitlab", "circleci", "sonarqube",
    "newrelic", "dynatrace", "saucelabs",
]

LEVER_SLUGS = [
    "github", "figma", "notion", "linear", "vercel",
    "segment", "heap", "percy", "chromatic", "testim",
    "mabl", "rainforest-qa", "checkly",
]

# ── Resume skill keywords ─────────────────────────────────────────────────────
SKILL_KEYWORDS = [
    "Selenium", "Playwright", "Cypress", "Appium", "WebdriverIO",
    "TestNG", "JUnit", "pytest", "NUnit", "xUnit",
    "Robot Framework", "Cucumber", "SpecFlow", "Gherkin",
    "Python", "Java", "JavaScript", "TypeScript", "C#", "Go", "Kotlin",
    "Jenkins", "GitHub Actions", "GitLab CI", "CircleCI", "Travis CI",
    "Docker", "Kubernetes", "Terraform", "Ansible",
    "JMeter", "k6", "Gatling", "Locust", "LoadRunner",
    "OWASP", "Burp Suite", "ZAP", "Nessus", "Snyk", "Penetration Testing",
    "SAST", "DAST", "Vulnerability",
    "REST", "GraphQL", "gRPC", "Postman", "RestAssured", "Karate",
    "SQL", "PostgreSQL", "MySQL", "MongoDB",
    "Grafana", "Prometheus", "Datadog", "Splunk", "ELK",
    "BDD", "TDD", "Agile", "Scrum", "Shift-left",
    "Contract Testing", "Pact", "A/B Testing",
    "AWS", "GCP", "Azure", "Lambda", "S3",
    "iOS", "Android", "XCUITest", "Espresso",
]

PRIORITY_COMPANIES = {
    "stripe", "notion", "linear", "vercel", "figma", "retool",
    "datadog", "hashicorp", "confluent", "postman", "dbt labs",
    "airbyte", "segment", "mixpanel", "amplitude", "heap",
    "browserstack", "lambdatest", "sauce labs", "testim",
    "mabl", "rainforest qa", "percy", "chromatic", "checkly",
    "github", "gitlab", "atlassian", "jetbrains", "circleci",
    "sonarqube", "snyk", "aqua security", "checkov",
    "grafana labs", "prometheus", "new relic", "dynatrace",
    "pagerduty", "incident.io", "rootly",
}


# ─────────────────────────────────────────────────────────────────────────────
# Exchange-rate helper
# ─────────────────────────────────────────────────────────────────────────────

def get_exchange_rates() -> dict[str, float]:
    rates = {
        "USD": 1.0,
        "LKR": FALLBACK_USD_TO_LKR,
    }
    api_key = os.getenv("EXCHANGE_RATE_API_KEY")
    if api_key:
        try:
            resp = requests.get(
                f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD",
                timeout=10,
            )
            resp.raise_for_status()
            live_rates = resp.json()["conversion_rates"]
            for currency in ["LKR", "EUR", "GBP", "AUD", "SGD", "INR", "AED", "USD"]:
                if currency in live_rates:
                    rates[currency] = float(live_rates[currency])
            log.info("Live USD→LKR rate: %.2f", rates["LKR"])
            return rates
        except Exception as exc:
            log.warning("Rate fetch failed (%s); using fallback %.0f", exc, FALLBACK_USD_TO_LKR)
    return rates


# ─────────────────────────────────────────────────────────────────────────────
# Scrapers
# ─────────────────────────────────────────────────────────────────────────────

def _make_job(
    title: str,
    company: str,
    location: str,
    description: str,
    url: str,
    date_posted: str,
    salary_text: str = "",
    salary_min: float = 0.0,
    salary_max: float = 0.0,
    salary_interval: str = "yearly",
    salary_currency: str = "USD",
    source: str = "",
) -> dict:
    return {
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip() or "Remote",
        "description": description,
        "job_url": url,
        "date_posted": date_posted,
        "salary_text": salary_text,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_interval": salary_interval,
        "salary_currency": salary_currency.upper(),
        "source": source,
    }


# ── 1. Indeed + ZipRecruiter via JobSpy ──────────────────────────────────────

def scrape_jobspy(query: str, location: str = "Sri Lanka", country: str = "worldwide") -> list[dict]:
    """Indeed + ZipRecruiter only — LinkedIn and Glassdoor block scrapers."""
    country = country.strip().lower()
    if country not in JOBSPY_VALID_COUNTRIES:
        log.warning("Skipping JobSpy '%s' in %s: unsupported country backend %r", query, location, country)
        return []
    try:
        df = scrape_jobs(
            site_name=["indeed", "zip_recruiter"],
            search_term=query,
            location=location,
            results_wanted=10,
            hours_old=MAX_AGE_HOURS,
            country_indeed=country,
        )
        if df is None or df.empty:
            return []
        jobs = []
        for row in df.to_dict("records"):
            s_min = float(row.get("min_amount") or 0)
            s_max = float(row.get("max_amount") or 0)
            interval = str(row.get("interval") or "yearly").lower()
            currency = str(row.get("currency") or "USD").upper()
            symbol = {"USD": "$", "LKR": "LKR ", "AUD": "A$", "SGD": "S$", "GBP": "£", "EUR": "€"}.get(currency, f"{currency} ")
            s_text = ""
            if s_min or s_max:
                label = {"hourly": "/hr", "monthly": "/mo", "yearly": "/yr"}.get(interval, f"/{interval}")
                s_text = f"{symbol}{s_min:,.0f}–{symbol}{s_max:,.0f}{label}" if s_max else f"{symbol}{s_min:,.0f}+{label}"
            # Convert pandas date to ISO string
            raw_date = row.get("date_posted")
            if hasattr(raw_date, "isoformat"):
                date_str = raw_date.isoformat()
            else:
                date_str = str(raw_date or "")
            jobs.append(_make_job(
                title=str(row.get("title") or ""),
                company=str(row.get("company") or ""),
                location=str(row.get("location") or location or "Remote"),
                description=str(row.get("description") or ""),
                url=str(row.get("job_url") or ""),
                date_posted=date_str,
                salary_text=s_text,
                salary_min=s_min,
                salary_max=s_max,
                salary_interval=interval,
                salary_currency=currency,
                source=str(row.get("site") or "JobSpy"),
            ))
        log.info("JobSpy '%s' in %s: %d results", query, location, len(jobs))
        return jobs
    except Exception as exc:
        log.warning("JobSpy '%s' in %s error: %s", query, country, exc)
        return []


# ── 2. We Work Remotely RSS ──────────────────────────────────────────────────

_WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-testing-qa-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-software-dev-jobs.rss",
]

def fetch_weworkremotely() -> list[dict]:
    jobs: list[dict] = []
    for feed_url in _WWR_FEEDS:
        try:
            resp = requests.get(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (QA Job Digest Bot)"},
                timeout=15,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                # WWR format: "Company: Title  [Region]"
                company, _, rest = title.partition(": ")
                job_title = re.sub(r"\s*\[.*?\]", "", rest).strip() or title
                pub_date = item.findtext("pubDate") or ""
                try:
                    dt = parsedate_to_datetime(pub_date).isoformat()
                except Exception:
                    dt = pub_date
                region = item.findtext("region") or "Remote"
                desc = item.findtext(f"content:encoded", namespaces=ns) or item.findtext("description") or ""
                url = item.findtext("link") or item.findtext("guid") or ""
                jobs.append(_make_job(
                    title=job_title,
                    company=company,
                    location=region,
                    description=desc,
                    url=url,
                    date_posted=dt,
                    source="WeWorkRemotely",
                ))
        except Exception as exc:
            log.warning("WWR feed %s error: %s", feed_url, exc)
    log.info("We Work Remotely: %d raw results", len(jobs))
    return jobs


# ── 3. Remotive API ───────────────────────────────────────────────────────────

def fetch_remotive() -> list[dict]:
    jobs: list[dict] = []
    for cat in ["qa", "testing", "devops"]:
        try:
            resp = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"category": cat, "limit": 50},
                timeout=15,
            )
            resp.raise_for_status()
            for j in resp.json().get("jobs", []):
                jobs.append(_make_job(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=j.get("candidate_required_location", "Remote"),
                    description=j.get("description", ""),
                    url=j.get("url", ""),
                    date_posted=j.get("publication_date", ""),
                    salary_text=j.get("salary", ""),
                    source="Remotive",
                ))
        except Exception as exc:
            log.warning("Remotive '%s' error: %s", cat, exc)
    log.info("Remotive: %d raw results", len(jobs))
    return jobs


# ── 4. RemoteOK API ───────────────────────────────────────────────────────────

def fetch_remoteok() -> list[dict]:
    jobs: list[dict] = []
    for tag in ["qa", "testing", "selenium", "playwright", "automation"]:
        try:
            resp = requests.get(
                f"https://remoteok.com/api?tag={tag}",
                headers={"User-Agent": "Mozilla/5.0 (QA Job Digest Bot)"},
                timeout=15,
            )
            resp.raise_for_status()
            for j in resp.json():
                if not isinstance(j, dict) or "position" not in j:
                    continue
                # epoch field is a Unix timestamp integer
                epoch = j.get("epoch")
                if epoch:
                    dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
                else:
                    dt = j.get("date", "")
                jobs.append(_make_job(
                    title=j.get("position", ""),
                    company=j.get("company", ""),
                    location=j.get("location", "Remote"),
                    description=j.get("description", ""),
                    url=j.get("url", ""),
                    date_posted=dt,
                    source="RemoteOK",
                ))
        except Exception as exc:
            log.warning("RemoteOK '%s' error: %s", tag, exc)
    log.info("RemoteOK: %d raw results", len(jobs))
    return jobs


# ── 5. Greenhouse public ATS API ──────────────────────────────────────────────

def fetch_greenhouse() -> list[dict]:
    jobs: list[dict] = []
    for slug in GREENHOUSE_SLUGS:
        try:
            resp = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                params={"content": "true"},
                timeout=10,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            company_name = slug.replace("-", " ").title()
            for j in resp.json().get("jobs", []):
                location = ""
                for loc in j.get("offices", []) or j.get("location", {}).values():
                    if isinstance(loc, dict):
                        location = loc.get("name", "")
                    else:
                        location = str(loc)
                    break
                if not location:
                    location = j.get("location", {}).get("name", "Remote")
                jobs.append(_make_job(
                    title=j.get("title", ""),
                    company=company_name,
                    location=location or "Remote",
                    description=j.get("content", ""),
                    url=j.get("absolute_url", ""),
                    date_posted=j.get("updated_at", ""),
                    source="Greenhouse",
                ))
        except Exception as exc:
            log.debug("Greenhouse '%s' error: %s", slug, exc)
    log.info("Greenhouse: %d raw results", len(jobs))
    return jobs


# ── 6. Lever public ATS API ───────────────────────────────────────────────────

def fetch_lever() -> list[dict]:
    jobs: list[dict] = []
    for slug in LEVER_SLUGS:
        try:
            resp = requests.get(
                f"https://api.lever.co/v0/postings/{slug}",
                params={"mode": "json"},
                timeout=10,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            company_name = slug.replace("-", " ").title()
            for j in resp.json():
                location = j.get("categories", {}).get("location", "Remote")
                # Lever uses createdAt as millisecond epoch
                created_ms = j.get("createdAt")
                if created_ms:
                    dt = datetime.fromtimestamp(int(created_ms) / 1000, tz=timezone.utc).isoformat()
                else:
                    dt = ""
                jobs.append(_make_job(
                    title=j.get("text", ""),
                    company=company_name,
                    location=location,
                    description=j.get("descriptionPlain", "") or j.get("description", ""),
                    url=j.get("hostedUrl", ""),
                    date_posted=dt,
                    source="Lever",
                ))
        except Exception as exc:
            log.debug("Lever '%s' error: %s", slug, exc)
    log.info("Lever: %d raw results", len(jobs))
    return jobs


# ── 7. Jobright (jobright.ai) — server-rendered __NEXT_DATA__ JSON ────────────
#
# Jobright has no public API. The /remote-jobs page is a Next.js app that
# server-renders the first 30 search results into an inline <script id="__NEXT_DATA__">
# JSON blob, which we parse. This is fragile: a frontend refactor could change
# the key path or move the data to client-side hydration. If results suddenly
# drop to 0 from this source, inspect the page HTML and update the JSON path.
#
# robots.txt explicitly allows /jobs/* and /remote-jobs/*, so this is permitted.

_JOBRIGHT_TITLES = ",".join([
    "QA Engineer", "QA Automation Engineer", "SDET",
    "Test Automation Engineer", "Quality Assurance Engineer",
    "Software Test Engineer", "Performance Test Engineer",
    "Security Test Engineer", "Test Engineer", "Automation Engineer",
])

_JOBRIGHT_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HTML_HEADERS = {
    "User-Agent": _JOBRIGHT_BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_jobright() -> list[dict]:
    """Parse Jobright's server-rendered job results from __NEXT_DATA__."""
    jobs: list[dict] = []
    try:
        resp = requests.get(
            "https://jobright.ai/remote-jobs",
            params={"jobTitle": _JOBRIGHT_TITLES},
            headers={"User-Agent": _JOBRIGHT_BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=20,
        )
        resp.raise_for_status()
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text, re.DOTALL,
        )
        if not m:
            log.warning("Jobright: __NEXT_DATA__ block not found — page structure may have changed")
            return jobs
        data = json.loads(m.group(1))
        items = data.get("props", {}).get("pageProps", {}).get("defaultData", []) or []
        for item in items:
            jr = item.get("jobResult") or {}
            cr = item.get("companyResult") or {}
            if not jr.get("jobTitle"):
                continue
            # publishTime arrives as "YYYY-MM-DD HH:MM:SS" in UTC
            raw_dt = (jr.get("publishTime") or "").strip()
            date_iso = ""
            if raw_dt:
                try:
                    dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S")
                    date_iso = dt.replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    date_iso = raw_dt
            location = jr.get("jobLocation") or ""
            is_remote_flag = str(jr.get("isRemote", "")).lower() in ("true", "1")
            if is_remote_flag:
                location = f"Remote — {location}" if location else "Remote"
            jobs.append(_make_job(
                title=jr.get("jobTitle", ""),
                company=cr.get("companyName") or "Unknown",
                location=location,
                description=jr.get("jobSummary", "") or "",
                url=jr.get("applyLink") or jr.get("url") or "",
                date_posted=date_iso,
                source="Jobright",
            ))
    except Exception as exc:
        log.warning("Jobright fetch error: %s", exc)
    log.info("Jobright: %d raw results", len(jobs))
    return jobs


# ── 8. Jobicy public JSON API ─────────────────────────────────────────────────
# Docs: https://jobicy.com/feed/job_feed/json — free, no auth.
# We pull the latest 50 jobs across all industries and rely on the QA title
# filter to keep what's relevant. Their `tag=qa` filter returns 0 in practice.

def fetch_jobicy() -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = requests.get(
            "https://jobicy.com/api/v2/remote-jobs",
            params={"count": 50},
            timeout=15,
        )
        resp.raise_for_status()
        for j in resp.json().get("jobs", []):
            s_min = float(j.get("annualSalaryMin") or 0)
            s_max = float(j.get("annualSalaryMax") or 0)
            currency = (j.get("salaryCurrency") or "USD").upper()
            salary_text = ""
            if s_min or s_max:
                if s_max:
                    salary_text = f"{currency} {s_min:,.0f}–{s_max:,.0f}/yr"
                else:
                    salary_text = f"{currency} {s_min:,.0f}+/yr"
            jobs.append(_make_job(
                title=j.get("jobTitle", ""),
                company=j.get("companyName", ""),
                location=j.get("jobGeo", "") or "Remote",
                description=j.get("jobDescription", "") or j.get("jobExcerpt", ""),
                url=j.get("url", ""),
                date_posted=j.get("pubDate", ""),
                salary_text=salary_text,
                salary_min=s_min,
                salary_max=s_max,
                salary_interval="yearly",
                salary_currency=currency,
                source="Jobicy",
            ))
    except Exception as exc:
        log.warning("Jobicy fetch error: %s", exc)
    log.info("Jobicy: %d raw results", len(jobs))
    return jobs


# ── 9. Working Nomads public JSON API ─────────────────────────────────────────
# `/api/exposed_jobs/` returns a flat array of the most recent jobs across all
# categories. Good signal for European/timezone-aware remote roles.

def fetch_workingnomads() -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = requests.get(
            "https://www.workingnomads.com/api/exposed_jobs/",
            headers={"User-Agent": "Mozilla/5.0 (QA Job Digest Bot)"},
            timeout=15,
        )
        resp.raise_for_status()
        for j in resp.json():
            jobs.append(_make_job(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", "") or "Remote",
                description=j.get("description", "") or "",
                url=j.get("url", ""),
                date_posted=j.get("pub_date", ""),
                source="Working Nomads",
            ))
    except Exception as exc:
        log.warning("Working Nomads fetch error: %s", exc)
    log.info("Working Nomads: %d raw results", len(jobs))
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Filters
# ─────────────────────────────────────────────────────────────────────────────

def _iter_jsonld_jobpostings(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_jobpostings(item)
        return
    if not isinstance(data, dict):
        return
    if data.get("@graph"):
        yield from _iter_jsonld_jobpostings(data["@graph"])
    item_type = data.get("@type")
    item_types = item_type if isinstance(item_type, list) else [item_type]
    if "JobPosting" in item_types:
        yield data


def _jsonld_to_job(item: dict, source: str, base_url: str) -> dict:
    org = item.get("hiringOrganization") or {}
    location = item.get("jobLocation") or item.get("applicantLocationRequirements") or "Remote"
    if isinstance(location, list):
        location = ", ".join(
            (loc.get("address", {}).get("addressLocality") or loc.get("name") or "Remote")
            if isinstance(loc, dict) else str(loc)
            for loc in location[:3]
        )
    elif isinstance(location, dict):
        address = location.get("address") or {}
        location = location.get("name") or address.get("addressLocality") or address.get("addressCountry") or "Remote"

    salary_text = ""
    salary_min = salary_max = 0.0
    salary_interval = "yearly"
    salary_currency = "USD"
    salary = item.get("baseSalary") or {}
    if isinstance(salary, dict):
        salary_currency = (salary.get("currency") or "USD").upper()
        value = salary.get("value") or {}
        if isinstance(value, dict):
            salary_min = float(value.get("minValue") or value.get("value") or 0)
            salary_max = float(value.get("maxValue") or value.get("value") or 0)
            salary_interval = str(value.get("unitText") or "yearly").lower()
            if salary_min or salary_max:
                salary_text = f"{salary_currency} {salary_min:,.0f}-{salary_max:,.0f}/{salary_interval}"

    url = item.get("url") or item.get("sameAs") or base_url
    company = org.get("name", "Unknown") if isinstance(org, dict) else "Unknown"
    return _make_job(
        title=item.get("title", ""),
        company=company,
        location=str(location),
        description=item.get("description", ""),
        url=urljoin(base_url, str(url)),
        date_posted=item.get("datePosted", ""),
        salary_text=salary_text,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_interval=salary_interval,
        salary_currency=salary_currency,
        source=source,
    )


def _extract_jsonld_jobs(html_text: str, source: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "lxml")
    jobs: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _iter_jsonld_jobpostings(data):
            jobs.append(_jsonld_to_job(item, source, base_url))
    return jobs


def _extract_anchor_jobs(html_text: str, source: str, base_url: str, href_markers: tuple[str, ...]) -> list[dict]:
    soup = BeautifulSoup(html_text, "lxml")
    jobs: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not any(marker in href for marker in href_markers):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        title = _plain_text(a.get_text(" ", strip=True), 160)
        if not title or len(title) < 4:
            continue
        parent = a.find_parent(["article", "li", "div"]) or a
        context = _plain_text(parent.get_text(" ", strip=True), 700)
        jobs.append(_make_job(
            title=title,
            company="Unknown",
            location=context or "Remote",
            description=context,
            url=url,
            date_posted="",
            source=source,
        ))
        seen.add(url)
        if len(jobs) >= 50:
            break
    return jobs


def _fetch_html_job_source(source: str, urls: list[str], href_markers: tuple[str, ...]) -> list[dict]:
    jobs: list[dict] = []
    for url in urls:
        try:
            resp = requests.get(url, headers=HTML_HEADERS, timeout=20)
            if resp.status_code in (401, 403):
                log.info("%s blocks automated/unauthenticated requests; skipping this source.", source)
                break
            resp.raise_for_status()
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            parsed_jobs = _extract_jsonld_jobs(resp.text, source, base_url)
            if not parsed_jobs:
                parsed_jobs = _extract_anchor_jobs(resp.text, source, base_url, href_markers)
            jobs.extend(parsed_jobs)
        except Exception as exc:
            log.warning("%s fetch %s error: %s", source, url, exc)
    jobs = deduplicate([j for j in jobs if _valid_job(j)])
    log.info("%s: %d raw results", source, len(jobs))
    return jobs


def fetch_workatastartup() -> list[dict]:
    urls = [
        "https://www.ycombinator.com/jobs",
        "https://www.ycombinator.com/jobs/role/software-engineer",
        "https://www.ycombinator.com/jobs/role/internship",
    ]
    return _fetch_html_job_source("Work at a Startup", urls, ("/jobs/", "/companies/"))


def _as_float(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _unix_or_text_date(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def fetch_arbeitnow() -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", data if isinstance(data, list) else [])
        for j in items[:100]:
            tags = ", ".join(j.get("tags") or [])
            description = " ".join([str(j.get("description") or ""), tags]).strip()
            location = j.get("location") or "Remote"
            if j.get("remote") and "remote" not in str(location).lower():
                location = f"Remote - {location}"
            jobs.append(_make_job(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=location,
                description=description,
                url=j.get("url", ""),
                date_posted=_unix_or_text_date(j.get("created_at") or j.get("date")),
                source="Arbeitnow",
            ))
    except Exception as exc:
        log.warning("Arbeitnow fetch error: %s", exc)
    log.info("Arbeitnow: %d raw results", len(jobs))
    return jobs


def fetch_remotefirstjobs() -> list[dict]:
    jobs: list[dict] = []
    queries = ["qa", "quality assurance", "test engineer", "automation qa"]
    for query in queries:
        try:
            resp = requests.get(
                "https://remotefirstjobs.com/api/search-jobs",
                params={"query": query, "page": 0},
                headers={"User-Agent": "Mozilla/5.0 (QA Job Digest Bot)"},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("jobs") or data.get("data") or []
            for j in items[:80]:
                locations = j.get("locations") or []
                if isinstance(locations, list):
                    location = ", ".join(str(loc) for loc in locations[:3]) or "Remote"
                else:
                    location = str(locations or "Remote")
                salary_min = _as_float(j.get("salary_min"))
                salary_max = _as_float(j.get("salary_max"))
                salary_text = ""
                if salary_min or salary_max:
                    salary_text = f"USD {salary_min:,.0f}-{salary_max:,.0f}/year"
                jobs.append(_make_job(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=f"Remote - {location}",
                    description=j.get("description", "") or str(j.get("seniority") or ""),
                    url=j.get("url", ""),
                    date_posted=j.get("published_at", ""),
                    salary_text=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_interval="yearly",
                    salary_currency="USD",
                    source="Remote First Jobs",
                ))
        except Exception as exc:
            log.warning("Remote First Jobs '%s' fetch error: %s", query, exc)
    jobs = deduplicate([j for j in jobs if _valid_job(j)])
    log.info("Remote First Jobs: %d raw results", len(jobs))
    return jobs


def fetch_remotejobs_org() -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = requests.get(
            "https://remotejobs.org/api/v1/jobs",
            params={"limit": 50, "category": "programming"},
            timeout=20,
        )
        resp.raise_for_status()
        for j in resp.json().get("data", []):
            company = j.get("company") or {}
            salary_min = _as_float(j.get("salary_min"))
            salary_max = _as_float(j.get("salary_max"))
            jobs.append(_make_job(
                title=j.get("title", ""),
                company=company.get("name", "") if isinstance(company, dict) else "",
                location=j.get("location", "") or "Remote",
                description=j.get("description", "") or j.get("type", ""),
                url=j.get("apply_url") or j.get("url", ""),
                date_posted=j.get("posted_at", ""),
                salary_text=j.get("salary_text", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_interval="yearly",
                salary_currency="USD",
                source="RemoteJobs.org",
            ))
    except Exception as exc:
        log.warning("RemoteJobs.org fetch error: %s", exc)
    log.info("RemoteJobs.org: %d raw results", len(jobs))
    return jobs


def _child_text_by_suffix(elem, suffix: str) -> str:
    for child in list(elem):
        tag = str(child.tag).split("}", 1)[-1]
        if tag == suffix:
            return (child.text or "").strip()
    return ""


def _fetch_rss_jobs(source: str, feed_url: str, company_field: str = "companyName", location_field: str = "location") -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0 (QA Job Digest Bot)"}, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        for item in root.findall(".//item")[:100]:
            title = item.findtext("title") or ""
            company = _child_text_by_suffix(item, company_field) or "Unknown"
            location = _child_text_by_suffix(item, location_field) or _child_text_by_suffix(item, "locationRestriction") or "Remote"
            timezone_text = _child_text_by_suffix(item, "timezoneRestriction")
            if timezone_text:
                location = f"{location} {timezone_text}"
            description = item.findtext("description") or item.findtext("content:encoded", namespaces=ns) or ""
            min_salary = _as_float(_child_text_by_suffix(item, "minSalary"))
            max_salary = _as_float(_child_text_by_suffix(item, "maxSalary"))
            salary_text = f"USD {min_salary:,.0f}-{max_salary:,.0f}/year" if min_salary or max_salary else ""
            jobs.append(_make_job(
                title=title,
                company=company,
                location=location,
                description=description,
                url=item.findtext("link") or "",
                date_posted=item.findtext("pubDate") or "",
                salary_text=salary_text,
                salary_min=min_salary,
                salary_max=max_salary,
                salary_interval="yearly",
                salary_currency="USD",
                source=source,
            ))
    except Exception as exc:
        log.warning("%s RSS fetch error: %s", source, exc)
    jobs = deduplicate([j for j in jobs if _valid_job(j)])
    log.info("%s: %d raw results", source, len(jobs))
    return jobs


def fetch_workanywhere() -> list[dict]:
    jobs: list[dict] = []
    for feed_url in [
        "https://workanywhere.pro/rss/engineer.xml",
        "https://workanywhere.pro/rss/developer.xml",
    ]:
        jobs.extend(_fetch_rss_jobs("WorkAnywhere", feed_url, company_field="companyName", location_field="location"))
    jobs = deduplicate(jobs)
    log.info("WorkAnywhere combined: %d raw results", len(jobs))
    return jobs


def fetch_himalayas() -> list[dict]:
    return _fetch_rss_jobs(
        "Himalayas",
        "https://himalayas.app/jobs/rss",
        company_field="companyName",
        location_field="locationRestriction",
    )


def fetch_hireweb3() -> list[dict]:
    return _fetch_rss_jobs(
        "HireWeb3",
        "https://hireweb3.io/job/rss",
        company_field="companyName",
        location_field="location",
    )


_QA_TITLE_PATTERN = re.compile(
    r"\b("
    r"qa intern|qa internship|software qa intern|qa trainee|trainee qa|"
    r"junior qa|associate qa|graduate qa|entry.?level qa|"
    r"qa engineer|qa automation|qa analyst|qa tester|qa specialist|"
    r"quality assurance|quality engineer|quality analyst|"
    r"test engineer|test automation|test analyst|"
    r"automation engineer|automation tester|automation qa|"
    r"sdet|software development engineer in test|"
    r"performance test|security test|load test|"
    r"e2e engineer|end.to.end|"
    r"software tester|manual tester|"
    r"mobile qa analyst|software test engineer|"
    r"engineer, qa automation|product tester|qa mobile|mobile qa"
    r")\b"
    r"|(?<!\w)qa(?!\w)",          # standalone "QA" not part of another word
    re.IGNORECASE,
)

_TITLE_BLOCKLIST = re.compile(
    r"\b("
    r"sales|erp|backend developer|frontend developer|full.?stack developer|"
    r"customer support|call cent(re|er)|field engineer|instrumentation|"
    r"internal audit|accountant|financial|marketing|data engineer|"
    r"devops engineer|site reliability engineer|sre|"
    r"product manager|project manager|scrum master|business analyst|"
    r"software engineer(?! in test)|staff engineer(?! in test)|"
    r"senior|sr\.?|lead|manager|principal|staff|architect|director|head of"
    r")\b",
    re.IGNORECASE,
)


# Canonical QA titles for fuzzy-match fallback. Mirrors _QA_TITLE_PATTERN
# alternations but as plain strings so SequenceMatcher can compare against them.
_CANONICAL_QA_TITLES = [
    "qa intern", "qa internship", "software qa intern", "qa trainee",
    "trainee qa engineer", "junior qa engineer", "associate qa engineer",
    "graduate qa engineer", "entry level qa engineer",
    "qa engineer", "qa automation engineer",
    "qa analyst", "qa tester", "qa specialist",
    "qa mobile", "mobile qa", "mobile qa analyst",
    "engineer qa automation",
    "quality assurance engineer", "quality assurance analyst",
    "quality engineer", "quality analyst", "quality lead", "quality manager",
    "test engineer", "test automation engineer",
    "test analyst", "software test engineer",
    "automation engineer", "automation tester",
    "sdet", "software development engineer in test",
    "performance test engineer", "security test engineer", "load test engineer",
    "software tester", "manual tester", "product tester",
]

FUZZY_TITLE_THRESHOLD = 0.90


def _normalize_title(s: str) -> str:
    """Lowercase + collapse punctuation to spaces for fair fuzzy comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _best_qa_fuzzy_score(title: str) -> tuple[float, str]:
    """Highest similarity ratio between a normalized title and any canonical QA title."""
    norm = _normalize_title(title)
    if not norm:
        return 0.0, ""
    best_score = 0.0
    best_match = ""
    for canonical in _CANONICAL_QA_TITLES:
        # Exact substring → 1.0 (handles "Senior X", "X II", "X (Remote)" etc.)
        if canonical in norm:
            return 1.0, canonical
        score = SequenceMatcher(None, norm, canonical).ratio()
        if score > best_score:
            best_score = score
            best_match = canonical
    return best_score, best_match


def is_qa_relevant(job: dict) -> bool:
    title = job.get("title", "")
    if _TITLE_BLOCKLIST.search(title):
        return False
    if _QA_TITLE_PATTERN.search(title):
        return True
    # Fuzzy fallback: catch titles the strict regex misses (abbreviations,
    # unusual punctuation, slight word variations).
    score, canonical = _best_qa_fuzzy_score(title)
    if score >= FUZZY_TITLE_THRESHOLD:
        log.info("Fuzzy match: %r ≈ %r (%.2f)", title, canonical, score)
        return True
    return False


_ENTRY_LEVEL_SIGNAL = re.compile(
    r"\b("
    r"intern|internship|trainee|fresh(er| graduate)?|graduate|entry.?level|"
    r"junior|associate|apprentice|campus|level 1|level i|engineer i|qa i|"
    r"0\s*[-–]\s*2 years|0\+?\s*years|1\+?\s*years|2\+?\s*years"
    r")\b",
    re.IGNORECASE,
)

_SENIORITY_BLOCKLIST = re.compile(
    r"\b("
    r"senior|sr\.?|lead|manager|principal|staff|architect|director|head of|"
    r"expert|consultant|specialist ii|level iii|engineer iii"
    r")\b",
    re.IGNORECASE,
)


def is_fresh_grad_friendly(job: dict) -> bool:
    title = job.get("title", "")
    text = f"{title} {job.get('description', '')}"
    if _SENIORITY_BLOCKLIST.search(title):
        return False
    for m in re.finditer(r"\b(?:minimum|min\.?|at least)?\s*(\d+)\+?\s*(?:years|yrs)\b", text, re.IGNORECASE):
        if int(m.group(1)) >= 3:
            return False
    if _ENTRY_LEVEL_SIGNAL.search(text):
        return True
    return True


_INTERNSHIP_SIGNAL = re.compile(
    r"\b(intern|internship|trainee|apprentice|campus)\b",
    re.IGNORECASE,
)

_FRESH_GRAD_SIGNAL = re.compile(
    r"\b(fresh(er| graduate)?|graduate|entry.?level|junior|associate|level 1|level i|engineer i|qa i)\b",
    re.IGNORECASE,
)

_LOW_EXPERIENCE_SIGNAL = re.compile(
    r"\b(0\s*[-]\s*2 years|0\+?\s*years|1\+?\s*years|2\+?\s*years)\b",
    re.IGNORECASE,
)

_EXPERIENCE_SIGNAL = re.compile(
    r"\b(\d+)\+?\s*(?:years|yrs)\b|\bexperience (?:required|needed|preferred)\b",
    re.IGNORECASE,
)


def role_priority_rank(job: dict) -> int:
    """Lower is better: internships first, experience-heavy roles last."""
    title = job.get("title", "")
    text = f"{title} {job.get('description', '')}"
    if _INTERNSHIP_SIGNAL.search(title):
        return 0
    if _INTERNSHIP_SIGNAL.search(text):
        return 1
    if _FRESH_GRAD_SIGNAL.search(title):
        return 2
    if _FRESH_GRAD_SIGNAL.search(text) or _LOW_EXPERIENCE_SIGNAL.search(text):
        return 3
    if _EXPERIENCE_SIGNAL.search(text):
        return 5
    return 4


def parse_posted_dt(job: dict) -> Optional[datetime]:
    raw = job.get("date_posted")
    if raw is None:
        return None
    if hasattr(raw, "tzinfo"):          # datetime / pandas Timestamp
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if hasattr(raw, "year") and not hasattr(raw, "hour"):   # date object
        return datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s or s.lower() in ("none", "nan", "nat", ""):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None


def is_posted_recently(job: dict) -> bool:
    """Accept jobs posted within MAX_AGE_HOURS; include those with no date."""
    dt = parse_posted_dt(job)
    if dt is None:
        return True   # unknown date - include, flag as "date unknown"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    return dt >= cutoff


def is_remote(job: dict) -> bool:
    location = job.get("location", "").lower()
    return "remote" in location or location.strip() in ("", "worldwide", "global", "anywhere")


def is_sri_lanka_location(job: dict) -> bool:
    text = (job.get("location", "") + " " + job.get("description", "")[:1000]).upper()
    return any(token in text for token in SRI_LANKA_LOCATION_TOKENS)


def is_location_ok(job: dict) -> bool:
    text = (job.get("location", "") + " " + job.get("description", "")[:1000]).upper()
    if is_sri_lanka_location(job):
        return True
    if not is_remote(job):
        return False
    if any(token in text for token in REMOTE_LOCATION_BLOCKLIST):
        return False
    if any(token in text for token in REMOTE_FRIENDLY_LOCATION_TOKENS):
        return True
    return True


def is_timezone_ok(job: dict) -> bool:
    text = (job.get("description", "") + " " + job.get("location", "")).upper()
    tz_mentions = re.findall(
        r"\b(?:UTC|GMT)\s*[+-]\s*\d{1,2}(?::?\d{2})?\b|"
        r"\b(?:SLST|IST|GST|SGT|SST|HKT|MYT|PHT|AWST|AEST|AEDT|NZST|NZDT|GMT|UTC|WET|BST|CET|CEST|EET|EEST)\b",
        text,
    )
    if not tz_mentions:
        return True
    for tok in tz_mentions:
        m = re.match(r"(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?", tok)
        if m:
            sign = 1 if m.group(1) == "+" else -1
            minutes = int(m.group(3) or 0)
            offset = sign * (int(m.group(2)) + minutes / 60)
            if 3 <= offset <= 11:
                return True
    for token in ACCEPTED_TZ_TOKENS:
        if token in text:
            return True
    return False


_CURRENCY_SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "USD": "USD",
    "LKR": "LKR",
    "RS": "LKR",
    "RS.": "LKR",
    "රු": "LKR",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
    "A$": "AUD",
    "AUD": "AUD",
    "S$": "SGD",
    "SGD": "SGD",
    "₹": "INR",
    "INR": "INR",
    "AED": "AED",
}


def _to_lkr(amount: float, currency: str, rates: dict[str, float]) -> Optional[float]:
    currency = (currency or "USD").upper().replace(".", "")
    if currency == "RS":
        currency = "LKR"
    if currency == "LKR":
        return amount
    if currency not in rates or "LKR" not in rates:
        return None
    return (amount / rates[currency]) * rates["LKR"]


def parse_salary_lkr_monthly(job: dict, rates: dict[str, float]) -> Optional[float]:
    if job.get("salary_min") or job.get("salary_max"):
        value = job["salary_max"] or job["salary_min"]
        interval = job.get("salary_interval", "yearly")
        currency = job.get("salary_currency", "USD")
        monthly = value
        if interval == "hourly":
            monthly = (value * 2080) / 12
        elif interval == "yearly":
            monthly = value / 12
        return _to_lkr(monthly, currency, rates)
    text = job.get("salary_text", "") + " " + job.get("description", "")
    matches = re.findall(
        r"(USD|US\$|LKR|Rs\.?|රු|EUR|GBP|AUD|SGD|INR|AED|[$€£₹])\s*([\d,]+(?:\.\d+)?)(k)?",
        text,
        re.IGNORECASE,
    )
    if not matches:
        return None
    monthly_values = []
    for raw_currency, raw_amount, kilo in matches:
        raw_amount = (raw_amount or "").strip()
        if not raw_amount:
            continue
        currency = _CURRENCY_SYMBOLS.get(raw_currency.upper().replace(".", ""), raw_currency.upper().replace(".", ""))
        try:
            amount = float(raw_amount.replace(",", ""))
        except ValueError:
            continue
        if amount <= 0:
            continue
        if kilo:
            amount *= 1000
        ctx_start = text.lower().find(raw_amount.lower())
        ctx = text[max(0, ctx_start - 30): ctx_start + 40].lower()
        if any(token in ctx for token in ["/hr", "hour", "hourly"]):
            monthly = (amount * 2080) / 12
        elif any(token in ctx for token in ["/mo", "month", "monthly"]):
            monthly = amount
        else:
            monthly = amount / 12 if amount >= 20_000 else amount
        lkr = _to_lkr(monthly, currency, rates)
        if lkr is not None:
            monthly_values.append(lkr)
    return max(monthly_values) if monthly_values else None


def salary_ok(job: dict, rates: dict[str, float]) -> bool:
    if MIN_LKR_MONTHLY <= 0:
        return True
    monthly = parse_salary_lkr_monthly(job, rates)
    if monthly is None:
        return True
    return monthly >= MIN_LKR_MONTHLY


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(jobs: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for job in jobs:
        key = (job["title"].lower().strip(), job["company"].lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Keyword extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_keywords(description: str) -> list[str]:
    desc_upper = description.upper()
    return [kw for kw in SKILL_KEYWORDS if kw.upper() in desc_upper]


# ─────────────────────────────────────────────────────────────────────────────
# Telegram message helpers
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Output sanitization — every field below originates from external job boards
# (Indeed posters, Lever boards, etc.) and must be treated as untrusted.
# ─────────────────────────────────────────────────────────────────────────────

_MAX_FIELD_LEN = 500   # cap any single field to avoid runaway HTML payloads


def _safe_text(value, max_len: int = _MAX_FIELD_LEN) -> str:
    """HTML-escape a value, coerce to string, and truncate to max_len chars."""
    if value is None:
        return ""
    s = str(value)
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return html.escape(s, quote=True)


def _plain_text(value, max_len: int = _MAX_FIELD_LEN) -> str:
    """Coerce a value to plain text and truncate it for Telegram messages."""
    if value is None:
        return ""
    s = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _safe_url(value) -> str:
    """Return value only if it is an http(s) URL; otherwise '#'."""
    if not value:
        return "#"
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return "#"
    if parsed.scheme not in ("http", "https"):
        return "#"
    if not parsed.netloc:
        return "#"
    return html.escape(str(value), quote=True)


def _plain_url(value) -> str:
    """Return a plain http(s) URL for Telegram auto-linking."""
    if not value:
        return ""
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return str(value)


def _valid_job(job: dict) -> bool:
    """Reject jobs that are missing required string fields or malformed."""
    title = job.get("title")
    company = job.get("company")
    if not isinstance(title, str) or not title.strip():
        return False
    if not isinstance(company, str) or not company.strip():
        return False
    return True


def _salary_str(job: dict, rates: dict[str, float]) -> str:
    monthly_lkr = parse_salary_lkr_monthly(job, rates)
    if monthly_lkr is None:
        return "Not disclosed"
    if job.get("salary_text"):
        return f"LKR {monthly_lkr:,.0f}/mo  ({_plain_text(job['salary_text'], 100)})"
    return f"LKR {monthly_lkr:,.0f}/mo"


def _type_labels(job: dict) -> list[str]:
    t = (job["title"] + " " + job["description"]).lower()
    out = []
    if any(k in t for k in ["selenium","playwright","cypress","appium","webdriver"]):
        out.append("UI Automation")
    if any(k in t for k in ["jmeter","k6","gatling","locust","performance","load test"]):
        out.append("Performance")
    if any(k in t for k in ["security","owasp","burp","pentest","sast","dast"]):
        out.append("Security")
    if any(k in t for k in ["api","rest","graphql","postman","restassured"]):
        out.append("API Testing")
    if any(k in t for k in ["mobile","ios","android","xcuitest","espresso"]):
        out.append("Mobile")
    return out or ["QA"]


# ─────────────────────────────────────────────────────────────────────────────
# Telegram dispatch
# ─────────────────────────────────────────────────────────────────────────────

def _telegram_header(jobs: list[dict], rates: dict[str, float], today: str, stats: dict) -> str:
    source_counts = " | ".join(
        f"{_plain_text(src, 28)} {count}"
        for src, count in sorted(stats.items())
    ) or "No qualified jobs"

    salary_note = (
        f"💰 Min salary: LKR {MIN_LKR_MONTHLY:,.0f}/mo"
        if MIN_LKR_MONTHLY > 0
        else "💰 Salary: shown when disclosed"
    )

    return "\n".join([
        f"🌤️ Daily QA Jobs - {today}",
        "",
        f"🎯 {len(jobs)} fresh-grad friendly role(s)",
        "📍 Sri Lanka local + Sri Lanka-friendly remote",
        "🕒 Posted in the last 72h",
        salary_note,
        f"💱 1 USD ≈ LKR {rates.get('LKR', FALLBACK_USD_TO_LKR):,.0f}",
        "",
        f"📚 Sources: {source_counts}",
    ])


def _telegram_job(job: dict, rates: dict[str, float], idx: int) -> str:
    company_raw = (job.get("company") or "Unknown").strip()
    is_priority = company_raw.lower() in PRIORITY_COMPANIES
    company = _plain_text(company_raw, 200)
    title = _plain_text(job.get("title", ""), 250)
    location = _plain_text(job.get("location", "Remote"), 150)
    source = _plain_text(job.get("source", ""), 50)
    salary = _salary_str(job, rates)
    labels = ", ".join(_plain_text(label, 50) for label in _type_labels(job))
    keywords = extract_keywords(job.get("description", ""))
    keyword_text = ", ".join(_plain_text(k, 50) for k in keywords[:8]) or "No matched keywords"

    dt = parse_posted_dt(job)
    date_label = dt.strftime("%Y-%m-%d") if dt else "date unknown"

    company_label = f"⭐ {company}" if is_priority else company
    url = _plain_url(job.get("job_url"))
    apply_line = f"🔗 Apply: {url}" if url else "🔗 Apply link unavailable"

    return "\n".join([
        "━━━━━━━━━━━━━━━━━━━━",
        f"#{idx}  {title}",
        "",
        f"🏢 {company_label}",
        f"📍 {location}",
        f"🗓️ {date_label}   •   {source}",
        f"🏷️ {labels}",
        f"💰 {salary}",
        f"🧰 {keyword_text}",
        "",
        apply_line,
    ])


def _fit_telegram_limit(message: str) -> str:
    if len(message) <= TELEGRAM_LIMIT:
        return message
    return message[: TELEGRAM_LIMIT - 20].rstrip() + "\n...truncated"


def build_telegram_messages(jobs: list[dict], rates: dict[str, float], today: str, stats: dict) -> list[str]:
    if not jobs:
        return [
            _telegram_header(jobs, rates, today, stats)
            + "\n\nNo new QA jobs matched your criteria in the last 72 h. Check back tomorrow!"
        ]

    chunks: list[str] = []
    current = _telegram_header(jobs, rates, today, stats)

    for idx, job in enumerate(jobs, start=1):
        entry = _fit_telegram_limit(_telegram_job(job, rates, idx))
        next_message = current + "\n\n" + entry
        if len(next_message) > TELEGRAM_LIMIT:
            chunks.append(current)
            current = entry
        else:
            current = next_message

    if current:
        chunks.append(current)

    return [_fit_telegram_limit(chunk) for chunk in chunks]


def send_telegram_messages(messages: list[str]) -> None:
    url = f"{TELEGRAM_API_BASE.rstrip('/')}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for idx, message in enumerate(messages, start=1):
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if not response.ok:
            log.error("Telegram API error %s: %s", response.status_code, response.text)
            response.raise_for_status()
        log.info("Telegram message %d/%d sent.", idx, len(messages))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today().isoformat()
    log.info("=== QA Job Scraper - %s ===", today)

    rates = get_exchange_rates()

    # ── 1. Collect raw jobs from all sources ──────────────────────────────────
    raw: list[dict] = []

    for query in JOBSPY_QUERIES:
        for location, country in JOBSPY_SEARCH_LOCATIONS:
            raw.extend(scrape_jobspy(query, location, country))

    raw.extend(fetch_weworkremotely())
    raw.extend(fetch_remotive())
    raw.extend(fetch_remoteok())
    raw.extend(fetch_greenhouse())
    raw.extend(fetch_lever())
    raw.extend(fetch_jobright())
    raw.extend(fetch_jobicy())
    raw.extend(fetch_workingnomads())
    raw.extend(fetch_workatastartup())
    raw.extend(fetch_arbeitnow())
    raw.extend(fetch_remotefirstjobs())
    raw.extend(fetch_remotejobs_org())
    raw.extend(fetch_workanywhere())
    raw.extend(fetch_himalayas())
    raw.extend(fetch_hireweb3())

    log.info("Total raw records before filtering: %d", len(raw))

    # ── 2. Filter with per-stage counts for debugging ─────────────────────────
    after_shape     = [j for j in raw             if _valid_job(j)]
    after_qa        = [j for j in after_shape     if is_qa_relevant(j)]
    after_level     = [j for j in after_qa        if is_fresh_grad_friendly(j)]
    after_recency   = [j for j in after_level     if is_posted_recently(j)]
    after_location  = [j for j in after_recency   if is_location_ok(j)]
    after_tz        = [j for j in after_location  if is_timezone_ok(j)]
    after_salary    = [j for j in after_tz        if salary_ok(j, rates)]

    log.info(
        "Filter funnel: raw=%d -> shape=%d -> qa_title=%d -> fresh_grad=%d -> recency=%d -> location=%d -> tz=%d -> salary=%d",
        len(raw), len(after_shape), len(after_qa), len(after_level), len(after_recency),
        len(after_location), len(after_tz), len(after_salary),
    )

    qualified = after_salary

    # ── 3. Deduplicate & sort (intern roles first, then priority companies, then newest) ─────────
    qualified = deduplicate(qualified)
    qualified.sort(
        key=lambda j: (
            role_priority_rank(j),
            0 if j["company"].lower().strip() in PRIORITY_COMPANIES else 1,
            -(parse_posted_dt(j) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        ),
    )
    qualified = qualified[:50]

    log.info("Final digest size: %d jobs", len(qualified))

    # ── 4. Source breakdown for Telegram header ───────────────────────────────
    source_stats: dict[str, int] = {}
    for j in qualified:
        src = j.get("source", "Other")
        source_stats[src] = source_stats.get(src, 0) + 1

    # ── 5. Build & send Telegram digest ───────────────────────────────────────
    messages = build_telegram_messages(qualified, rates, today, source_stats)
    send_telegram_messages(messages)
    log.info("Done.")


if __name__ == "__main__":
    main()
