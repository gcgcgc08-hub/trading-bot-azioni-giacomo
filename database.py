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

    # FASE 6: tabella per il "battito cardiaco" (heartbeat) del bot. Ad ogni
    # esecuzione, il bot registra qui come e' andata: e' la base per il
    # watchdog, cioe' per accorgersi se il bot ha smesso di funzionare
    # (utile soprattutto quando girera' da solo, senza nessuno a guardare
    # lo schermo).
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS battiti_cuore (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora TEXT NOT NULL,
            stato TEXT NOT NULL,
            messaggio TEXT
        )
    """)

    # FASE 8: tabelle per il take profit frazionato. Servono due tabelle
    # collegate tra loro:
    #   - 'posizioni_aperte': ogni volta che compriamo un titolo, registriamo
    #     QUI la quantita' originale e il prezzo di carico. Ci serve perche'
    #     Alpaca ci dice solo "quante azioni abbiamo ADESSO", ma il take
    #     profit frazionato deve ragionare sulla quantita' ORIGINALE (per
    #     decidere "vendi un terzo della posizione", non "vendi un terzo di
    #     quello che rimane", che sarebbe una frazione diversa ogni volta).
    #   - 'take_profit_eseguiti': ogni volta che vendiamo un "pezzo" per un
    #     livello di guadagno raggiunto, lo registriamo qui. 'UNIQUE' sulla
    #     coppia (posizione_id, livello_indice) e' la nostra idempotenza:
    #     anche se il bot gira piu' volte, un livello scatta una volta sola.
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS posizioni_aperte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simbolo TEXT NOT NULL,
            quantita_originale INTEGER NOT NULL,
            prezzo_entrata REAL NOT NULL,
            data_apertura TEXT NOT NULL,
            aperta INTEGER NOT NULL DEFAULT 1
        )
    """)
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS take_profit_eseguiti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            posizione_id INTEGER NOT NULL,
            livello_indice INTEGER NOT NULL,
            quantita_venduta INTEGER NOT NULL,
            prezzo_vendita REAL NOT NULL,
            data_ora TEXT NOT NULL,
            UNIQUE(posizione_id, livello_indice)
        )
    """)

    # FASE 8: tabella per la matrice di correlazione tra titoli. Ogni riga
    # e' una COPPIA di titoli con il loro coefficiente di correlazione in
    # quel momento (vedi fase8_matrice_correlazione.py per i dettagli).
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS correlazioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora TEXT NOT NULL,
            simbolo_a TEXT NOT NULL,
            simbolo_b TEXT NOT NULL,
            coefficiente REAL NOT NULL
        )
    """)

    # FASE 8: tabella per le notizie scaricate dal feed RSS gratuito.
    # 'link' e' UNIQUE apposta: e' quello che usiamo per capire se una
    # notizia l'abbiamo gia' salvata in passato, cosi' non la duplichiamo
    # ogni volta che il bot scarica di nuovo lo stesso feed (che contiene
    # sempre anche le notizie piu' vecchie, non solo quelle nuove).
    cursore.execute("""
        CREATE TABLE IF NOT EXISTS notizie (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_ora_salvataggio TEXT NOT NULL,
            simbolo TEXT NOT NULL,
            titolo TEXT NOT NULL,
            link TEXT NOT NULL UNIQUE,
            data_pubblicazione TEXT,
            fonte TEXT
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


def registra_battito_cuore(stato, messaggio=""):
    """
    Registra un "battito cardiaco": una riga che dice "il bot e' girato in
    questo momento, ed e' andata cosi'". 'stato' e' una parola breve (es.
    "ok", "errore", "fermato_circuit_breaker", "fermato_kill_switch");
    'messaggio' e' una frase libera con qualche dettaglio in piu'.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "INSERT INTO battiti_cuore (data_ora, stato, messaggio) VALUES (?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), stato, messaggio),
    )
    connessione.commit()
    connessione.close()


def ultimo_battito_cuore():
    """
    Restituisce (data_ora, stato, messaggio) dell'ultimo battito registrato,
    oppure None se non ne e' ancora stato registrato nessuno.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT data_ora, stato, messaggio FROM battiti_cuore ORDER BY id DESC LIMIT 1"
    )
    riga = cursore.fetchone()
    connessione.close()
    return riga


def mostra_battiti_cuore():
    """Stampa tutti i battiti cardiaci registrati finora, dal piu' vecchio al piu' recente."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute("SELECT data_ora, stato, messaggio FROM battiti_cuore ORDER BY id")
    righe = cursore.fetchall()
    connessione.close()

    print("\nBattiti cardiaci registrati finora (dentro bot.db):")
    for data_ora, stato, messaggio in righe:
        print(f"  {data_ora} - {stato}: {messaggio}")


