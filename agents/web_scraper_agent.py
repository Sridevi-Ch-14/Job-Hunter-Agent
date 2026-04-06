"""
Web Scraping Agent - Scrapes fresher jobs from Naukri.com
Uses Playwright for browser automation (handles JavaScript-rendered pages)
"""

import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright


# ──────────────────────────────────────────────
# CONFIG — edit these to match your preferences
# ──────────────────────────────────────────────
SEARCH_QUERIES = [
    "software engineer fresher",
    "python developer fresher",
    "web developer fresher",
    "data analyst fresher",
    "java developer fresher",
]

LOCATION = "India"
MAX_PAGES = 3          # pages to scrape per query (each page has ~20 jobs)
OUTPUT_FILE = "scraped_jobs.json"


# ──────────────────────────────────────────────
# SCRAPER
# ──────────────────────────────────────────────
class NaukriScraper:
    def __init__(self):
        self.jobs = []
        self.seen_links = set()   # avoid duplicates

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip() if text else ""

    def _is_fresher_job(self, experience: str) -> bool:
        """Only keep jobs requiring 0-2 years experience."""
        exp = experience.lower()
        if "fresher" in exp or "0 year" in exp or "0-1" in exp or "0-2" in exp:
            return True
        # catch patterns like "0 - 2 Yrs" or "1 Yrs"
        nums = re.findall(r"\d+", exp)
        if nums and int(nums[0]) <= 2:
            return True
        return False

    async def scrape_naukri(self, query: str, page_obj) -> list[dict]:
        """Scrape one search query from Naukri."""
        results = []

        for page_num in range(1, MAX_PAGES + 1):
            url = (
                f"https://www.naukri.com/{query.replace(' ', '-')}-jobs"
                f"?k={query.replace(' ', '%20')}&l={LOCATION}&experience=0&pageNo={page_num}"
            )

            print(f"  🔍 Scraping page {page_num}: {url[:80]}...")

            try:
                await page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page_obj.wait_for_timeout(2000)   # let JS render

                # Extract job cards
                job_cards = await page_obj.query_selector_all("article.jobTuple")

                if not job_cards:
                    # Try alternate selector (Naukri updates their HTML sometimes)
                    job_cards = await page_obj.query_selector_all('[class*="jobTuple"]')

                if not job_cards:
                    print(f"  ⚠️  No job cards found on page {page_num}. Site layout may have changed.")
                    break

                for card in job_cards:
                    job = await self._extract_job_data(card)
                    if job and job["link"] not in self.seen_links:
                        if self._is_fresher_job(job.get("experience", "")):
                            self.seen_links.add(job["link"])
                            results.append(job)

                print(f"     ✅ Found {len(results)} fresher jobs so far for '{query}'")

            except Exception as e:
                print(f"  ❌ Error on page {page_num}: {e}")
                continue

        return results

    async def _extract_job_data(self, card) -> dict | None:
        """Extract job details from a single job card."""
        try:
            # Title
            title_el = await card.query_selector("a.title")
            title = self._clean_text(await title_el.inner_text()) if title_el else ""
            link = await title_el.get_attribute("href") if title_el else ""

            # Company
            company_el = await card.query_selector("a.subTitle")
            company = self._clean_text(await company_el.inner_text()) if company_el else ""

            # Experience
            exp_el = await card.query_selector('[class*="experience"]')
            experience = self._clean_text(await exp_el.inner_text()) if exp_el else ""

            # Location
            loc_el = await card.query_selector('[class*="location"]')
            location = self._clean_text(await loc_el.inner_text()) if loc_el else ""

            # Skills (tags)
            skill_els = await card.query_selector_all('[class*="tag"]')
            skills = [self._clean_text(await s.inner_text()) for s in skill_els]

            # Salary (may not always be shown)
            sal_el = await card.query_selector('[class*="salary"]')
            salary = self._clean_text(await sal_el.inner_text()) if sal_el else "Not disclosed"

            # Description snippet
            desc_el = await card.query_selector('[class*="job-description"]')
            description = self._clean_text(await desc_el.inner_text()) if desc_el else ""

            if not title or not link:
                return None

            return {
                "title": title,
                "company": company,
                "experience": experience,
                "location": location,
                "skills": skills,
                "salary": salary,
                "description": description,
                "link": link if link.startswith("http") else f"https://www.naukri.com{link}",
                "source": "Naukri",
                "scraped_at": datetime.now().isoformat(),
                "status": "new",
            }

        except Exception as e:
            print(f"     ⚠️  Failed to parse a card: {e}")
            return None


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_scraper():
    scraper = NaukriScraper()
    all_jobs = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,                      # set False to watch the browser
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        for query in SEARCH_QUERIES:
            print(f"\n📌 Searching: '{query}'")
            jobs = await scraper.scrape_naukri(query, page)
            all_jobs.extend(jobs)
            await asyncio.sleep(2)   # polite delay between queries

        await browser.close()

    # Remove cross-query duplicates
    unique_jobs = {j["link"]: j for j in all_jobs}.values()
    final_jobs = list(unique_jobs)

    # Save to JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_jobs, f, indent=2, ensure_ascii=False)

    print(f"\n🎉 Done! Scraped {len(final_jobs)} unique fresher jobs → {OUTPUT_FILE}")
    return final_jobs


if __name__ == "__main__":
    asyncio.run(run_scraper())
