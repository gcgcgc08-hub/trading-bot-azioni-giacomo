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
    Crea le tabelle se non esistono ancora.
    Va richiamata all'inizio di ogni script, non fa danni se le tabelle
    esistono gia' (grazie a "IF NOT EXISTS").
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

    # FASE 3: tabella per il "logging contestuale" dei segnali della strategia.
    # Non salviamo solo BUY/SELL/NONE, ma anche i numeri che hanno portato
    # a quella decisione (le due medie mobili, di ieri e di oggi), cosi'
    # possiamo sempre ricostruire "perche' il bot ha deciso cosi'" anche
    # mesi dopo, senza dover ricordare a memoria la logica del codice.
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS segnali (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora TEXT NOT NULL,
            simbolo TEXT NOT NULL,
            segnale TEXT NOT NULL,
            prezzo_attuale REAL,
            media_breve_oggi REAL,
            media_lunga_oggi REAL,
            media_breve_ieri REAL,
            media_lunga_ieri REAL,
            periodo_breve INTEGER,
            periodo_lungo INTEGER
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


def salva_segnale(simbolo, segnale, prezzo_attuale, contesto, periodo_breve, periodo_lungo):
    """
    Salva un segnale generato dalla strategia, insieme a tutto il contesto
    che lo ha motivato (logging contestuale).

    'contesto' e' il dizionario restituito da decidi_segnale() dentro
    fase3_strategia_sma.py: contiene le medie mobili di oggi e di ieri
    (quando disponibili).
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        INSERT INTO segnali (
            data_ora, simbolo, segnale, prezzo_attuale,
            media_breve_oggi, media_lunga_oggi,
            media_breve_ieri, media_lunga_ieri,
            periodo_breve, periodo_lungo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            simbolo,
            segnale,
            prezzo_attuale,
            contesto.get("media_breve_oggi"),
            contesto.get("media_lunga_oggi"),
            contesto.get("media_breve_ieri"),
            contesto.get("media_lunga_ieri"),
            periodo_breve,
            periodo_lungo,
        ),
    )
    connessione.commit()
    connessione.close()


def mostra_segnali():
    """Stampa tutti i segnali salvati finora, cosi' possiamo controllarli."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        SELECT data_ora, simbolo, segnale, prezzo_attuale,
               media_breve_oggi, media_lunga_oggi, periodo_breve, periodo_lungo
        FROM segnali ORDER BY id
        """
    )
    righe = cursore.fetchall()
    connessione.close()

    print("\nSegnali salvati finora (segnali dentro bot.db):")
    for data_ora, simbolo, segnale, prezzo, mb, ml, pb, pl in righe:
        prezzo_testo = f"{prezzo:,.2f} $" if prezzo is not None else "n/d"
        mb_testo = f"{mb:,.2f}" if mb is not None else "n/d"
        ml_testo = f"{ml:,.2f}" if ml is not None else "n/d"
        print(
            f"  {data_ora} - {simbolo}: {segnale}  "
            f"(prezzo {prezzo_testo}, media{pb}gg={mb_testo}, media{pl}gg={ml_testo})"
        )
