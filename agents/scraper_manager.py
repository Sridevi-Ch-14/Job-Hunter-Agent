"""
Multi-Platform Scraper — Scrapes fresher jobs from:
  1. Naukri.com       — largest Indian job board
  2. Internshala.com  — best for Indian freshers & recent grads
  3. Indeed India     — entry-level filters built-in
  4. LinkedIn Jobs    — MNC and startup jobs

All results are merged, deduplicated, and saved to scraped_jobs.json.

Usage:
  python agents/scraper_manager.py                   # scrape all platforms
  python agents/scraper_manager.py --only naukri     # scrape one platform
  python agents/scraper_manager.py --only internshala
"""

import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page


# ── Config ────────────────────────────────────────────────────────────────────
SEARCH_QUERIES = [
    "software engineer fresher",
    "python developer fresher",
    "web developer fresher",
    "data analyst fresher",
    "internshala.com/jobs/matching-fresher-jobs"
]

OUTPUT_FILE = "scraped_jobs.json"
MAX_PAGES   = 2   # per query per platform


# ── Shared utilities ──────────────────────────────────────────────────────────
def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_salary_from_text(text):
    # Regex to find patterns like 4-6 LPA, 5,00,000, 80k per month, etc.
    patterns = [
        r'(\d+\s*-\s*\d+\s*LPA)',
        r'(₹?\d+[,.]\d+[,.]\d+)',
        r'(\d+\s*k\s*/\s*month)'
    ]
    for p in patterns:
        match = re.search(p, text or "", re.IGNORECASE)
        if match:
            return match.group(0)
    return "Not disclosed"


def is_fresher(experience: str) -> bool:
    exp = experience.lower()
    if any(k in exp for k in ("fresher", "0 year", "0-1", "0-2", "entry")):
        return True
    nums = re.findall(r"\d+", exp)
    return bool(nums and int(nums[0]) <= 2)


def make_job(title, company, location, experience, skills,
             salary, description, link, source) -> dict:
    salary_text = clean(salary)
    if not salary_text or salary_text.lower().strip() in ("not disclosed", "n/a"):
        salary_text = extract_salary_from_text(description)

    return {
        "title"      : clean(title),
        "company"    : clean(company),
        "location"   : clean(location),
        "experience" : clean(experience),
        "skills"     : [clean(s) for s in skills if s],
        "salary"     : salary_text or "Not disclosed",
        "description": clean(description),
        "link"       : link,
        "source"     : source,
        "scraped_at" : datetime.now().isoformat(),
        "status"     : "new",
    }


def save_and_merge_jobs(new_jobs):
    FILE_PATH = OUTPUT_FILE
    existing_jobs = []

    # 1. Load existing jobs
    if os.path.exists(FILE_PATH):
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            try:
                existing_jobs = json.load(f)
            except Exception:
                existing_jobs = []

    # 2. Merge by Link (Deduplicate), keep old records
    job_dict = {j.get("link"): j for j in existing_jobs if j.get("link")}
    for nj in new_jobs:
        if nj.get("link"):
            job_dict[nj["link"]] = nj

    final_list = list(job_dict.values())

    # 3. Keep only last 300 jobs as requested
    final = sorted(
        final_list,
        key=lambda x: x.get("scraped_at", ""),
        reverse=True
    )[:300]

    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2, ensure_ascii=False)

    print(f"✅ Total Jobs in Database: {len(final)} (Fetched {len(new_jobs)} new)")
    return final


