"""
FASE 1 - Prima connessione ad Alpaca
=====================================

Cosa fa questo script:
  1. Legge le tue chiavi segrete dal file .env (mai scritte dentro al codice,
     e mai caricate su GitHub grazie al .gitignore)
  2. Si collega al tuo conto di PAPER TRADING su Alpaca (soldi finti,
     nessun rischio reale)
  3. Stampa il saldo e il valore del tuo portafoglio virtuale
  4. Controlla se in questo momento la borsa americana e' aperta o chiusa
     (il primo pezzo del nostro "calendario di mercato")

Concetti nuovi che incontri qui:
  - ".env" + "python-dotenv": un file separato dove tieni le chiavi segrete.
    Il programma le legge da li', cosi' non stanno mai scritte nel codice
    che finisce su GitHub.
  - "Client": un oggetto che si occupa di tutta la comunicazione con Alpaca
    (mandare le richieste, gestire l'autenticazione, ecc.) cosi' tu lavori
    con semplici funzioni come client.get_account() invece di costruire a
    mano le richieste internet.
"""

import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

from database import inizializza_database, salva_snapshot_conto, mostra_storico

# Carica le variabili scritte nel file .env nella "memoria" del programma.
# Da questo momento os.getenv("NOME_VARIABILE") le puo' leggere.
load_dotenv()

api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")

if not api_key or not secret_key:
    raise SystemExit(
        "Non trovo le chiavi Alpaca nel file .env.\n"
        "Controlla di aver creato il file '.env' (senza '.example' alla fine) "
        "nella stessa cartella, e di averlo compilato con le tue chiavi vere."
    )

# paper=True dice ad Alpaca: "voglio il conto di SIMULAZIONE, non quello vero"
client = TradingClient(api_key, secret_key, paper=True)


def mostra_saldo_conto():
    """Legge, stampa e restituisce il saldo del conto paper trading."""
    account = client.get_account()
    liquidita = float(account.cash)
    valore_portafoglio = float(account.portfolio_value)

    print("Il tuo conto Alpaca (PAPER = soldi finti):")
    print(f"  Liquidita' disponibile:     {liquidita:>12,.2f} $")
    print(f"  Valore totale portafoglio:  {valore_portafoglio:>12,.2f} $")

    return liquidita, valore_portafoglio


def mostra_stato_mercato():
    """Controlla se la borsa americana e' aperta in questo momento, e lo restituisce."""
    orologio = client.get_clock()
    stato = "APERTO" if orologio.is_open else "CHIUSO"
    print(f"\nMercato USA in questo momento: {stato}")
    if orologio.is_open:
        print(f"  Chiudera' alle: {orologio.next_close}")
    else:
        print(f"  Riaprira' alle: {orologio.next_open}")

    return orologio.is_open


if __name__ == "__main__":
    # Crea la tabella nel database se non esiste ancora (non fa danni se c'e' gia')
    inizializza_database()

    liquidita, valore_portafoglio = mostra_saldo_conto()
    mercato_aperto = mostra_stato_mercato()

    # Salviamo questa "fotografia" del conto nel database, cosi' costruiamo
    # uno storico ogni volta che lanciamo lo script
    salva_snapshot_conto(liquidita, valore_portafoglio, mercato_aperto)

    # Stampiamo tutto lo storico salvato finora, per vedere che funziona
    mostra_storico()