def controlla_battito_cuore_scaduto(minuti_massimi=60):
    """
    Controlla se e' passato troppo tempo dall'ultimo battito cardiaco
    registrato. Utile soprattutto quando il bot girera' in automatico
    (Fase 7): se dovrebbe far sentire il battito ogni tot minuti e non lo
    fa piu' da troppo tempo, vuol dire che si e' bloccato o e' crashato
    cosi' male da non essere nemmeno riuscito a segnalarlo.

    Restituisce una coppia (scaduto: True/False, minuti_passati: numero
    oppure None se non c'e' ancora nessun battito registrato).
    """
    ultimo = ultimo_battito_cuore()
    if ultimo is None:
        return True, None

    data_ora_ultimo = datetime.fromisoformat(ultimo[0])
    minuti_passati = (datetime.now() - data_ora_ultimo).total_seconds() / 60
    scaduto = minuti_passati > minuti_massimi
    return scaduto, minuti_passati


def notizia_gia_salvata(link):
    """
    Controlla se questo link e' gia' stato salvato in passato. Ci serve
    perche' ogni volta che scarichiamo il feed RSS troviamo di nuovo anche
    le notizie vecchie: senza questo controllo le salveremmo (e stamperemmo)
    piu' volte.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute("SELECT 1 FROM notizie WHERE link = ?", (link,))
    esiste = cursore.fetchone() is not None
    connessione.close()
    return esiste


def salva_notizia(simbolo, titolo, link, data_pubblicazione, fonte):
    """Salva una notizia scaricata dal feed RSS."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        INSERT INTO notizie (
            data_ora_salvataggio, simbolo, titolo, link,
            data_pubblicazione, fonte
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            simbolo,
            titolo,
            link,
            data_pubblicazione,
            fonte,
        ),
    )
    connessione.commit()
    connessione.close()


def mostra_notizie(simbolo=None, limite=10):
    """
    Stampa le ultime notizie salvate (le piu' recenti per prime).
    Se 'simbolo' e' indicato, mostra solo le notizie di quel titolo.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    if simbolo:
        cursore.execute(
            """
            SELECT data_pubblicazione, fonte, titolo, link FROM notizie
            WHERE simbolo = ? ORDER BY id DESC LIMIT ?
            """,
            (simbolo, limite),
        )
    else:
        cursore.execute(
            """
            SELECT data_pubblicazione, fonte, titolo, link FROM notizie
            ORDER BY id DESC LIMIT ?
            """,
            (limite,),
        )
    righe = cursore.fetchall()
    connessione.close()

    print("\nUltime notizie salvate (dentro bot.db):")
    if not righe:
        print("  (nessuna notizia salvata finora)")
    for data_pubblicazione, fonte, titolo, link in righe:
        data_testo = data_pubblicazione if data_pubblicazione else "data sconosciuta"
        fonte_testo = fonte if fonte else "fonte sconosciuta"
        print(f"  [{data_testo}] ({fonte_testo}) {titolo}")
        print(f"    {link}")


def salva_correlazione(simbolo_a, simbolo_b, coefficiente):
    """Salva il coefficiente di correlazione calcolato tra due titoli."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "INSERT INTO correlazioni (data_ora, simbolo_a, simbolo_b, coefficiente) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), simbolo_a, simbolo_b, coefficiente),
    )
    connessione.commit()
    connessione.close()


def mostra_correlazioni(limite=20):
    """Stampa le ultime correlazioni salvate (le piu' recenti per prime)."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT data_ora, simbolo_a, simbolo_b, coefficiente FROM correlazioni ORDER BY id DESC LIMIT ?",
        (limite,),
    )
    righe = cursore.fetchall()
    connessione.close()

    print("\nUltime correlazioni salvate (dentro bot.db):")
    if not righe:
        print("  (nessuna correlazione salvata finora)")
    for data_ora, simbolo_a, simbolo_b, coefficiente in righe:
        print(f"  {data_ora} - {simbolo_a} / {simbolo_b}: {coefficiente:+.2f}")


def apri_posizione(simbolo, quantita_originale, prezzo_entrata):
    """
    Registra l'apertura di una nuova posizione (dopo un BUY andato a buon
    fine). Restituisce l'id della riga appena creata: ci servira' per
    collegare i futuri take profit frazionati a QUESTA posizione specifica.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        INSERT INTO posizioni_aperte (
            simbolo, quantita_originale, prezzo_entrata, data_apertura, aperta
        )
        VALUES (?, ?, ?, ?, 1)
        """,
        (
            simbolo,
            quantita_originale,
            prezzo_entrata,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    connessione.commit()
    posizione_id = cursore.lastrowid
    connessione.close()
    return posizione_id


def posizione_aperta_di(simbolo):
    """
    Restituisce la posizione attualmente aperta per 'simbolo' (la piu'
    recente, se per assurdo ce ne fosse piu' di una), come dizionario con
    le chiavi 'id', 'quantita_originale', 'prezzo_entrata', 'data_apertura'.
    Restituisce None se non c'e' nessuna posizione aperta per quel simbolo.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        """
        SELECT id, quantita_originale, prezzo_entrata, data_apertura
        FROM posizioni_aperte
        WHERE simbolo = ? AND aperta = 1
        ORDER BY id DESC LIMIT 1
        """,
        (simbolo,),
    )
    riga = cursore.fetchone()
    connessione.close()
    if riga is None:
        return None
    return {
        "id": riga[0],
        "quantita_originale": riga[1],
        "prezzo_entrata": riga[2],
        "data_apertura": riga[3],
    }


