"""
AI Filter Agent — Scores scraped jobs against every registered user.

Uses Ollama (local) for scoring. Sends instant email alert for 90%+ matches.

Input  : scraped_jobs.json  (from scraper_manager.py)
         users.json         (registered users from dashboard)
Output : filtered_jobs.json (per-user scored jobs, used by email_agent.py)
"""

import json
import os
import time
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

INPUT_FILE   = "scraped_jobs.json"
USERS_FILE   = "users.json"
OUTPUT_FILE  = "filtered_jobs.json"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:1b"


def load_users() -> list[dict]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if url and key:
        try:
            from supabase import create_client
            return create_client(url, key).table("users").select("*").eq("active", True).execute().data
        except Exception as e:
            print(f"⚠️  Supabase error: {e}. Falling back to users.json")

    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def build_prompt(user: dict, job: dict) -> str:
    return f"""
You are a job matching assistant. Score how well this job fits the candidate.

--- CANDIDATE PROFILE ---
Skills             : {', '.join(s for s in user.get('skills', []) if s)}
Education          : {user.get('education', '')}
Experience         : {user.get('experience_years', 0)} years
Internships        : {user.get('internship_months', 0)} months
Looking For        : {user.get('looking_for', 'Full-time Job')}
Preferred Roles    : {', '.join(r for r in user.get('preferred_roles', []) if r)}
Preferred Locations: {', '.join(l for l in user.get('preferred_locations', []) if l)}

--- JOB DETAILS ---
Title      : {job.get('title', '')}
Company    : {job.get('company', '')}
Location   : {job.get('location', '')}
Experience : {job.get('experience', '')}
Skills     : {', '.join(job.get('skills', []))}
Description: {job.get('description', '')[:500]}

--- TASK ---
Reply in this EXACT JSON format (no markdown, no extra text):
{{
  "score": <integer 0-100>,
  "reason": "<one sentence>",
  "matched_skills": ["skill1"],
  "missing_skills": ["skill2"]
}}

Scoring guide:
- 80-100: Strong match
- 60-79 : Decent match
- 40-59 : Partial match
- 0-39  : Poor match
""".strip()


def score_job(user: dict, job: dict) -> dict:
    try:
        resp   = requests.post(OLLAMA_URL, json={
            "model" : OLLAMA_MODEL,
            "prompt": build_prompt(user, job),
            "stream": False,
        }, timeout=120)
        raw    = resp.json()["response"].strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return {
            "ai_score"      : int(result.get("score", 0)),
            "ai_reason"     : result.get("reason", ""),
            "matched_skills": result.get("matched_skills", []),
            "missing_skills": result.get("missing_skills", []),
        }
    except Exception as e:
        return {"ai_score": 0, "ai_reason": f"Error: {e}", "matched_skills": [], "missing_skills": []}


def assign_status(score: int) -> str:
    if score >= 70: return "auto_apply"
    if score >= 50: return "manual_review"
    return "ignored"


def send_instant_alert(user: dict, top_jobs: list[dict]):
    """Send immediate email for 90%+ matches."""
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_pass = os.getenv("EMAIL_PASSWORD")
    if not email_addr or not email_pass:
        return
    try:
        rows = "".join(
            f"<tr><td><a href='{j['link']}'>{j['title']}</a></td>"
            f"<td>{j.get('company','')}</td>"
            f"<td><b>{j['ai_score']}%</b></td></tr>"
            for j in top_jobs
        )
        html = f"""<html><body>
        <h2>⚡ Top Match Alert — {len(top_jobs)} job(s) scored 90%+</h2>
        <table border='1' cellpadding='8' style='border-collapse:collapse'>
        <tr><th>Title</th><th>Company</th><th>Score</th></tr>{rows}
        </table></body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚡ Top Match! {len(top_jobs)} job(s) scored 90%+ for {user['name']}"
        msg["From"]    = email_addr
        msg["To"]      = user["email"]
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(email_addr, email_pass)
            s.sendmail(email_addr, user["email"], msg.as_string())
        print(f"  ⚡ Instant alert sent to {user['email']}")
    except Exception as e:
        print(f"  ⚠️  Instant alert failed: {e}")


def run_filter_agent():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ '{INPUT_FILE}' not found. Run scraper_manager.py first.")
        return

    users = load_users()
    if not users:
        print("❌ No users found. Register via the dashboard first.")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"📋 {len(jobs)} jobs × {len(users)} users = {len(jobs) * len(users)} scores")
    print("🤖 Scoring with Ollama (llama3.2)...\n")

    results = []
    for user in users:
        print(f"\n👤 {user['name']} ({user['email']})")
        user_results = []

        for i, job in enumerate(jobs, 1):
            print(f"  [{i}/{len(jobs)}] {job.get('title','?')} @ {job.get('company','?')} ...", end=" ", flush=True)

            ai_data = score_job(user, job)
            status  = assign_status(ai_data["ai_score"])
            user_results.append({**job, **ai_data, "status": status,
                                  "user_email": user["email"], "user_name": user["name"]})

            emoji = {"auto_apply": "✅", "manual_review": "👀", "ignored": "❌"}[status]
            print(f"{emoji} {ai_data['ai_score']}%")

            time.sleep(0.5)

        auto   = sum(1 for j in user_results if j["status"] == "auto_apply")
        review = sum(1 for j in user_results if j["status"] == "manual_review")
        print(f"  → ✅ {auto} auto-apply  👀 {review} to review")

        # Instant alert for 90%+ matches
        top_jobs = [j for j in user_results if j["ai_score"] >= 90]
        if top_jobs:
            print(f"  ⚡ {len(top_jobs)} top match(es) >=90% — sending instant alert...")
            send_instant_alert(user, top_jobs)

        results.extend(user_results)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved {len(results)} matches to {OUTPUT_FILE}")
    print("▶️  Run email_agent.py to send alerts.")


if __name__ == "__main__":
    run_filter_agent()
