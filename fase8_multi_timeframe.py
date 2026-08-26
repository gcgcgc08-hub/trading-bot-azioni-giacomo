"""
FASE 8 - Raffinamento: analisi multi-timeframe
=================================================

Cos'e' un "timeframe"?
-------------------------
E' semplicemente l'intervallo di tempo di ogni singola candela che
guardiamo. Finora la strategia (fase3_strategia_sma.py) guarda SOLO
candele GIORNALIERE: una candela per ogni giorno di borsa, con il prezzo
di chiusura di quel giorno.

L'idea dell'analisi multi-timeframe e' semplice: guardare ANCHE un
intervallo piu' breve (qui usiamo candele ORARIE) prima di comprare, per
vedere se il trend di brevissimo termine e' coerente con il segnale
calcolato sul giornaliero, o se lo sta gia' contraddicendo.

Perche' puo' avere senso
---------------------------
Il segnale giornaliero (incrocio delle medie mobili) si basa sui prezzi
di CHIUSURA di giorni passati: nel momento in cui il bot lo calcola
(durante l'orario di mercato), il prezzo potrebbe essersi gia' mosso
parecchio rispetto a quella chiusura. Se le ultime ore mostrano un trend
chiaramente opposto al segnale giornaliero, forse conviene aspettare
invece di comprare subito - e' una specie di "secondo parere" prima di
agire, esattamente come i filtri di liquidita' e di concentrazione gia'
aggiunti in Fase 8.

Una scelta importante, per restare prudenti
-----------------------------------------------
Questo controllo si applica SOLO ai segnali BUY, mai ai segnali SELL: se
abbiamo gia' una posizione aperta e la strategia dice di chiuderla,
vogliamo sempre poterlo fare, senza che un trend orario "sbagliato" ce lo
impedisca (stessa identica scelta gia' fatta per il filtro di liquidita'
in risk_management.py).

Inoltre, se non abbiamo ancora abbastanza candele orarie per calcolare le
medie (es. Alpaca non ha ancora dati sufficienti in questo momento), NON
blocchiamo l'acquisto: sarebbe peggio restare bloccati per sempre solo
perche' manca un dato accessorio. Blocchiamo l'acquisto SOLO quando il
trend orario e' chiaramente in discesa.

Non cambia in nessun modo decidi_segnale() di fase3_strategia_sma.py (la
logica che genera il segnale giornaliero resta esattamente la stessa,
gia' testata): questo modulo aggiunge solo un controllo IN PIU' prima di
eseguire un BUY, con la stessa logica dei filtri di liquidita' e
concentrazione gia' visti in fase4_esecuzione_ordini.py.
"""

import pandas as pd

from fase3_strategia_sma import SIMBOLO, calcola_medie_mobili

# Periodi piu' brevi di quelli giornalieri (10/30): su candele ORARIE,
# 5 ore e 20 ore rappresentano gia' rispettivamente meno di un giorno di
# borsa e circa 3 giorni di borsa (il mercato USA e' aperto circa 6.5 ore
# al giorno).
PERIODO_BREVE_ORARIO = 5
PERIODO_LUNGO_ORARIO = 20

# Quante ore di CALENDARIO chiediamo indietro (vedi scarica_prezzi_orari()
# in fase3_strategia_sma.py): 360 ore = 15 giorni di calendario, piu' che
# sufficienti per avere almeno 20 candele orarie di borsa vera anche
# contando weekend e notti in mezzo.
ORE_STORIA_DA_RICHIEDERE = 360


def calcola_trend_orario(prezzi_orari, periodo_breve=PERIODO_BREVE_ORARIO, periodo_lungo=PERIODO_LUNGO_ORARIO):
    """
    Calcola le due medie mobili (stessa funzione della Fase 3, riusata qui
    sulle candele ORARIE invece che giornaliere) e guarda solo l'ULTIMO
    valore delle due medie - qui non ci serve un incrocio come nel
    giornaliero, ci basta sapere "in questo momento" se il breve termine
    e' sopra o sotto il trend un po' piu' lento.

    Restituisce una stringa:
      - "salita"  : media breve oraria sopra la media lunga oraria
      - "discesa" : media breve oraria sotto la media lunga oraria
      - "incerto" : dati orari insufficienti, o le due medie sono uguali
    """
    media_breve, media_lunga = calcola_medie_mobili(prezzi_orari, periodo_breve, periodo_lungo)

    if len(media_breve) == 0 or len(media_lunga) == 0:
        return "incerto"

    breve_attuale = media_breve.iloc[-1]
    lunga_attuale = media_lunga.iloc[-1]

    if pd.isna(breve_attuale) or pd.isna(lunga_attuale):
        return "incerto"
    if breve_attuale > lunga_attuale:
        return "salita"
    elif breve_attuale < lunga_attuale:
        return "discesa"
    else:
        return "incerto"


def conferma_segnale_BUY(trend_orario):
    """
    Decide se un segnale BUY del giornaliero e' confermato dal trend
    orario di brevissimo termine.

    Blocchiamo l'acquisto SOLO se il trend orario e' chiaramente
    "discesa" (il brevissimo termine sta andando in direzione opposta al
    segnale giornaliero). Se e' "salita" (concorde) o "incerto" (dati
    orari non ancora sufficienti), lasciamo procedere: e' pensato come una
    conferma in piu', non come un secondo semaforo indipendente che deve
    sempre essere verde.
    """
    return trend_orario != "discesa"


if __name__ == "__main__":
    from fase3_strategia_sma import scarica_prezzi_orari

    print(f"Scarico le candele orarie di {SIMBOLO} da Alpaca...")
    prezzi_orari = scarica_prezzi_orari(SIMBOLO, ore=ORE_STORIA_DA_RICHIEDERE)
    print(f"Ricevute {len(prezzi_orari)} candele orarie.\n")

    trend = calcola_trend_orario(prezzi_orari)
    print(f"=== Trend orario di brevissimo termine per {SIMBOLO}: {trend} ===")

    if trend == "discesa":
        print("Un segnale BUY in questo momento verrebbe BLOCCATO dal controllo multi-timeframe.")
    else:
        print(
            "Un segnale BUY in questo momento verrebbe CONFERMATO (oppure non ci sono "
            "ancora abbastanza dati orari per bloccarlo)."
        )
