"""
Email Agent — Sends personalized job alert emails to every registered user.

Reads filtered_jobs.json (output of filter_agent.py).
Groups jobs by user_email and sends one email per user.
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE     = "filtered_jobs.json"
EMAIL_ADDRESS  = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def validate_config():
    missing = [k for k, v in {
        "EMAIL_ADDRESS" : EMAIL_ADDRESS,
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
    }.items() if not v]
    if missing:
        raise EnvironmentError(
            f"Missing .env keys: {', '.join(missing)}\n"
            "Add them to your .env file and try again."
        )


def build_html(user_name: str, jobs: list[dict]) -> str:
    auto   = [j for j in jobs if j.get("status") == "auto_apply"]
    review = [j for j in jobs if j.get("status") == "manual_review"]

    table_style = "border-collapse:collapse;width:100%;font-family:Arial,sans-serif;font-size:14px;"
    th_style    = "background:#4CAF50;color:white;padding:10px 8px;text-align:left;"
    td_style    = "padding:8px;border-bottom:1px solid #ddd;vertical-align:top;"

    def rows(job_list):
        if not job_list:
            return f'<tr><td colspan="5" style="{td_style}color:#999;">No jobs in this category.</td></tr>'
        return "".join(
            f"""<tr>
                <td style="{td_style}"><a href="{j['link']}" style="color:#1a73e8;">{j['title']}</a></td>
                <td style="{td_style}">{j.get('company','')}</td>
                <td style="{td_style}">{j.get('location','')}</td>
                <td style="{td_style};font-weight:bold;color:{'green' if j.get('ai_score',0)>=70 else 'orange'}">
                    {j.get('ai_score',0)}%
                </td>
                <td style="{td_style};color:#555;">{j.get('ai_reason','')}</td>
            </tr>"""
            for j in job_list
        )

    headers    = ["Title", "Company", "Location", "Score", "Reason"]
    header_row = "".join(f'<th style="{th_style}">{h}</th>' for h in headers)

    return f"""
    <html>
    <body style="background:#f9f9f9;padding:20px;">
      <div style="max-width:900px;margin:auto;background:white;padding:24px;
                  border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
        <h2 style="color:#333;">🤖 AI Job Hunter — Your Daily Matches</h2>
        <p style="color:#777;">Hi {user_name}, here are today's job matches personalized for your profile.</p>
        <p style="color:#777;margin-top:0;">
          {len(auto)+len(review)} matches &nbsp;|&nbsp;
          {len(auto)} auto-apply &nbsp;|&nbsp; {len(review)} to review
        </p>
        <hr style="border:none;border-top:1px solid #eee;margin-bottom:20px;">

        <h3 style="color:#2e7d32;">✅ Auto-Apply Jobs ({len(auto)})</h3>
        <table style="{table_style}"><tr>{header_row}</tr>{rows(auto)}</table>
        <br>
        <h3 style="color:#e65100;">👀 Manual Review Jobs ({len(review)})</h3>
        <table style="{table_style}"><tr>{header_row}</tr>{rows(review)}</table>

        <br>
        <p style="color:#aaa;font-size:12px;text-align:center;">
          Sent by AI Job Hunter · Do not reply to this email
        </p>
      </div>
    </body>
    </html>
    """


def send_email(to_address: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_ADDRESS
    msg["To"]      = to_address
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_address, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed.\n"
            "Use a Gmail App Password, not your account password.\n"
            "Generate one at: myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Failed to send email: {e}")


def run_email_agent():
    validate_config()

    if not os.path.exists(INPUT_FILE):
        print(f"❌ '{INPUT_FILE}' not found. Run filter_agent.py first.")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        all_jobs = json.load(f)

    # Group jobs by user
    user_jobs: dict[str, list] = {}
    for job in all_jobs:
        email = job.get("user_email")
        if email and job.get("status") in ("auto_apply", "manual_review"):
            user_jobs.setdefault(email, []).append(job)

    if not user_jobs:
        print("📭 No relevant jobs to email.")
        return

    print(f"📧 Sending emails to {len(user_jobs)} user(s)...\n")

    for email, jobs in user_jobs.items():
        user_name  = jobs[0].get("user_name", "there")
        auto_count = sum(1 for j in jobs if j["status"] == "auto_apply")
        rev_count  = sum(1 for j in jobs if j["status"] == "manual_review")

        try:
            send_email(
                to_address = email,
                subject    = f"🤖 Job Alert — {len(jobs)} matches ({auto_count} auto-apply, {rev_count} to review)",
                html_body  = build_html(user_name, jobs),
            )
            print(f"  ✅ {email} — {auto_count} auto-apply, {rev_count} to review")
        except Exception as e:
            print(f"  ❌ {email} — failed: {e}")


if __name__ == "__main__":
    run_email_agent()
