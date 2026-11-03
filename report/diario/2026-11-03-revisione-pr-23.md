# 2026-11-03 — Revisione della PR #23

**Chi:** Francesco · **Fase:** F1 · **Durata:** 1 h · **Issue:** #10, #20, #22

## Cosa abbiamo fatto

Gianmarco ha lasciato due review sulla PR #23: 9 commenti sul documento tecnico e 9 sulla relazione di sintesi. Li abbiamo discussi uno per uno e corretti.

**Documento tecnico**

| Punto | Esito |
|---|---|
| Costo sotto W2 | La finestra comune vale anche per V3 con 3 worker; corretto anche il cap. 3, che parlava di «due riferimenti» |
| Refuso | «Serve la stessa precisione» |
| Costo della replica sincrona (RQ4) | Si misura sul minuto di riferimento dei 20 run con guasto F4 su V4a e V4s (10 ripetizioni), nella latenza del client; i run senza guasti sono una verifica |
| Scalatura dei worker | Nuova riga $\mu_N = N\mu_1$ fino a 10 worker nella tabella delle ipotesi (documento e sintesi); criterio 5 di F4: capacità misurata con 1, 3 e 10 worker |
| RQ5 | «compromesso migliore tra coda massima e costo, durante un picco» invece di «a parità di costo», in 4 punti |
| AWS | «V2 e V3 con W1 e i guasti F1, F2 e F3; V3 anche con W2, senza guasti», in 3 punti |
| Diario del 02/11 | «Risultato» aggiornato a 220 run; durate a 1 h |

**Relazione di sintesi**

| Punto | Esito |
|---|---|
| T06 e T12 | Citazioni [1] e [2] con `\cite` e una sezione «Riferimenti» |
| Punto unico di guasto | È il punto d'ingresso, che in kind è il nodo del control plane |
| Codici delle decisioni | Tolti dal testo, con il paragrafo «Come leggere questo documento» |
| Sezione 6 | Eliminata; i fatti che stavano solo lì sono nel testo (riprova del worker, doppi, sonde, connessioni, KEDA, ambiente, collocazione) |
| Termini | Spiegati nodo, pod e Service |
| Tabella delle misure | Colonna «In parole»; ripristino e fermo separati per accettazione e completamento, come nel documento tecnico |
| Limiti | Introduzione con un esempio per categoria |

## Perché

- **Latenza del client per RQ4:** per D0005 `ts_scrittura` è l'istante dell'inserimento, non del commit, quindi l'attesa della replica sincrona non entra nel tempo end-to-end.
- **Nessuna previsione «V5 costa meno di V3 con 3 worker»:** con l'attesa di 60 s V5 costa circa 1350–1650 worker-secondi, vicino ai 1800 di V3 con 3 worker; dopo il tag `m1` non si potrebbe correggere.
- **Niente V3 con 2 worker:** +10 run per un confronto che comunque non sarebbe a costo uguale.
- **$\mu_N$ come riga della tabella:** segue la regola delle altre ipotesi (la previsione non si corregge, lo scarto si spiega).
- **Due ripristini anche nella sintesi:** con un solo $t_r$ il fermo di accettazione 0 di V3 nella tabella delle previsioni non si potrebbe calcolare.
- **Collocazione (D0006):** stava solo nella tabella della sezione 6, che è stata eliminata.

## Comandi e configurazione

```bash
cd docs && make
```

## Risultato

- Documento tecnico: 51 pagine, stessi avvisi di impaginazione di prima.
- Relazione di sintesi: 19 pagine, con la sezione «Riferimenti» su una pagina propria.
- Da fare per chiudere M1: approvazione di Gianmarco, poi tag `m1`; #10 (conferma dei valori principali).

## Problemi e soluzioni

- Con `thebibliography` la classe `report` apre un capitolo: nella sintesi l'ambiente usa una sezione, aggiunta all'indice.

## Limiti dello strumento emersi

Nessuno.
