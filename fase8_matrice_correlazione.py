"""
FASE 8 - Raffinamento: matrice di correlazione tra titoli
============================================================

Cos'e' la "correlazione" tra due titoli?
-------------------------------------------
E' un numero tra -1 e +1 che dice quanto due titoli si muovono INSIEME:

  - vicino a +1: quando uno sale, sale (quasi) sempre anche l'altro, e
    quando uno scende, scende anche l'altro (es. due aziende tecnologiche
    molto simili tendono a muoversi insieme)
  - vicino a -1: quando uno sale, l'altro tende a scendere (raro tra
    azioni "normali", piu' comune tra un'azione e un titolo che scommette
    sul suo ribasso)
  - vicino a 0: non c'e' una relazione lineare evidente, si muovono in
    modo abbastanza indipendente

Perche' ci interessa? Se un giorno il bot dovesse gestire piu' di un
titolo insieme (per ora ne gestisce solo uno, SIMBOLO in fase3_strategia_
sma.py), comprare due titoli MOLTO correlati non diversifica quasi per
niente il rischio: e' quasi come raddoppiare la stessa scommessa, anche
se sulla carta sembrano due posizioni diverse. La matrice di correlazione
e' lo strumento per accorgersene.

Per ora questo script e' SOLO INFORMATIVO (come il feed RSS della Fase 8):
calcola e salva le correlazioni, ma non cambia ancora le decisioni del
bot - serve a farci vedere il concetto e ad avere il numero pronto per
quando (se) in futuro il bot gestira' piu' di un titolo alla volta.

Come si calcola, in breve
---------------------------
1. Scarichiamo lo storico dei prezzi di chiusura di ogni titolo nel
   paniere (stessa funzione gia' scritta in fase3_strategia_sma.py, che
   accetta gia' un simbolo qualsiasi, non solo AAPL).
2. Trasformiamo i prezzi in RENDIMENTI giornalieri (di quanto e' cambiato
   il prezzo, in percentuale, rispetto al giorno prima): confrontiamo i
   rendimenti e non i prezzi grezzi, perche' un titolo da 500$ e uno da
   50$ non sono confrontabili a occhio solo guardando i prezzi.
3. pandas ha gia' una funzione pronta (.corr()) che calcola la matrice di
   correlazione tra tutte le coppie di colonne di una tabella: gliela
   passiamo e basta.
"""

import pandas as pd

from database import inizializza_database, salva_correlazione, mostra_correlazioni
from fase3_strategia_sma import SIMBOLO, GIORNI_STORIA_DA_RICHIEDERE, scarica_prezzi_di_chiusura

# Il paniere di titoli da confrontare con il nostro SIMBOLO principale.
# Per ora sono scelti a mano (aziende tecnologiche grandi e molto
# scambiate, cosi' il filtro di liquidita' minima della Fase 8 non
# avrebbe comunque nulla da ridire su nessuno di questi).
TITOLI_DA_CONFRONTARE = [SIMBOLO, "MSFT", "GOOGL", "AMZN"]

# Sopra questa soglia (valore assoluto) consideriamo due titoli "molto
# correlati": e' una scelta arbitraria ragionevole, non una legge fisica.
SOGLIA_CORRELAZIONE_ALTA = 0.8


def scarica_rendimenti_giornalieri(simboli, giorni=GIORNI_STORIA_DA_RICHIEDERE):
    """
    Scarica i prezzi di chiusura di ogni simbolo nella lista e restituisce
    una tabella (pandas DataFrame) con il RENDIMENTO giornaliero di
    ciascuno (variazione percentuale rispetto al giorno prima), allineati
    per data. Una colonna per simbolo, una riga per giorno di borsa.
    """
    prezzi_per_simbolo = {}
    for simbolo in simboli:
        prezzi_per_simbolo[simbolo] = scarica_prezzi_di_chiusura(simbolo, giorni=giorni)

    tabella_prezzi = pd.DataFrame(prezzi_per_simbolo)

    # pct_change() calcola, per ogni giorno, quanto e' cambiato il prezzo
    # rispetto al giorno prima, in percentuale (es. 0.02 = +2%). Il primo
    # giorno non ha un "giorno prima" nello storico scaricato, quindi
    # risulta NaN: dropna() lo toglie.
    rendimenti = tabella_prezzi.pct_change().dropna()
    return rendimenti


def calcola_matrice_correlazione(rendimenti):
    """
    Calcola la matrice di correlazione tra le colonne (i titoli) di una
    tabella di rendimenti giornalieri. Restituisce un'altra tabella
    (DataFrame) quadrata: stessi titoli sia sulle righe che sulle colonne,
    con 1.0 sulla diagonale (un titolo e' sempre perfettamente correlato
    con se stesso).
    """
    return rendimenti.corr()


def trova_coppie_molto_correlate(matrice_correlazione, soglia=SOGLIA_CORRELAZIONE_ALTA):
    """
    Restituisce la lista delle coppie di titoli DIVERSI tra loro con
    correlazione (in valore assoluto) sopra la soglia indicata, come lista
    di tuple (simbolo_a, simbolo_b, coefficiente).

    Ogni coppia viene restituita una volta sola (non sia "AAPL, MSFT" che
    "MSFT, AAPL"), scorrendo solo la meta' superiore della matrice.
    """
    coppie_trovate = []
    simboli = list(matrice_correlazione.columns)

    for indice_a, simbolo_a in enumerate(simboli):
        for simbolo_b in simboli[indice_a + 1:]:
            coefficiente = matrice_correlazione.loc[simbolo_a, simbolo_b]
            if abs(coefficiente) >= soglia:
                coppie_trovate.append((simbolo_a, simbolo_b, coefficiente))

    return coppie_trovate


if __name__ == "__main__":
    inizializza_database()

    print(f"Scarico lo storico di {', '.join(TITOLI_DA_CONFRONTARE)} da Alpaca...")
    rendimenti = scarica_rendimenti_giornalieri(TITOLI_DA_CONFRONTARE)
    print(f"Ricevuti {len(rendimenti)} giorni di rendimenti in comune.\n")

    matrice = calcola_matrice_correlazione(rendimenti)

    print("=== Matrice di correlazione (rendimenti giornalieri) ===")
    print(matrice.round(2).to_string())

    # Salviamo ogni coppia (una volta sola) nel database, per tenerne lo storico.
    simboli = list(matrice.columns)
    for indice_a, simbolo_a in enumerate(simboli):
        for simbolo_b in simboli[indice_a + 1:]:
            coefficiente = float(matrice.loc[simbolo_a, simbolo_b])
            salva_correlazione(simbolo_a, simbolo_b, coefficiente)

    coppie_alte = trova_coppie_molto_correlate(matrice)
    print(f"\n=== Coppie molto correlate (soglia {SOGLIA_CORRELAZIONE_ALTA}) ===")
    if not coppie_alte:
        print("Nessuna coppia sopra la soglia: in questo paniere non stiamo raddoppiando lo stesso rischio.")
    else:
        for simbolo_a, simbolo_b, coefficiente in coppie_alte:
            print(
                f"  {simbolo_a} / {simbolo_b}: {coefficiente:+.2f} - comprarli entrambi "
                "diversificherebbe poco, si muovono quasi allo stesso modo."
            )

    mostra_correlazioni()
