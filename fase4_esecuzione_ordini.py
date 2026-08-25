"""
FASE 4 - Dal segnale all'ordine vero (paper trading), con affidabilita'
=========================================================================

Questo e' il pezzo che collega tutto quello che abbiamo costruito finora:

  Fase 1 (conto/calendario) + Fase 2 (risk management) + Fase 3 (segnale)
                              |
                              v
              QUESTO SCRIPT: decide SE e QUANTO comprare/vendere,
              e prova davvero a mandare l'ordine ad Alpaca (paper = finto)

Rispetto ai requisiti che avevi chiesto fin dall'inizio, qui dentro
implementiamo la parte "Affidabilita'" della roadmap:

  1. IDEMPOTENZA DEGLI ORDINI: ad ogni ordine associamo un "client_order_id"
     costruito in modo deterministico (simbolo + segnale + data di oggi).
     Se per sbaglio lanci lo script due volte nello stesso giorno con lo
     stesso segnale, il bot se ne accorge (controllo locale nel database)
     e NON manda un secondo ordine identico. Alpaca stessa, in aggiunta,
     rifiuterebbe comunque un secondo ordine con lo stesso client_order_id:
     e' una doppia sicurezza.

  2. GESTIONE ERRORI DI RETE: le chiamate verso Alpaca (che passano per
     internet) possono fallire per un problema temporaneo di connessione,
     non perche' qualcosa sia sbagliato. La funzione esegui_con_retry()
     ritenta automaticamente qualche volta, aspettando un po' di piu' tra
     un tentativo e l'altro, prima di arrendersi davvero.

  3. RICONCILIAZIONE DELLE POSIZIONI: alla fine confrontiamo quello che
     Alpaca dice di avere in portafoglio con quello che ci aspettiamo,
     cosi' notiamo subito se qualcosa non torna.

Cose importanti da sapere su questo script
--------------------------------------------
- Per ora gestisce UN SOLO titolo alla volta (quello scelto in
  fase3_strategia_sma.py, cioe' SIMBOLO).
- Un segnale SELL chiude solo una posizione che gia' possediamo: non
  apriamo posizioni "allo scoperto" (vendere azioni che non abbiamo,
  scommettendo che scendano) - e' un discorso piu' avanzato che lasciamo
  fuori per ora.
- PRIMA di guardare il segnale della strategia, controlliamo il circuit
  breaker (Fase 2): se abbiamo gia' perso troppo oggi, il bot si ferma e
  non piazza nessun nuovo ordine, punto.
- E' ancora tutto in paper trading: nessun soldo vero si muove.
"""

import time
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from fase3_strategia_sma import (
    SIMBOLO,
    PERIODO_BREVE,
    PERIODO_LUNGO,
    scarica_prezzi_di_chiusura,
    calcola_medie_mobili,
    decidi_segnale,
    api_key,
    secret_key,
)
from risk_management import (
    calcola_stop_loss,
    calcola_dimensione_posizione,
    controlla_limite_perdita_giornaliera,
)
from database import (
    inizializza_database,
    salva_snapshot_conto,
    primo_valore_portafoglio_di_oggi,
    salva_segnale,
    client_order_id_gia_usato,
    salva_ordine,
    mostra_ordini,
)

# Le chiavi sono gia' state lette da fase3_strategia_sma (che ha gia'
# richiamato load_dotenv() e controllato che non fossero vuote): qui
# creiamo solo un secondo client, quello per fare TRADING (comprare/
# vendere/leggere posizioni), diverso dal client_dati usato per i prezzi.
client_trading = TradingClient(api_key, secret_key, paper=True)


# ---------------------------------------------------------------------------
# AFFIDABILITA': RETRY SU ERRORI DI RETE
# ---------------------------------------------------------------------------

def esegui_con_retry(funzione, tentativi_massimi=3, attesa_iniziale_secondi=2, descrizione="operazione"):
    """
    Esegue 'funzione' (una funzione senza argomenti, es. una lambda) e la
    ritenta in caso di errore, aspettando sempre un po' di piu' tra un
    tentativo e l'altro (backoff: 2s, poi 4s, poi 8s...).

    Se anche l'ULTIMO tentativo fallisce, rilancia l'errore originale:
    non vogliamo nascondere un problema vero, vogliamo solo dargli una
    seconda (e terza) possibilita' nel caso fosse temporaneo.
    """
    attesa = attesa_iniziale_secondi
    for tentativo in range(1, tentativi_massimi + 1):
        try:
            return funzione()
        except Exception as errore:
            if tentativo == tentativi_massimi:
                print(f"'{descrizione}' fallita dopo {tentativi_massimi} tentativi: {errore}")
                raise
            print(f"Tentativo {tentativo} di '{descrizione}' fallito ({errore}). Riprovo tra {attesa}s...")
            time.sleep(attesa)
            attesa *= 2


