import os
import datetime
from zoneinfo import ZoneInfo
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from langchain_core.tools import tool

SCOPES = ['https://www.googleapis.com/auth/calendar']
IST = ZoneInfo("Asia/Kolkata")


def get_calendar_service():
    creds = None
    if os.path.exists('token.json'):
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',
                SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            auth_url, _ = flow.authorization_url(prompt='consent')
            print("\n-> Go to this URL:\n", auth_url)
            code = input("\n-> Paste the authorization code here: ")
            flow.fetch_token(code=code)
            creds = flow.credentials
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def _parse_event_times(event):
    """Helper to parse start/end from a Google Calendar event dict."""
    start_str = event['start'].get('dateTime', event['start'].get('date'))
    end_str = event['end'].get('dateTime', event['end'].get('date'))
    # Handle both date-only and datetime strings
    try:
        start = datetime.datetime.fromisoformat(start_str)
        end = datetime.datetime.fromisoformat(end_str)
    except ValueError:
        # date-only (all-day events)
        start = datetime.datetime.fromisoformat(start_str + "T00:00:00+05:30")
        end = datetime.datetime.fromisoformat(end_str + "T23:59:59+05:30")
    return start, end


@tool
def get_calendar_events(date: str) -> str:
    """
    Fetches all events from Google Calendar on a given date.

    Args:
        date: The date to check in YYYY-MM-DD format.

    Returns:
        A readable string listing all events (name, start time, end time)
        on that date, or a message saying the day is free.
    """
    service = get_calendar_service()

    day_start = datetime.datetime(
        *[int(x) for x in date.split('-')],
        0, 0, 0, tzinfo=IST
    )
    day_end = day_start + datetime.timedelta(days=1)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    if not events:
        return f"No events found on {date}. The day is completely free."

    lines = [f"Events on {date}:"]
    for ev in events:
        start, end = _parse_event_times(ev)
        title = ev.get('summary', '(No Title)')
        lines.append(
            f"  - {title}: {start.strftime('%H:%M')} → {end.strftime('%H:%M')}"
        )
    return "\n".join(lines)


