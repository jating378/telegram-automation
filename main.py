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
API_KEY = os.environ["FOOTBALL_API_KEY"]  # football-data.org API token
GIST_ID = os.environ.get("GIST_ID")
GH_TOKEN = os.environ.get("GH_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# football-data.org competition codes and IDs
# Free tier available: WC, CL, BL1, DED, BSA, PD, FL1, ELC, PPL, EC, SA, PL
COMPETITION_CODES = {
    "PL": 2021,    # Premier League
    "PD": 2014,    # La Liga (Primera Division)
    "SA": 2019,    # Serie A
    "BL1": 2002,   # Bundesliga
    "FL1": 2015,   # Ligue 1
    "CL": 2001,    # Champions League
    "DED": 2003,   # Eredivisie
    "PPL": 2017,   # Primeira Liga (Portugal)
    "ELC": 2016,   # Championship
    "WC": 2000,    # World Cup
    "EC": 2018,    # European Championship
    "BSA": 2013,   # Brasileirão
}

LEAGUE_PRIORITY = {
    # INTERNATIONAL
    2000: 100,   # FIFA World Cup
    2018: 98,    # UEFA Euro (EC)
    
    # CLUB - TOP TIER
    2001: 92,    # UEFA Champions League
    2021: 88,    # Premier League
    2014: 86,    # La Liga
    2019: 84,    # Serie A
    2002: 82,    # Bundesliga
    2015: 80,    # Ligue 1
    
    # CLUB - SECOND TIER
    2017: 75,    # Primeira Liga (Portugal)
    2003: 74,    # Eredivisie
    2016: 70,    # Championship
    2013: 68,    # Brasileirão
}


def match_importance_score(match):
    comp_id = match["competition"]["id"]
    league_score = LEAGUE_PRIORITY.get(comp_id, 0)

    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]

    big_clubs = [
        "Real Madrid CF", "FC Barcelona", "Manchester United FC",
        "Manchester City FC", "Liverpool FC", "Arsenal FC",
        "FC Bayern München", "Paris Saint-Germain FC", "Juventus FC", "AC Milan",
        "FC Internazionale Milano", "Chelsea FC"
    ]

    club_boost = 0
    if home in big_clubs:
        club_boost += 5
    if away in big_clubs:
        club_boost += 5

    return league_score + club_boost


MAJOR_COMPETITION_IDS = set(LEAGUE_PRIORITY.keys())


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
# FOOTBALL-DATA.ORG API v4
# =====================
def fetch_fixtures_window():
    """Fetch matches from ±1 day window using football-data.org API"""
    fixtures = []
    seen = set()
    
    # Calculate date range
    date_from = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": API_KEY}
    params = {
        "dateFrom": date_from,
        "dateTo": date_to
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        
        data = r.json()
        all_matches = data.get("matches", [])
        print(f"[DEBUG] Date range {date_from} to {date_to}: Found {len(all_matches)} total matches")
        
        for m in all_matches:
            if m["competition"]["id"] in MAJOR_COMPETITION_IDS:
                match_id = m["id"]
                if match_id not in seen:
                    seen.add(match_id)
                    fixtures.append(m)
        
        print(f"[DEBUG] Major competition matches found: {len(fixtures)}")
        
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API request failed: {e}")
    
    return fixtures


def fetch_fixtures(live=False):
    """Fetch fixtures - either live matches or today's matches"""
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": API_KEY}
    
    if live:
        # football-data.org uses status filter for live matches
        params = {"status": "LIVE"}
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        params = {"dateFrom": today, "dateTo": tomorrow}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        
        data = r.json()
        matches = data.get("matches", [])
        
        return [m for m in matches if m["competition"]["id"] in MAJOR_COMPETITION_IDS]
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API request failed: {e}")
        return []


# =====================
# PREDICTION
# =====================
def predict_base_outcome(match):
    """Predict match outcome based on home advantage (no live stats in this API)"""
    # football-data.org free tier doesn't have odds, so we use home advantage
    r = random.random()
    if r < 0.45:
        return "home"
    elif r < 0.72:
        return "draw"
    else:
        return "away"


def format_odds(match):
    """Format odds block - football-data.org free tier doesn't have odds"""
    return ""


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
        print("No matches found in ±1 day window")
        return

    # Filter for SCHEDULED matches only
    fixtures = [m for m in fixtures if m["status"] == "SCHEDULED" or m["status"] == "TIMED"]
    
    if not fixtures:
        print("No scheduled matches found")
        return

    fixtures.sort(key=match_importance_score, reverse=True)

    selected = []
    for m in fixtures:
        selected.append(m)
        if len(selected) >= 5:
            break

    if len(selected) < 2:
        selected = fixtures[:2]

    fixtures = selected

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = {"date": today, "matches": [], "day_summary_sent": False}

    for i, m in enumerate(fixtures, 1):
        match_data = {
            "match_id": str(m["id"]),
            "match_number": i,
            "home": m["homeTeam"]["name"],
            "away": m["awayTeam"]["name"],
            "league": m["competition"]["name"],
            "kickoff": m["utcDate"],
            "odds": None,  # football-data.org free tier doesn't have odds
            "base_outcome": predict_base_outcome(m),
            "ht_draw_advised": False,
            "alert": False,
            "pre": False,
            "ht": False,
            "ft": False,
            "success": None
        }
        state["matches"].append(match_data)

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
        return

    now = datetime.now(timezone.utc)
    total = len(state["matches"])
    
    # Fetch all matches (live + today's)
    live = fetch_fixtures(live=True)
    today_matches = fetch_fixtures(live=False)
    all_matches = live + today_matches
    
    # Remove duplicates
    seen_ids = set()
    unique_matches = []
    for m in all_matches:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_matches.append(m)

    for m in state["matches"]:
        kickoff = datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))

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

        # PRE MATCH
        if not m["pre"] and 0 <= (kickoff - now).total_seconds() / 60 <= 35:
            header = build_header(
                "PRE-MATCH ANALYSIS",
                m["match_number"], total,
                m["league"], m["home"], m["away"]
            )
            await send_message(header + build_prediction(m))
            m["pre"] = True

        # LIVE MATCH
        live_match = next((x for x in unique_matches if str(x["id"]) == m["match_id"]), None)

        if not live_match:
            if not m["ft"] and now > kickoff + timedelta(hours=2, minutes=30):
                m["ft"] = True
                m["success"] = None
                save_state(state)
            continue

        # Get goals from score
        score = live_match.get("score", {})
        full_time = score.get("fullTime", {})
        half_time = score.get("halfTime", {})
        
        home_goals = full_time.get("home") or half_time.get("home") or 0
        away_goals = full_time.get("away") or half_time.get("away") or 0
        goals = (home_goals, away_goals)
        
        status = live_match["status"]
        
        # Map football-data.org status to simple status
        # SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED, POSTPONED, CANCELLED, SUSPENDED
        
        # Get elapsed time (football-data.org provides "minute" field)
        elapsed = live_match.get("minute", 0) or 0

        # HALF-TIME UPDATE
        if not m["ht"] and (status == "PAUSED" or (status == "IN_PLAY" and 45 <= elapsed <= 55)):
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
        if not m["ft"] and status == "FINISHED":
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
