"""
Database Models — Supabase setup for multi-user AI Job Hunter.

Usage:
  python database/models.py        # prints SQL → paste into Supabase SQL Editor
  python database/models.py --sync # pushes filtered_jobs.json → Supabase
"""

import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ── Run both of these once in Supabase SQL Editor ─────────────────────────────
CREATE_TABLE_SQL = """
-- Users table (one row per registered user)
create table if not exists users (
    id                bigserial primary key,
    name              text not null,
    email             text unique not null,
    phone             text,
    linkedin          text,
    skills            text[],
    education         text,
    graduation_year   int,
    experience_years  int default 0,
    preferred_roles   text[],
    preferred_locations text[],
    telegram_chat_id  text,
    active            boolean default true,
    created_at        timestamptz default now()
);

-- Jobs table (shared across all users)
create table if not exists jobs (
    id             bigserial primary key,
    title          text,
    company        text,
    location       text,
    experience     text,
    salary         text,
    skills         text[],
    description    text,
    link           text unique,
    source         text,
    scraped_at     timestamptz,
    created_at     timestamptz default now()
);

-- User-job matches (one row per user per job)
create table if not exists user_job_matches (
    id             bigserial primary key,
    user_id        bigint references users(id) on delete cascade,
    job_id         bigint references jobs(id)  on delete cascade,
    ai_score       int,
    ai_reason      text,
    matched_skills text[],
    missing_skills text[],
    status         text default 'new',
    follow_up_sent boolean default false,
    applied_at     timestamptz,
    created_at     timestamptz default now(),
    unique(user_id, job_id)
);
"""


def _get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise EnvironmentError(
            "Missing SUPABASE_URL or SUPABASE_KEY in .env\n"
            "Get them from: supabase.com → Project Settings → API"
        )
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── User helpers ──────────────────────────────────────────────────────────────
def get_all_users() -> list[dict]:
    return _get_client().table("users").select("*").eq("active", True).execute().data


def upsert_user(user: dict) -> dict:
    result = _get_client().table("users").upsert(user, on_conflict="email").execute()
    return result.data[0] if result.data else {}


def get_user_by_email(email: str) -> dict | None:
    result = _get_client().table("users").select("*").eq("email", email).execute()
    return result.data[0] if result.data else None


# ── Job helpers ───────────────────────────────────────────────────────────────
def sync_jobs(filepath="scraped_jobs.json"):
    supabase = _get_client()
    with open(filepath, encoding="utf-8") as f:
        jobs = json.load(f)

    records = [{
        "title"      : j.get("title"),
        "company"    : j.get("company"),
        "location"   : j.get("location"),
        "experience" : j.get("experience"),
        "salary"     : j.get("salary"),
        "skills"     : j.get("skills", []),
        "description": j.get("description"),
        "link"       : j.get("link"),
        "source"     : j.get("source"),
        "scraped_at" : j.get("scraped_at"),
    } for j in jobs if j.get("link")]

    supabase.table("jobs").upsert(records, on_conflict="link").execute()
    print(f"✅ Synced {len(records)} jobs to Supabase.")


# ── Match helpers ─────────────────────────────────────────────────────────────
def upsert_match(user_id: int, job_id: int, match: dict):
    _get_client().table("user_job_matches").upsert({
        "user_id"       : user_id,
        "job_id"        : job_id,
        "ai_score"      : match.get("ai_score"),
        "ai_reason"     : match.get("ai_reason"),
        "matched_skills": match.get("matched_skills", []),
        "missing_skills": match.get("missing_skills", []),
        "status"        : match.get("status", "new"),
    }, on_conflict="user_id,job_id").execute()


def get_matches_for_user(user_id: int) -> list[dict]:
    return (
        _get_client().table("user_job_matches")
        .select("*, jobs(*)")
        .eq("user_id", user_id)
        .execute().data
    )


def mark_applied(user_id: int, job_id: int):
    _get_client().table("user_job_matches").update({
        "status"    : "applied",
        "applied_at": datetime.utcnow().isoformat(),
    }).eq("user_id", user_id).eq("job_id", job_id).execute()


if __name__ == "__main__":
    if "--sync" in sys.argv:
        sync_jobs()
    else:
        print("📋 Run this SQL once in your Supabase SQL Editor:\n")
        print(CREATE_TABLE_SQL)
        print("\nThen run:  python database/models.py --sync")
