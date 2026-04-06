# AI Job Hunter Agent 🤖

Multi-agent system to auto-discover and apply to fresher jobs in India.

---

## ⚡ Quick Setup (Step by Step)

### Step 1 — Install Python dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 2 — Set up your `.env` file
Create a file called `.env` in the root folder:
```
GEMINI_API_KEY=your_key_here        # from makersuite.google.com/app/apikey
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
EMAIL_ADDRESS=your_gmail@gmail.com
EMAIL_PASSWORD=your_app_password    # Gmail App Password (not your real password)
```

### Step 3 — Run the Web Scraping Agent
```bash
cd agents
python web_scraper_agent.py
```

Output: `scraped_jobs.json` with all fresher jobs found.

---

## 📁 Project Structure
```
job_agent/
│
├── agents/
│   ├── web_scraper_agent.py     ✅ DONE — scrapes Naukri
│   ├── filter_agent.py          🔜 Next — AI skill matching
│   ├── apply_agent.py           🔜 Auto-fills application forms
│   ├── email_agent.py           🔜 Sends job alerts
│   └── followup_agent.py        🔜 Follows up after 7 days
│
├── ai/
│   └── resume_optimizer.py      🔜 Gemini-powered cover letter gen
│
├── database/
│   └── models.py                🔜 Supabase table setup
│
├── dashboard/
│   └── app.py                   🔜 Streamlit tracking dashboard
│
├── scheduler/
│   └── tasks.py                 🔜 Celery + Redis (runs every 5 min)
│
├── requirements.txt             ✅ DONE
├── .env                         👈 You create this
└── README.md                    ✅ DONE
```

---

## 🔑 Free Accounts to Create
| Service | Purpose | Link |
|---|---|---|
| Google AI Studio | Gemini API key | makersuite.google.com |
| Supabase | Free PostgreSQL DB | supabase.com |
| Streamlit | Free dashboard hosting | streamlit.io |
| Render | 24/7 free hosting | render.com |

---

## 🗺️ Build Order (recommended)
1. ✅ Web Scraper Agent (Naukri)
2. 🔜 AI Filter Agent (Gemini skill matching)
3. 🔜 Email Notification Agent
4. 🔜 Dashboard
5. 🔜 Auto Apply Agent
6. 🔜 Follow-up Agent
7. 🔜 Scheduler (Celery + Redis)
