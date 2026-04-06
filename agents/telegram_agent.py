"""
Telegram Alert Agent — Sends instant job alerts to your Telegram.

Setup (2 minutes):
  1. Telegram → search @BotFather → /newbot → copy token → set TELEGRAM_BOT_TOKEN in .env
  2. Telegram → search @userinfobot → send any message → copy Chat ID → set TELEGRAM_CHAT_ID in .env

Test:
  python agents/telegram_agent.py --test
"""

import json
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE         = "filtered_jobs.json"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def validate_config():
    missing = [k for k, v in {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID"  : TELEGRAM_CHAT_ID,
    }.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing .env keys: {', '.join(missing)}\n"
            "  1. Telegram → @BotFather → /newbot → copy token\n"
            "  2. Telegram → @userinfobot → copy your chat ID"
        )


def send_message(text: str, disable_preview: bool = False) -> bool:
    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id"                 : TELEGRAM_CHAT_ID,
                "text"                    : text,
                "parse_mode"              : "Markdown",
                "disable_web_page_preview": disable_preview,
            },
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"  ⚠️  Telegram error: {data.get('description')}")
            return False
        return True
    except requests.RequestException as e:
        print(f"  ⚠️  Request failed: {e}")
        return False


def build_summary(auto: list, review: list) -> str:
    return (
        f"🤖 *AI Job Hunter — New Batch*\n"
        f"{'─' * 28}\n"
        f"✅ Auto-apply : {len(auto)} jobs\n"
        f"👀 To review  : {len(review)} jobs\n"
        f"📊 Total      : {len(auto) + len(review)} matches\n"
        f"\n_Sending details below..._"
    )


def build_job_message(job: dict) -> str:
    score  = job.get("ai_score", 0)
    status = job.get("status", "")
    badge  = "✅ AUTO-APPLY" if status == "auto_apply" else "👀 REVIEW"

    matched = ", ".join(job.get("matched_skills", [])[:4]) or "—"
    missing = ", ".join(job.get("missing_skills", [])[:3]) or "—"

    return (
        f"{badge} | Score: *{score}%*\n"
        f"\n"
        f"🏢 *{job.get('title', '')}*\n"
        f"📍 {job.get('company', '')} · {job.get('location', '')}\n"
        f"💼 {job.get('experience', 'Not mentioned')}\n"
        f"💰 {job.get('salary', 'Not disclosed')}\n"
        f"\n"
        f"✔️ Matched: {matched}\n"
        f"❗ Missing: {missing}\n"
        f"\n"
        f"🔗 [Apply Here]({job.get('link', '')})"
    )


def run_telegram_agent():
    validate_config()

    if not os.path.exists(INPUT_FILE):
        print(f"❌ '{INPUT_FILE}' not found. Run filter_agent.py first.")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        jobs = json.load(f)

    auto    = [j for j in jobs if j.get("status") == "auto_apply"]
    review  = [j for j in jobs if j.get("status") == "manual_review"]
    relevant = auto + review

    if not relevant:
        print("📭 No relevant jobs to send.")
        return

    print(f"📲 Sending {len(relevant)} jobs to Telegram...")

    send_message(build_summary(auto, review))
    time.sleep(1)

    if auto:
        send_message("✅ *AUTO-APPLY JOBS*", disable_preview=True)
        for job in auto:
            send_message(build_job_message(job))
            time.sleep(0.5)  # Telegram rate limit: 30 msg/sec

    if review:
        send_message("👀 *MANUAL REVIEW JOBS*", disable_preview=True)
        for job in review:
            send_message(build_job_message(job))
            time.sleep(0.5)

    print(f"✅ Sent {len(relevant)} job alerts to Telegram.")


def test_connection():
    validate_config()
    ok = send_message(
        "🤖 *AI Job Hunter Bot is connected!*\n"
        "You will receive job alerts here automatically."
    )
    print("✅ Test message sent!" if ok else "❌ Failed — check your token and chat ID.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_connection()
    else:
        run_telegram_agent()
