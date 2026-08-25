"""
Kill switch manuale
======================

Il modo piu' semplice e affidabile per fermare il bot in qualsiasi momento,
anche "da remoto": creare un file chiamato STOP.txt nella cartella del
progetto. La prossima volta che uno script del bot parte, vede quel file e
si ferma subito, senza controllare nemmeno il conto o il mercato.

Perche' un file e non, ad esempio, un sito web o un comando remoto?
Perche' e' il modo piu' semplice possibile da capire e usare, e non
richiede altri account o servizi in piu': basta creare o cancellare un
file. Quando il bot girera' su Oracle Cloud (Fase 7), potrai fare la
stessa cosa collegandoti al server, anche dal telefono con una semplice
app di terminale (SSH).

Per fermare il bot: crea un file di testo vuoto chiamato "STOP.txt" nella
stessa cartella degli script (puoi farlo anche da Finder: tasto destro >
Nuovo documento > rinominalo "STOP.txt").

Per far ripartire il bot: cancella quel file.
"""

import os

NOME_FILE_STOP = "STOP.txt"


def kill_switch_attivo():
    """Restituisce True se il file di stop esiste nella cartella corrente."""
    return os.path.exists(NOME_FILE_STOP)


def attiva_kill_switch(motivo=""):
    """
    Crea il file di stop. Puo' tornare utile anche per far fermare il bot
    DA SOLO in casi estremi (es. troppi errori consecutivi in futuro),
    oltre che manualmente da te.
    """
    with open(NOME_FILE_STOP, "w") as file_stop:
        file_stop.write("Bot fermato.\n")
        if motivo:
            file_stop.write(f"Motivo: {motivo}\n")


def disattiva_kill_switch():
    """Rimuove il file di stop, permettendo al bot di ripartire."""
    if os.path.exists(NOME_FILE_STOP):
        os.remove(NOME_FILE_STOP)
