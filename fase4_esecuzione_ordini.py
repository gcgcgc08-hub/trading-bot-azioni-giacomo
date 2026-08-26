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

Aggiunte di questa versione (watchdog, kill switch, notifiche)
------------------------------------------------------------------
  4. KILL SWITCH MANUALE (kill_switch.py): prima di fare qualsiasi cosa,
     il bot controlla se esiste un file "STOP.txt" nella cartella. Se
     esiste, si ferma subito senza guardare nemmeno il conto. Per fermare
     il bot in qualsiasi momento basta creare quel file.

  5. BATTITO CARDIACO / WATCHDOG (registra_battito_cuore in database.py):
     ad ogni esecuzione, il bot registra nel database come e' andata
     (ok / errore / fermato per circuit breaker / fermato per kill switch).
     Non e' ancora un "controllore" automatico che ti avvisa da solo se il
     bot smette di far sentire il battito - quello arrivera' con Fase 7,
     quando il bot girera' in un ciclo continuo - ma la base dati c'e' gia'.

  6. NOTIFICHE VERE (notifiche.py): quando succede qualcosa di importante
     (circuit breaker, ordine inviato, ordine fallito, errore imprevisto,
     kill switch attivo), il bot prova a mandarti un messaggio Telegram.
     Se le notifiche non sono ancora configurate, il bot continua a
     funzionare comunque: le notifiche sono un extra utile, non devono mai
     poter rompere la logica di trading.

  Anche tutto il corpo dello script e' avvolto in un try/except: se
  succede un errore che non avevamo previsto, il bot lo registra (battito
  "errore" + notifica) invece di sparire in silenzio - importante perche'
  un giorno girera' da solo, senza nessuno davanti allo schermo.

