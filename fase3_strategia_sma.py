"""
FASE 3 - La prima strategia vera: incrocio di medie mobili (SMA crossover)
============================================================================

Finalmente una strategia che decide DAVVERO se comprare o vendere (per ora
si limita a deciderlo e scriverlo: non manda ancora ordini ad Alpaca, quello
verra' in una fase successiva, quando saremo sicuri che i segnali abbiano
senso).

L'idea della strategia, spiegata semplice
------------------------------------------
Calcoliamo due "medie mobili" sul prezzo di chiusura di un'azione:
  - una MEDIA BREVE (es. media degli ultimi 10 giorni) che reagisce in
    fretta ai movimenti recenti del prezzo
  - una MEDIA LUNGA (es. media degli ultimi 30 giorni) che si muove piu'
    lentamente e rappresenta il "trend di fondo"

Quando la media breve ATTRAVERSA la media lunga dal basso verso l'alto,
vuol dire che il prezzo si sta muovendo piu' in fretta verso l'alto rispetto
al trend di fondo: e' un possibile segnale di ACQUISTO (BUY).

Quando succede il contrario (la media breve scende sotto la media lunga),
e' un possibile segnale di VENDITA (SELL).

Se non c'e' nessun incrocio, il segnale e' NONE: il bot non fa nulla.

Logging contestuale
--------------------
Come richiesto fin dall'inizio, non salviamo solo la parola "BUY" o "SELL":
salviamo anche i valori esatti delle due medie (di oggi e di ieri) che hanno
prodotto quella decisione. Cosi', anche tra mesi, possiamo riaprire il
database e capire ESATTAMENTE perche' il bot ha deciso in un certo modo,
senza doverci fidare a memoria della logica del codice.

Nota sui fusi orari
--------------------
Il mercato USA segue l'orario di New York, non quello italiano. Per non fare
confusione chiediamo i dati ad Alpaca usando date "consapevoli del fuso
orario" (timezone-aware, in UTC), invece di usare l'ora locale del tuo Mac
senza specificare nulla.
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from database import inizializza_database, salva_segnale, mostra_segnali

# ---------------------------------------------------------------------------
# CONFIGURAZIONE DELLA STRATEGIA
# ---------------------------------------------------------------------------

SIMBOLO = "AAPL"          # l'azione che analizziamo (Apple, per iniziare)
PERIODO_BREVE = 10        # media mobile a 10 giorni
PERIODO_LUNGO = 30        # media mobile a 30 giorni

# Quanti giorni di calendario chiediamo indietro: servono almeno 30 giorni
# DI BORSA (weekend e festivita' escluse) per calcolare la media lunga, quindi
# chiediamone parecchi di piu' per essere sicuri di averne abbastanza.
GIORNI_STORIA_DA_RICHIEDERE = 90


# ---------------------------------------------------------------------------
# CARICAMENTO CHIAVI E CREAZIONE DEL CLIENT DATI
# ---------------------------------------------------------------------------

load_dotenv()

api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")

if not api_key or not secret_key:
    raise SystemExit(
        "Non trovo le chiavi Alpaca nel file .env.\n"
        "Controlla di aver creato il file '.env' (senza '.example' alla fine) "
        "nella stessa cartella, e di averlo compilato con le tue chiavi vere."
    )

# Il client per i DATI di mercato e' un oggetto diverso dal TradingClient
# della Fase 1 (quello serviva per saldo/ordini, questo serve per i prezzi
# storici). Le chiavi usate sono le stesse.
client_dati = StockHistoricalDataClient(api_key, secret_key)


# ---------------------------------------------------------------------------
# FUNZIONI DELLA STRATEGIA (logica pura, senza rete: testabili da sole)
# ---------------------------------------------------------------------------

def calcola_medie_mobili(prezzi, periodo_breve=PERIODO_BREVE, periodo_lungo=PERIODO_LUNGO):
    """
    Riceve una serie di prezzi di chiusura (una pandas Series, ordinata dal
    piu' vecchio al piu' recente) e restituisce due nuove serie: la media
    mobile breve e quella lunga.

    'rolling(window=N).mean()' calcola, per ogni giorno, la media degli
    ultimi N giorni (compreso quel giorno). I primi N-1 valori sono NaN
    ("Not a Number") perche' non ci sono ancora abbastanza giorni indietro
    per calcolare la media.
    """
    media_breve = prezzi.rolling(window=periodo_breve).mean()
    media_lunga = prezzi.rolling(window=periodo_lungo).mean()
    return media_breve, media_lunga


def decidi_segnale(media_breve, media_lunga):
    """
    Guarda gli ultimi due valori delle due medie (oggi e ieri) e decide se
    c'e' stato un incrocio:

      - BUY  : ieri la media breve era sotto (o uguale) alla lunga,
               oggi e' sopra  -> incrocio rialzista
      - SELL : ieri la media breve era sopra (o uguale) alla lunga,
               oggi e' sotto  -> incrocio ribassista
      - NONE : nessun incrocio (o dati non ancora sufficienti)

    Restituisce una coppia (segnale, contesto), dove 'contesto' e' un
    dizionario con i numeri usati per decidere: e' esattamente quello che
    finira' salvato nel database (logging contestuale).
    """
    if len(media_breve) < 2 or len(media_lunga) < 2:
        return "NONE", {}

    breve_oggi = media_breve.iloc[-1]
    breve_ieri = media_breve.iloc[-2]
    lunga_oggi = media_lunga.iloc[-1]
    lunga_ieri = media_lunga.iloc[-2]

    # Se ieri una delle due medie era ancora NaN (dati insufficienti),
    # non possiamo dire se ci sia stato un incrocio: meglio non decidere.
    if pd.isna(breve_ieri) or pd.isna(lunga_ieri) or pd.isna(breve_oggi) or pd.isna(lunga_oggi):
        return "NONE", {
            "media_breve_oggi": None if pd.isna(breve_oggi) else breve_oggi,
            "media_lunga_oggi": None if pd.isna(lunga_oggi) else lunga_oggi,
        }

    contesto = {
        "media_breve_ieri": breve_ieri,
        "media_lunga_ieri": lunga_ieri,
        "media_breve_oggi": breve_oggi,
        "media_lunga_oggi": lunga_oggi,
    }

    era_sotto_o_uguale = breve_ieri <= lunga_ieri
    e_sopra = breve_oggi > lunga_oggi

    era_sopra_o_uguale = breve_ieri >= lunga_ieri
    e_sotto = breve_oggi < lunga_oggi

    if era_sotto_o_uguale and e_sopra:
        return "BUY", contesto
    elif era_sopra_o_uguale and e_sotto:
        return "SELL", contesto
    else:
        return "NONE", contesto


# ---------------------------------------------------------------------------
# PARTE CHE PARLA CON ALPACA (dati di mercato veri)
# ---------------------------------------------------------------------------

def scarica_prezzi_di_chiusura(simbolo=SIMBOLO, giorni=GIORNI_STORIA_DA_RICHIEDERE):
    """
    Chiede ad Alpaca le barre giornaliere (candele) degli ultimi 'giorni'
    giorni di calendario per 'simbolo', e restituisce solo i prezzi di
    chiusura, in ordine dal piu' vecchio al piu' recente, come pandas Series.

    feed=DataFeed.IEX: gli account Alpaca gratuiti hanno accesso ai dati
    della borsa IEX (gratuiti), non ai dati "consolidati" di tutte le borse
    (SIP, a pagamento). Se non lo specifichiamo, alcune versioni della
    libreria possono provare a chiedere dati che il tuo piano gratuito non
    include, e Alpaca risponderebbe con un errore di sottoscrizione.
    """
    adesso_utc = datetime.now(timezone.utc)
    inizio = adesso_utc - timedelta(days=giorni)

    richiesta = StockBarsRequest(
        symbol_or_symbols=simbolo,
        timeframe=TimeFrame.Day,
        start=inizio,
        feed=DataFeed.IEX,
    )

    barre = client_dati.get_stock_bars(richiesta)

    # barre.df e' una tabella (pandas DataFrame) con un indice a due livelli
    # (simbolo, data). La estraiamo per il nostro simbolo e prendiamo solo
    # la colonna "close" (prezzo di chiusura).
    prezzi = barre.df.xs(simbolo).sort_index()["close"]
    return prezzi


# ---------------------------------------------------------------------------
# PROGRAMMA PRINCIPALE
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    inizializza_database()

    print(f"Scarico i prezzi storici di {SIMBOLO} da Alpaca...")
    prezzi = scarica_prezzi_di_chiusura()
    print(f"Ricevute {len(prezzi)} candele giornaliere.\n")

    media_breve, media_lunga = calcola_medie_mobili(prezzi)
    segnale, contesto = decidi_segnale(media_breve, media_lunga)

    prezzo_attuale = float(prezzi.iloc[-1]) if len(prezzi) > 0 else None

    print(f"=== Segnale per {SIMBOLO}: {segnale} ===")
    if prezzo_attuale is not None:
        print(f"Ultimo prezzo di chiusura: {prezzo_attuale:>10,.2f} $")
    if contesto.get("media_breve_oggi") is not None:
        print(f"Media mobile a {PERIODO_BREVE} giorni (oggi):  {contesto['media_breve_oggi']:>10,.2f}")
    if contesto.get("media_lunga_oggi") is not None:
        print(f"Media mobile a {PERIODO_LUNGO} giorni (oggi):  {contesto['media_lunga_oggi']:>10,.2f}")

    if segnale == "NONE" and not contesto.get("media_breve_ieri"):
        print(
            "\n(Nota: se non vedi le medie di ieri qui sopra, vuol dire che "
            "non abbiamo ancora abbastanza giorni di storico per calcolare "
            "la media lunga: non e' un errore, serve solo aspettare qualche "
            "giorno di dati in piu', oppure va bene cosi' per ora.)"
        )

    salva_segnale(SIMBOLO, segnale, prezzo_attuale, contesto, PERIODO_BREVE, PERIODO_LUNGO)

    mostra_segnali()
