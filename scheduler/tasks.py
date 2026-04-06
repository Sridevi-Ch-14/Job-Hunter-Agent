"""
scheduler/tasks.py — Local scheduler (runs agents on your PC).

Usage:
  python scheduler/tasks.py

Schedule:
  - Scrape all platforms + Filter + Email + Telegram : every 30 minutes
  - Follow-up check                                  : daily at 9:00 AM
"""

import asyncio
import logging
import os
import sys
import time

import schedule
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "agents"))

from scraper_manager import run_all_scrapers
from filter_agent    import run_filter_agent
from email_agent     import run_email_agent
from telegram_agent  import run_telegram_agent
from followup_agent  import run_followup_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scheduler.log", mode="a"),
    ],
)
log = logging.getLogger(__name__)


def run_full_pipeline():
    log.info("=" * 55)
    log.info("🚀 PIPELINE START")
    log.info("=" * 55)

    try:
        log.info("Step 1/4 — Multi-Platform Scraper")
        asyncio.run(run_all_scrapers())
    except Exception as e:
        log.error(f"❌ Scraper failed: {e}")
        return

    try:
        log.info("Step 2/4 — AI Filter Agent")
        run_filter_agent()
    except Exception as e:
        log.error(f"❌ Filter failed: {e}")
        return

    try:
        log.info("Step 3/4 — Email Agent")
        run_email_agent()
    except Exception as e:
        log.error(f"❌ Email failed: {e}")

    try:
        log.info("Step 4/4 — Telegram Agent")
        run_telegram_agent()
    except Exception as e:
        log.error(f"❌ Telegram failed: {e}")

    log.info("✅ PIPELINE COMPLETE\n")


def run_followup():
    log.info("📬 Running Follow-up Agent...")
    try:
        run_followup_agent()
        log.info("✅ Follow-up done.\n")
    except Exception as e:
        log.error(f"❌ Follow-up failed: {e}\n")


schedule.every(30).minutes.do(run_full_pipeline)
schedule.every().day.at("09:00").do(run_followup)

if __name__ == "__main__":
    log.info("🤖 AI Job Hunter Scheduler started")
    log.info("   Pipeline  : every 30 min (Naukri + Internshala + Indeed + LinkedIn)")
    log.info("   Alerts    : Email + Telegram")
    log.info("   Follow-up : daily at 09:00 AM")
    log.info("   Press Ctrl+C to stop\n")

    log.info("▶️  Running pipeline now on startup...")
    run_full_pipeline()

    while True:
        schedule.run_pending()
        time.sleep(30)
