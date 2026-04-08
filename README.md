# AI Meeting Scheduler
### LangChain + Gemini + Google Calendar

---

## Project Structure

```
meeting_scheduler/
├── credentials.json   ← Downloaded from Google Cloud Console
├── token.json         ← Auto-generated on first run (do NOT commit)
├── .env               ← Your API keys (do NOT commit)
├── tools.py           ← All LangChain tool definitions
├── agent.py           ← LangChain agent with multi-turn loop
├── main.py            ← Entry point / chat loop
└── README.md
```

---

## Setup Instructions

### Step 1 — Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### Step 2 — Install Dependencies

```bash
pip install langchain langchain-google-genai
pip install google-auth google-auth-oauthlib google-api-python-client
pip install python-dotenv
```

### Step 3 — Gemini API Key

1. Go to: https://aistudio.google.com/app/apikey
2. Click **Create API Key**
3. Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your_gemini_api_key_here
```

### Step 4 — Google Calendar API Setup

1. Go to https://console.cloud.google.com
2. **Select a project → New Project**, name it, create it
3. Sidebar → **APIs & Services → Library**
4. Search **Google Calendar API** → click **Enable**
5. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
6. Set **Application Type** to **Desktop App**, name it, click **Create**
7. Click **Download JSON** — rename the file to `credentials.json` and place it in the project root

### Step 5 — Add Yourself as a Test User

Since the app is in development mode, you must whitelist your own Gmail:

1. Go to **APIs & Services → OAuth consent screen**
2. Scroll to **Test users** → click **Add Users**
3. Enter your Gmail address and save

### Step 6 — First Run (OAuth Flow)

The app uses a terminal copy-paste OAuth flow (no browser redirect needed):

```bash
python main.py
```

- It prints a URL in the terminal
- Open the URL in any browser
- Log in and grant Calendar permissions
- Google shows you a code — copy it
- Paste it back into the terminal
- `token.json` is created automatically — future runs skip this step

---

## Usage Examples

| Input | What Happens |
|---|---|
| `"Schedule a 1-hour Team Sync tomorrow at 10am"` | Creates the event in Google Calendar |
| `"Book a 30-minute standup at 9am this Friday"` | Creates the event at the correct time |
| `"Set up a 45-min call with raj@example.com on Monday at 3pm"` | Creates the event with attendee invited |
| `"Book a meeting yesterday at 2pm"` | Rejected — past date guard triggers |
| `"Schedule a meeting tomorrow at 10am"` (when slot is taken) | Conflict detected + smart alternatives suggested |
| `"Which days am I free this week?"` | Lists free weekdays from your calendar |
| `"What was my busiest day this month?"` | Returns the day with the most meetings |
| `"How many hours of meetings do I have this week?"` | Computes total meeting hours |

---

## Features

### Trivial Meeting Creation
- Natural language → LLM parses intent → `create_event` tool → Google Calendar API

### Conflict Detection & Past Date Validation
- **Past date guard**: Rejects any request with a datetime in the past
- **Overlap check**: Fetches existing events and checks for time range overlap using `A_start < B_end AND A_end > B_start`
- **Multi-turn agent loop**: LLM ↔ tools ↔ LLM until a final text answer is produced

### Smart Alternative Suggestions
When a conflict is detected:
1. `analyse_booking_patterns` — studies last 30 days of history
2. `find_free_slots` — scans 9am–6pm on the requested day for free gaps
3. `find_free_slots` — also checks the user's lightest days
4. Agent presents 2–3 ranked alternatives with reasons

### Calendar Intelligence Queries
`query_calendar_insights` answers open-ended questions:
- Free days this week
- Busiest day this month
- Total meeting hours this week
- General weekly/monthly summaries

---

## Notes

- Timezone is set to **Asia/Kolkata (IST)** throughout
- All-day events are handled gracefully (skipped in duration calculations)