# ---------------------------------------------------------------------------
# IDEMPOTENZA: UN ID UNIVOCO E DETERMINISTICO PER OGNI ORDINE
# ---------------------------------------------------------------------------

def genera_client_order_id(simbolo, segnale):
    """
    Costruisce un identificativo dell'ordine che e' SEMPRE lo stesso se lo
    calcoliamo di nuovo con lo stesso simbolo, segnale e giorno.

    Esempio: "AAPL-BUY-20260825". Se lo script gira due volte lo stesso
    giorno con lo stesso segnale BUY su AAPL, otteniamo lo stesso ID, e
    quindi possiamo accorgercene ed evitare un ordine doppio.
    """
    oggi = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{simbolo}-{segnale}-{oggi}"


# ---------------------------------------------------------------------------
# RICONCILIAZIONE: CONFRONTO TRA "QUELLO CHE ALPACA HA DAVVERO" E LE ATTESE
# ---------------------------------------------------------------------------

def mostra_riconciliazione():
    """
    Chiede ad Alpaca l'elenco vero delle posizioni aperte in questo momento
    e lo stampa. Non modifica nulla: e' solo un controllo di sanita', per
    accorgerci in fretta se il nostro database locale e la realta' su
    Alpaca iniziano a non corrispondere piu'.
    """
    posizioni = esegui_con_retry(
        lambda: client_trading.get_all_positions(),
        descrizione="lettura posizioni per riconciliazione",
    )
    if not posizioni:
        print("Alpaca dice: nessuna posizione aperta al momento.")
        return
    print("Posizioni aperte secondo Alpaca in questo momento:")
    for posizione in posizioni:
        print(
            f"  {posizione.symbol}: {posizione.qty} azioni, "
            f"valore di mercato {float(posizione.market_value):,.2f} $"
        )