def chiudi_posizione(posizione_id):
    """
    Segna una posizione come chiusa (dopo un SELL che ha chiuso tutto).
    Da questo momento in poi non conta piu' per il take profit frazionato:
    se in futuro ricompriamo lo stesso simbolo, apri_posizione() creera'
    una riga nuova, e i livelli di take profit ripartiranno da zero.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute("UPDATE posizioni_aperte SET aperta = 0 WHERE id = ?", (posizione_id,))
    connessione.commit()
    connessione.close()


def livelli_take_profit_eseguiti(posizione_id):
    """
    Restituisce l'insieme (set) degli indici dei livelli di take profit gia'
    eseguiti per questa posizione, cosi' possiamo capire quali mancano ancora.
    """
    connessione = ottieni_connessione()
    cursore = connessione.cursor()
    cursore.execute(
        "SELECT livello_indice FROM take_profit_eseguiti WHERE posizione_id = ?",
        (posizione_id,),
    )
    righe = cursore.fetchall()
    connessione.close()
    return {riga[0] for riga in righe}


def salva_take_profit_eseguito(posizione_id, livello_indice, quantita_venduta, prezzo_vendita):
    """
    Registra che un livello di take profit e' stato eseguito per questa
    posizione. Chi chiama questa funzione dovrebbe aver gia' controllato
    con livelli_take_profit_eseguiti() che questo livello non sia gia'
    stato eseguito: il vincolo UNIQUE della tabella e' solo un secondo
    scudo di sicurezza (stessa idea del client_order_id nella Fase 4), non
    il controllo principale.

    Usiamo 'try/finally' per essere sicuri di chiudere SEMPRE la
    connessione al database, anche se l'INSERT fallisce (es. per il
    vincolo UNIQUE): altrimenti la connessione resterebbe aperta e
    bloccherebbe il file del database per le chiamate successive.
    """
    connessione = ottieni_connessione()
    try:
        cursore = connessione.cursor()
        cursore.execute(
            """
            INSERT INTO take_profit_eseguiti (
                posizione_id, livello_indice, quantita_venduta, prezzo_vendita, data_ora
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                posizione_id,
                livello_indice,
                quantita_venduta,
                prezzo_vendita,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        connessione.commit()
    finally:
        connessione.close()


def mostra_take_profit():
    """Stampa tutte le posizioni tracciate e tutti i take profit eseguiti finora (per controllo/debug)."""
    connessione = ottieni_connessione()
    cursore = connessione.cursor()

    cursore.execute(
        "SELECT id, simbolo, quantita_originale, prezzo_entrata, data_apertura, aperta "
        "FROM posizioni_aperte ORDER BY id"
    )
    posizioni = cursore.fetchall()

    cursore.execute(
        "SELECT posizione_id, livello_indice, quantita_venduta, prezzo_vendita, data_ora "
        "FROM take_profit_eseguiti ORDER BY id"
    )
    eseguiti = cursore.fetchall()
    connessione.close()

    print("\nPosizioni tracciate per il take profit frazionato (dentro bot.db):")
    if not posizioni:
        print("  (nessuna posizione tracciata finora)")
    for id_pos, simbolo, quantita, prezzo, data_apertura, aperta in posizioni:
        stato = "APERTA" if aperta else "chiusa"
        print(
            f"  #{id_pos} {simbolo}: {quantita} azioni @ {prezzo:,.2f} $ "
            f"(aperta il {data_apertura}) - {stato}"
        )

    print("\nTake profit eseguiti finora:")
    if not eseguiti:
        print("  (nessun take profit eseguito finora)")
    for posizione_id, livello_indice, quantita_venduta, prezzo_vendita, data_ora in eseguiti:
        print(
            f"  {data_ora} - posizione #{posizione_id}, livello {livello_indice}: "
            f"venduta {quantita_venduta} azioni @ {prezzo_vendita:,.2f} $"
        )
