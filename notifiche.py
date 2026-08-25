"""
Notifiche vere via Telegram
=============================

Un modo per farti avvisare SUBITO sul telefono quando il bot fa qualcosa di
importante: piazza un ordine, si ferma per il circuit breaker, il kill
switch e' attivo, oppure incontra un errore che non riesce a risolvere da
solo.

Come funziona (concetti nuovi)
--------------------------------
Telegram permette di creare gratuitamente un "bot" (un contatto automatico)
che puo' mandarti messaggi tramite semplici richieste internet. Servono
due informazioni segrete, da mettere nel file .env (mai su GitHub, esattamente
come le chiavi di Alpaca):

  TELEGRAM_BOT_TOKEN  -> l'indirizzo/password del tuo bot Telegram
  TELEGRAM_CHAT_ID    -> il "numero" della tua conversazione col bot

Come ottenerle te lo spiego a parte in chat quando arriviamo a testare
questo pezzo (si fa tutto dentro l'app di Telegram, in due minuti).

Regola importante: le notifiche non devono MAI poter rompere il bot. Se
Telegram non e' configurato, o la richiesta fallisce per qualsiasi motivo
(rete assente, token sbagliato...), stampiamo solo un avviso a schermo e
andiamo avanti: il bot deve continuare a funzionare comunque.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Stampiamo l'avviso "notifiche non configurate" una volta sola per
# esecuzione, invece di ripeterlo ogni volta che invia_notifica() viene
# chiamata: altrimenti riempiremmo lo schermo di avvisi inutili.
_avviso_gia_mostrato = False


def notifiche_configurate():
    """True se sia il token che il chat id sono presenti nel file .env."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def invia_notifica(messaggio):
    """
    Prova a mandare 'messaggio' su Telegram. Restituisce True se e' andata
    bene, False in ogni altro caso (notifiche non configurate, errore di
    rete, risposta di errore da Telegram). Non solleva MAI un'eccezione:
    il chiamante non deve preoccuparsi di gestire errori qui.
    """
    global _avviso_gia_mostrato

    if not notifiche_configurate():
        if not _avviso_gia_mostrato:
            print(
                "\n(Nota: notifiche Telegram non configurate - mancano "
                "TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID nel file .env. "
                "Il bot continua a funzionare normalmente, semplicemente "
                "non manda avvisi sul telefono.)"
            )
            _avviso_gia_mostrato = True
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        risposta = requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": messaggio},
            timeout=10,
        )
        if risposta.status_code != 200:
            print(f"Notifica Telegram non riuscita (risposta {risposta.status_code}): {risposta.text}")
            return False
        return True
    except Exception as errore:
        print(f"Notifica Telegram non riuscita: {errore}")
        return False


if __name__ == "__main__":
    # Piccolo script di prova: lancia "python3 notifiche.py" per testare
    # se le notifiche Telegram funzionano, senza dover far girare tutto
    # il bot.
    if not notifiche_configurate():
        print(
            "TELEGRAM_BOT_TOKEN e/o TELEGRAM_CHAT_ID non trovati nel file .env.\n"
            "Aggiungili prima di testare (vedi .env.example)."
        )
    else:
        print("Provo a mandare un messaggio di prova su Telegram...")
        riuscito = invia_notifica("Messaggio di prova dal bot di Giacomo. Se lo vedi, le notifiche funzionano!")
        print("Riuscito!" if riuscito else "Non riuscito, controlla i dettagli sopra.")
