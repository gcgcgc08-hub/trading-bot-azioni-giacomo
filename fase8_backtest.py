"""
FASE 8 - Raffinamento: backtest con slippage e commissioni
==============================================================

Cos'e' un backtest?
---------------------
E' il modo di rispondere alla domanda "se questa strategia (l'incrocio di
medie mobili della Fase 3) fosse girata negli ultimi due anni, come
sarebbe andata?" - senza aspettare due anni veri, riguardando invece lo
storico dei prezzi gia' passato. Questo script non piazza NESSUN ordine
vero: legge solo lo storico dei prezzi da Alpaca e simula tutto a
tavolino, in memoria.

Il problema del backtest "ottimistico"
-----------------------------------------
Un backtest ingenuo assume che ogni ordine si riempia ESATTAMENTE al
prezzo di chiusura del giorno, senza nessun costo. Nella realta' non e'
mai cosi':

  - SLIPPAGE: tra il momento in cui il bot decide di comprare/vendere e il
    momento in cui l'ordine viene davvero eseguito, il prezzo si e' gia'
    mosso un po' - di solito leggermente CONTRO di noi (compriamo a un
    prezzo un filo piu' alto di quello visto, vendiamo a uno un filo piu'
    basso).
  - COMMISSIONI: alcuni broker fanno pagare qualcosa per ogni ordine.
    Alpaca (quello che usiamo noi) in realta' NON fa pagare commissioni
    sulle azioni USA - ma vale la pena vedere che effetto avrebbe, sia per
    abituarsi a un ragionamento realistico, sia in caso un giorno si usi
    un broker diverso.

Se il backtest ignora questi due costi, il risultato sembra sempre
migliore di quello che sarebbe stato davvero. Per questo qui sotto
lanciamo la STESSA simulazione due volte sugli STESSI dati - una
"ottimistica" (senza costi) e una "realistica" (con slippage e
commissioni) - e confrontiamo i due risultati finali. La differenza tra i
due e' esattamente quanto i costi "morderebbero" i nostri guadagni.

Un dettaglio importante
--------------------------
Questo script chiama decidi_segnale() di fase3_strategia_sma.py, la
STESSA funzione che usa la strategia vera dal vivo (non una sua copia
riscritta a parte): cosi' siamo sicuri che il backtest testi esattamente
la logica che gira davvero, non un'imitazione che potrebbe comportarsi in
modo leggermente diverso per un errore di trascrizione.
"""

from database import inizializza_database, salva_risultato_backtest, mostra_backtest
from fase3_strategia_sma import (
    SIMBOLO,
    scarica_prezzi_di_chiusura,
    calcola_medie_mobili,
    decidi_segnale,
)
from risk_management import (
    calcola_stop_loss,
    calcola_dimensione_posizione,
    applica_limite_concentrazione,
)

# Per un backtest ci serve MOLTO piu' storico dei 90 giorni che bastano
# alla strategia dal vivo (che deve solo calcolare la media mobile a 30
# giorni piu' recente): qui vogliamo vedere tanti incroci diversi nel
# tempo, quindi chiediamo circa due anni di calendario.
GIORNI_STORIA_BACKTEST = 730

CAPITALE_INIZIALE = 10_000.0

# 0.1%: assunzione prudenziale di quanto il prezzo si muove contro di noi
# tra la decisione e l'esecuzione vera dell'ordine.
SLIPPAGE_PERCENTUALE = 0.001

# $1 per ordine: Alpaca non la fa pagare davvero sulle azioni USA, e'
# un'assunzione prudenziale per vedere l'effetto se cambiasse in futuro.
COMMISSIONE_PER_ORDINE = 1.0


def prezzo_di_esecuzione(prezzo_chiusura, lato, slippage_percentuale):
    """
    Calcola il prezzo a cui l'ordine si riempirebbe DAVVERO, tenendo conto
    dello slippage: comprando paghiamo un po' di piu', vendendo incassiamo
    un po' di meno, rispetto al prezzo di chiusura "sulla carta".
    """
    if lato == "BUY":
        return prezzo_chiusura * (1 + slippage_percentuale)
    return prezzo_chiusura * (1 - slippage_percentuale)  # lato == "SELL"