# ---------------------------------------------------------------------------
# PROGRAMMA PRINCIPALE
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    inizializza_database()

    # ----- Passo 1: leggo il conto e controllo il circuit breaker -----
    print("=== Passo 1: leggo il conto e controllo il limite di perdita giornaliera ===")

    account = esegui_con_retry(lambda: client_trading.get_account(), descrizione="lettura conto")
    orologio = esegui_con_retry(lambda: client_trading.get_clock(), descrizione="lettura calendario di mercato")

    liquidita = float(account.cash)
    valore_portafoglio = float(account.portfolio_value)

    # Salviamo uno snapshot adesso: se e' il primo di oggi, diventa anche il
    # nostro "valore di inizio giornata" per il circuit breaker.
    salva_snapshot_conto(liquidita, valore_portafoglio, orologio.is_open)
    valore_inizio_giornata = primo_valore_portafoglio_di_oggi()

    deve_fermarsi, perdita_oggi = controlla_limite_perdita_giornaliera(
        valore_inizio_giornata, valore_portafoglio
    )
    print(
        f"Portafoglio: inizio giornata {valore_inizio_giornata:,.2f} $, "
        f"adesso {valore_portafoglio:,.2f} $ (perdita di oggi: {perdita_oggi * 100:.2f}%)"
    )

    if deve_fermarsi:
        print(
            "\nCIRCUIT BREAKER ATTIVATO: la perdita di oggi ha superato la soglia. "
            "Il bot NON piazza nuovi ordini oggi, in attesa di una revisione manuale."
        )
        raise SystemExit(0)

    if not orologio.is_open:
        print("\nIl mercato e' chiuso in questo momento: non ha senso piazzare ordini adesso. Mi fermo qui.")
        raise SystemExit(0)

    # ----- Passo 2: calcolo il segnale della strategia -----
    print(f"\n=== Passo 2: calcolo il segnale per {SIMBOLO} ===")

    prezzi = scarica_prezzi_di_chiusura()
    media_breve, media_lunga = calcola_medie_mobili(prezzi)
    segnale, contesto = decidi_segnale(media_breve, media_lunga)
    prezzo_attuale = float(prezzi.iloc[-1])

    salva_segnale(SIMBOLO, segnale, prezzo_attuale, contesto, PERIODO_BREVE, PERIODO_LUNGO)
    print(f"Segnale: {segnale} (prezzo attuale: {prezzo_attuale:,.2f} $)")

    if segnale == "NONE":
        print("\nNessun incrocio oggi: non piazzo nessun ordine. Va bene cosi'.")
        raise SystemExit(0)

    # ----- Passo 3: controllo idempotenza e preparo l'ordine -----
    client_order_id = genera_client_order_id(SIMBOLO, segnale)

    if client_order_id_gia_usato(client_order_id):
        print(
            f"\nUn ordine con questo identificativo ('{client_order_id}') e' gia' "
            "stato registrato oggi: non lo rimando, per evitare un ordine doppio "
            "(idempotenza)."
        )
        raise SystemExit(0)

    print(f"\n=== Passo 3: preparo l'ordine ({segnale}) ===")

    if segnale == "BUY":
        stop_loss = calcola_stop_loss(prezzo_attuale)
        sizing = calcola_dimensione_posizione(valore_portafoglio, prezzo_attuale, stop_loss)
        quantita = sizing["numero_azioni"]

        print(
            f"Stop loss teorico: {stop_loss:,.2f} $ | Azioni da comprare: {quantita} | "
            f"Costo stimato: {sizing['costo_totale']:,.2f} $"
        )

        if quantita <= 0:
            print("\nIl position sizing dice 0 azioni (capitale troppo piccolo per questo prezzo/rischio): non piazzo nulla.")
            salva_ordine(SIMBOLO, segnale, 0, prezzo_attuale, client_order_id, "saltato", "position sizing = 0 azioni")
            raise SystemExit(0)

        if sizing["costo_totale"] > liquidita:
            print(
                f"\nAttenzione: servirebbero {sizing['costo_totale']:,.2f} $ ma hai solo "
                f"{liquidita:,.2f} $ di liquidita' disponibile. Non piazzo l'ordine per sicurezza."
            )
            salva_ordine(SIMBOLO, segnale, quantita, prezzo_attuale, client_order_id, "saltato", "liquidita' insufficiente")
            raise SystemExit(0)

        richiesta_ordine = MarketOrderRequest(
            symbol=SIMBOLO,
            qty=quantita,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

    else:  # segnale == "SELL"
        posizioni_attuali = esegui_con_retry(
            lambda: client_trading.get_all_positions(),
            descrizione="lettura posizioni prima della vendita",
        )
        posizione_esistente = next((p for p in posizioni_attuali if p.symbol == SIMBOLO), None)

        if posizione_esistente is None:
            print(f"\nSegnale SELL ma non ho nessuna posizione aperta su {SIMBOLO}: non c'e' nulla da vendere.")
            salva_ordine(SIMBOLO, segnale, 0, prezzo_attuale, client_order_id, "saltato", "nessuna posizione da chiudere")
            raise SystemExit(0)

        quantita = int(float(posizione_esistente.qty))
        print(f"Chiudo la posizione esistente: {quantita} azioni di {SIMBOLO}.")

        richiesta_ordine = MarketOrderRequest(
            symbol=SIMBOLO,
            qty=quantita,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

    # ----- Passo 4: invio l'ordine (con retry automatico) -----
    print("\n=== Passo 4: invio l'ordine ad Alpaca ===")

    try:
        ordine_inviato = esegui_con_retry(
            lambda: client_trading.submit_order(richiesta_ordine),
            descrizione=f"invio ordine {segnale} {quantita} {SIMBOLO}",
        )
        print(f"Ordine inviato! ID Alpaca: {ordine_inviato.id}, stato: {ordine_inviato.status}")
        salva_ordine(SIMBOLO, segnale, quantita, prezzo_attuale, client_order_id, "inviato", str(ordine_inviato.status))
    except Exception as errore:
        print(f"\nNon sono riuscito a inviare l'ordine: {errore}")
        salva_ordine(SIMBOLO, segnale, quantita, prezzo_attuale, client_order_id, "errore", str(errore))

    # ----- Passo 5: storico ordini + riconciliazione -----
    mostra_ordini()

    print("\n=== Passo 5: riconciliazione posizioni ===")
    mostra_riconciliazione()
