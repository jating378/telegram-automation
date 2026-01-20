import asyncio
import random
import requests
import json
import os
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
channel_id = int(os.environ["TELEGRAM_CHANNEL_ID"])
RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]  # Your RapidAPI key
GIST_ID = os.environ.get("GIST_ID")
GH_TOKEN = os.environ.get("GH_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# RapidAPI settings
RAPIDAPI_HOST = "free-api-live-football-data.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

# League IDs for this API
LEAGUE_IDS = {
    "premier_league": 47,      # Premier League
    "la_liga": 87,             # La Liga
    "serie_a": 55,             # Serie A
    "bundesliga": 54,          # Bundesliga
    "ligue_1": 53,             # Ligue 1
    "champions_league": 42,    # Champions League
    "europa_league": 73,       # Europa League
}

LEAGUE_PRIORITY = {
    42: 100,   # Champions League
    73: 95,    # Europa League
    47: 90,    # Premier League
    87: 85,    # La Liga
    55: 80,    # Serie A
    54: 75,    # Bundesliga
    53: 70,    # Ligue 1
}

MAJOR_LEAGUE_IDS = set(LEAGUE_PRIORITY.keys())


def match_importance_score(match):
    league_id = match.get("leagueId", 0)
    league_score = LEAGUE_PRIORITY.get(league_id, 0)

    home = match.get("homeTeam", {}).get("name", "")
    away = match.get("awayTeam", {}).get("name", "")

    big_clubs = [
        "Real Madrid", "Barcelona", "Manchester United",
        "Manchester City", "Liverpool", "Arsenal",
        "Bayern Munich", "Bayern München", "PSG", "Paris Saint-Germain",
        "Juventus", "AC Milan", "Milan",
        "Inter", "Inter Milan", "Chelsea"
    ]

    club_boost = 0
    for club in big_clubs:
        if club.lower() in home.lower():
            club_boost += 5
            break
    for club in big_clubs:
        if club.lower() in away.lower():
            club_boost += 5
            break

    return league_score + club_boost


# =====================
# MESSAGE TEMPLATES
# =====================
STYLE_LINES = [
    "Abhi tak toh dekh ke lag raha hai",
    "Live game mein jo dikh raha hai",
    "Ground se jo signal aa raha hai",
    "Match ki current situation ke hisaab se",
    "Jo abhi tak hua hai uske basis pe",
    "Meri experience ke hisaab se"
]

PREDICTIONS = [
    "{team} ke yahan chances zyada ban rahe hain.",
    "{team} ka control zyada lag raha hai.",
    "{team} yeh match jeetega.",
    "{team} will win this match"
]

DRAW_LINES = [
    "Abhi ke liye match balanced hai , half time tak wait krenge.",
    "Dono side barabar fight kar rahi hain , kuch entry banti toh update karta.",
    "Filhaal draw type game lag raha hai."
]

CLOSERS = [
    "🕶️ Phantom Time",
    "Match ke baad milte hain!",
    "Stay tuned for more updates!"
]

HT_DRAW_LINES = [
    "Draw ki entry bhi lelo.",
    "Match draw ki taraf jaa raha hai.",
    "Balanced game hai, draw ho sakta hai. Thodi Limit draw par bhi rakho."
]

HT_LOSING_LINES = [
    "Apni entry par hi rehenge.",
    "Match badalne ke poore chance hai.",
    "Second half mein comeback ho sakta hai.",
    "Wait , abhi game khatam nahi hua"
]


# =====================
# GIST STATE
# =====================
def load_state():
    if not GIST_ID or not GH_TOKEN:
        return {"matches": [], "date": None, "day_summary_sent": False}

    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GH_TOKEN}"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()

        files = r.json().get("files", {})
        if "match_state.json" not in files:
            print("match_state.json not found in Gist, returning empty state")
            return {"matches": [], "date": None, "day_summary_sent": False}

        content = files["match_state.json"]["content"]
        
        if not content or not content.strip():
            print("Gist content is empty, returning empty state")
            return {"matches": [], "date": None, "day_summary_sent": False}

        return json.loads(content)
    
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in Gist: {e}, returning empty state")
        return {"matches": [], "date": None, "day_summary_sent": False}
    except Exception as e:
        print(f"Error loading state: {e}, returning empty state")
        return {"matches": [], "date": None, "day_summary_sent": False}


