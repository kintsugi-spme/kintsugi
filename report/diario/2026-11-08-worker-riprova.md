# 2026-11-08 — Worker: riprova e coda dei falliti

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #34

## Cosa abbiamo fatto

Quando il database non risponde, il worker ritenta lo stesso ordine tenendolo con sé, come in D0003. Al posto della soluzione provvisoria della #33 (rimettere l'ordine in coda dopo 1 s).

| File | Cosa cambia |
|---|---|
| `app/worker.py` | `salva_con_riprova`: ogni tentativo ha 1,5 s; tra un tentativo e l'altro 0,5 s, poi 1, 2, 4, 8 s, poi ogni 10 s; dopo almeno 120 s l'ordine va in `ordini.falliti`. Tolta `ATTESA_DOPO_ERRORE_S` |
| `app/test_worker.py` | 6 prove senza servizi (attese, riprova riuscita, scrittura lenta, falliti, errore non temporaneo, arresto durante la riprova) e 2 con RabbitMQ e PostgreSQL veri |

## Perché

- **Un tentativo dura al massimo 1,5 s** (`asyncio.wait_for`): è il limite di D0003 per una scrittura troppo lenta. Senza, con il database fermo il worker aspetterebbe una connessione del pool fino a 30 s (limite predefinito, già visto nella #33).
- **Si ritentano solo gli errori temporanei** (D0003): database irraggiungibile, attesa del pool scaduta, connessione caduta, scrittura oltre 1,5 s. Ogni altro errore (per esempio un errore di programma) manda l'ordine subito tra i falliti: riprovarlo non lo cambierebbe. In entrambi i casi il log dice perché.
- **Il messaggio resta con il worker tra un tentativo e l'altro:** non è né confermato né rimesso in coda. Se il processo si ferma durante la riprova resta non confermato e RabbitMQ lo riconsegna a un altro worker (D0002); c'è una prova.
- **120 s contati dal primo tentativo, controllati dopo ogni tentativo fallito:** l'ordine è quindi rifiutato tra 120 e circa 130 s (nella prima prova da 150 s: 127–130 s).
- **Un ordine già salvato è un doppio** (D0004), come per qualsiasi consegna ripetuta. Una scrittura arrivata al database ma non confermata entro 1,5 s alla riprova risulta un doppio, e si conta in `duplicati`.
- **I valori sono costanti in `worker.py`,** non in `config/parametri.yaml`: i 120 s sono scritti anche in più documenti e cambieranno dopo F4, quindi la regola 2 del file li metterebbe lì. Collegarli richiede di passarli al worker (come `DEADLINE_S`) e ai manifest: lo lascio alla #41.

## Comandi e configurazione

```bash
# test con RabbitMQ e PostgreSQL veri (comandi completi in testa a app/test_worker.py)
TEST_BROKER_URL=amqp://prova:prova@127.0.0.1:5672/ \
  TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/kintsugi pytest -q

# V3 con Docker Compose (file della PR #64), database fermo e riavviato dopo un po'
make v3
docker compose -f base.yaml -f v3.yaml stop db      # poi, dopo 30, 60 o 150 s:
docker compose -f base.yaml -f v3.yaml start db
```

## Risultato

Test su Python 3.14: **68 superati** con RabbitMQ 4.4.0 e PostgreSQL 18.6 veri; 53 superati e 15 saltati senza (come nella CI).

V3 con Docker Compose (immagine costruita da questo codice, tre worker, client della #36). Sono prove di sviluppo, non misure (il Mac era molto carico da altre attività):

| Prova | Risultato |
|---|---|
| Database fermo 30 s, 600 ordini a 10/s | 600 × `202`, **600 salvati**, 0 doppi, 0 nei falliti |
| Database fermo 60 s, 600 ordini a 10/s (criterio 4 di M2) | 600 × `202`, **600 salvati, 0 persi**, 0 doppi, 0 nei falliti; primo ordine salvato 8,5 s dopo il riavvio |
| Database fermo circa 150 s, 300 ordini a 5/s (due prove) | in entrambe **297 salvati e 3 nei falliti** (uno per worker, rifiutati dopo circa 2 minuti); gli altri sono rimasti in coda e sono stati salvati dopo il riavvio. 300 su 300 contati |

Nei log del worker ogni tentativo scrive l'ordine, la causa, il numero del tentativo e quanto tempo è passato.

## Problemi e soluzioni

- **Doppi e timeout del client all'arresto del database:** nelle due prove da 150 s, appena dato `docker compose stop db`, per qualche secondo anche le richieste del client all'API (che non usa il database) sono andate in timeout (10 e 2). Alcuni ordini sono stati scritti ma non confermati entro 1,5 s, e alla riprova sono risultati doppi: 3 nella prima prova e 1 nella seconda, tutti contati in `duplicati`, nessun ordine perso. Non ho indagato la causa: il computer era molto carico per altre attività, che è la spiegazione più probabile. Nelle prove da 30 e 60 s non è successo.

## Limiti dello strumento emersi

- **psycopg_pool 3.3.3, riconnessione in background:** l'attesa tra un tentativo di riconnessione raddoppia (1, 2, 4… s) fino a `reconnect_timeout` (300 s) e non è configurabile. Il raddoppio è nel codice della libreria e non dipende dal carico del Mac; i secondi misurati variano da una prova all'altra. Dopo un fermo lungo il pool si riprende molto dopo il ritorno del database: **8,5 s** dopo un fermo di 60 s, ma **circa 36 s e 79 s** nelle due prove da 150 s (il primo ordine salvato). D0003 prevede «fino a 10 s», e questo ritardo entra nel tempo di recupero di V3. Le previsioni congelate dal tag `m1` non si toccano; la discrepanza va discussa prima di F4. Lo stesso pool è usato dall'API sincrona (V1, V2): non l'ho provato.
- **Log del pool rumorosi:** durante il fermo `psycopg_pool` scrive un avviso per ogni tentativo di connessione (`error connecting in 'pool-1'`), senza dire quale ordine riguarda.
