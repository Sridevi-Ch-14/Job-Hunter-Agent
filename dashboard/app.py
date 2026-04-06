"""
Dashboard — Multi-user AI Job Hunter.

Run:
  streamlit run dashboard/app.py

New users register via the onboarding form.
Each user sees only their own job matches.
Works without Supabase (stores users in users.json locally).
"""

import json
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st
import subprocess
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

ROOT          = os.path.join(os.path.dirname(__file__), "..")
USERS_FILE    = os.path.join(ROOT, "users.json")
JOBS_FILE     = os.path.join(ROOT, "filtered_jobs.json")

STATUS_COLORS = {
    "auto_apply"   : "🟢",
    "manual_review": "🟡",
    "applied"      : "🔵",
    "ignored"      : "🔴",
}

COMMON_SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#",
    "React", "Angular", "Vue", "Node.js", "HTML", "CSS",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Firebase",
    "FastAPI", "Django", "Flask", "Spring Boot",
    "Git", "Docker", "AWS", "Linux",
    "Machine Learning", "Data Analysis", "Excel", "Power BI", "Tableau",
    "REST APIs", "GraphQL", "Figma", "Android", "iOS",
]

ROLES = [
    "Software Engineer", "Frontend Developer", "Backend Developer",
    "Full Stack Developer", "Python Developer", "Java Developer",
    "Data Analyst", "Data Scientist", "ML Engineer",
    "Web Developer", "Mobile Developer", "DevOps Engineer",
    "UI/UX Designer", "Business Analyst", "QA Engineer",
]

LOCATIONS = [
    "Bangalore", "Hyderabad", "Chennai", "Mumbai", "Pune", "Delhi NCR",
    "Kolkata", "Ahmedabad", "Kochi", "Remote", "Any",
]


# ── Local storage helpers (fallback when Supabase not configured) ─────────────
def load_users_local() -> list[dict]:
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_users_local(users: list[dict]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def get_user_local(email: str) -> dict | None:
    return next((u for u in load_users_local() if u["email"] == email), None)


def upsert_user_local(user: dict):
    users = load_users_local()
    idx   = next((i for i, u in enumerate(users) if u["email"] == user["email"]), None)
    if idx is not None:
        users[idx] = user
    else:
        users.append(user)
    save_users_local(users)


# ── Supabase helpers ──────────────────────────────────────────────────────────
def _supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not (url and key):
        return None
    from supabase import create_client
    return create_client(url, key)


def save_user(user: dict):
    sb = _supabase()
    if sb:
        try:
            sb.table("users").upsert(user, on_conflict="email").execute()
            return
        except Exception as e:
            st.warning(f"⚠️ Supabase save failed: {e}. Saved locally.")
    upsert_user_local(user)


def load_user(email: str) -> dict | None:
    sb = _supabase()
    if sb:
        try:
            result = sb.table("users").select("*").eq("email", email).execute()
            return result.data[0] if result.data else None
        except Exception:
            pass
    return get_user_local(email)


# ── Resume full extractor using Gemini ───────────────────────────────────────
def extract_resume_text(resume_file) -> str:
    """Extract raw text from uploaded PDF or TXT file."""
    if resume_file.type == "application/pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(resume_file)
            return " ".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            st.warning("Install pypdf: pip install pypdf")
            return ""
    return resume_file.read().decode("utf-8", errors="ignore")


def parse_resume_with_gemini(text: str) -> dict:
    """Extract all profile fields from resume — tries Gemini first, falls back to Ollama."""
    prompt = f"""
Extract the following details from this resume and return ONLY a valid JSON object.
No markdown, no explanation.

{{
  "name": "full name of the person",
  "email": "email address or empty string",
  "phone": "phone number or empty string",
  "linkedin": "linkedin url or empty string",
  "education": "degree and field e.g. B.Tech Computer Science",
  "graduation_year": <year as integer or 2025>,
  "experience_years": <total years of full-time work experience as integer>,
  "internship_months": <total months of internship experience as integer>,
  "looking_for": "Full-time Job or Internship or Both",
  "skills": ["skill1", "skill2"],
  "preferred_roles": ["role1", "role2"],
  "preferred_locations": ["city1", "city2"]
}}

Resume text:
{text[:4000]}
"""

    def clean(raw: str) -> dict:
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    # Try Gemini first
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash-lite")
            return clean(model.generate_content(prompt).text)
        except Exception:
            pass  # fall through to Ollama

    # Fallback: Ollama (local)
    try:
        import requests
        resp = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.2:1b", "prompt": prompt, "stream": False,
        }, timeout=120)
        return clean(resp.json()["response"])
    except Exception as e:
        st.warning(f"⚠️ Resume parsing error: {e}")
        return {}


# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Job Hunter", page_icon="🤖", layout="wide")
st.title("🤖 AI Job Hunter")

# ── Session state ─────────────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.session_state.user = None

# ══════════════════════════════════════════════════════════════════════════════
# ONBOARDING — shown when no user is logged in
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.user:
    tab1, tab2 = st.tabs(["🆕 Register", "🔑 Login"])

    # ── Register ──────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Create your profile")
        st.caption("Upload your resume and AI will fill everything automatically.")

        # ── Step 1: Resume upload (outside form so it triggers instantly) ──────
        resume_file = st.file_uploader(
            "📄 Upload Resume (PDF or TXT) — AI will auto-fill the form below",
            type=["pdf", "txt"],
            key="resume_upload"
        )

        # Parse resume and store in session state
        if resume_file and "parsed_resume" not in st.session_state:
            with st.spinner("🤖 Reading your resume with AI..."):
                text   = extract_resume_text(resume_file)
                parsed = parse_resume_with_gemini(text)
                if parsed:
                    st.session_state.parsed_resume = parsed
                    st.success("✅ Resume parsed! Fields auto-filled below — review and confirm.")
                else:
                    st.session_state.parsed_resume = {}

        # Clear parsed resume if file removed
        if not resume_file and "parsed_resume" in st.session_state:
            del st.session_state.parsed_resume

        p = st.session_state.get("parsed_resume", {})

        # ── Step 2: Form pre-filled from resume ───────────────────────────────
        with st.form("register_form"):
            c1, c2 = st.columns(2)
            name  = c1.text_input("Full Name *",      value=p.get("name", ""))
            email = c2.text_input("Email Address *",  value=p.get("email", ""))

            c3, c4 = st.columns(2)
            phone    = c3.text_input("Phone Number",  value=p.get("phone", ""))
            linkedin = c4.text_input("LinkedIn URL",  value=p.get("linkedin", ""))

            c5, c6, c7, c8 = st.columns(4)
            education        = c5.text_input("Degree",              value=p.get("education", ""))
            grad_year        = c6.number_input("Graduation Year",    2020, 2030, int(p.get("graduation_year", 2025)))
            experience_years = c7.number_input("Experience (yrs)",   0, 20,    int(p.get("experience_years", 0)))
            internship_months= c8.number_input("Internships (months)", 0, 24, 0)

            # Skills — pre-select extracted ones that match COMMON_SKILLS, rest go to extra
            extracted_skills = p.get("skills", [])
            pre_selected     = [s for s in extracted_skills if s in COMMON_SKILLS]
            extra_default    = ", ".join(s for s in extracted_skills if s not in COMMON_SKILLS)

            st.markdown("**Skills** — extracted from resume, edit if needed")
            selected_skills = st.multiselect("Skills", COMMON_SKILLS, default=pre_selected)
            extra_skills    = st.text_input("Other skills (comma separated)", value=extra_default)

            st.markdown("**Job Preferences**")
            looking_for         = st.selectbox("Looking for", ["Full-time Job", "Internship", "Both"])
            pre_roles = [r for r in p.get("preferred_roles", []) if r in ROLES]
            pre_locs  = [l for l in p.get("preferred_locations", []) if l in LOCATIONS]
            preferred_roles     = st.multiselect("Preferred Roles",     ROLES,     default=pre_roles)
            preferred_locations = st.multiselect("Preferred Locations", LOCATIONS, default=pre_locs)

            submitted = st.form_submit_button("🚀 Create Profile & Find Jobs", use_container_width=True)

        if submitted:
            if not name or not email:
                st.error("Name and Email are required.")
            else:
                all_skills = list(selected_skills)
                if extra_skills:
                    all_skills += [s.strip() for s in extra_skills.split(",") if s.strip()]

                user = {
                    "name"               : name,
                    "email"              : email,
                    "phone"              : phone,
                    "linkedin"           : linkedin,
                    "skills"             : list(set(all_skills)),
                    "education"          : education,
                    "graduation_year"    : int(grad_year),
                    "experience_years"   : int(experience_years),
                    "internship_months"  : int(internship_months),
                    "looking_for"        : looking_for,
                    "preferred_roles"    : preferred_roles,
                    "preferred_locations": preferred_locations,
                    "active"             : True,
                    "created_at"         : datetime.utcnow().isoformat(),
                }

                save_user(user)
                st.session_state.user = user
                if "parsed_resume" in st.session_state:
                    del st.session_state.parsed_resume
                st.success(f"✅ Profile created for {name}!")
                st.rerun()

    # ── Login ─────────────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Login with your email")
        login_email = st.text_input("Email Address", key="login_email")
        if st.button("Login", use_container_width=True):
            user = load_user(login_email)
            if user:
                st.session_state.user = user
                st.success(f"Welcome back, {user['name']}!")
                st.rerun()
            else:
                st.error("No profile found. Please register first.")

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD — shown after login/register
# ══════════════════════════════════════════════════════════════════════════════
user = st.session_state.user

