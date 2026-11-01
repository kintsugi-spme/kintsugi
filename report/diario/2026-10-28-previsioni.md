# 2026-10-28 — Previsioni e valori dei carichi

**Chi:** Francesco · **Fase:** F1 · **Durata:** 3 h · **Issue:** #11

## Cosa abbiamo fatto

Scritte tutte le previsioni nel capitolo 8 del documento (versione 0.9) e fissati i valori che servivano per scriverle.

| Scelta | Esito |
|---|---|
| Forma delle previsioni | Formula + valori ipotizzati dichiarati come tali + relazioni attese tra versioni (es. «fermo V2 < fermo V1») |
| Istante di ripristino $t_r$ | È l'**inizio** dei 5 s stabili: i 5 s confermano il ripristino ma non entrano nel fermo. La figura «Anatomia di un fermo» lo disegnava alla fine: corretta |
| Sonde | **Veloci** in tutti i run; F7 si ripete con entrambe le configurazioni |
| Ipotesi di partenza | Rilevamento di un crash ~1 s, riavvio API 1–3 s, esclusione dal Service 1–2 s, riavvio PostgreSQL 3–8 s, riavvio RabbitMQ 5–15 s, riconnessione al broker 1–5 s, promozione dello standby 3–10 s, 2–3 scambi col DB per ordine |
| F4 su V4 | Si uccide il **processo principale del pod** del primario, non solo PostgreSQL, così il failover parte davvero |
| Tabella delle previsioni | Colonne aggiunte: persi e doppi; per V3 fermo separato tra accettazione e completamento |
| Ritmo di W1 (λ) | **Uguale per tutte le versioni**: 50% della capacità più bassa misurata in F4 tra V1, V2, V3, V4a, V4s |
| W2 e W3 | W2 rispetto alla capacità di un worker μ₁: base 50%, picco 500% (sopra 3 worker, sotto 10). W3 per versione: 150% della sua capacità |
| F5 | Latenza di **200 ms** per 60 s; timeout di scrittura del worker a 1,5 s |

Aggiunta anche la sezione 8.1 «Le grandezze in breve» (λ, μ, ρ, N, $t_g$, $t_r$, D) con tre esempi numerici semplici.

Riscritta e spostata in fondo al capitolo la sezione «Dal fermo alla disponibilità»: invece di ipotizzare l'MTBF, calcola quanti guasti al mese una versione sopporta prima di esaurire il budget di errore (43,2 min = 2592 s): `guasti sopportabili = 2592 s / D`. La formula con l'MTBF resta come nota; la frequenza dei guasti si chiama ora $f_i$, per non confonderla con λ (ritmo degli ordini).

Rileggendo l'intero documento sono emerse alcune incoerenze, raccolte nell'issue #20: tre (ripristino unico per accettazione e completamento, liveness o readiness in F7, tempi di rilevamento di F7) vanno corrette prima del tag `m1`.

## Perché

- **λ uguale per tutti:** se ogni versione ricevesse il 50% della propria capacità, il carico diventerebbe un secondo fattore che cambia e non si potrebbe attribuire la differenza tra V2 e V3 alla coda. Il prezzo è che V2 lavora a un'utilizzazione più bassa di V3: va dichiarato.
- **200 ms e non 500 ms:** Toxiproxy aggiunge la latenza a ogni scambio con il database (2–3 per ordine). Con 500 ms un ordine arriva a ~1,5 s, pari alla deadline dell'API: il sincrono fallirebbe quasi del tutto e F5 sarebbe un F4 travestito, invece di un degrado.
- **Timeout di scrittura del worker:** non era fissato. Se fosse sotto il ritardo di F5, ogni scrittura di V3 andrebbe in riprova e dopo 120 s finirebbe nella coda dei falliti.
- **Uccidere il pod in V4:** in CloudNativePG il processo principale del pod è il gestore dell'istanza, che potrebbe riavviare PostgreSQL sul posto senza failover.

## Comandi e configurazione

```bash
cd docs && make
```

## Risultato

- Tabella delle previsioni completa per tutte le celle della matrice (F1–F5, F7 su V1–V4); F6 facoltativo senza previsione.
- Relazioni attese scritte per RQ1–RQ6.
- Parametri aggiunti alla tabella unica: sonde usate nei run, ritmo di W1, latenza di F5, timeout di scrittura del worker.
- Da fare per chiudere M1: revisione e approvazione di Gianmarco, poi tag `m1`; #10 (valori principali).

## Problemi e soluzioni

- La figura dell'anatomia di un fermo contraddiceva la definizione di «ripristinato» (5 s di differenza sul fermo): corretta la figura, il testo era giusto.
- Previsione onesta su RQ4: su kind il failover di V4 potrebbe non essere più rapido del semplice riavvio del database di V2.

## Limiti dello strumento emersi

- Toxiproxy aggiunge la latenza a ogni scambio e non a ogni ordine: l'effetto di F5 dipende da quanti scambi fa l'applicazione per ordine. Da tenere fisso in F2.
