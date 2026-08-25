# Trading Bot – Azioni

Progetto didattico che costruiamo insieme, un pezzo alla volta. Per ora è un bot di **paper trading**: simula compravendite con soldi finti, così possiamo testare idee e imparare senza nessun rischio reale. Riguarda solo il mercato azionario — un bot per le crypto sarà un progetto separato, più avanti.

Obiettivo dichiarato: collaudare il bot per mesi in simulazione, e solo se la strategia si dimostra solida iniziare a operare con un piccolo capitale reale (100-200€).

> Nota: niente di quello che costruiamo qui è un consiglio di investimento. È un progetto per imparare a programmare e capire come funzionano i mercati — le decisioni finanziarie vere sono un'altra cosa, e prima di muovere soldi veri (se mai vorrai farlo) è sempre meglio informarsi bene e magari sentire un professionista.

## Requisiti definiti insieme

Idee originali di Giacomo:
- Stop loss sempre 1-2%, con calcolo della dimensione della posizione
- Leva finanziaria: si parte senza leva, tetto massimo 5x da introdurre solo dopo aver validato la strategia
- Logging contestuale: ogni decisione salvata insieme al contesto/indicatori che l'hanno motivata
- Dati e paper trading tramite **Alpaca Markets**
- Feed RSS gratuito per le news, come integrazione
- Analisi multi-timeframe (giornaliero / 4h / 1h / 15min)
- Matrice di correlazione tra titoli
- Take profit frazionato
- Modulo watchdog/heartbeat, perché il bot deve girare da solo H24
- Non deve girare sul PC di Giacomo → hosting su **Oracle Cloud (Always Free tier)**
- Codice versionato su **GitHub**
- Memoria/storage su **SQLite**

Aggiunte proposte e accettate:
- **Limite di perdita complessivo** (circuit breaker giornaliero/settimanale): se le perdite accumulate superano una soglia, il bot si ferma da solo in attesa di revisione manuale — non solo lo stop loss sul singolo trade
- **Calendario di mercato**: il bot controlla quando la borsa è davvero aperta (weekend, festività USA, pre/after-market)
- **Gestione robusta degli errori di rete**: retry sicuri senza inviare ordini duplicati (client order id univoco)
- **Separazione netta chiavi paper/live** e **segreti mai su GitHub** (file di configurazione escluso dal repository)
- **Kill switch manuale**: un modo rapido per fermare il bot da remoto in qualsiasi momento
- **Notifiche vere** (es. bot Telegram gratuito) per sapere in tempo reale quando fa un trade o incontra un errore
- **Riconciliazione periodica**: verificare che le posizioni registrate localmente corrispondano davvero a quelle su Alpaca
- **Slippage e commissioni nel backtest**, per risultati realistici e non ottimistici
- **Filtro di liquidità minima**: evitare titoli scambiati troppo poco
- **Attenzione ai fusi orari**: il mercato USA segue l'orario di New York, Giacomo è in Italia
- **Limite di concentrazione massima per titolo** (es. 20-25% del capitale): perché uno stop loss stretto permette matematicamente posizioni molto grandi (visto nel test della Fase 2), quindi serve un secondo tetto indipendente dal calcolo del position sizing

## Ordine di costruzione concordato

1. Connessione ai dati Alpaca + calendario di mercato + storage SQLite di base
2. Risk management: position sizing, stop loss, limite di perdita complessivo (circuit breaker)
3. Configurazione sicura: separazione chiavi paper/live, segreti mai su GitHub
4. Prima strategia semplice su un solo timeframe, con logging contestuale (attenzione ai fusi orari)
5. Affidabilità: gestione errori di rete/retry, idempotenza ordini, riconciliazione periodica delle posizioni
6. Watchdog/heartbeat, kill switch manuale, notifiche (es. Telegram)
7. Deploy su Oracle Cloud + versionamento su GitHub
8. Raffinamenti: multi-timeframe, take profit frazionato, matrice di correlazione, limite di concentrazione massima per titolo, feed RSS, filtro di liquidità, slippage/commissioni nel backtest
9. Solo se e quando deciso: leva finanziaria e passaggio a conto reale (100-200€ per iniziare)

Ogni fase viene spiegata passo passo mentre la costruiamo: non serve sapere già programmare, il codice sarà commentato riga per riga.

## Stato attuale

- [x] Fase 1 — Connessione Alpaca + calendario di mercato + SQLite di base (`fase1_connessione_alpaca.py`, `database.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 2 — Risk management: stop loss, position sizing, circuit breaker giornaliero (`risk_management.py`, `fase2_demo_risk_management.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 3 — Prima strategia (incrocio di medie mobili) con logging contestuale (`fase3_strategia_sma.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 4 — Dal segnale all'ordine vero (paper trading): position sizing + circuit breaker + idempotenza degli ordini (client_order_id univoco) + retry sugli errori di rete + riconciliazione delle posizioni (`fase4_esecuzione_ordini.py`) — testata (parzialmente: non c'è ancora stato un vero BUY/SELL da verificare), pushata su GitHub
- [ ] Fase 6 — Kill switch manuale (`kill_switch.py`, file STOP.txt), battito cardiaco/watchdog (`database.py`, tabella `battiti_cuore`), notifiche Telegram (`notifiche.py`), tutto collegato dentro `fase4_esecuzione_ordini.py` — appena scritta, da testare (in particolare le notifiche Telegram richiedono di configurare TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nel `.env`)
- [ ] Fase 7 (Oracle Cloud), Fase 8 (raffinamenti), Fase 9 (leva/reale) — non ancora iniziate

## Come far girare il codice

Serve Python 3 installato sul tuo Mac (di solito c'è già; se non sei sicuro, dimmelo e controlliamo insieme).

```bash
cd "Trading Bot Azioni"
pip install -r requirements.txt
```

(Man mano che scriviamo gli script, li lanci con `python3 nome_dello_script.py`.)