# ══════════════════════════════════════════════════════════════════════════════
# 1. NAUKRI
# ══════════════════════════════════════════════════════════════════════════════
async def scrape_naukri(query: str, page: Page) -> list[dict]:
    results = []
    # Use fresher-specific Naukri URL structure
    for page_num in range(1, MAX_PAGES + 1):
        url = (
            f"https://www.naukri.com/fresher-jobs-in-india"
            f"?k={query.replace(' ', '%20')}&experience=0&sort=freshness&pageNo={page_num}"
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Try multiple selector patterns — Naukri updates these frequently
            cards = (
                await page.query_selector_all('article.jobTuple') or
                await page.query_selector_all('[class*="jobTuple"]') or
                await page.query_selector_all('[class*="job-tuple"]') or
                await page.query_selector_all('.cust-job-tuple')
            )

            if not cards:
                print(f"  ⚠️  Naukri: no cards found on page {page_num} — selectors may have changed")
                break

            for card in cards:
                try:
                    title_el  = (
                        await card.query_selector("a.title") or
                        await card.query_selector('[class*="title"] a') or
                        await card.query_selector("a[title]")
                    )
                    title = clean(await title_el.inner_text()) if title_el else ""
                    link  = await title_el.get_attribute("href") if title_el else ""
                    if not title or not link:
                        continue
                    if not link.startswith("http"):
                        link = f"https://www.naukri.com{link}"

                    comp_el   = await card.query_selector("a.subTitle, [class*='comp-name']")
                    exp_el    = await card.query_selector('[class*="experience"], [class*="exp"]')
                    loc_el    = await card.query_selector('[class*="location"], [class*="loc"]')
                    sal_el    = await card.query_selector('[class*="salary"], [class*="sal"]')
                    desc_el   = await card.query_selector('[class*="job-description"], [class*="desc"]')
                    skill_els = await card.query_selector_all('[class*="tag"], [class*="skill"]')

                    exp = clean(await exp_el.inner_text()) if exp_el else ""
                    if not exp or is_fresher(exp):
                        results.append(make_job(
                            title       = title,
                            company     = clean(await comp_el.inner_text())  if comp_el  else "",
                            location    = clean(await loc_el.inner_text())   if loc_el   else "",
                            experience  = exp or "Fresher",
                            skills      = [clean(await s.inner_text()) for s in skill_els],
                            salary      = clean(await sal_el.inner_text())   if sal_el   else "",
                            description = clean(await desc_el.inner_text())  if desc_el  else "",
                            link        = link,
                            source      = "Naukri",
                        ))
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️  Naukri page {page_num} error: {e}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 2. INTERNSHALA
# ══════════════════════════════════════════════════════════════════════════════
async def scrape_internshala(query: str, page: Page) -> list[dict]:
    """
    Internshala is very bot-friendly and best for Indian freshers.
    Uses the matching-fresher-jobs URL for better results.
    """
    results = []

    # Use the fresher-specific matching URL
    urls = [
        f"https://internshala.com/jobs/matching-fresher-jobs",
        f"https://internshala.com/jobs/{query.replace(' ', '-').lower()}-jobs",
    ]

    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            cards = (
                await page.query_selector_all(".individual_internship") or
                await page.query_selector_all('[class*="internship_meta"]') or
                await page.query_selector_all(".job-internship-card")
            )

            for card in cards:
                try:
                    title_el = (
                        await card.query_selector(".job-internship-name") or
                        await card.query_selector(".profile") or
                        await card.query_selector("h3")
                    )
                    title = clean(await title_el.inner_text()) if title_el else ""
                    if not title:
                        continue

                    link_el = (
                        await card.query_selector("a.view_detail_button") or
                        await card.query_selector("a.job-title-href") or
                        await card.query_selector("a[href*='/jobs/']") or
                        await card.query_selector("a[href*='/internship/']") 
                    )
                    href = await link_el.get_attribute("href") if link_el else ""
                    link = f"https://internshala.com{href}" if href and not href.startswith("http") else href
                    if not link:
                        continue

                    comp_el = await card.query_selector(".company-name, .company_name")
                    loc_el  = await card.query_selector(".locations, .location_link")
                    sal_el  = await card.query_selector(".stipend, .salary")

                    results.append(make_job(
                        title       = title,
                        company     = clean(await comp_el.inner_text()) if comp_el else "",
                        location    = clean(await loc_el.inner_text())  if loc_el  else "",
                        experience  = "0 years",
                        skills      = [],
                        salary      = clean(await sal_el.inner_text())  if sal_el  else "",
                        description = "",
                        link        = link,
                        source      = "Internshala",
                    ))
                except Exception:
                    continue

            if results:
                break  # stop if first URL worked

        except Exception as e:
            print(f"  ⚠️  Internshala error ({url[:50]}): {e}")

    return list({j["link"]: j for j in results}.values())


# ══════════════════════════════════════════════════════════════════════════════
# 3. INDEED INDIA
# ══════════════════════════════════════════════════════════════════════════════
async def scrape_indeed(query: str, page: Page) -> list[dict]:
    results = []
    for page_num in range(MAX_PAGES):
        start = page_num * 10
        url   = (
            f"https://in.indeed.com/jobs?q={query.replace(' ', '+')}"
            f"&l=India&fromage=1&explvl=entry_level&sort=date&start={start}"
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            cards = await page.query_selector_all('[class*="job_seen_beacon"]')
            for card in cards:
                try:
                    title_el = await card.query_selector('[class*="jobTitle"]')
                    title    = clean(await title_el.inner_text()) if title_el else ""
                    if not title:
                        continue

                    link_el  = await card.query_selector("a[data-jk]")
                    jk       = await link_el.get_attribute("data-jk") if link_el else ""
                    link     = f"https://in.indeed.com/viewjob?jk={jk}" if jk else ""
                    if not link:
                        continue

                    comp_el  = await card.query_selector('[data-testid="company-name"]')
                    loc_el   = await card.query_selector('[data-testid="text-location"]')
                    sal_el   = await card.query_selector('[class*="salary"]')
                    snip_el  = await card.query_selector('[class*="job-snippet"]')

                    results.append(make_job(
                        title       = title,
                        company     = clean(await comp_el.inner_text()) if comp_el else "",
                        location    = clean(await loc_el.inner_text())  if loc_el  else "",
                        experience  = "0-2 years",
                        skills      = [],
                        salary      = clean(await sal_el.inner_text())  if sal_el  else "",
                        description = clean(await snip_el.inner_text()) if snip_el else "",
                        link        = link,
                        source      = "Indeed",
                    ))
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️  Indeed page {page_num + 1} error: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 4. LINKEDIN JOBS
# ══════════════════════════════════════════════════════════════════════════════
async def scrape_linkedin(query: str, page: Page) -> list[dict]:
    results = []
    url = (
        f"https://www.linkedin.com/jobs/search?"
        f"keywords={query.replace(' ', '%20')}"
        f"&location=India&f_E=1&f_E=2&f_TPR=r86400"   # experience: Internship + Entry level + Posted last 24h
    )
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)  # LinkedIn needs more render time

        cards = await page.query_selector_all(".job-search-card")
        for card in cards:
            try:
                title_el = await card.query_selector(".base-search-card__title")
                title    = clean(await title_el.inner_text()) if title_el else ""
                if not title:
                    continue

                link_el  = await card.query_selector("a.base-card__full-link")
                link     = await link_el.get_attribute("href") if link_el else ""
                if not link:
                    continue

                comp_el  = await card.query_selector(".base-search-card__subtitle")
                loc_el   = await card.query_selector(".job-search-card__location")

                results.append(make_job(
                    title       = title,
                    company     = clean(await comp_el.inner_text()) if comp_el else "",
                    location    = clean(await loc_el.inner_text())  if loc_el  else "",
                    experience  = "Entry Level",
                    skills      = [],
                    salary      = "Not disclosed",
                    description = "",
                    link        = link.split("?")[0],  # strip tracking params
                    source      = "LinkedIn",
                ))
            except Exception:
                continue
    except Exception as e:
        print(f"  ⚠️  LinkedIn error: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MANAGER — runs selected platforms, merges and deduplicates
# ══════════════════════════════════════════════════════════════════════════════
PLATFORMS = {
    "naukri"     : scrape_naukri,
    "internshala": scrape_internshala,
    "indeed"     : scrape_indeed,
    "linkedin"   : scrape_linkedin,
}


async def run_all_scrapers(only: str = None) -> list[dict]:
    platforms = {only: PLATFORMS[only]} if only else PLATFORMS
    all_jobs  = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        page = await context.new_page()

        for name, scraper_fn in platforms.items():
            print(f"\n{'═' * 50}")
            print(f"🌐 {name.upper()}")
            print(f"{'═' * 50}")

            platform_jobs = []
            for query in SEARCH_QUERIES:
                print(f"  🔍 '{query}'")
                jobs = await scraper_fn(query, page)
                platform_jobs.extend(jobs)
                print(f"     → {len(jobs)} jobs")
                await asyncio.sleep(2)

            # Deduplicate within platform
            unique = list({j["link"]: j for j in platform_jobs if j["link"]}.values())
            print(f"  ✅ {len(unique)} unique jobs from {name}")
            all_jobs.extend(unique)

        await browser.close()

    # Deduplicate across all platforms
    final = list({j["link"]: j for j in all_jobs if j["link"]}.values())

    # Append + rotate onto existing dataset
    saved = save_and_merge_jobs(final)

    print(f"\n{'═' * 50}")
    print(f"🎉 Total unique jobs after merge: {len(saved)}")
    for source, count in Counter(j["source"] for j in saved).items():
        print(f"   {source:15} : {count}")
    print(f"{'═' * 50}")
    print(f"💾 Saved to {OUTPUT_FILE}")

    return saved


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        idx  = sys.argv.index("--only")
        only = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if only and only not in PLATFORMS:
            print(f"❌ Unknown platform '{only}'. Choose from: {', '.join(PLATFORMS)}")
            sys.exit(1)

    asyncio.run(run_all_scrapers(only=only))
