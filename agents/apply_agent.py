"""
Apply Agent — Automatically applies to jobs using two methods:
  1. Email Apply  — sends resume via Gmail if job has a contact email
  2. Easy Apply   — uses Playwright to click Apply button and fill forms

Safety rules:
  - Max 20 applications per day per platform (to avoid bans)
  - 30-60 second random delay between applications
  - Skips if required field is missing from master_profile

Usage:
  python agents/apply_agent.py
"""

import json
import os
import random
import smtplib
import time
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE    = "filtered_jobs.json"
USERS_FILE    = "users.json"
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
MAX_APPLIES_PER_DAY = 20


def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return {u["email"]: u for u in json.load(f)}
    return {}


def generate_cover_letter(user: dict, job: dict) -> str:
    mp = user.get("master_profile", {})
    return f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job.get('title', 'position')} role at {job.get('company', 'your company')}.

I am a {user.get('education', 'Computer Science graduate')} with {user.get('experience_years', 0)} year(s) of experience and {user.get('internship_months', 0)} month(s) of internship experience. My key skills include {', '.join(s for s in user.get('skills', [])[:6] if s)}.

I am available to join {mp.get('notice_period', 'immediately')} and my expected CTC is {mp.get('expected_ctc', 'negotiable')} LPA.

I have attached my resume for your review and would welcome the opportunity to discuss this role further.

Best regards,
{user.get('name', '')}
{user.get('phone', '')} | {user.get('email', '')}
{user.get('linkedin', '')}
{mp.get('github', '')}
"""


def email_apply(user: dict, job: dict) -> tuple[bool, str]:
    """Send resume + cover letter to job contact email."""
    contact_email = job.get("contact_email")
    if not contact_email:
        return False, "No contact email"

    resume_path = user.get("resume_path")
    if not resume_path or not os.path.exists(resume_path):
        return False, "Resume file not found — set resume_path in your profile"

    try:
        msg = MIMEMultipart()
        msg["Subject"] = f"Application for {job.get('title')} — {user.get('name')}"
        msg["From"]    = EMAIL_ADDRESS
        msg["To"]      = contact_email
        msg.attach(MIMEText(generate_cover_letter(user, job), "plain"))

        with open(resume_path, "rb") as f:
            att = MIMEApplication(f.read(), _subtype="pdf")
            att.add_header("Content-Disposition", "attachment",
                           filename=os.path.basename(resume_path))
            msg.attach(att)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            s.sendmail(EMAIL_ADDRESS, contact_email, msg.as_string())
        return True, "Email sent"
    except Exception as e:
        return False, str(e)


def easy_apply(user: dict, job: dict) -> tuple[bool, str]:
    """Use Playwright to click Easy Apply and fill the form."""
    from playwright.sync_api import sync_playwright

    mp = user.get("master_profile", {})
    resume_path = user.get("resume_path", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()

        try:
            page.goto(job["link"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Find Apply button
            apply_btn = page.query_selector(
                'button:has-text("Easy Apply"), button:has-text("Apply Now"), '
                'button:has-text("Apply"), a:has-text("Apply")'
            )
            if not apply_btn:
                return False, "No Apply button found"

            apply_btn.click()
            page.wait_for_timeout(2000)

            content = page.content()

            # Check for fields we can't fill
            required_missing = []
            if "Total Experience" in content and not user.get("experience_years"):
                required_missing.append("Total Experience")
            if "Current CTC" in content and not mp.get("current_ctc"):
                required_missing.append("Current CTC")
            if "Notice Period" in content and not mp.get("notice_period"):
                required_missing.append("Notice Period")

            if required_missing:
                browser.close()
                return False, f"Missing fields: {', '.join(required_missing)}"

            # Fill common fields
            for selector in ['input[name*="phone"]', 'input[placeholder*="phone"]',
                             'input[placeholder*="Phone"]']:
                el = page.query_selector(selector)
                if el and user.get("phone"):
                    el.fill(user["phone"])

            for selector in ['input[name*="name"]', 'input[placeholder*="Full Name"]']:
                el = page.query_selector(selector)
                if el and user.get("name"):
                    el.fill(user["name"])

            for selector in ['input[name*="email"]', 'input[placeholder*="email"]']:
                el = page.query_selector(selector)
                if el and user.get("email"):
                    el.fill(user["email"])

            if mp.get("current_ctc"):
                for selector in ['input[name*="currentCTC"]', 'input[placeholder*="Current CTC"]']:
                    el = page.query_selector(selector)
                    if el:
                        el.fill(str(mp["current_ctc"]))

            if mp.get("expected_ctc"):
                for selector in ['input[name*="expectedCTC"]', 'input[placeholder*="Expected CTC"]']:
                    el = page.query_selector(selector)
                    if el:
                        el.fill(str(mp["expected_ctc"]))

            # Upload resume
            if resume_path and os.path.exists(resume_path):
                file_input = page.query_selector('input[type="file"]')
                if file_input:
                    file_input.set_input_files(resume_path)

            # Submit
            submit_btn = page.query_selector(
                'button:has-text("Submit"), button:has-text("Send Application"), '
                'button:has-text("Apply")'
            )
            if submit_btn:
                submit_btn.click()
                page.wait_for_timeout(2000)
                browser.close()
                return True, "Easy Apply submitted"

            browser.close()
            return False, "Submit button not found"

        except Exception as e:
            browser.close()
            return False, str(e)


def run_apply_agent():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ '{INPUT_FILE}' not found. Run filter_agent.py first.")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        all_jobs = json.load(f)

    users        = load_users()
    applied      = 0
    skipped      = 0
    daily_counts = {}  # track per-platform count

    for job in all_jobs:
        if job.get("status") != "auto_apply":
            continue
        if job.get("applied_at"):
            skipped += 1
            continue

        user = users.get(job.get("user_email"))
        if not user:
            continue

        source = job.get("source", "unknown")
        daily_counts[source] = daily_counts.get(source, 0)

        # Rate limit: max 20 per platform per day
        if daily_counts[source] >= MAX_APPLIES_PER_DAY:
            print(f"⏸️  Daily limit reached for {source} — skipping")
            skipped += 1
            continue

        print(f"\n📤 {job.get('title')} @ {job.get('company')} [{source}]")

        # Try email apply first, then Easy Apply
        success, msg = False, "No method available"

        if job.get("contact_email"):
            success, msg = email_apply(user, job)
            print(f"   📧 Email apply: {msg}")
        else:
            success, msg = easy_apply(user, job)
            print(f"   🖱️  Easy apply: {msg}")

        if success:
            job["status"]     = "applied"
            job["applied_at"] = datetime.utcnow().isoformat()
            job["apply_method"] = "email" if job.get("contact_email") else "easy_apply"
            applied += 1
            daily_counts[source] += 1
        else:
            if "Missing fields" in msg:
                job["status"] = "manual_review"
            skipped += 1

        # Polite delay: 30-60 seconds between applications
        if applied > 0:
            delay = random.randint(30, 60)
            print(f"   ⏳ Waiting {delay}s before next application...")
            time.sleep(delay)

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Applied: {applied}  |  Skipped: {skipped}")
    print(f"💾 {INPUT_FILE} updated.")


if __name__ == "__main__":
    run_apply_agent()
