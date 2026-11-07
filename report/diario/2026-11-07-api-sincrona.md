# 2026-11-07 — API sincrona e deadline (V1, V2)

**Chi:** Francesco · **Fase:** F2 · **Durata:** 2 h · **Issue:** #30, #31

## Cosa abbiamo fatto

Con `MODE=sync` l'API salva l'ordine nel database e risponde `201` solo dopo il salvataggio. Se non ci riesce entro `DEADLINE_S` risponde `503`. Così V1 e V2 funzionano. V2 non richiede codice: è V1 in più copie sullo stesso database.

| File | Cosa cambia |
|---|---|
| `app/servizio.py` | `accetta_ordine` con `MODE=sync` chiama `salva`, la stessa funzione del worker. Una sola regola di deadline per i due modi |
| `app/main.py` | con `MODE=sync` apre il pool di 5 connessioni (D0010) all'avvio, senza aspettare il database; il worker usa lo stesso codice |
| `app/api.py` | l'endpoint esiste in ogni API: `201` «salvato» con `MODE=sync`, `202` «ricevuto» con `MODE=async` |
| `app/config.py` | con `MODE=sync`, `DATABASE_URL` è obbligatorio |
| Test e CI | `test_ordini.py` con un `salva` finto, `test_api_sincrona.py` (nuovo) con PostgreSQL vero, job «Immagine» con l'indirizzo del database |

## Perché

- **Stessa funzione di salvataggio per API e worker (D0012):** tempi e doppi si misurano nello stesso modo in tutte le versioni.
- **Il 503 non aspetta la fine del lavoro annullato:** `asyncio.wait_for` aspetterebbe, e con il database congelato la risposta arrivava dopo 11,5 s (vedi sotto). La deadline di D0008 serve proprio a non far scadere il client a 2 s.
- **`DATABASE_URL` obbligatorio con `MODE=sync`:** senza, ogni ordine riceverebbe `503` e il problema si vedrebbe solo nei risultati.

## Comandi e configurazione

```bash
# test con PostgreSQL vero (comandi completi in testa a app/test_db.py)
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/kintsugi pytest -q

# V1 e V2: due copie dell'API sullo stesso database, in una rete Docker
docker run -d --name api1 --hostname api1 --network kintsugi-prova -p 8001:8000 \
  -e MODE=sync -e DEADLINE_S=1.5 -e DATABASE_URL=postgresql://postgres@db:5432/kintsugi kintsugi:<hash>
docker run -d --name api2 --hostname api2 ... -p 8002:8000 ...   # stessa configurazione
docker pause db; docker unpause db    # database congelato (come SIGSTOP)
docker kill db                        # database ucciso (SIGKILL)
```

## Risultato

Prove con l'immagine, database e API in container sulla stessa rete Docker:

| Prova | Risultato |
|---|---|
| Un ordine a V1 | `201` |
| Criterio 2 di M2: tempo di servizio 0,2 s, 20 ordini senza carico | end-to-end min 0,2019 s, mediana 0,2043 s, max 0,2333 s |
| Criterio della #31: tempo di servizio 3 s, deadline 1,5 s | `503` dopo 1,518 s, ordine non salvato |
| V2: 200 ordini su api1 e api2, 20 alla volta | 200 `201`, 200 righe |
| V2: lo stesso identificativo a api1 e api2 insieme, 50 volte | sempre due `201`; 50 ordini e 50 doppi, registrati da entrambe le copie |
| Database congelato, 8 ordini insieme (più delle 5 connessioni) | 8 `503` a 1,52-1,53 s; `/readyz` `200`; nessuno degli 8 nel database |
| Database scongelato | `201` subito, 4-15 ms |
| Database ucciso e ricreato | `503` a 1,53 s; al ritorno il primo ordine `201` in 1,1 s, poi 4-15 ms |

Test: 43 passano, gli altri si saltano senza RabbitMQ e PostgreSQL; con PostgreSQL vero passano anche `test_api_sincrona.py` e `test_db.py`.

## Problemi e soluzioni

- **Deadline non rispettata con il database congelato:** `503` dopo 11,5 s invece di 1,5 s. Alla deadline `asyncio.wait_for` annulla il salvataggio e ne aspetta la fine. psycopg, annullato a metà di una query, prova per 5 s ad annullarla sul server e poi aspetta altri 5 s che finisca (`connection_async.py`, `_wait_conn`): con il server congelato, 1,5 + 5 + 5 = 11,5 s. Con il database ucciso il problema non c'è, perché la connessione cade subito. Ora il `503` parte alla deadline e la pulizia continua in sottofondo. Un test con un salvataggio finto che impiega 2 s a finire dopo l'annullamento falliva prima della correzione e passa dopo.
- **Orologio di Docker indietro di 11,6 ms rispetto al Mac:** con l'API sul Mac e il database in Docker, `ts_scrittura - ts_ricezione` era 0,195 s con un tempo di servizio di 0,2 s. Lo sfasamento era previsto da D0005; qui è misurato (5 campioni, tutti tra -11,1 e -11,7 ms). `test_api_sincrona.py` lo misura e lo sottrae. Nelle prove con l'immagine API e database sono nella stessa macchina virtuale, quindi l'orologio è uno solo.
- **Un ordine respinto con `503` può essere già nel database:** se la deadline scade dopo che la query è arrivata al server. Nelle prove non è successo, ma il client lo conterà come una categoria a parte (#37).

## Limiti dello strumento emersi

- psycopg 3.3: annullare una query in corso con il server che non risponde richiede fino a 10 s, e i due tempi non sono configurabili.
- Docker Desktop: l'orologio della macchina virtuale non coincide con quello di macOS (11,6 ms il 07/11/2026).