def save_state(state):
    if not GIST_ID or not GH_TOKEN:
        return

    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    payload = {
        "files": {
            "match_state.json": {
                "content": json.dumps(state, indent=2)
            }
        }
    }
    requests.patch(url, headers=headers, json=payload, timeout=10)


# =====================
# RAPIDAPI FOOTBALL API
# =====================
def get_api_headers():
    return {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }


def fetch_matches_by_date_and_league(league_id, date=None):
    """Fetch matches for a specific league on a specific date"""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
    
    url = f"{BASE_URL}/football-get-matches-by-date-and-league"
    params = {"date": date, "leagueid": league_id}
    
    try:
        r = requests.get(url, headers=get_api_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        if data.get("status") and data.get("response"):
            matches = data["response"].get("matches", [])
            return matches
        return []
    except Exception as e:
        print(f"[ERROR] fetch_matches_by_date_and_league({league_id}, {date}): {e}")
        return []


def fetch_live_matches():
    """Fetch today's matches from major leagues and filter for live ones"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    all_live_matches = []
    
    # Live status indicators (adjust based on actual API response)
    live_statuses = [
        "1H", "2H", "HT", "ET", "P", "LIVE", "IN_PLAY", "PLAYING", 
        "FIRST_HALF", "SECOND_HALF", "EXTRA_TIME", "PENALTY",
        "1st Half", "2nd Half", "Half Time", "Extra Time"
    ]
    
    for league_name, league_id in LEAGUE_IDS.items():
        print(f"[DEBUG] Checking {league_name} for live matches...")
        matches = fetch_matches_by_date_and_league(league_id, today)
        
        for m in matches:
            m["leagueId"] = league_id
            m["leagueName"] = league_name.replace("_", " ").title()
            
            # Check if match is live based on status
            status = str(m.get("status", "")).strip()
            status_upper = status.upper()
            
            # Check various live indicators
            is_live = False
            
            # Check if status is in known live statuses
            if status_upper in [s.upper() for s in live_statuses]:
                is_live = True
            # Check if status is a minute number (e.g., "45", "67")
            elif status.isdigit() and 1 <= int(status) <= 120:
                is_live = True
            # Check if status contains minute indicator (e.g., "45'", "67+2")
            elif "'" in status or (status.replace("+", "").replace(" ", "").isdigit()):
                is_live = True
            
            if is_live:
                all_live_matches.append(m)
                print(f"[DEBUG] Live match found: {m.get('homeTeam', {}).get('name', 'Unknown')} vs {m.get('awayTeam', {}).get('name', 'Unknown')}")
    
    print(f"[DEBUG] Total live matches found: {len(all_live_matches)}")
    return all_live_matches


def fetch_match_details(match_id):
    """Fetch detailed info for a specific match"""
    url = f"{BASE_URL}/football-get-match-details"
    params = {"matchid": match_id}
    
    try:
        r = requests.get(url, headers=get_api_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        if data.get("status") and data.get("response"):
            return data["response"]
        return None
    except Exception as e:
        print(f"[ERROR] fetch_match_details({match_id}): {e}")
        return None


def fetch_fixtures_window():
    """Fetch today's and tomorrow's matches from major leagues"""
    all_fixtures = []
    seen = set()
    
    today = datetime.now(timezone.utc)
    tomorrow = today + timedelta(days=1)
    
    dates_to_check = [
        today.strftime("%Y%m%d"),
        tomorrow.strftime("%Y%m%d")
    ]
    
    for date in dates_to_check:
        for league_name, league_id in LEAGUE_IDS.items():
            print(f"[DEBUG] Fetching matches for {league_name} (ID: {league_id}) on {date}")
            matches = fetch_matches_by_date_and_league(league_id, date)
            
            for m in matches:
                match_id = m.get("id") or m.get("matchId")
                if match_id and match_id not in seen:
                    seen.add(match_id)
                    m["leagueId"] = league_id
                    m["leagueName"] = league_name.replace("_", " ").title()
                    all_fixtures.append(m)
    
    print(f"[DEBUG] Total fixtures found: {len(all_fixtures)}")
    
    # Filter for scheduled/upcoming matches (not finished)
    finished_statuses = ["FT", "FINISHED", "FULL TIME", "FULL-TIME", "AET", "PEN", "CANC", "PST", "ABD"]
    upcoming = []
    
    for m in all_fixtures:
        status = str(m.get("status", "")).upper()
        if status not in finished_statuses:
            upcoming.append(m)
    
    # If no upcoming found, return all
    if not upcoming:
        upcoming = all_fixtures
    
    return upcoming


def fetch_fixtures(live=False):
    """Fetch fixtures - either live matches or today's matches"""
    if live:
        return fetch_live_matches()
    else:
        return fetch_fixtures_window()


# =====================
# PREDICTION
# =====================
def predict_base_outcome(match):
    """Predict match outcome based on home advantage"""
    r = random.random()
    if r < 0.45:
        return "home"
    elif r < 0.72:
        return "draw"
    else:
        return "away"


def format_odds(match):
    """Format odds block"""
    return ""  # This free API doesn't provide odds


# =====================
# MESSAGE BUILDERS
# =====================
def build_prediction(match, goals=None):
    style = random.choice(STYLE_LINES)
    closer = random.choice(CLOSERS)
    base = match["base_outcome"]
    home, away = match["home"], match["away"]
    odds_block = format_odds(match)

    if base == "draw":
        line = random.choice(DRAW_LINES)
        outcome = "Phantom Tip : DRAW"
    else:
        team = home if base == "home" else away
        line = random.choice(PREDICTIONS).format(team=team)
        outcome = f"📌 Phantom Tip : {team.upper()} Ko WIN Karo"

    score = ""
    if goals:
        score = f"\n⚽ {home} {goals[0]} - {goals[1]} {away}\n"

    return f"""{odds_block}
🧠 {style}
{line}

{outcome}
{score}
{closer}
"""


def build_header(title, match_no, total, league, home, away):
    return f"""🚨 MATCH {match_no}/{total} — {title}

🏆 {league}
{home} vs {away}
"""


# =====================
# TELEGRAM SEND
# =====================
async def send_message(text):
    await client.send_message(channel_id, text)
    print("✅ Message sent")


# =====================
# HELPER FUNCTIONS
# =====================
def extract_match_info(match):
    """Extract match info from API response (handles different response formats)"""
    # Try different field names
    match_id = match.get("id") or match.get("matchId") or match.get("match_id")
    
    # Home team
    home_team = match.get("homeTeam", {})
    if isinstance(home_team, dict):
        home_name = home_team.get("name") or home_team.get("teamName") or "Home"
    else:
        home_name = match.get("homeTeamName") or match.get("home") or "Home"
    
    # Away team
    away_team = match.get("awayTeam", {})
    if isinstance(away_team, dict):
        away_name = away_team.get("name") or away_team.get("teamName") or "Away"
    else:
        away_name = match.get("awayTeamName") or match.get("away") or "Away"
    
    # League
    league_name = match.get("leagueName") or match.get("league", {}).get("name") or "Unknown League"
    
    # Kickoff time
    kickoff = match.get("startTime") or match.get("time") or match.get("date") or match.get("utcDate")
    if not kickoff:
        # Default to 2 hours from now if no time found
        kickoff = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    
    # Score - handle different formats
    home_score = 0
    away_score = 0
    
    # Try homeScore/awayScore
    if "homeScore" in match:
        home_score = match.get("homeScore", 0) or 0
    elif "homeGoals" in match:
        home_score = match.get("homeGoals", 0) or 0
    elif "home_score" in match:
        home_score = match.get("home_score", 0) or 0
    
    if "awayScore" in match:
        away_score = match.get("awayScore", 0) or 0
    elif "awayGoals" in match:
        away_score = match.get("awayGoals", 0) or 0
    elif "away_score" in match:
        away_score = match.get("away_score", 0) or 0
    
    # Try score object
    score = match.get("score", {})
    if isinstance(score, dict):
        if "home" in score:
            home_score = score.get("home", 0) or 0
        if "away" in score:
            away_score = score.get("away", 0) or 0
    
    # Status
    status = match.get("status") or match.get("matchStatus") or "SCHEDULED"
    
    return {
        "match_id": str(match_id) if match_id else "",
        "home": home_name,
        "away": away_name,
        "league": league_name,
        "kickoff": kickoff,
        "home_score": int(home_score) if home_score else 0,
        "away_score": int(away_score) if away_score else 0,
        "status": str(status)
    }


# =====================
# MORNING JOB
# =====================
async def job_morning():
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if state.get("date") == today and state.get("matches"):
        print("Morning job already executed today")
        return

    fixtures = fetch_fixtures_window()
    if not fixtures:
        print("No matches found")
        return

    # Sort by importance
    fixtures.sort(key=match_importance_score, reverse=True)

    # Select top 5
    selected = fixtures[:5] if len(fixtures) >= 5 else fixtures

    if not selected:
        print("No matches to select")
        return

    state = {"date": today, "matches": [], "day_summary_sent": False}

    for i, m in enumerate(selected, 1):
        info = extract_match_info(m)
        
        match_data = {
            "match_id": info["match_id"],
            "match_number": i,
            "home": info["home"],
            "away": info["away"],
            "league": info["league"],
            "kickoff": info["kickoff"],
            "odds": None,
            "base_outcome": predict_base_outcome(m),
            "ht_draw_advised": False,
            "alert": False,
            "pre": False,
            "ht": False,
            "ft": False,
            "success": None
        }
        state["matches"].append(match_data)
        print(f"[DEBUG] Added match {i}: {info['home']} vs {info['away']}")

    save_state(state)

    msg = f"🌅 GOOD MORNING PHANTOMS! Aaj Jo Matches Hum Karenge --\n\n"
    for m in state["matches"]:
        msg += f"⚽ Match {m['match_number']}: {m['home']} vs {m['away']}\n"
    msg += "\n🕶️ Phantom Time"

    await send_message(msg)


# =====================
# CHECK JOB
# =====================
async def job_check():
    state = load_state()
    if not state.get("matches"):
        print("No matches in state")
        return

    now = datetime.now(timezone.utc)
    total = len(state["matches"])
    
    # Fetch live matches
    live_matches = fetch_live_matches()
    print(f"[DEBUG] Found {len(live_matches)} live matches")

    for m in state["matches"]:
        # Parse kickoff time
        try:
            kickoff_str = m["kickoff"]
            if "T" in kickoff_str:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            else:
                # Try to parse as timestamp or other format
                kickoff = datetime.now(timezone.utc) + timedelta(hours=1)
        except:
            kickoff = datetime.now(timezone.utc) + timedelta(hours=1)

        # ⏰ BE ACTIVE ALERT (1–1.5 HOURS BEFORE)
        if not m.get("alert", False):
            minutes_to_kickoff = (kickoff - now).total_seconds() / 60

            if 60 <= minutes_to_kickoff <= 90:
                IST = timezone(timedelta(hours=5, minutes=30))

                msg = f"""🚨 BE ACTIVE

⚽ {m['home']} vs {m['away']}
⏰ MATCH TIME – {kickoff.astimezone(IST).strftime('%I:%M %p')} IST

🕶️ Phantom Time
"""
                await send_message(msg)
                m["alert"] = True

        # PRE MATCH (0-35 minutes before kickoff)
        if not m["pre"]:
            minutes_to_kickoff = (kickoff - now).total_seconds() / 60
            if 0 <= minutes_to_kickoff <= 35:
                header = build_header(
                    "PRE-MATCH ANALYSIS",
                    m["match_number"], total,
                    m["league"], m["home"], m["away"]
                )
                await send_message(header + build_prediction(m))
                m["pre"] = True

        # Find live match data
        live_match = None
        for lm in live_matches:
            lm_info = extract_match_info(lm)
            if m["match_id"] and lm_info["match_id"] == m["match_id"]:
                live_match = lm
                break
            # Also try matching by team names
            if (m["home"].lower() in lm_info["home"].lower() or 
                lm_info["home"].lower() in m["home"].lower()):
                if (m["away"].lower() in lm_info["away"].lower() or 
                    lm_info["away"].lower() in m["away"].lower()):
                    live_match = lm
                    break

        if not live_match:
            # Check if match should be finished
            if not m["ft"] and now > kickoff + timedelta(hours=2, minutes=30):
                m["ft"] = True
                m["success"] = None
                save_state(state)
            continue

        # Extract live match info
        live_info = extract_match_info(live_match)
        goals = (live_info["home_score"], live_info["away_score"])
        status = live_info["status"].upper()

        # HALF-TIME UPDATE
        ht_statuses = ["HT", "HALFTIME", "HALF TIME", "HALF-TIME", "PAUSED"]
        if not m["ht"] and status in ht_statuses:
            home_goals, away_goals = goals
            base = m["base_outcome"]

            if base == "home":
                diff = home_goals - away_goals
            elif base == "away":
                diff = away_goals - home_goals
            else:
                if home_goals == away_goals:
                    diff = 0
                elif abs(home_goals - away_goals) == 1:
                    diff = -1
                else:
                    diff = -2

            # Skip HT message if losing by 2+
            if diff <= -2:
                m["ht"] = True
                continue

            header = build_header(
                "HALF-TIME UPDATE",
                m["match_number"], total,
                m["league"], m["home"], m["away"]
            )

            if diff > 0:
                await send_message(header + build_prediction(m, goals))

            elif diff == 0:
                if not m.get("ht_draw_advised"):
                    m["ht_draw_advised"] = True
                    msg = f"""{header}
🧠 Match abhi tak tight chal raha hai
Zyada domination nahi dikh rahi

⚽ {m['home']} {home_goals} - {away_goals} {m['away']}

📌 Hedge Tip:
Thodi Limit Draw Par Lagao 🤝

🕶️ Phantom Time
"""
                    await send_message(msg)

            elif diff == -1:
                line = random.choice(HT_LOSING_LINES)
                msg = f"""{header}
🧠 {line}

⚽ {m['home']} {home_goals} - {away_goals} {m['away']}

🕶️ Phantom Time
"""
                await send_message(msg)

            m["ht"] = True

        # FULL-TIME
        ft_statuses = ["FT", "FINISHED", "FULL TIME", "FULL-TIME", "AET", "PEN"]
        if not m["ft"] and status in ft_statuses:
            final_is_draw = goals[0] == goals[1]
            success = (
                (m["base_outcome"] == "draw" and final_is_draw) or
                (m["base_outcome"] == "home" and goals[0] > goals[1]) or
                (m["base_outcome"] == "away" and goals[1] > goals[0]) or
                (final_is_draw and m.get("ht_draw_advised", False))
            )

            result = "✅ Tip Pass" if success else "❌ Tip Fail"
            m["success"] = success

            header = build_header(
                f"FULL-TIME RESULT — {result}",
                m["match_number"], total,
                m["league"], m["home"], m["away"]
            )

            await send_message(
                header +
                f"\n⚽ FINAL SCORE: {goals[0]}-{goals[1]}\n\n🕶️ Phantom Time"
            )

            m["ft"] = True
            save_state(state)

            # DAY SUMMARY
            if all(x.get("ft") for x in state["matches"]) and not state.get("day_summary_sent"):
                passed = sum(1 for x in state["matches"] if x.get("success"))
                failed = len(state["matches"]) - passed

                summary_msg = f"""📊 DAY SUMMARY

✅ PASSED: {passed}
❌ FAILED: {failed}

🕶️ Phantom Time
"""
                await send_message(summary_msg)
                state["day_summary_sent"] = True
                save_state(state)

    save_state(state)


# =====================
# MAIN
# =====================
async def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py [morning|check]")
        return

    global client
    client = TelegramClient(
        session=None,
        api_id=api_id,
        api_hash=api_hash
    )

    await client.start(bot_token=TELEGRAM_BOT_TOKEN)

    try:
        if sys.argv[1] == "morning":
            await job_morning()
        elif sys.argv[1] == "check":
            await job_check()
        else:
            print(f"Unknown command: {sys.argv[1]}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())