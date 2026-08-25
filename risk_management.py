"""
FASE 2 - Risk management: quanto rischiare, dove mettere lo stop, quando fermarsi
===================================================================================

Le funzioni qui dentro rispondono a tre domande fondamentali, PRIMA ancora
di pensare a quale azione comprare o quando comprarla:

  1. Se compro, a che prezzo metto lo stop loss?
     -> calcola_stop_loss()
  2. Quante azioni posso permettermi di comprare, sapendo dove metto lo
     stop loss e quanto voglio rischiare al massimo?
     -> calcola_dimensione_posizione()
  3. Ho perso troppo oggi? Il bot si deve fermare?
     -> controlla_limite_perdita_giornaliera()

Questo modulo non compra o vende nulla da solo: prepara i "numeri giusti"
che la strategia vera (Fase 3) usera' per decidere cosa fare.
"""


# ---------------------------------------------------------------------------
# 1) STOP LOSS
# ---------------------------------------------------------------------------

# 1.5%, a meta' tra l'1% e il 2% che avevi indicato tu
STOP_LOSS_PERCENTUALE = 0.015


def calcola_stop_loss(prezzo_entrata, percentuale=STOP_LOSS_PERCENTUALE):
    """
    Calcola a che prezzo mettere lo stop loss per una posizione LONG
    (cioe' quando compri un'azione sperando che il prezzo salga).

    Esempio: se compri a 100$ con uno stop loss dell'1.5%, lo stop
    scatta (cioe' vendi per limitare la perdita) se il prezzo scende
    a 98.50$.
    """
    return prezzo_entrata * (1 - percentuale)


# ---------------------------------------------------------------------------
# 2) DIMENSIONE DELLA POSIZIONE (position sizing)
# ---------------------------------------------------------------------------

# Rischia al massimo l'1% del capitale totale su un singolo trade
RISCHIO_PER_TRADE_PERCENTUALE = 0.01


def calcola_dimensione_posizione(
    capitale_totale,
    prezzo_entrata,
    prezzo_stop_loss,
    rischio_percentuale=RISCHIO_PER_TRADE_PERCENTUALE,
):
    """
    Calcola quante azioni comprare in modo che, SE lo stop loss scatta,
    la perdita sia al massimo una piccola percentuale del capitale totale.

    Il ragionamento e' in tre passi:
      1. Quanto sono disposto a perdere in totale su questo trade?
         (capitale_totale * rischio_percentuale)
      2. Quanto perdo per ogni singola azione, se scatta lo stop?
         (prezzo_entrata - prezzo_stop_loss)
      3. Quindi quante azioni posso comprare?
         (capitale a rischio) / (perdita per azione)

    Restituisce un dizionario con i dettagli del calcolo, cosi' possiamo
    controllarli invece di fidarci alla cieca di un solo numero.
    """
    perdita_per_azione = prezzo_entrata - prezzo_stop_loss

    if perdita_per_azione <= 0:
        raise ValueError(
            "Lo stop loss deve stare SOTTO il prezzo di entrata "
            "(qui calcoliamo solo posizioni long, cioe' 'compro sperando salga')."
        )

    capitale_a_rischio = capitale_totale * rischio_percentuale
    numero_azioni = int(capitale_a_rischio / perdita_per_azione)  # arrotondato per difetto

    return {
        "numero_azioni": numero_azioni,
        "costo_totale": numero_azioni * prezzo_entrata,
        "capitale_a_rischio": capitale_a_rischio,
        "perdita_massima_stimata": numero_azioni * perdita_per_azione,
    }


# ---------------------------------------------------------------------------
# 3) LIMITE DI PERDITA GIORNALIERA (circuit breaker)
# ---------------------------------------------------------------------------

# Ferma tutto se il portafoglio perde il 3% (o piu') rispetto a stamattina
LIMITE_PERDITA_GIORNALIERA_PERCENTUALE = 0.03


def controlla_limite_perdita_giornaliera(
    valore_portafoglio_inizio_giornata,
    valore_portafoglio_attuale,
    limite_percentuale=LIMITE_PERDITA_GIORNALIERA_PERCENTUALE,
):
    """
    Controlla se abbiamo perso troppo OGGI rispetto a stamattina.
    Se si', il bot deve fermarsi e aspettare una revisione manuale
    invece di continuare a fare trade su trade sperando di recuperare.

    Restituisce una coppia:
      (deve_fermarsi: True/False, perdita_percentuale_oggi: numero es. 0.034 = 3.4%)
    """
    perdita_percentuale_oggi = (
        valore_portafoglio_inizio_giornata - valore_portafoglio_attuale
    ) / valore_portafoglio_inizio_giornata

    deve_fermarsi = perdita_percentuale_oggi >= limite_percentuale

    return deve_fermarsi, perdita_percentuale_oggi