# Sidebar
with st.sidebar:
    st.success(f"👤 {user['name']}")
    st.caption(user["email"])

    if st.button("🔄 Force Refresh Jobs"):
        st.cache_data.clear()
        st.success("Cache Cleared! Fetching latest data from files...")
        st.rerun()

    if st.button("🔍 Run Scraper Now", use_container_width=True):
        with st.spinner("Searching for new jobs..."):
            subprocess.run(["python", "agents/scraper_manager.py"], check=False)
            subprocess.run(["python", "agents/filter_agent.py"], check=False)
            st.cache_data.clear()
            st.success("✅ Scrape Complete! New jobs added.")
            st.rerun()

    st.divider()
    st.markdown(f"**Skills:** {', '.join(s for s in user.get('skills', []) if s)[:6*20]}")
    st.markdown(f"**Roles:** {', '.join(r for r in user.get('preferred_roles', []) if r)}")
    st.markdown(f"**Locations:** {', '.join(l for l in user.get('preferred_locations', []) if l)}")
    st.divider()
    if st.button("✏️ Edit Profile"):
        st.session_state.user = None
        st.rerun()
    if st.button("🚪 Logout"):
        st.session_state.user = None
        st.rerun()

    # ── Resume updater ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📝 Update Resume")
    new_resume = st.file_uploader("Upload new Resume (PDF/TXT)", type=["pdf", "txt"], key="sidebar_resume")
    if new_resume:
        if st.button("🔄 Update Profile from Resume", use_container_width=True):
            with st.spinner("🤖 AI is re-parsing your resume..."):
                new_text    = extract_resume_text(new_resume)
                new_data    = parse_resume_with_gemini(new_text)
                if new_data:
                    new_data.pop("email", None)  # never overwrite email
                    user.update({k: v for k, v in new_data.items() if v})
                    save_user(user)
                    st.session_state.user = user
                    st.session_state["clear_jobs_cache"] = True
                    st.success("✅ Profile updated successfully!")
                    st.rerun()
                else:
                    st.error("❌ Could not parse resume. Try a cleaner PDF.")

