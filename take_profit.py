"""
FASE 8 - Raffinamento: take profit frazionato
================================================

L'idea, spiegata semplice
--------------------------
Finora, quando compriamo un titolo, lo rivendiamo tutto insieme solo quando
arriva un segnale SELL dalla strategia (l'incrocio di medie mobili al
contrario) - che potrebbe succedere molto piu' tardi, magari dopo che il
prezzo e' gia' sceso di nuovo, lasciandoci sul tavolo un guadagno che
avevamo gia' fatto.

Il take profit frazionato aggiunge un'idea diversa e complementare: mano a
mano che la posizione va in guadagno, vendiamo dei "pezzi" (non tutto in
una volta) a soglie di guadagno prestabilite. Cosi' mettiamo in cassa parte
del guadagno prima, e lasciamo che il resto della posizione continui a
correre in caso il titolo salga ancora.

Esempio con i livelli di default (LIVELLI_TAKE_PROFIT qui sotto):
  - guadagno del 3% sopra il prezzo di carico -> vendi 1/3 della posizione
    ORIGINALE (non di quella rimasta in quel momento)
  - guadagno del 6% -> vendi un altro 1/3 della posizione originale
  - guadagno del 10% -> vendi il resto

Perche' "posizione ORIGINALE" e non "quello che rimane"? Perche' altrimenti
ogni "un terzo" sarebbe un terzo di un numero sempre piu' piccolo, e
finiremmo per vendere sempre meno azioni ad ogni livello invece di parti
uguali. Per questo, quando compriamo (Fase 4), registriamo la quantita'
originale nel database (tabella posizioni_aperte).

Idempotenza: ogni livello deve scattare UNA VOLTA SOLA per ogni posizione
aperta, esattamente come gli ordini della Fase 4. Qui la responsabilita' di
questo modulo si ferma a "quali livelli sono stati raggiunti ma non ancora
eseguiti": chi chiama queste funzioni (fase4_esecuzione_ordini.py) e'
responsabile di controllare nel database (tabella take_profit_eseguiti)
quali livelli sono gia' stati eseguiti, prima di chiedere a questo modulo
cosa manca ancora.
"""

# Ogni livello e' una coppia: a che guadagno scatta, e quale FRAZIONE della
# posizione ORIGINALE vendere quando scatta. Le frazioni sommate devono
# arrivare a 1.0 (cioe' l'intera posizione), altrimenti resterebbero sempre
# delle azioni "orfane" che non vendiamo mai con il take profit (andrebbero
# comunque chiuse dal normale segnale SELL della strategia, quindi non e'
# un problema grave, ma e' piu' pulito se i conti tornano).
LIVELLI_TAKE_PROFIT = [
    {"guadagno_percentuale": 0.03, "frazione_posizione_originale": 1 / 3},
    {"guadagno_percentuale": 0.06, "frazione_posizione_originale": 1 / 3},
    {"guadagno_percentuale": 0.10, "frazione_posizione_originale": 1 / 3},
]


def calcola_guadagno_percentuale(prezzo_attuale, prezzo_entrata):
    """
    Calcola il guadagno percentuale rispetto al prezzo di carico della
    posizione. Esempio: comprato a 100$, ora vale 103$ -> 0.03 (cioe' 3%).
    """
    return (prezzo_attuale - prezzo_entrata) / prezzo_entrata


def trova_livelli_da_eseguire(guadagno_percentuale, livelli_gia_eseguiti):
    """
    Restituisce la lista (in ordine) degli INDICI dei livelli di
    LIVELLI_TAKE_PROFIT che sono stati raggiunti dal guadagno attuale ma non
    sono ancora stati eseguiti per questa posizione.

    'livelli_gia_eseguiti' e' un insieme (set) di indici, cosi' come
    restituito da database.livelli_take_profit_eseguiti(posizione_id).

    Restituisce piu' di un indice nello stesso momento se il prezzo e'
    salito cosi' in fretta da "saltare" un livello tra un'esecuzione del bot
    e la successiva (es. il bot gira ogni 15 minuti, il prezzo potrebbe
    superare due soglie insieme): in quel caso li eseguiamo entrambi.
    """
    da_eseguire = []
    for indice, livello in enumerate(LIVELLI_TAKE_PROFIT):
        if indice in livelli_gia_eseguiti:
            continue
        if guadagno_percentuale >= livello["guadagno_percentuale"]:
            da_eseguire.append(indice)
    return da_eseguire


def calcola_quantita_da_vendere(indice_livello, quantita_originale_posizione, quantita_attualmente_posseduta):
    """
    Calcola quante azioni vendere per un dato livello, in base alla frazione
    della posizione ORIGINALE (vedi commento in cima al file).

    Non vendiamo mai piu' di quello che possediamo davvero in questo
    momento (arrotondamenti dei livelli precedenti, o azioni gia' vendute
    per un altro motivo, potrebbero far si' che ne restino meno del previsto):
    per sicurezza il risultato e' sempre limitato a
    'quantita_attualmente_posseduta'.
    """
    frazione = LIVELLI_TAKE_PROFIT[indice_livello]["frazione_posizione_originale"]
    quantita_teorica = int(round(quantita_originale_posizione * frazione))
    return min(quantita_teorica, quantita_attualmente_posseduta)