@tool
def create_event(
    title: str,
    date: str,
    start_time: str,
    duration_minutes: int,
    attendee_email: str = None
) -> str:
    """
    Creates a meeting in Google Calendar after checking for past dates and conflicts.

    Args:
        title: Meeting title.
        date: Date in YYYY-MM-DD format.
        start_time: Start time in HH:MM (24-hour) format.
        duration_minutes: Duration of the meeting in minutes.
        attendee_email: Optional attendee email address.

    Returns:
        A success message with the event link, or an error message if the
        slot is in the past or conflicts with an existing event.
    """
    service = get_calendar_service()

    # --- Guard 1: Past date/time check ---
    start_dt = datetime.datetime.strptime(
        f"{date} {start_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
    now = datetime.datetime.now(tz=IST)

    if start_dt < now:
        return (
            f"Error: The requested time ({date} {start_time}) is in the past. "
            "Please provide a future date and time."
        )

    # --- Guard 2: Overlap check ---
    day_start = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + datetime.timedelta(days=1)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    existing_events = events_result.get('items', [])

    for ev in existing_events:
        ev_start, ev_end = _parse_event_times(ev)
        # Overlap condition: A_start < B_end AND A_end > B_start
        if start_dt < ev_end and end_dt > ev_start:
            ev_title = ev.get('summary', '(No Title)')
            return (
                f"Conflict detected: '{ev_title}' is already scheduled from "
                f"{ev_start.strftime('%H:%M')} to {ev_end.strftime('%H:%M')} "
                f"on {date}. Please choose a different time slot."
            )

    # --- Create the event ---
    event_body = {
        'summary': title,
        'start': {
            'dateTime': start_dt.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
        'end': {
            'dateTime': end_dt.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
    }

    if attendee_email:
        event_body['attendees'] = [{'email': attendee_email}]

    created = service.events().insert(
        calendarId='primary',
        body=event_body,
        sendUpdates='all' if attendee_email else 'none'
    ).execute()

    return f"Event created successfully! Link: {created.get('htmlLink')}"


@tool
def find_free_slots(date: str, duration_minutes: int) -> str:
    """
    Scans working hours (9am–6pm) on a given date and returns all time gaps
    that are large enough to fit a meeting of the specified duration.

    Args:
        date: Date to scan in YYYY-MM-DD format.
        duration_minutes: Required meeting duration in minutes.

    Returns:
        A string listing all available free slots on that date.
    """
    service = get_calendar_service()

    day_start = datetime.datetime(
        *[int(x) for x in date.split('-')], 9, 0, 0, tzinfo=IST
    )
    day_end = datetime.datetime(
        *[int(x) for x in date.split('-')], 18, 0, 0, tzinfo=IST
    )

    events_result = service.events().list(
        calendarId='primary',
        timeMin=day_start.isoformat(),
        timeMax=day_end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    # Build list of busy intervals
    busy = []
    for ev in events:
        ev_start, ev_end = _parse_event_times(ev)
        # Clamp to working hours
        ev_start = max(ev_start, day_start)
        ev_end = min(ev_end, day_end)
        if ev_start < ev_end:
            busy.append((ev_start, ev_end))

    busy.sort(key=lambda x: x[0])

    # Find gaps
    free_slots = []
    cursor = day_start

    for ev_start, ev_end in busy:
        if cursor < ev_start:
            gap_minutes = (ev_start - cursor).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                free_slots.append((cursor, ev_start))
        cursor = max(cursor, ev_end)

    # Check remaining time after last event
    if cursor < day_end:
        gap_minutes = (day_end - cursor).total_seconds() / 60
        if gap_minutes >= duration_minutes:
            free_slots.append((cursor, day_end))

    if not free_slots:
        return f"No free slots of {duration_minutes} minutes found on {date} (9am–6pm)."

    lines = [f"Free slots on {date} (minimum {duration_minutes} min):"]
    for start, end in free_slots:
        lines.append(f"  - {start.strftime('%H:%M')} → {end.strftime('%H:%M')}")
    return "\n".join(lines)


@tool
def analyse_booking_patterns() -> str:
    """
    Analyses the user's Google Calendar over the past 30 days and returns
    a structured summary of scheduling habits including busiest days,
    lightest days, preferred meeting hours, and average meeting duration.

    Returns:
        A string summary of the user's booking patterns.
    """
    service = get_calendar_service()

    now = datetime.datetime.now(tz=IST)
    thirty_days_ago = now - datetime.timedelta(days=30)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=thirty_days_ago.isoformat(),
        timeMax=now.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        maxResults=200
    ).execute()

    events = events_result.get('items', [])

    if not events:
        return "No events found in the last 30 days to analyse."

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_counts = {d: 0 for d in day_names}
    hour_counts = {}
    durations = []
    dates_seen = set()

    for ev in events:
        start_str = ev['start'].get('dateTime')
        end_str = ev['end'].get('dateTime')
        if not start_str or not end_str:
            continue  # Skip all-day events

        start = datetime.datetime.fromisoformat(start_str)
        end = datetime.datetime.fromisoformat(end_str)
        duration = (end - start).total_seconds() / 60

        day_name = day_names[start.weekday()]
        day_counts[day_name] += 1

        hour = start.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

        durations.append(duration)
        dates_seen.add(start.date())

    # Compute stats
    sorted_days = sorted(day_counts.items(), key=lambda x: x[1], reverse=True)
    busiest_days = [d for d, c in sorted_days[:2] if c > 0]
    lightest_days = [d for d, c in sorted_days if c == 0] or [sorted_days[-1][0]]

    preferred_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    preferred_str = ", ".join(
        f"{h:02d}:00–{h+1:02d}:00" for h, _ in preferred_hours
    )

    avg_duration = sum(durations) / len(durations) if durations else 0
    total_meetings = len(events)

    summary = (
        f"=== Booking Pattern Analysis (Last 30 Days) ===\n"
        f"Total meetings: {total_meetings}\n"
        f"Busiest days: {', '.join(busiest_days) if busiest_days else 'N/A'}\n"
        f"Lightest days (fewest meetings): {', '.join(lightest_days[:2])}\n"
        f"Preferred meeting hours: {preferred_str if preferred_str else 'N/A'}\n"
        f"Average meeting duration: {avg_duration:.0f} minutes\n"
        f"Active meeting days in period: {len(dates_seen)}"
    )
    return summary


@tool
def query_calendar_insights(question: str) -> str:
    """
    Answers general natural-language questions about the user's calendar,
    such as free days this week, busiest day this month, or total meeting
    hours this week.

    Args:
        question: A natural language question about the user's calendar.

    Returns:
        A string answer derived from real calendar data.
    """
    service = get_calendar_service()
    now = datetime.datetime.now(tz=IST)

    # Define time windows
    start_of_week = now - datetime.timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + datetime.timedelta(days=7)

    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_month = (start_of_month + datetime.timedelta(days=32)).replace(day=1)

    q_lower = question.lower()

    # Determine window
    if 'month' in q_lower:
        t_min, t_max = start_of_month, end_of_month
        window_label = "this month"
    else:
        t_min, t_max = start_of_week, end_of_week
        window_label = "this week"

    events_result = service.events().list(
        calendarId='primary',
        timeMin=t_min.isoformat(),
        timeMax=t_max.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        maxResults=200
    ).execute()

    events = events_result.get('items', [])

    # Aggregate by date
    from collections import defaultdict
    day_events = defaultdict(list)
    total_minutes = 0

    for ev in events:
        start_str = ev['start'].get('dateTime')
        end_str = ev['end'].get('dateTime')
        if not start_str or not end_str:
            continue
        start = datetime.datetime.fromisoformat(start_str)
        end = datetime.datetime.fromisoformat(end_str)
        duration = (end - start).total_seconds() / 60
        total_minutes += duration
        day_events[start.date()].append({
            'title': ev.get('summary', '(No Title)'),
            'start': start,
            'end': end,
            'duration': duration
        })

    # Build all weekdays in window
    all_days = []
    cursor = t_min.date()
    while cursor < t_max.date():
        all_days.append(cursor)
        cursor += datetime.timedelta(days=1)

    # Answer specific question types
    if 'free' in q_lower:
        free_days = [d for d in all_days if d not in day_events and d.weekday() < 5]
        if free_days:
            day_strs = [d.strftime('%A, %b %d') for d in free_days]
            return f"Free days {window_label}: {', '.join(day_strs)}"
        return f"No completely free weekdays found {window_label}."

    elif 'busiest' in q_lower:
        if not day_events:
            return f"No meetings found {window_label}."
        busiest = max(day_events.items(), key=lambda x: len(x[1]))
        return (
            f"Busiest day {window_label}: {busiest[0].strftime('%A, %b %d')} "
            f"with {len(busiest[1])} meetings."
        )

    elif 'hour' in q_lower or 'how many' in q_lower:
        hours = total_minutes / 60
        return (
            f"Total meeting time {window_label}: {hours:.1f} hours "
            f"({total_minutes:.0f} minutes) across {len(events)} meetings."
        )

    else:
        # Generic summary
        lines = [f"Calendar summary {window_label}:"]
        lines.append(f"  Total meetings: {len(events)}")
        lines.append(f"  Total meeting time: {total_minutes/60:.1f} hours")
        if day_events:
            busiest = max(day_events.items(), key=lambda x: len(x[1]))
            lines.append(
                f"  Busiest day: {busiest[0].strftime('%A, %b %d')} "
                f"({len(busiest[1])} meetings)"
            )
        free_days = [d for d in all_days if d not in day_events and d.weekday() < 5]
        if free_days:
            lines.append(
                f"  Free weekdays: {', '.join(d.strftime('%A') for d in free_days)}"
            )
        return "\n".join(lines)