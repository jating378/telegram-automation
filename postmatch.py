import asyncio
import random
import requests
from telethon import TelegramClient

# =====================
# TELEGRAM CONFIG
# =====================
api_id = 38564520
api_hash = "61b5819b845231a2ddb7e951acaca002"
channel_id = -1003548105404

# =====================
# FOOTBALL API CONFIG
# =====================
API_KEY = "eecc122a9892c624ebd9878cc5108b93"
MAJOR_LEAGUE_IDS = {39, 140, 135, 78, 61, 2, 3}

# =====================
# MATCH COUNTER
# =====================
MATCH_COUNTER_FILE = "match_counter.txt"

def get_match_counter():
    try:
        with open(MATCH_COUNTER_FILE, "r") as f:
            counter = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        counter = 0

    counter += 1

    with open(MATCH_COUNTER_FILE, "w") as f:
        f.write(str(counter))

    return counter

# =====================
# TEXT BLOCKS
# =====================
ATTENTION_LINES = [
    "🚨 Attention Everyone",
    "📣 Attention Public"
]

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
    "{team} ke chances better dikh rahe hain.",
    "{team} pressure bana rahi hai."
]

DRAW_LINES = [
    "Abhi ke liye match balanced hai.",
    "Dono side barabar fight kar rahi hain.",
    "Filhaal draw type game lag raha hai.",
    "Kuch bhi ho sakta hai, dono teams equally matched hain.",
    "Draw hone ke chances zyada lag rahe hain.",
    "Aise matches mein draw common hota hai."
]

CLOSERS = [
    "Phantom Time 🕶️",
    "Match ke baad milte hain!",
    "Kuch bhi change hota toh update karenge.",
    "Stay tuned for more updates!"
]

# =====================
# SMART PREDICTION LOGIC
# =====================
def predict_outcome(ht_home, ht_away, red_home, red_away):
    if red_home > red_away:
        return random.choices(["away", "draw"], weights=[70, 30])[0]
    if red_away > red_home:
        return random.choices(["home", "draw"], weights=[70, 30])[0]

    if ht_home == 0 and ht_away == 0:
        return random.choice(["home", "away", "draw"])

    if ht_home == 1 and ht_away == 0:
        return random.choices(["home", "draw"], weights=[70, 30])[0]

    if ht_home == 0 and ht_away == 1:
        return random.choices(["away", "draw"], weights=[70, 30])[0]

    if ht_home - ht_away >= 2:
        return random.choices(["home", "draw"], weights=[85, 15])[0]

    if ht_away - ht_home >= 2:
        return random.choices(["away", "draw"], weights=[85, 15])[0]

    return random.choice(["home", "away", "draw"])

# =====================
# MAIN LOGIC
# =====================
async def main():
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_KEY}
    params = {"live": "all"}

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    fixtures = [
        m for m in data.get("response", [])
        if m.get("league", {}).get("id") in MAJOR_LEAGUE_IDS
    ]

    if not fixtures:
        print("No live major matches right now.")
        return

    match = random.choice(fixtures)

    home = match["teams"]["home"]["name"]
    away = match["teams"]["away"]["name"]
    league = match["league"]["name"]

    status = match["fixture"]["status"]["short"]
    minute = match["fixture"]["status"]["elapsed"]

    goals_home = match["goals"]["home"] or 0
    goals_away = match["goals"]["away"] or 0

    ht = match.get("score", {}).get("halftime", {})
    ht_home = ht.get("home", 0)
    ht_away = ht.get("away", 0)

    cards = match.get("cards", {}).get("red", {})
    red_home = cards.get("home", 0)
    red_away = cards.get("away", 0)

    score_line = f"⚽ Score: {home} {goals_home} - {goals_away} {away}"

    card_line = ""
    if red_home or red_away:
        card_line = f"🟥 Red Cards — {home}: {red_home} | {away}: {red_away}\n"

    outcome = predict_outcome(ht_home, ht_away, red_home, red_away)

    if outcome == "draw":
        prediction_line = random.choice(DRAW_LINES)
        outcome_line = "📌 MATCH OUTCOME : DRAW"
    else:
        team = home if outcome == "home" else away
        prediction_line = random.choice(PREDICTIONS).format(team=team)
        outcome_line = f"📌 MATCH OUTCOME : {team.upper()} WIN"

    match_no = get_match_counter()

    opener_block = f"""📊 MATCH No: {match_no}
🔴 LIVE MATCH 🔴
{random.choice(ATTENTION_LINES)}"""

    message = f"""{opener_block}

🏆 {league}
⏱️ {minute}' ({status})

{score_line}
{card_line}{home} vs {away}

{random.choice(STYLE_LINES)}
{prediction_line}

{outcome_line}

{random.choice(CLOSERS)}
"""

    async with TelegramClient("phantom_session", api_id, api_hash) as client:
        await client.send_message(channel_id, message)

    print("✅ Live match post sent successfully")

# =====================
# RUN
# =====================
asyncio.run(main())
