"""
Modulo per salvare i dati del bot in un piccolo database locale (SQLite).

Perche' un database e non un semplice file di testo?
  - Possiamo salvare tante informazioni nel tempo (uno "storico") e poi
    interrogarle facilmente, ad esempio "dammi solo le righe di oggi",
    invece di dover leggere e capire a mano un file di testo sempre piu' lungo.
  - SQLite e' un database che vive in un unico file (bot.db) senza bisogno
    di installare o far girare un programma server a parte: perfetto per
    un progetto personale come il nostro.
  - Il modulo 'sqlite3' e' gia' incluso in Python: non serve installare nulla.

Concetti nuovi:
  - "Tabella": una specie di foglio di calcolo dentro al database, con
    colonne fisse (qui: data, liquidita', valore portafoglio, mercato aperto)
    e tante righe, una per ogni "fotografia" che salviamo.
  - "SQL": il linguaggio con cui si parla ai database (le stringhe scritte
    in maiuscolo qui sotto, tipo CREATE TABLE o INSERT INTO).
"""

import sqlite3
from datetime import datetime

NOME_DATABASE = "bot.db"


def ottieni_connessione():
    """Apre il file del database (lo crea da zero se non esiste ancora)."""
    return sqlite3.connect(NOME_DATABASE)


def inizializza_database():
    """
    Crea la tabella 'snapshot_conto' se non esiste ancora.
    Va richiamata all'inizio di ogni script, non fa danni se la tabella
    esiste gia' (grazie a "IF NOT EXISTS").
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_conto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora TEXT NOT NULL,
            liquidita REAL NOT NULL,
            valore_portafoglio REAL NOT NULL,
            mercato_aperto INTEGER NOT NULL
        )
    """)
    connessione.commit()
    connessione.close()


def salva_snapshot_conto(liquidita, valore_portafoglio, mercato_aperto):
    """Salva una nuova riga con lo stato attuale del conto."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        INSERT INTO snapshot_conto (data_ora, liquidita, valore_portafoglio, mercato_aperto)
        VALUES (?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            liquidita,
            valore_portafoglio,
            1 if mercato_aperto else 0,
        ),
    )
    connessione.commit()
    connessione.close()


def mostra_storico():
    """Stampa tutte le righe salvate finora, cosi' possiamo controllarle."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT data_ora, liquidita, valore_portafoglio, mercato_aperto "
        "FROM snapshot_conto ORDER BY id"
    )
    righe = cursore.fetchall()
    connessione.close()

    print("\nStorico salvato nel database (bot.db):")
    for data_ora, liquidita, valore, aperto in righe:
        stato = "aperto" if aperto else "chiuso"
        print(
            f"  {data_ora} - liquidita': {liquidita:>12,.2f} $ - "
            f"portafoglio: {valore:>12,.2f} $ - mercato {stato}"
        )