def simula_strategia(prezzi, capitale_iniziale=CAPITALE_INIZIALE, slippage_percentuale=0.0, commissione_per_ordine=0.0):
    """
    Simula la strategia SMA crossover su uno storico di prezzi di chiusura
    gia' scaricato, giorno per giorno, applicando risk management (stop
    loss, position sizing, limite di concentrazione), slippage e
    commissioni. Restituisce un dizionario con i risultati.

    Gestisce un solo titolo alla volta, esattamente come la strategia dal
    vivo: compra quando arriva un segnale BUY (se non abbiamo gia' una
    posizione aperta), vende tutto quando arriva un segnale SELL.
    """
    media_breve, media_lunga = calcola_medie_mobili(prezzi)

    cassa = capitale_iniziale
    posizione_quantita = 0
    operazioni = []  # log di ogni BUY/SELL eseguito, utile per controllare a mano

    for indice_giorno in range(1, len(prezzi)):
        prezzo_oggi = float(prezzi.iloc[indice_giorno])

        # Guardiamo solo i dati FINO a oggi (indice_giorno + 1 righe): un
        # backtest onesto non deve mai "vedere il futuro" rispetto al
        # giorno che sta simulando.
        segnale, _ = decidi_segnale(
            media_breve.iloc[: indice_giorno + 1],
            media_lunga.iloc[: indice_giorno + 1],
        )

        if segnale == "BUY" and posizione_quantita == 0:
            stop_loss = calcola_stop_loss(prezzo_oggi)
            sizing = calcola_dimensione_posizione(cassa, prezzo_oggi, stop_loss)
            limite = applica_limite_concentrazione(sizing["numero_azioni"], prezzo_oggi, cassa)
            quantita = limite["numero_azioni"]

            if quantita > 0:
                prezzo_esecuzione = prezzo_di_esecuzione(prezzo_oggi, "BUY", slippage_percentuale)
                costo = quantita * prezzo_esecuzione + commissione_per_ordine

                if costo <= cassa:
                    cassa -= costo
                    posizione_quantita = quantita
                    operazioni.append({
                        "giorno": indice_giorno, "lato": "BUY",
                        "quantita": quantita, "prezzo": prezzo_esecuzione,
                    })

        elif segnale == "SELL" and posizione_quantita > 0:
            prezzo_esecuzione = prezzo_di_esecuzione(prezzo_oggi, "SELL", slippage_percentuale)
            incasso = posizione_quantita * prezzo_esecuzione - commissione_per_ordine
            cassa += incasso
            operazioni.append({
                "giorno": indice_giorno, "lato": "SELL",
                "quantita": posizione_quantita, "prezzo": prezzo_esecuzione,
            })
            posizione_quantita = 0

    # Se alla fine dello storico e' rimasta una posizione aperta, la
    # valutiamo al prezzo dell'ultimo giorno SOLO per calcolare il valore
    # finale del portafoglio (non e' un vero ordine, e' solo "quanto
    # varrebbe oggi se la chiudessimo adesso").
    prezzo_finale = float(prezzi.iloc[-1])
    valore_posizione_aperta = posizione_quantita * prezzo_finale
    capitale_finale = cassa + valore_posizione_aperta

    return {
        "capitale_iniziale": capitale_iniziale,
        "capitale_finale": capitale_finale,
        "rendimento_percentuale": (capitale_finale - capitale_iniziale) / capitale_iniziale,
        "numero_operazioni": len(operazioni),
        "posizione_aperta_alla_fine": posizione_quantita > 0,
        "operazioni": operazioni,
    }


if __name__ == "__main__":
    inizializza_database()

    print(f"Scarico {GIORNI_STORIA_BACKTEST} giorni di storico per {SIMBOLO} da Alpaca...")
    prezzi = scarica_prezzi_di_chiusura(SIMBOLO, giorni=GIORNI_STORIA_BACKTEST)
    print(f"Ricevute {len(prezzi)} candele giornaliere.\n")

    risultato_ottimistico = simula_strategia(prezzi, slippage_percentuale=0.0, commissione_per_ordine=0.0)
    risultato_realistico = simula_strategia(
        prezzi, slippage_percentuale=SLIPPAGE_PERCENTUALE, commissione_per_ordine=COMMISSIONE_PER_ORDINE
    )

    print("=== Backtest OTTIMISTICO (nessuno slippage, nessuna commissione) ===")
    print(f"Capitale iniziale: {risultato_ottimistico['capitale_iniziale']:>12,.2f} $")
    print(f"Capitale finale:   {risultato_ottimistico['capitale_finale']:>12,.2f} $")
    print(f"Rendimento:        {risultato_ottimistico['rendimento_percentuale'] * 100:>+11.2f}%")
    print(f"Operazioni:        {risultato_ottimistico['numero_operazioni']}")

    print("\n=== Backtest REALISTICO (con slippage e commissioni) ===")
    print(f"Capitale iniziale: {risultato_realistico['capitale_iniziale']:>12,.2f} $")
    print(f"Capitale finale:   {risultato_realistico['capitale_finale']:>12,.2f} $")
    print(f"Rendimento:        {risultato_realistico['rendimento_percentuale'] * 100:>+11.2f}%")
    print(f"Operazioni:        {risultato_realistico['numero_operazioni']}")

    differenza = risultato_ottimistico["capitale_finale"] - risultato_realistico["capitale_finale"]
    print(f"\n=== Differenza dovuta a slippage e commissioni: {differenza:,.2f} $ ===")
    print(
        "(E' il 'costo nascosto' che un backtest senza questi due fattori "
        "avrebbe fatto sparire, facendo sembrare la strategia migliore di "
        "quello che sarebbe stata davvero.)"
    )

    salva_risultato_backtest(
        SIMBOLO,
        len(prezzi),
        risultato_ottimistico["capitale_finale"],
        risultato_realistico["capitale_finale"],
        risultato_realistico["numero_operazioni"],
    )
    mostra_backtest()