# Load jobs filtered for this user
@st.cache_data(ttl=60)
def load_user_jobs(email: str) -> list[dict]:
    sb = _supabase()
    if sb:
        try:
            # Get user id
            u = sb.table("users").select("id").eq("email", email).execute()
            if not u.data:
                return []
            uid     = u.data[0]["id"]
            matches = sb.table("user_job_matches").select("*, jobs(*)").eq("user_id", uid).execute().data
            # Flatten
            result = []
            for m in matches:
                job = m.get("jobs") or {}
                result.append({**job, "ai_score": m["ai_score"], "ai_reason": m["ai_reason"],
                                "status": m["status"], "matched_skills": m.get("matched_skills", []),
                                "missing_skills": m.get("missing_skills", [])})
            return result
        except Exception:
            pass

    # Fallback: filtered_jobs.json (single-user mode)
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


jobs = load_user_jobs(user["email"])

# Clear cache if resume was just updated
if st.session_state.pop("clear_jobs_cache", False):
    load_user_jobs.clear()
    jobs = load_user_jobs(user["email"])

if not jobs:
    st.info("👋 Your profile is saved! Jobs will appear here after the next scraper run.")
    st.code("python agents/scraper_manager.py\npython agents/filter_agent.py", language="bash")
    st.stop()

df = pd.DataFrame(jobs)

for col, default in [("ai_score", 0), ("status", "new"), ("company", ""), ("location", "")]:
    if col not in df.columns:
        df[col] = default

df["ai_score"] = pd.to_numeric(df["ai_score"], errors="coerce").fillna(0).astype(int)

# ── Stats ─────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
avg = df["ai_score"].mean()
c1.metric("Total Jobs",    len(df))
c2.metric("🟢 Auto-Apply", len(df[df["status"] == "auto_apply"]))
c3.metric("🟡 To Review",  len(df[df["status"] == "manual_review"]))
c4.metric("🔵 Applied",    len(df[df["status"] == "applied"]))
c5.metric("Avg Score",     f"{avg:.0f}%" if not df["ai_score"].eq(0).all() else "—")

st.divider()

# ── Filters ───────────────────────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")
status_filter = st.sidebar.selectbox("Status", ["All"] + sorted(df["status"].dropna().unique().tolist()))
min_score     = st.sidebar.slider("Min AI Score", 0, 100, 0)
search        = st.sidebar.text_input("Search title / company")

filtered = df.copy()
if status_filter != "All":
    filtered = filtered[filtered["status"] == status_filter]
filtered = filtered[filtered["ai_score"] >= min_score]
if search:
    mask = (
        filtered.get("title",   pd.Series(dtype=str)).str.contains(search, case=False, na=False) |
        filtered.get("company", pd.Series(dtype=str)).str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]

st.subheader(f"📋 {len(filtered)} jobs matched to your profile")

# 1. Add 'link' and 'salary' to the columns we want to see
display_cols = [
    "title",
    "company",
    "location",
    "salary",
    "ai_score",
    "status",
    "link",        # <--- ADD THIS
    "ai_reason"
]

# Keep only available cols (safety check)
display_cols = [c for c in display_cols if c in filtered.columns]
display_df = filtered[display_cols].copy()
display_df["status"] = display_df["status"].map(lambda s: f"{STATUS_COLORS.get(s,'')} {s}" if s else "")

# 2. Configure the LinkColumn so it becomes a clickable button
st.dataframe(
    display_df,
    column_config={
        "title"    : "Job Title",
        "company"  : "Company",
        "location" : "Location",
        "salary"   : st.column_config.TextColumn("💰 Package", help="Salary offered"),
        "ai_score" : st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d%%"),
        "status"   : "Status",
        "link"     : st.column_config.LinkColumn("🔗 Apply Link", display_text="Open Job"),
        "ai_reason": "AI Reason"
    },
    use_container_width=True,
    hide_index=True,
)

# ── Score chart ───────────────────────────────────────────────────────────────
if df["ai_score"].gt(0).any():
    st.divider()
    st.subheader("📊 AI Score Distribution")
    st.bar_chart(df["ai_score"].value_counts().sort_index())

