import asyncio
import random
import requests
import json
import os
from datetime import datetime, timezone
from telethon import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
channel_id = int(os.environ["TELEGRAM_CHANNEL_ID"])
API_KEY = os.environ["FOOTBALL_API_KEY"]
GIST_ID = os.environ.get("GIST_ID")
GH_TOKEN = os.environ.get("GH_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

LEAGUE_PRIORITY = {
    2: 100,   # Champions League
    3: 95,    # Europa League
    39: 90,   # Premier League
    140: 88,  # La Liga
    135: 85,  # Serie A
    78: 83,   # Bundesliga
    61: 80,   # Ligue 1
}
def match_importance_score(match):
    league_id = match["league"]["id"]
    league_score = LEAGUE_PRIORITY.get(league_id, 0)

    home = match["teams"]["home"]["name"]
    away = match["teams"]["away"]["name"]

    # Extra boost for big clubs
    big_clubs = [
        "Real Madrid", "Barcelona", "Manchester United",
        "Manchester City", "Liverpool", "Arsenal",
        "Bayern Munich", "PSG", "Juventus", "AC Milan",
        "Inter", "Chelsea"
    ]

    club_boost = 0
    if home in big_clubs:
        club_boost += 5
    if away in big_clubs:
        club_boost += 5

    return league_score + club_boost

MAJOR_LEAGUE_IDS = set(LEAGUE_PRIORITY.keys())


# =====================



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
    "{team} ki side momentum jaata hua lag raha hai.",
    "{team} pressure bana rahi hai."
]

DRAW_LINES = [
    "Abhi ke liye match balanced hai.",
    "Dono side barabar fight kar rahi hain.",
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
    "Balanced game hai, draw ho sakta hai. Put some on draw."
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
        return {"matches": [], "date": None}

    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()

    files = r.json().get("files", {})
    if "match_state.json" not in files:
        raise RuntimeError("match_state.json missing in Gist")

    return json.loads(files["match_state.json"]["content"])


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
# FOOTBALL API
# =====================
def fetch_fixtures(live=False):
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"live": "all"} if live else {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    }

    r = requests.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()

    return [
        m for m in r.json().get("response", [])
        if m["league"]["id"] in MAJOR_LEAGUE_IDS
    ]


# =====================
# PREDICTION
# =====================
def predict_base_outcome(match):
    stats = match.get("statistics", [])

    home_shots = away_shots = 0

    # ✅ ADD THIS BLOCK (PRE-MATCH FIX)
    if not stats:
        r = random.random()

        if r < 0.45:
            return "home"
        elif r < 0.70:
            return "draw"
        else:
            return "away"
    # ✅ END CHANGE

    for team in stats:
        if team["team"]["id"] == match["teams"]["home"]["id"]:
            home_shots = next(
                (s["value"] for s in team["statistics"] if s["type"] == "Shots on Goal"),
                0
            ) or 0
        else:
            away_shots = next(
                (s["value"] for s in team["statistics"] if s["type"] == "Shots on Goal"),
                0
            ) or 0

    if abs(home_shots - away_shots) <= 1:
        return "draw"
    return "home" if home_shots > away_shots else "away"

