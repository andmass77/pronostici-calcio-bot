
import os
import json
import math
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

LEAGUES = {
    "it.1": "Serie A",
    "en.1": "Premier League",
    "es.1": "Liga",
    "de.1": "Bundesliga",
    "fr.1": "Ligue 1",
}

SEASONS = ["2026-27", "2025-26"]


def download_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "PronosticiCalcioBot/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def get_score(match):
    score = match.get("score")

    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, list) and len(ft) >= 2:
            try:
                return int(ft[0]), int(ft[1])
            except (ValueError, TypeError):
                return None

    if isinstance(score, list) and len(score) >= 2:
        try:
            return int(score[0]), int(score[1])
        except (ValueError, TypeError):
            pass

    return None


def load_league(code):
    matches = []

    for season in SEASONS:
        url = (
            "https://raw.githubusercontent.com/openfootball/"
            f"football.json/master/{season}/{code}.json"
        )
        try:
            data = download_json(url)
            for match in data.get("matches", []):
                match["_season"] = season
                matches.append(match)
        except Exception as exc:
            print(f"Dati non disponibili {code}/{season}: {exc}")

    matches.sort(key=lambda m: m.get("date", ""))
    return matches


def poisson(lam, goals):
    return math.exp(-lam) * (lam ** goals) / math.factorial(goals)


def predict(home, away, matches):
    history = []

    for match in matches:
        try:
            match_date = date.fromisoformat(match["date"])
        except (ValueError, KeyError, TypeError):
            continue

        if match_date >= date.today():
            continue

        score = get_score(match)
        if score is None:
            continue

        h, a = score
        home_name = match.get("team1")
        away_name = match.get("team2")

        if not home_name or not away_name:
            continue

        history.append((home_name, away_name, h, a))

    if len(history) < 10:
        return None

    league_home = sum(m[2] for m in history) / len(history)
    league_away = sum(m[3] for m in history) / len(history)

    if league_home <= 0 or league_away <= 0:
        return None

    def team_stats(team, venue):
        relevant = []

        for hname, aname, hg, ag in history:
            if venue == "home" and hname == team:
                relevant.append((hg, ag))
            elif venue == "away" and aname == team:
                relevant.append((ag, hg))

        relevant = relevant[-12:]
        if not relevant:
            return None

        scored = sum(x[0] for x in relevant) / len(relevant)
        conceded = sum(x[1] for x in relevant) / len(relevant)
        return scored, conceded

    hs = team_stats(home, "home")
    aws = team_stats(away, "away")

    if hs is None or aws is None:
        return None

    home_attack = hs[0] / league_home
    home_defence = hs[1] / league_away
    away_attack = aws[0] / league_away
    away_defence = aws[1] / league_home

    lam_home = max(
        0.15, min(4.0, league_home * home_attack * away_defence)
    )
    lam_away = max(
        0.15, min(4.0, league_away * away_attack * home_defence)
    )

    ph = [poisson(lam_home, g) for g in range(9)]
    pa = [poisson(lam_away, g) for g in range(9)]

    p1 = px = p2 = over = btts = 0.0

    for hg in range(9):
        for ag in range(9):
            p = ph[hg] * pa[ag]

            if hg > ag:
                p1 += p
            elif hg == ag:
                px += p
            else:
                p2 += p

            if hg + ag >= 3:
                over += p

            if hg > 0 and ag > 0:
                btts += p

    return {
        "1": p1, "X": px, "2": p2,
        "over": over, "under": 1 - over,
        "goal": btts, "nogol": 1 - btts,
    }


def send_message(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Secrets Telegram mancanti.")

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
    }).encode()

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError("Telegram non ha accettato il messaggio.")


def main():
    now = datetime.now(ROME)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    lines = [
        "⚽ PRONOSTICI CALCIO",
        f"📅 {now.strftime('%d/%m/%Y')}",
        "",
        "Stime statistiche, non garanzie di risultato.",
    ]

    count = 0

    for code, league_name in LEAGUES.items():
        matches = load_league(code)
        if not matches:
            continue

        upcoming = []

        for match in matches:
            try:
                match_date = date.fromisoformat(match["date"])
            except (ValueError, KeyError, TypeError):
                continue

            if not today <= match_date <= tomorrow:
                continue

            time_text = match.get("time", "23:59")

            try:
                kickoff = datetime.strptime(
                    f"{match['date']} {time_text}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=ROME)
            except ValueError:
                continue

            if kickoff <= now:
                continue

            # Salta le partite già registrate come concluse.
            score = match.get("score")
            if isinstance(score, dict) and isinstance(score.get("ft"), list):
                continue

            upcoming.append((kickoff, match))

        for kickoff, match in upcoming:
            prediction = predict(
                match.get("team1", ""),
                match.get("team2", ""),
                matches
            )

            if prediction is None:
                continue

            home = match["team1"]
            away = match["team2"]

            best_1x2 = max(
                ["1", "X", "2"], key=lambda x: prediction[x]
            )
            market = max(
                ["Over 2.5", "Under 2.5"],
                key=lambda x: prediction[
                    "over" if x == "Over 2.5" else "under"
                ]
            )
            goal_market = max(
                ["Goal", "No Goal"],
                key=lambda x: prediction[
                    "goal" if x == "Goal" else "nogol"
                ]
            )

            lines.extend([
                "",
                f"🏆 {league_name} — {kickoff.strftime('%d/%m %H:%M')}",
                f"{home} - {away}",
                f"1X2: {best_1x2} ({prediction[best_1x2]:.0%})",
                f"Over/Under 2.5: {market} "
                f"({max(prediction['over'], prediction['under']):.0%})",
                f"Goal/No Goal: {goal_market} "
                f"({max(prediction['goal'], prediction['nogol']):.0%})",
            ])

            count += 1
            if count >= 12:
                break

        if count >= 12:
            break

    if count == 0:
        lines.extend([
            "",
            "Non ho trovato partite future con dati sufficienti "
            "nelle competizioni configurate.",
            "I calendari potrebbero essere incompleti o non aggiornati."
        ])

    lines.extend([
        "",
        "ℹ️ Probabilità indicative basate sui risultati disponibili.",
        "Non sono quote e non garantiscono vincite."
    ])

    send_message("\n".join(lines)[:4000])
    print(f"Elaborazione terminata. Partite analizzate: {count}")


if __name__ == "__main__":
    main()
