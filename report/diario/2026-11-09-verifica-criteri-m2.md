# 2026-11-09 — Verifica dei quattro criteri di M2

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #38

## Cosa abbiamo fatto

Abbiamo eseguito i quattro criteri di F2 (`report/fasi-e-milestone.md`) con `docker-compose` (#35), il client (#36) e lo script delle categorie (#37), sul codice di `main` al commit `cec0724` (contiene la riprova del worker, #34). Ogni run ha esportato `db.csv`, `duplicati.csv` e `falliti.csv` **prima** di qualsiasi rielaborazione dei falliti, poi `python analysis/categorie.py <cartella>`.

| Criterio | Come | Risultato |
|---|---|---|
| 1. Con 100 ordini ne risultano 100 «completati in tempo» in V1, V2 e V3 | 100 ordini a 10/s con tempo di servizio 0,2 s, una versione alla volta | V1, V2, V3: **100 × «completato in tempo»**, 0 duplicati; V1 e V2 rispondono `201`, V3 `202` |
| 2. Senza carico il tempo end-to-end è pari al tempo di servizio, entro pochi ms | 10 ordini a 1/s con tempo di servizio 0,2 s; `ts_scrittura − ts_ricezione` da `db.csv` | scarto dal tempo di servizio (mediana, minimo e massimo su 10 ordini): V1 +4,9 ms (da +2,7 a +9,4); V2 +5,8 ms (da +3,2 a +10,8); V3 +9,0 ms (da +4,7 a +18,9). Soddisfatto in tutte e tre con la soglia spiegata nel Risultato |
| 3. Lo stesso messaggio mandato due volte in V3 è rifiutato **e contato** | stesso ID in due `POST` | 2 × `202`; nel database **1 ordine e 1 doppio** (in `duplicati`); nessun ordine nei falliti |
| 4. Con il database fermo 60 s in V3, a fine run gli ordini persi sono 0 | 600 ordini a 10/s; `docker compose stop db` dopo 10 s, `start db` dopo altri 60 s | 600 × `202`; **600 su 600 salvati, 9 s dopo il riavvio del database**; **600 × «completato in tempo»**, 0 persi, 0 nei falliti, coda vuota |

## Perché

- **Tempo di servizio 0,2 s nei criteri 1 e 2:** con 0 s il criterio 2 non distinguerebbe il tempo di servizio dal resto. 10 ordini/s bastano a tenere V1 a 2 richieste in corso su 5 connessioni del pool (D0010): il criterio 1 non è una prova di carico.
- **Criterio 4 con tempo di servizio 0:** per poter confrontare con la prova del database fermo fatta nella #35.
- **Esportazione prima della rielaborazione dei falliti:** `data/README.md` spiega perché; in questi run i falliti erano comunque 0.
- **`falliti.csv` letto con `get` senza conferma** dal container del worker, in modo che i messaggi tornino in coda e la prova non cambi lo stato.

## Comandi e configurazione

```bash
cd deploy/compose
make v3 SERVICE_TIME_S=0.2          # oppure v1, v2
python3 ../../harness/client/cliente.py --url http://localhost:8000/ordini \
    --richieste 100 --ritmo 10 --timeout 2 --uscita <cartella>/client.csv
# db.csv e duplicati.csv: \copy da PostgreSQL (docker compose exec db psql ...)
# falliti.csv: i messaggi di «ordini.falliti», letti senza conferma
python3 ../../analysis/categorie.py <cartella>
docker compose -f base.yaml -f v3.yaml stop db   # criterio 4: poi start db dopo 60 s
```

## Risultato

I quattro criteri di F2 sono soddisfatti. Un ordine non è mai stato perso né è finito nei falliti in nessuno degli otto run, e lo script delle categorie è uscito con codice 0 ogni volta.

**Come si giudica il criterio 2.** Il documento dice «entro pochi millisecondi» senza un numero, ma una soglia esiste già: `app/test_api_sincrona.py` (criterio 2 di M2) chiede `S ≤ end-to-end < S + 10 ms`, ed è stata scritta il 07/11, prima di questi dati. Qui si giudica la **mediana** dello scarto e non il massimo, perché un singolo ordine lento dipende dal computer e non dall'app:

| Versione | Soglia sulla mediana dello scarto | Mediana misurata | Massimo misurato | Esito |
|---|---|---|---|---|
| V1 | 10 ms (già scritta nel test) | +4,9 ms | +9,4 ms | soddisfatto |
| V2 | 10 ms (già scritta nel test) | +5,8 ms | +10,8 ms | soddisfatto |
| V3 | 20 ms | +9,0 ms | +18,9 ms | soddisfatto |

**La soglia di V3 è stata fissata dopo aver visto i dati.** In V3 l'intervallo comprende anche la coda e la presa in carico del worker, quindi 10 ms non è la soglia giusta per quel percorso. Il criterio di passaggio di F2 non è una previsione del capitolo 8, che non si tocca. Il lettore può controllare da sé che non è stata scelta per far passare il risultato: la mediana di V3 (+9,0 ms) sarebbe sotto anche la soglia di 10 ms, e il massimo (+18,9 ms) sotto i 20 ms.
**Seconda verifica.** Francesco ha rifatto i quattro criteri sul suo Mac (8 GB, Docker a 5 GB), sullo stesso commit: passano tutti, con una mediana dello scarto in linea con la nostra (V1 5-8 ms, V2 7-8 ms, V3 12-18 ms). Sul suo computer, con il Mac carico, i massimi arrivavano a 324 ms: per questo la mediana è la misura giusta. Il criterio 3 l'ha provato anche con lo stesso messaggio pubblicato due volte sulla coda.

## Problemi e soluzioni

Nessuno: ogni versione è partita al primo tentativo e `make giu` ha lasciato i container di kind al loro posto.

## Limiti dello strumento emersi

- **La categoria «in dead-letter» non è stata esercitata con dati veri:** in tutti i run i falliti erano 0. Lo script è provato solo dai suoi test (#66). Per vederla con dati veri serve un fermo del database più lungo di 120 s in V3.
- **Il criterio 3 è provato in due modi:** con due richieste del client (questo run) e con lo stesso messaggio pubblicato due volte sulla coda (`test_lo_stesso_messaggio_due_volte_e_salvato_una_volta_e_contato` in `app/test_worker.py`, che gira nella CI dalla #67, e una prova a mano di Francesco del 10/11). In entrambi i casi: un ordine e un doppio.
- **Se il Mac va in stop durante un run, quel run non vale.** Durante la verifica di Francesco il Mac è andato in stop per 15 minuti a metà di un run del criterio 2: due timeout, risposte da 1-2 s al risveglio e, nel run successivo, uno scarto **negativo** (−3,8 ms), impossibile con un orologio solo, perché al risveglio Docker Desktop riallinea l'orologio della sua macchina virtuale. Rilanciando con `caffeinate -i` non è più successo. Vale anche per la campagna sul Mac delle misure (D0013): i run lunghi si lanciano con `caffeinate -i`.
- **Un solo run per criterio,** sul MacBook M5 con altri container accesi (cluster kind e altri progetti): vale come verifica del funzionamento, non come misura.
