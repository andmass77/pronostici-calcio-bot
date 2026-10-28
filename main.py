
import os
import json
import urllib.request
import urllib.parse


def invia_messaggio(testo):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Configurazione Telegram mancante.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    dati = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": testo
    }).encode("utf-8")

    richiesta = urllib.request.Request(url, data=dati)

    with urllib.request.urlopen(richiesta, timeout=20) as risposta:
        risultato = json.loads(risposta.read().decode("utf-8"))

    if not risultato.get("ok"):
        raise RuntimeError("Invio Telegram non riuscito.")

    print("Messaggio Telegram inviato correttamente.")


if __name__ == "__main__":
    invia_messaggio(
        "⚽ Bot Pronostici Calcio avviato!\n\n"
        "Configurazione Telegram verificata. "
        "Prossimo passo: collegare i dati delle partite "
        "e calcolare i pronostici."
    )
