"""
FASE 8 - Raffinamento: feed RSS gratuito per le notizie
========================================================

Cosa facciamo qui: scarichiamo le notizie piu' recenti su un titolo (per
ora AAPL, lo stesso della nostra strategia) da un feed RSS gratuito, e le
salviamo nel database. Per ora e' solo un modulo di "contesto": il bot le
legge e le registra, ma NON decide ancora di comprare o vendere in base a
quello che dicono (potremmo insegnargli a farlo in futuro, con calma).

Cos'e' un feed RSS? E' semplicemente un indirizzo internet che, invece di
restituire una pagina web fatta per essere letta da un umano, restituisce
un file XML con una lista di notizie (titolo, link, data, fonte). Possiamo
scaricarlo con 'requests' (la stessa libreria che usiamo gia' per
Telegram) e leggerlo con 'xml.etree.ElementTree', che fa gia' parte di
Python: non serve installare nessuna libreria nuova.

Perche' Google News RSS e non un feed di Yahoo Finance? Perche' il vecchio
feed di Yahoo Finance filtrato per singolo titolo (quello con "?s=AAPL"
nell'indirizzo) non funziona piu' in modo affidabile: Yahoo lo ha di fatto
abbandonato. Google News RSS invece si puo' interrogare con una ricerca
libera (come se scrivessimo "AAPL stock" nella barra di ricerca di Google
News) e restituisce sempre le notizie piu' recenti su quella ricerca,
senza bisogno di nessuna chiave API e senza bisogno di registrarsi.

Nota per Giacomo: questo script fa una richiesta di rete vera (verso
news.google.com), quindi va eseguito da te sul Mac, non posso testarlo
davvero io nel mio ambiente (stesso discorso gia' fatto per Alpaca e
Telegram: il mio container non ha accesso a internet verso questi siti).
Ho pero' testato a parte, con un file XML di esempio scritto a mano nello
stesso formato che restituisce Google News, che la funzione che legge le
notizie (leggi_notizie_da_xml) estrae correttamente titolo/link/data/fonte.
"""

import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

from database import inizializza_database, notizia_gia_salvata, salva_notizia, mostra_notizie
from fase3_strategia_sma import SIMBOLO


def costruisci_url_feed(simbolo, parola_chiave="stock"):
    """
    Costruisce l'indirizzo del feed RSS di Google News per un titolo.
    'quote' serve per trasformare spazi e simboli speciali nel formato che
    un indirizzo internet puo' contenere (es. lo spazio diventa "%20").
    """
    ricerca = quote(f"{simbolo} {parola_chiave}")
    return f"https://news.google.com/rss/search?q={ricerca}&hl=en-US&gl=US&ceid=US:en"


def leggi_notizie_da_xml(testo_xml, numero_massimo=10):
    """
    Legge un testo XML nel formato del feed RSS di Google News e restituisce
    una lista di dizionari, uno per notizia, con le chiavi:
    'titolo', 'link', 'data_pubblicazione', 'fonte'.

    Separare questa funzione da quella che scarica il feed (piu' sotto) ci
    permette di testarla anche senza accesso a internet: le passiamo
    semplicemente un testo XML scritto a mano, invece che scaricato.
    """
    radice = ET.fromstring(testo_xml)
    notizie = []

    # Dentro a un feed RSS, ogni notizia e' un tag <item> dentro <channel>.
    for elemento in radice.findall("./channel/item")[:numero_massimo]:
        titolo = (elemento.findtext("title") or "").strip()
        link = (elemento.findtext("link") or "").strip()
        data_pubblicazione = (elemento.findtext("pubDate") or "").strip()

        # <source> e' un tag opzionale con il nome della testata (es. Reuters).
        elemento_fonte = elemento.find("source")
        if elemento_fonte is not None and elemento_fonte.text:
            fonte = elemento_fonte.text.strip()
        else:
            fonte = "sconosciuta"

        # Se manca titolo o link la notizia non ci serve a niente: la saltiamo.
        if not titolo or not link:
            continue

        notizie.append(
            {
                "titolo": titolo,
                "link": link,
                "data_pubblicazione": data_pubblicazione,
                "fonte": fonte,
            }
        )

    return notizie


def scarica_notizie(simbolo, numero_massimo=10):
    """
    Scarica davvero il feed RSS da internet e lo passa a leggi_notizie_da_xml.
    Mettiamo un timeout (10 secondi) per non restare bloccati all'infinito
    se il sito non risponde: e' la stessa idea gia' vista con Alpaca e
    Telegram, un errore di rete non deve far restare impiccato il bot.

    Alcuni siti rifiutano le richieste che non sembrano provenire da un
    vero browser: per questo aggiungiamo un header "User-Agent" che dice
    "sono un browser normale", invece di lasciare quello di default di
    'requests' (che alcuni siti bloccano).
    """
    url = costruisci_url_feed(simbolo)
    intestazioni = {"User-Agent": "Mozilla/5.0 (compatible; TradingBotGiacomo/1.0)"}
    risposta = requests.get(url, headers=intestazioni, timeout=10)
    risposta.raise_for_status()
    return leggi_notizie_da_xml(risposta.text, numero_massimo=numero_massimo)


def aggiorna_notizie(simbolo, numero_massimo=10):
    """
    Scarica le notizie piu' recenti e salva nel database solo quelle che
    non avevamo ancora visto (controllo con notizia_gia_salvata, basato sul
    link). Restituisce quante notizie NUOVE ha salvato.

    Se il download fallisce per un problema di rete, non facciamo crashare
    il chiamante: stampiamo un avviso e restituiamo 0. Le notizie sono un
    "di piu'" utile da avere, non una parte critica come gli ordini: non
    vale la pena far fallire tutto il bot solo perche' il feed RSS non ha
    risposto in un dato momento.
    """
    try:
        notizie = scarica_notizie(simbolo, numero_massimo=numero_massimo)
    except Exception as errore:
        print(f"Avviso: non sono riuscito a scaricare le notizie ({errore}).")
        return 0

    nuove = 0
    for notizia in notizie:
        if not notizia_gia_salvata(notizia["link"]):
            salva_notizia(
                simbolo,
                notizia["titolo"],
                notizia["link"],
                notizia["data_pubblicazione"],
                notizia["fonte"],
            )
            nuove += 1

    return nuove


if __name__ == "__main__":
    # Test manuale: scarica le notizie per il simbolo della Fase 3 (AAPL),
    # le salva nel database e stampa le ultime salvate per controllarle.
    inizializza_database()
    numero_nuove = aggiorna_notizie(SIMBOLO)
    print(f"Notizie nuove salvate questa volta: {numero_nuove}")
    mostra_notizie(SIMBOLO)
