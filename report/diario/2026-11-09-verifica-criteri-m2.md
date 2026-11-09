# 2026-11-09 — Verifica dei quattro criteri di M2

**Chi:** Gianmarco · **Fase:** F2 · **Durata:** 0,5 h · **Issue:** #38

## Cosa abbiamo fatto

Abbiamo eseguito i quattro criteri di F2 (`report/fasi-e-milestone.md`) con `docker-compose` (#35), il client (#36) e lo script delle categorie (#37), sul codice di `main` al commit `cec0724` (contiene la riprova del worker, #34). Ogni run ha esportato `db.csv`, `duplicati.csv` e `falliti.csv` **prima** di qualsiasi rielaborazione dei falliti, poi `python analysis/categorie.py <cartella>`.

| Criterio | Come | Risultato |
|---|---|---|
| 1. Con 100 ordini ne risultano 100 «completati in tempo» in V1, V2 e V3 | 100 ordini a 10/s con tempo di servizio 0,2 s, una versione alla volta | V1, V2, V3: **100 × «completato in tempo»**, 0 duplicati; V1 e V2 rispondono `201`, V3 `202` |
| 2. Senza carico il tempo end-to-end è pari al tempo di servizio, entro pochi ms | 10 ordini a 1/s con tempo di servizio 0,2 s; `ts_scrittura − ts_ricezione` da `db.csv` | scarto dal tempo di servizio: V1 da +2,7 a +9,4 ms; V2 da +3,2 a +10,8 ms; V3 da +4,7 a +18,9 ms |
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

Il criterio 2 è soddisfatto in V1 e V2 (scarto massimo circa 10 ms); in V3 lo scarto massimo è 18,9 ms, perché l'intervallo comprende anche la coda e la presa in carico del worker. Nel documento il criterio dice «entro pochi millisecondi», senza un numero: se serve una soglia scritta, va decisa.

## Problemi e soluzioni

Nessuno: ogni versione è partita al primo tentativo e `make giu` ha lasciato i container di kind al loro posto.

## Limiti dello strumento emersi

- **La categoria «in dead-letter» non è stata esercitata con dati veri:** in tutti i run i falliti erano 0. Lo script è provato solo dai suoi test (#66). Per vederla con dati veri serve un fermo del database più lungo di 120 s in V3.
- **Il criterio 3 è provato con due richieste del client,** non facendo rimandare al broker lo stesso messaggio due volte: nel database il risultato è lo stesso (un ordine e un doppio), perché il rifiuto lo decide la chiave primaria.
- **Un solo run per criterio,** sul MacBook M5 con altri container accesi (cluster kind e altri progetti): vale come verifica del funzionamento, non come misura.