Aggiunte della Fase 8: take profit frazionato e analisi multi-timeframe
--------------------------------------------------------------------------
  7. TAKE PROFIT FRAZIONATO (take_profit.py, tabelle posizioni_aperte e
     take_profit_eseguiti in database.py): quando compriamo, registriamo
     la posizione (quantita' e prezzo di carico). Ad ogni esecuzione,
     INDIPENDENTEMENTE dal segnale della strategia di quel giorno,
     controlliamo se il guadagno ha raggiunto una nuova soglia (Passo
     2bis): in quel caso vendiamo un pezzo della posizione, invece di
     aspettare solo il segnale SELL per chiudere tutto in un colpo solo.

  8. ANALISI MULTI-TIMEFRAME (fase8_multi_timeframe.py): prima di
     eseguire un BUY, oltre al filtro di liquidita', controlliamo anche
     il trend delle candele ORARIE (non solo quelle giornaliere): se il
     brevissimo termine e' chiaramente in discesa, contraddicendo il
     segnale giornaliero, aspettiamo invece di comprare subito. Si
     applica solo al BUY, mai al SELL (una posizione aperta deve poter
     essere sempre chiusa), e non blocca mai per "dati insufficienti" -
     solo quando il trend orario e' chiaramente contrario.

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
    scarica_volume_medio,
    scarica_prezzi_orari,
    calcola_medie_mobili,
    decidi_segnale,
    api_key,
    secret_key,
)
from risk_management import (
    calcola_stop_loss,
    calcola_dimensione_posizione,
    controlla_limite_perdita_giornaliera,
    applica_limite_concentrazione,
    CONCENTRAZIONE_MASSIMA_PERCENTUALE,
    verifica_liquidita_sufficiente,
    VOLUME_MEDIO_MINIMO_AZIONI,
)
from database import (
    inizializza_database,
    salva_snapshot_conto,
    primo_valore_portafoglio_di_oggi,
    salva_segnale,
    client_order_id_gia_usato,
    salva_ordine,
    mostra_ordini,
    registra_battito_cuore,
    apri_posizione,
    posizione_aperta_di,
    chiudi_posizione,
    livelli_take_profit_eseguiti,
    salva_take_profit_eseguito,
    salva_controllo_multi_timeframe,
)
from kill_switch import kill_switch_attivo
from notifiche import invia_notifica
from take_profit import (
    calcola_guadagno_percentuale,
    trova_livelli_da_eseguire,
    calcola_quantita_da_vendere,
)
from fase8_multi_timeframe import (
    calcola_trend_orario,
    conferma_segnale_BUY,
    ORE_STORIA_DA_RICHIEDERE as ORE_STORIA_ORARIA,
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

    # ----- Passo 0: kill switch manuale -----
    # Prima di fare qualsiasi altra cosa, controlliamo se esiste il file
    # STOP.txt: se c'e', qualcuno (tu, o il bot stesso in futuro) ha deciso
    # di fermare tutto. Non guardiamo nemmeno il conto o il mercato.
    if kill_switch_attivo():
        messaggio = "Kill switch attivo (file STOP.txt presente): il bot non esegue nulla."
        print(f"\n{messaggio}")
        registra_battito_cuore("fermato_kill_switch", messaggio)
        invia_notifica(f"Bot FERMATO: {messaggio}")
        raise SystemExit(0)

    # Tutto il resto e' avvolto in un try/except: se succede QUALSIASI cosa
    # di inaspettato (un errore che non avevamo previsto), vogliamo che il
    # bot lo registri (battito cuore "errore" + notifica), invece di sparire
    # nel nulla senza che tu te ne accorga. Questo diventa importante
    # soprattutto quando il bot girera' da solo H24 (Fase 7), senza
    # nessuno che guarda lo schermo in quel momento.
    try:
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
            messaggio = (
                f"CIRCUIT BREAKER ATTIVATO su {SIMBOLO}: perdita di oggi "
                f"{perdita_oggi * 100:.2f}%. Il bot non piazza nuovi ordini oggi."
            )
            print(f"\n{messaggio}")
            registra_battito_cuore("fermato_circuit_breaker", messaggio)
            invia_notifica(messaggio)
            raise SystemExit(0)

        if not orologio.is_open:
            print("\nIl mercato e' chiuso in questo momento: non ha senso piazzare ordini adesso. Mi fermo qui.")
            registra_battito_cuore("ok", "Mercato chiuso, nessuna azione.")
            raise SystemExit(0)

        # ----- Passo 2: calcolo il segnale della strategia -----
        print(f"\n=== Passo 2: calcolo il segnale per {SIMBOLO} ===")

        prezzi = scarica_prezzi_di_chiusura()
        media_breve, media_lunga = calcola_medie_mobili(prezzi)
        segnale, contesto = decidi_segnale(media_breve, media_lunga)
        prezzo_attuale = float(prezzi.iloc[-1])

        salva_segnale(SIMBOLO, segnale, prezzo_attuale, contesto, PERIODO_BREVE, PERIODO_LUNGO)
        print(f"Segnale: {segnale} (prezzo attuale: {prezzo_attuale:,.2f} $)")

        # ----- Passo 2bis: take profit frazionato (Fase 8) -----
        # Questo controllo e' INDIPENDENTE dal segnale della strategia qui
        # sopra: anche in un giorno "NONE" (la maggioranza dei giorni),
        # se abbiamo gia' una posizione aperta e tracciata (vedi
        # apri_posizione() piu' in basso), controlliamo se il suo guadagno
        # ha raggiunto una nuova soglia di take profit, e in quel caso
        # vendiamo un pezzo. E' avvolto in un try/except tutto suo: un
        # problema qui non deve mai impedire al resto dello script di
        # valutare comunque il segnale della strategia.
        posizione_locale = posizione_aperta_di(SIMBOLO)

        if posizione_locale is not None:
            try:
                print(f"\n=== Passo 2bis: controllo take profit frazionato su {SIMBOLO} ===")

                guadagno = calcola_guadagno_percentuale(prezzo_attuale, posizione_locale["prezzo_entrata"])
                gia_eseguiti = livelli_take_profit_eseguiti(posizione_locale["id"])
                livelli_da_eseguire = trova_livelli_da_eseguire(guadagno, gia_eseguiti)

                print(
                    f"Prezzo di carico: {posizione_locale['prezzo_entrata']:,.2f} $ | "
                    f"Guadagno attuale: {guadagno * 100:.2f}% | "
                    f"Livelli gia' eseguiti: {sorted(gia_eseguiti) if gia_eseguiti else 'nessuno'}"
                )

                if not livelli_da_eseguire:
                    print("Nessun nuovo livello di take profit raggiunto.")
                else:
                    for indice_livello in livelli_da_eseguire:
                        posizioni_attuali_tp = esegui_con_retry(
                            lambda: client_trading.get_all_positions(),
                            descrizione="lettura posizioni per il take profit",
                        )
                        posizione_alpaca = next((p for p in posizioni_attuali_tp if p.symbol == SIMBOLO), None)
                        quantita_posseduta = int(float(posizione_alpaca.qty)) if posizione_alpaca else 0

                        if quantita_posseduta <= 0:
                            print("Non possediamo piu' azioni da vendere: mi fermo qui con il take profit.")
                            break

                        quantita_tp = calcola_quantita_da_vendere(
                            indice_livello, posizione_locale["quantita_originale"], quantita_posseduta
                        )

                        if quantita_tp <= 0:
                            print(f"Livello {indice_livello}: la frazione calcolata e' 0 azioni, salto.")
                            continue

                        client_order_id_tp = f"{SIMBOLO}-TP{indice_livello}-POS{posizione_locale['id']}"
                        if client_order_id_gia_usato(client_order_id_tp):
                            # Secondo scudo di idempotenza, stessa idea degli ordini normali.
                            continue

                        print(
                            f"Livello {indice_livello} raggiunto (guadagno {guadagno * 100:.2f}%): "
                            f"vendo {quantita_tp} azioni di {SIMBOLO}."
                        )

                        richiesta_tp = MarketOrderRequest(
                            symbol=SIMBOLO,
                            qty=quantita_tp,
                            side=OrderSide.SELL,
                            time_in_force=TimeInForce.DAY,
                            client_order_id=client_order_id_tp,
                        )

                        try:
                            ordine_tp = esegui_con_retry(
                                lambda: client_trading.submit_order(richiesta_tp),
                                descrizione=f"invio ordine take profit livello {indice_livello}",
                            )
                            salva_ordine(
                                SIMBOLO, "SELL", quantita_tp, prezzo_attuale, client_order_id_tp,
                                "inviato", f"take profit livello {indice_livello}",
                            )
                            salva_take_profit_eseguito(posizione_locale["id"], indice_livello, quantita_tp, prezzo_attuale)
                            registra_battito_cuore(
                                "ok", f"Take profit livello {indice_livello} su {SIMBOLO}: vendute {quantita_tp} azioni."
                            )
                            invia_notifica(
                                f"Take profit su {SIMBOLO} (livello {indice_livello}): vendute {quantita_tp} "
                                f"azioni @ ~{prezzo_attuale:,.2f}$ (guadagno {guadagno * 100:.1f}%)."
                            )
                        except Exception as errore_tp:
                            print(f"Non sono riuscito a inviare l'ordine di take profit: {errore_tp}")
                            salva_ordine(
                                SIMBOLO, "SELL", quantita_tp, prezzo_attuale, client_order_id_tp,
                                "errore", str(errore_tp),
                            )
                            registra_battito_cuore(
                                "errore", f"Take profit livello {indice_livello} fallito su {SIMBOLO}: {errore_tp}"
                            )
                            invia_notifica(f"ERRORE: take profit su {SIMBOLO} (livello {indice_livello}) fallito: {errore_tp}")
            except Exception as errore_take_profit:
                # Il take profit e' un raffinamento, non il cuore della logica
                # di trading: un suo errore non deve mai far crashare tutto lo
                # script prima ancora di valutare il segnale della strategia.
                print(f"\nAvviso: il controllo del take profit frazionato ha avuto un problema: {errore_take_profit}")
                registra_battito_cuore("errore", f"Take profit su {SIMBOLO} fallito: {errore_take_profit}")
                invia_notifica(f"ERRORE: controllo take profit su {SIMBOLO} fallito: {errore_take_profit}")

        if segnale == "NONE":
            print("\nNessun incrocio oggi: non piazzo nessun ordine. Va bene cosi'.")
            registra_battito_cuore("ok", f"Nessun incrocio su {SIMBOLO}, nessuna azione.")
            raise SystemExit(0)

        # ----- Passo 3: controllo idempotenza e preparo l'ordine -----
        client_order_id = genera_client_order_id(SIMBOLO, segnale)

        if client_order_id_gia_usato(client_order_id):
            print(
                f"\nUn ordine con questo identificativo ('{client_order_id}') e' gia' "
                "stato registrato oggi: non lo rimando, per evitare un ordine doppio "
                "(idempotenza)."
            )
            registra_battito_cuore("ok", f"Segnale {segnale} gia' gestito oggi (idempotenza), nessuna azione.")
            raise SystemExit(0)

        print(f"\n=== Passo 3: preparo l'ordine ({segnale}) ===")

        if segnale == "BUY":
            # FASE 8: prima di qualsiasi calcolo di quantita', controlliamo
            # che il titolo si scambi abbastanza da poterlo comprare in
            # sicurezza (filtro di liquidita' minima). Non ha senso
            # applicarlo anche al ramo SELL: se abbiamo gia' una posizione
            # aperta vogliamo sempre poterla chiudere, anche se la
            # liquidita' del titolo fosse calata nel frattempo.
            volume_medio = esegui_con_retry(
                lambda: scarica_volume_medio(SIMBOLO),
                descrizione="lettura volume medio per il filtro di liquidita'",
            )

            if not verifica_liquidita_sufficiente(volume_medio):
                print(
                    f"\nSegnale BUY ma {SIMBOLO} ha un volume medio di {volume_medio:,.0f} "
                    f"azioni/giorno, sotto la soglia minima di {VOLUME_MEDIO_MINIMO_AZIONI:,} "
                    "azioni/giorno: non lo compro (filtro di liquidita' minima)."
                )
                salva_ordine(
                    SIMBOLO, segnale, 0, prezzo_attuale, client_order_id, "saltato",
                    f"liquidita' insufficiente (volume medio {volume_medio:,.0f}/giorno)",
                )
                registra_battito_cuore("ok", f"Segnale BUY ma liquidita' insufficiente su {SIMBOLO}, nessuna azione.")
                raise SystemExit(0)

            # FASE 8: analisi multi-timeframe - oltre al segnale
            # giornaliero, controlliamo anche il trend orario di
            # brevissimo termine come "secondo parere" prima di comprare
            # (stessa logica del filtro di liquidita' qui sopra: si
            # applica solo al BUY, mai al SELL, per poter sempre chiudere
            # una posizione gia' aperta).
            prezzi_orari = esegui_con_retry(
                lambda: scarica_prezzi_orari(SIMBOLO, ore=ORE_STORIA_ORARIA),
                descrizione="lettura prezzi orari per l'analisi multi-timeframe",
            )
            trend_orario = calcola_trend_orario(prezzi_orari)
            segnale_confermato = conferma_segnale_BUY(trend_orario)
            salva_controllo_multi_timeframe(
                SIMBOLO, trend_orario, "confermato" if segnale_confermato else "bloccato"
            )

            if not segnale_confermato:
                print(
                    f"\nSegnale BUY ma il trend orario di brevissimo termine e' in "
                    f"'{trend_orario}': non compro, aspetto una conferma migliore "
                    "(analisi multi-timeframe)."
                )
                salva_ordine(
                    SIMBOLO, segnale, 0, prezzo_attuale, client_order_id, "saltato",
                    f"trend orario non conferma il segnale (trend: {trend_orario})",
                )
                registra_battito_cuore(
                    "ok", f"Segnale BUY ma trend orario '{trend_orario}' su {SIMBOLO}, nessuna azione."
                )
                raise SystemExit(0)

            print(f"Trend orario di brevissimo termine: '{trend_orario}' -> segnale confermato.")

            stop_loss = calcola_stop_loss(prezzo_attuale)
            sizing = calcola_dimensione_posizione(valore_portafoglio, prezzo_attuale, stop_loss)
            quantita_da_stop_loss = sizing["numero_azioni"]

            # FASE 8: secondo tetto, indipendente dal position sizing basato
            # sul rischio - non piu' del 25% (di default) del portafoglio su
            # un solo titolo, anche se il calcolo del rischio permetterebbe
            # di comprarne di piu'.
            limite_concentrazione = applica_limite_concentrazione(
                quantita_da_stop_loss, prezzo_attuale, valore_portafoglio
            )
            quantita = limite_concentrazione["numero_azioni"]
            costo_totale = quantita * prezzo_attuale

            print(
                f"Stop loss teorico: {stop_loss:,.2f} $ | Azioni suggerite dal rischio: "
                f"{quantita_da_stop_loss} | Azioni finali: {quantita} | Costo stimato: {costo_totale:,.2f} $"
            )
            if limite_concentrazione["ridotto_per_concentrazione"]:
                print(
                    f"(Ridotte da {quantita_da_stop_loss} a {quantita}: il position sizing basato "
                    f"sullo stop loss avrebbe superato il tetto del "
                    f"{CONCENTRAZIONE_MASSIMA_PERCENTUALE * 100:.0f}% del portafoglio su un solo titolo.)"
                )

            if quantita <= 0:
                print("\nIl calcolo dice 0 azioni (capitale troppo piccolo per questo prezzo, o tetto di concentrazione troppo basso): non piazzo nulla.")
                salva_ordine(SIMBOLO, segnale, 0, prezzo_attuale, client_order_id, "saltato", "position sizing/concentrazione = 0 azioni")
                registra_battito_cuore("ok", "Segnale BUY ma quantita' finale 0 azioni, nessuna azione.")
                raise SystemExit(0)

            if costo_totale > liquidita:
                print(
                    f"\nAttenzione: servirebbero {costo_totale:,.2f} $ ma hai solo "
                    f"{liquidita:,.2f} $ di liquidita' disponibile. Non piazzo l'ordine per sicurezza."
                )
                salva_ordine(SIMBOLO, segnale, quantita, prezzo_attuale, client_order_id, "saltato", "liquidita' insufficiente")
                registra_battito_cuore("ok", "Segnale BUY ma liquidita' insufficiente, nessuna azione.")
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
                registra_battito_cuore("ok", "Segnale SELL ma nessuna posizione da chiudere, nessuna azione.")
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
            registra_battito_cuore("ok", f"Ordine {segnale} x{quantita} {SIMBOLO} inviato.")
            invia_notifica(
                f"Ordine {segnale} su {SIMBOLO}: {quantita} azioni @ ~{prezzo_attuale:,.2f}$ "
                f"inviato (stato Alpaca: {ordine_inviato.status})."
            )

            # FASE 8: iniziamo a tracciare questa posizione per il take
            # profit frazionato (Passo 2bis), oppure smettiamo di tracciarla
            # se questo era il segnale SELL che ha chiuso tutto.
            if segnale == "BUY":
                apri_posizione(SIMBOLO, quantita, prezzo_attuale)
            elif posizione_locale is not None:
                chiudi_posizione(posizione_locale["id"])
        except Exception as errore:
            print(f"\nNon sono riuscito a inviare l'ordine: {errore}")
            salva_ordine(SIMBOLO, segnale, quantita, prezzo_attuale, client_order_id, "errore", str(errore))
            registra_battito_cuore("errore", f"Invio ordine {segnale} {SIMBOLO} fallito: {errore}")
            invia_notifica(f"ERRORE: invio ordine {segnale} su {SIMBOLO} fallito: {errore}")

        # ----- Passo 5: storico ordini + riconciliazione -----
        mostra_ordini()

        print("\n=== Passo 5: riconciliazione posizioni ===")
        mostra_riconciliazione()

    except SystemExit:
        # Le uscite "volute" (raise SystemExit(0) qui sopra) non sono errori:
        # le lasciamo passare senza toccarle.
        raise
    except Exception as errore_imprevisto:
        messaggio = f"Errore imprevisto nel bot: {errore_imprevisto}"
        print(f"\n{messaggio}")
        registra_battito_cuore("errore", messaggio)
        invia_notifica(f"ERRORE IMPREVISTO nel bot: {errore_imprevisto}")
        raise
