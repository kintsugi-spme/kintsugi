# 2026-11-14 — Harness minimo: carico a ritmo fisso e controllo del ritmo

**Chi:** Gianmarco · **Fase:** F3 · **Durata:** 1 h · **Issue:** #83

## Cosa abbiamo fatto

- `analysis/ritmo.py`: dal `client.csv` controlla che il ritmo inviato resti entro la tolleranza da quello chiesto, sia in media sia in ogni finestra di 10 s. Esce con codice 1 se non è così. Prove in `analysis/test_ritmo.py`.
- `harness/client/cliente.py`: nuova opzione `--durata` (secondi) al posto di `--richieste`, perché il criterio è scritto in tempo («50 ordini/s per 3 minuti»). Il resto c'era già dalla F2: modello aperto e una riga di log per richiesta.
- `config/parametri.yaml`: nuova chiave `carichi.ritmo_tolleranza_percentuale` (5). Il ±5% era scritto a mano in quattro punti (capitoli «Protocollo di misura» e «Minacce alla validità», relazione di sintesi, `report/fasi-e-milestone.md`): ora lo leggono da lì.
- README (albero delle cartelle) e `config/README.md` (tabella «Dove si usa»).

## Perché

Il capitolo «Protocollo di misura» chiede, per ogni run, che il ritmo inviato resti entro ±5% di quello previsto, anche durante il guasto: un generatore a modello chiuso smetterebbe di inviare proprio lì.

- **Dal log, non dal client.** Il controllo legge gli istanti di invio scritti in `client.csv`, che avrà le stesse colonne anche con il generatore di F4: la verifica servirà ancora.
- **Anche a finestre.** Cinque secondi senza invii in un run di 3 minuti spostano la media di meno del 3%, ma nelle finestre che li contengono il ritmo cala di un quarto o più.
- **Finestra di 10 s.** A 50 richieste/s ne contiene 500: l'arrotondamento di una o due non conta e poco più di mezzo secondo senza invii supera il 5%. È una scelta di questa issue, da riconfermare con il generatore di F4. L'ultimo tratto, più corto di una finestra, conta solo nella media.
- **Solo ritmo costante** (W1, W3): W2 ha un profilo con base e picco.

## Comandi e configurazione

```bash
python harness/client/cliente.py --url http://localhost:8080/ordini --durata 180 --ritmo 50 --uscita data/<ambiente>/<run-id>/client.csv
python harness/faults/arresto.py --cartella data/<ambiente>/<run-id>   # a 90 s dall'inizio
python analysis/ritmo.py data/<ambiente>/<run-id> --ritmo 50
```

La cartella del run va creata prima. La tolleranza si legge da `config/parametri.yaml`; `--tolleranza` e `--finestra` la cambiano.

## Risultato

Prova su V2 (tre copie dell'API, `make v2` della #75), con una copia uccisa a 90 s dall'inizio con `arresto.py` (SIGKILL dal nodo, riavviata nello stesso pod):

- 9000 richieste in 180,1 s: 8998 × `201` e 2 errori. Le 2 richieste fallite per il guasto, secondo `fermo.py`, sono queste. Nel database ci sono gli 8998 ordini del run (e uno di una richiesta di prova fatta prima), 0 doppi.
- `ritmo.py`: ritmo medio 50,00 richieste/s (scarto +0,0%), 17 finestre da 10 s, scarto massimo +0,0%. La finestra del guasto (dal 90° al 100° s) ha 500 richieste come le altre. Con finestre da 1 s (179) lo scarto massimo è lo stesso.
- Lo stesso log con `--ritmo 55` (un ritmo chiesto sbagliato): scarto −9,1% in media e in tutte le 17 finestre, codice di uscita 1.
- Nelle prove, un buco di 5 s in 180 s dà −2,8% in media (dentro la tolleranza) e −50% nella finestra che lo contiene (fuori).
- Per vedere che la catena client, guasto e calcolo gira, `fermo.py` sullo stesso log dà fermo 0,115 s con 2 richieste fallite. È una sola prova: la misura del fermo è della #86.

## Problemi e soluzioni

Nessuno.

## Limiti dello strumento emersi

Nessuno nuovo.