# =====================
# MESSAGE BUILDERS (WITH MATCH COUNTER)
# =====================
def build_prediction(match, goals=None):
    style = random.choice(STYLE_LINES)
    closer = random.choice(CLOSERS)
    base = match["base_outcome"]
    home, away = match["home"], match["away"]

    if base == "draw":
        line = random.choice(DRAW_LINES)
        outcome = "Phantom Tip : DRAW"
    else:
        team = home if base == "home" else away
        line = random.choice(PREDICTIONS).format(team=team)
        outcome = f"📌 Phantom Tip : {team.upper()} WIN"

    score = ""
    if goals:
        score = f"\n⚽ {home} {goals[0]} - {goals[1]} {away}\n"

    return f"""🧠 {style}
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

    fixtures = fetch_fixtures(False)

    # Sort by importance (highest first)
    fixtures.sort(key=match_importance_score, reverse=True)

    # Dynamic selection
    selected = []

    for m in fixtures:
        selected.append(m)
        if len(selected) >= 5:
            break

    # Minimum guarantee (at least 2 big matches)
    if len(selected) < 2:
        selected = fixtures[:2]

    fixtures = selected


    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = {"date": today, "matches": []}

    for i, m in enumerate(fixtures, 1):
        state["matches"].append({
            "match_id": str(m["fixture"]["id"]),
            "match_number": i,
            "home": m["teams"]["home"]["name"],
            "away": m["teams"]["away"]["name"],
            "league": m["league"]["name"],
            "kickoff": m["fixture"]["date"],
            "base_outcome": predict_base_outcome(m),
            "alert": False,
            "pre": False,
            "ht": False,
            "ft": False
        })

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
    if not state["matches"]:
        return

    now = datetime.now(timezone.utc)
    total = len(state["matches"])
    live = fetch_fixtures(True)

    for m in state["matches"]:
        kickoff = datetime.fromisoformat(m["kickoff"].replace("Z", "+00:00"))
        # ⏰ BE ACTIVE ALERT (1–1.5 HOURS BEFORE)
        if not m.get("alert", False):
            minutes_to_kickoff = (kickoff - now).total_seconds() / 60
        
            if 60 <= minutes_to_kickoff <= 90:
                from datetime import timedelta, timezone
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

        # LIVE
        live_match = next((x for x in live if str(x["fixture"]["id"]) == m["match_id"]), None)
        if not live_match:
            continue

        goals = (
            live_match["goals"]["home"] or 0,
            live_match["goals"]["away"] or 0
        )
        status = live_match["fixture"]["status"]["short"]

        if status == "HT" and not m["ht"]:
            home_goals, away_goals = goals
            base = m["base_outcome"]

            # Determine goal difference relative to our prediction
            if base == "home":
                diff = home_goals - away_goals
            elif base == "away":
                diff = away_goals - home_goals
            else:  # base == "draw"
                if home_goals == away_goals:
                    diff = 0
                elif abs(home_goals - away_goals) == 1:
                    diff = -1
                else:
                    diff = -2
  # draw case

            # ❌ Skip HT if losing by 2 or more
            if diff <= -2:
                m["ht"] = True
                continue

            header = build_header(
                "HALF-TIME UPDATE",
                m["match_number"], total,
                m["league"], m["home"], m["away"]
            )

            # ✅ If winning → normal prediction
            if diff > 0:
                await send_message(header + build_prediction(m, goals))

            # 🔁 If draw (1–1 etc.)
            elif diff == 0:
                line = random.choice(HT_DRAW_LINES)
                msg = f"""{header}
        🧠 {line}

        ⚽ {m['home']} {home_goals} - {away_goals} {m['away']}

        🕶️ Phantom Time
        """
                await send_message(msg)

            # 🔁 Losing by exactly 1
            elif diff == -1:
                line = random.choice(HT_LOSING_LINES)
                msg = f"""{header}
        🧠 {line}

        ⚽ {m['home']} {home_goals} - {away_goals} {m['away']}

        🕶️ Phantom Time
        """
                await send_message(msg)

            m["ht"] = True


        if status == "FT" and not m["ft"]:
            success = (
                goals[0] == goals[1] if m["base_outcome"] == "draw"
                else goals[0] > goals[1] if m["base_outcome"] == "home"
                else goals[1] > goals[0]
            )
            result = "✅ WON" if success else "❌ LOST"
            header = build_header(
                f"FULL-TIME RESULT — {result}",
                m["match_number"], total,
                m["league"], m["home"], m["away"]
            )
            await send_message(header + f"\n⚽ FINAL SCORE: {goals[0]}-{goals[1]}\n\n🕶️ Phantom Time")
            m["ft"] = True

    save_state(state)


# =====================
# MAIN
# =====================
async def main():
    import sys

    if len(sys.argv) < 2:
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
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
