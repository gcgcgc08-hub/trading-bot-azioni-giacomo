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

    # FASE 4: tabella per gli ordini che il bot prova a piazzare su Alpaca.
    # 'client_order_id' e' UNIQUE apposta: e' la nostra chiave di idempotenza.
    # Se proviamo a salvare due volte lo stesso client_order_id, SQLite
    # rifiuta la seconda riga con un errore invece di duplicarla in silenzio,
    # cosi' abbiamo una doppia protezione (anche Alpaca, dal canto suo,
    # rifiuta un secondo ordine con lo stesso client_order_id).
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS ordini (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora TEXT NOT NULL,
            simbolo TEXT NOT NULL,
            lato TEXT NOT NULL,
            quantita INTEGER NOT NULL,
            prezzo_riferimento REAL,
            client_order_id TEXT NOT NULL UNIQUE,
            stato TEXT NOT NULL,
            dettagli TEXT
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


def primo_valore_portafoglio_di_oggi():
    """
    Restituisce il valore del portafoglio salvato nel PRIMO snapshot di oggi
    (quello con l'orario piu' vecchio tra tutti quelli di oggi). Ci serve
    come "valore di inizio giornata" per il circuit breaker: se il primo
    snapshot di oggi non e' ancora stato salvato, restituisce None (chi
    chiama questa funzione deve aver gia' salvato uno snapshot prima).

    Confrontiamo le date come testo (es. "2026-08-25") perche' salviamo
    data_ora con datetime.now().isoformat(), che inizia sempre con
    "AAAA-MM-GG": funziona anche solo con un confronto di stringhe, senza
    bisogno di librerie in piu' per il parsing delle date.
    """
    oggi = datetime.now().strftime("%Y-%m-%d")
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT valore_portafoglio FROM snapshot_conto "
        "WHERE data_ora LIKE ? ORDER BY id ASC LIMIT 1",
        (f"{oggi}%",),
    )
    riga = cursore.fetchone()
    connessione.close()
    return riga[0] if riga is not None else None


def client_order_id_gia_usato(client_order_id):
    """
    Controlla se questo client_order_id e' gia' presente nel database locale.
    E' il primo dei due "scudi" contro gli ordini doppi (idempotenza): prima
    ancora di provare a contattare Alpaca, controlliamo se abbiamo gia'
    salvato un ordine con lo stesso identificativo (es. lo stesso simbolo e
    segnale, nello stesso giorno).
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute("SELECT 1 FROM ordini WHERE client_order_id = ?", (client_order_id,))
    esiste = cursore.fetchone() is not None
    connessione.close()
    return esiste


def salva_ordine(simbolo, lato, quantita, prezzo_riferimento, client_order_id, stato, dettagli=""):
    """Salva il tentativo di ordine (andato a buon fine o no) nel database."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        INSERT INTO ordini (
            data_ora, simbolo, lato, quantita, prezzo_riferimento,
            client_order_id, stato, dettagli
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            simbolo,
            lato,
            quantita,
            prezzo_riferimento,
            client_order_id,
            stato,
            dettagli,
        ),
    )
    connessione.commit()
    connessione.close()


def mostra_ordini():
    """Stampa tutti gli ordini (tentati o riusciti) salvati finora."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT data_ora, simbolo, lato, quantita, prezzo_riferimento, stato, dettagli "
        "FROM ordini ORDER BY id"
    )
    righe = cursore.fetchall()
    connessione.close()

    print("\nOrdini registrati finora (dentro bot.db):")
    for data_ora, simbolo, lato, quantita, prezzo, stato, dettagli in righe:
        prezzo_testo = f"{prezzo:,.2f} $" if prezzo is not None else "n/d"
        print(
            f"  {data_ora} - {simbolo} {lato} x{quantita} @ {prezzo_testo} "
            f"-> {stato} ({dettagli})"
        )