# ── Master Auto-Apply Profile ─────────────────────────────────────────────────
st.divider()
with st.expander("🚀 Configure Master Auto-Apply Profile"):
    mp = user.get("master_profile", {})
    with st.form("master_profile"):
        st.info("This data will be used to automatically fill 'Easy Apply' forms.")
        c1, c2 = st.columns(2)
        notice_period = c1.selectbox("Notice Period",
            ["Immediate", "15 Days", "30 Days", "90 Days"],
            index=["Immediate", "15 Days", "30 Days", "90 Days"].index(mp.get("notice_period", "Immediate")))
        current_ctc   = c2.text_input("Current CTC (LPA)",  mp.get("current_ctc", "0"))
        expected_ctc  = c1.text_input("Expected CTC (LPA)", mp.get("expected_ctc", ""))
        gender        = c2.selectbox("Gender", ["Male", "Female", "Other"],
            index=["Male", "Female", "Other"].index(mp.get("gender", "Male")))
        github_url    = st.text_input("GitHub Profile URL",    mp.get("github", ""))
        portfolio_url = st.text_input("Portfolio/Website URL", mp.get("portfolio", ""))
        st.markdown("---")
        st.subheader("Address & Legal")
        current_city  = st.text_input("Current City",               mp.get("city", ""))
        hometown      = st.text_input("Hometown/Permanent Address",  mp.get("hometown", ""))
        is_authorized = st.checkbox("Authorized to work in India?",  mp.get("authorized", True))
        requires_visa = st.checkbox("Will require visa sponsorship?", mp.get("visa", False))

        if st.form_submit_button("💾 Save Master Profile", use_container_width=True):
            user["master_profile"] = {
                "notice_period": notice_period, "current_ctc": current_ctc,
                "expected_ctc" : expected_ctc,  "gender"     : gender,
                "github"       : github_url,    "portfolio"  : portfolio_url,
                "city"         : current_city,  "hometown"   : hometown,
                "authorized"   : is_authorized, "visa"       : requires_visa,
            }
            save_user(user)
            st.session_state.user = user
            st.success("✅ Master Profile Saved!")

# ── Interview / Success Tracker ───────────────────────────────────────────────
st.divider()
st.subheader("🎯 Interview & Success Tracker")

applied_jobs = [j for j in jobs if j.get("status") in ("applied", "interview", "offer", "rejected")
                and j.get("user_email", user["email"]) == user["email"]]

if not applied_jobs:
    st.info("No applied jobs yet. Jobs you apply to will appear here for tracking.")
else:
    OUTCOMES = ["applied", "interview", "offer", "rejected"]
    OUTCOME_COLORS = {"applied": "🔵", "interview": "🟣", "offer": "🟢", "rejected": "🔴"}

    for job in applied_jobs:
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.markdown(f"**[{job.get('title','')}]({job.get('link','#')})** — {job.get('company','')}")
        c2.markdown(f"{OUTCOME_COLORS.get(job.get('status',''), '')} {job.get('status', '').title()}")

        new_status = c3.selectbox(
            "Update",
            OUTCOMES,
            index=OUTCOMES.index(job.get("status", "applied")),
            key=f"tracker_{job.get('link','')}",
            label_visibility="collapsed",
        )

        if new_status != job.get("status"):
            # Update in filtered_jobs.json
            if os.path.exists(JOBS_FILE):
                with open(JOBS_FILE, encoding="utf-8") as f:
                    all_jobs = json.load(f)
                for j in all_jobs:
                    if j.get("link") == job.get("link") and j.get("user_email") == user["email"]:
                        j["status"] = new_status
                with open(JOBS_FILE, "w", encoding="utf-8") as f:
                    json.dump(all_jobs, f, indent=2, ensure_ascii=False)
                load_user_jobs.clear()
                st.rerun()

    # Summary
    st.divider()
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("🔵 Applied",   sum(1 for j in applied_jobs if j.get("status") == "applied"))
    t2.metric("🟣 Interviews", sum(1 for j in applied_jobs if j.get("status") == "interview"))
    t3.metric("🟢 Offers",    sum(1 for j in applied_jobs if j.get("status") == "offer"))
    t4.metric("🔴 Rejected",  sum(1 for j in applied_jobs if j.get("status") == "rejected"))
