"""
Follow-up Agent — Sends follow-up emails for jobs applied 7+ days ago with no response.

Add to your .env:
  YOUR_NAME=Your Full Name
  YOUR_PHONE=+91 9876543210
  YOUR_LINKEDIN=linkedin.com/in/yourprofile
"""

import json
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(__file__))
from email_agent import send_email, validate_config

JOBS_FILE     = "filtered_jobs.json"
FOLLOWUP_DAYS = 7

YOUR_NAME     = os.getenv("YOUR_NAME", "Your Name")
YOUR_PHONE    = os.getenv("YOUR_PHONE", "")
YOUR_LINKEDIN = os.getenv("YOUR_LINKEDIN", "")


def needs_followup(job: dict) -> bool:
    """Return True if job was applied 7+ days ago, no response, no follow-up sent yet."""
    # Include both "applied" (manually marked) and "auto_apply" (agent-applied, status not updated)
    if job.get("status") not in ("applied", "auto_apply"):
        return False
    if job.get("follow_up_sent"):
        return False
    if job.get("response") in ("interview", "rejected", "shortlisted", "offer"):
        return False  # already got a response

    # Fallback to scraped_at if applied_at not set (auto_apply jobs may not have it)
    applied_at = job.get("applied_at") or job.get("scraped_at")
    if not applied_at:
        return False

    try:
        cutoff = datetime.utcnow() - timedelta(days=FOLLOWUP_DAYS)
        return datetime.fromisoformat(applied_at) <= cutoff
    except ValueError:
        return False


def build_followup_html(jobs: list[dict]) -> str:
    td = "padding:10px;border-bottom:1px solid #eee;"
    th = "background:#1a73e8;color:white;padding:10px;text-align:left;"

    rows = "".join(
        f"""<tr>
            <td style="{td}"><a href="{j['link']}" style="color:#1a73e8;">{j['title']}</a></td>
            <td style="{td}">{j.get('company', '')}</td>
            <td style="{td}">{(j.get('applied_at') or j.get('scraped_at', ''))[:10]}</td>
        </tr>"""
        for j in jobs
    )

    contact_line = " · ".join(filter(None, [YOUR_PHONE, YOUR_LINKEDIN]))

    return f"""
    <html>
    <body style="background:#f9f9f9;padding:20px;">
      <div style="max-width:700px;margin:auto;background:white;padding:24px;
                  border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
        <h2 style="color:#333;">📬 Follow-up Reminder</h2>
        <p style="color:#555;">
          These <b>{len(jobs)}</b> applications were sent 7+ days ago with no response.
          Consider sending a follow-up email to each company.
        </p>
        <table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;">
          <tr>
            <th style="{th}">Job Title</th>
            <th style="{th}">Company</th>
            <th style="{th}">Applied On</th>
          </tr>
          {rows}
        </table>
        <br>
        <p style="color:#555;font-size:13px;">
          <b>Suggested follow-up message:</b><br>
          <i>"Hi, I applied for the [Role] position on [Date] and wanted to follow up
          on my application status. I remain very interested in this opportunity."</i>
        </p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="color:#aaa;font-size:12px;">
          {YOUR_NAME}{' · ' + contact_line if contact_line else ''}
        </p>
      </div>
    </body>
    </html>
    """


def run_followup_agent():
    validate_config()

    if not os.path.exists(JOBS_FILE):
        print(f"❌ '{JOBS_FILE}' not found. Run filter_agent.py first.")
        return

    with open(JOBS_FILE, encoding="utf-8") as f:
        jobs = json.load(f)

    due = [j for j in jobs if needs_followup(j)]

    if not due:
        print("✅ No follow-ups needed today.")
        return

    print(f"📬 {len(due)} job(s) need a follow-up. Sending email...")

    send_email(
        subject=f"📬 Follow-up Reminder — {len(due)} application(s) need attention",
        html_body=build_followup_html(due),
    )

    due_links = {j["link"] for j in due}
    for job in jobs:
        if job.get("link") in due_links:
            job["follow_up_sent"] = True

    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)

    print(f"📧 Follow-up email sent for {len(due)} job(s).")
    print("💾 filtered_jobs.json updated with follow_up_sent: true")


if __name__ == "__main__":
    run_followup_agent()
