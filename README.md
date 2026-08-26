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
- Non deve girare sul PC di Giacomo → **inizialmente pensato per Oracle Cloud (Always Free tier), poi passato a GitHub Actions** perché Giacomo non ha una carta di credito/debito da usare per la verifica di Oracle (vedi Fase 7)
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
7. Deploy per farlo girare da solo H24 — inizialmente pensato per Oracle Cloud, **passato a GitHub Actions** (schedule automatico, gratuito, senza carta di credito)
8. Raffinamenti: multi-timeframe, take profit frazionato, matrice di correlazione, limite di concentrazione massima per titolo, feed RSS, filtro di liquidità, slippage/commissioni nel backtest
9. Solo se e quando deciso: leva finanziaria e passaggio a conto reale (100-200€ per iniziare)

Ogni fase viene spiegata passo passo mentre la costruiamo: non serve sapere già programmare, il codice sarà commentato riga per riga.

## Stato attuale

- [x] Fase 1 — Connessione Alpaca + calendario di mercato + SQLite di base (`fase1_connessione_alpaca.py`, `database.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 2 — Risk management: stop loss, position sizing, circuit breaker giornaliero (`risk_management.py`, `fase2_demo_risk_management.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 3 — Prima strategia (incrocio di medie mobili) con logging contestuale (`fase3_strategia_sma.py`) — testata, funzionante, pushata su GitHub
- [x] Fase 4 — Dal segnale all'ordine vero (paper trading): position sizing + circuit breaker + idempotenza degli ordini (client_order_id univoco) + retry sugli errori di rete + riconciliazione delle posizioni (`fase4_esecuzione_ordini.py`) — testata (parzialmente: non c'è ancora stato un vero BUY/SELL da verificare), pushata su GitHub
- [ ] Fase 6 — Kill switch manuale (`kill_switch.py`, file STOP.txt), battito cardiaco/watchdog (`database.py`, tabella `battiti_cuore`), notifiche Telegram (`notifiche.py`), tutto collegato dentro `fase4_esecuzione_ordini.py` — appena scritta, da testare (in particolare le notifiche Telegram richiedono di configurare TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nel `.env`)
- [x] Fase 7 — Deploy H24 con **GitHub Actions** (`.github/workflows/trading-bot.yml`): schedule automatico ogni 15 minuti nell'orario di mercato USA (in UTC, con margine per l'ora legale), esecuzione manuale disponibile (`workflow_dispatch`), `bot.db` salvato nel repository ad ogni esecuzione perché i runner di GitHub sono temporanei — secrets configurati, test manuale eseguito con successo (bot ha correttamente riconosciuto il mercato chiuso e non ha fatto nulla), schedule automatica attiva; in monitoraggio nei prossimi giorni
- [ ] Fase 8 (raffinamenti) — IN CORSO, un pezzo alla volta:
  - [x] Feed RSS per le news (`fase8_feed_rss.py`, tabella `notizie` in `database.py`) — testato con successo, scarica e salva le notizie reali su AAPL da Google News RSS, senza duplicati; per ora solo di contesto/lettura, non influenza ancora le decisioni del bot
  - [x] Limite di concentrazione massima per titolo (`risk_management.py`: `applica_limite_concentrazione()`, tetto di default 25%; collegato dentro `fase4_esecuzione_ordini.py` prima di ogni ordine BUY) — testato: conferma che perfino con lo stop loss di default il position sizing basato solo sul rischio suggerirebbe il 66% del portafoglio su un solo titolo, esattamente quanto notato nel test della Fase 2; il nuovo tetto lo riduce correttamente
  - [x] Filtro di liquidità minima (`fase3_strategia_sma.py`: `scarica_volume_medio()`; `risk_management.py`: `verifica_liquidita_sufficiente()`, soglia di default 500.000 azioni/giorno; collegato in `fase4_esecuzione_ordini.py` prima di ogni ordine BUY, non su SELL così si può sempre chiudere una posizione già aperta) — testato: con AAPL (decine di milioni di azioni/giorno) il filtro passa sempre, servirà davvero quando proveremo titoli meno scambiati
  - [x] Take profit frazionato (`take_profit.py`, nuove tabelle `posizioni_aperte`/`take_profit_eseguiti` in `database.py`, collegato in `fase4_esecuzione_ordini.py` come "Passo 2bis") — vende un terzo della posizione a +3%, un altro terzo a +6%, il resto a +10% di guadagno, indipendentemente dal segnale della strategia di quel giorno; ogni livello scatta una volta sola per posizione (idempotenza), e i livelli ripartono da zero se si richiude e riapre la posizione — testato con una simulazione completa (rialzo graduale, ricontrollo allo stesso prezzo, salto di più livelli insieme, chiusura e riapertura posizione)
  - [x] Matrice di correlazione tra titoli (`fase8_matrice_correlazione.py`, tabella `correlazioni` in `database.py`) — scarica lo storico di AAPL + un piccolo paniere di confronto (MSFT, GOOGL, AMZN), calcola la correlazione tra i rendimenti giornalieri con pandas, ed evidenzia le coppie molto correlate (sopra soglia 0.8 in valore assoluto); per ora solo informativo/di contesto come il feed RSS, non cambia ancora le decisioni del bot (che gestisce un solo titolo alla volta) — testato con dati sintetici a correlazione nota (positiva forte, negativa forte, indipendente)
  - [ ] Analisi multi-timeframe
  - [ ] Slippage e commissioni nel backtest
- [ ] Fase 9 (leva/reale) — non ancora iniziata

## Come far girare il codice

Serve Python 3 installato sul tuo Mac (di solito c'è già; se non sei sicuro, dimmelo e controlliamo insieme).

```bash
cd "Trading Bot Azioni"
pip install -r requirements.txt
```

(Man mano che scriviamo gli script, li lanci con `python3 nome_dello_script.py`.)
