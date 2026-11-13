# 2026-11-12 — Documenti: Kubernetes in breve, minacce del guasto F1, grafici

**Chi:** Francesco · **Fase:** F3 · **Durata:** 2 h · **Issue:** #91

## Cosa abbiamo fatto

- «Kubernetes in breve» prima delle versioni, nel documento di architettura (sezione 3.1) e nella sintesi (2.1): stato voluto, control plane, nodi worker e quale parte ripara ciascun guasto. Schema unico in `docs/figure/kubernetes.tex`, sei termini nuovi tra gli acronimi.
- Tre minacce alla validità emerse provando il guasto F1 (#84), nel capitolo 9 e nei limiti della sintesi: back-off dei riavvii, orologio della macchina virtuale di Docker, margine sull'istante del guasto. La tabella del capitolo 9 diventa `longtable`.
- Grafico dei moduli della sintesi rifatto a strati, con i collegamenti presi dagli `import` reali.
- `report/presentazione/grafici/kintsugi.drawio` per le slide; in `.gitignore` la cartella versiona solo i `.drawio`.
- Versioni: documento di architettura 0.11, sintesi 0.3.

Dopo la revisione di Gianmarco (PR #92):
- **Margine sull'istante del guasto:** «da pochi millisecondi a oltre cento su un computer carico», non «decine di millisecondi». Sul Mac da 16 GB delle misure (D0013) Gianmarco l'ha misurato in 1,5–3,8 ms; i 13–134 ms erano del Mac da 8 GB.
- **Didascalia del grafico dei moduli:** ora dice che le frecce piene sono i collegamenti principali e nomina gli import usati solo all'avvio che non sono disegnati (`main.py` verso `db.py` e `broker.py`, `servizio.py` verso `config.py`). Le etichette «async» e «chiama `salva()`» hanno uno sfondo bianco e non coprono più le frecce.
- Conflitto con `main` in `.gitignore`: tenute entrambe le regole (`deploy/k8s/base/parametri.env` della #88 e la cartella della presentazione).

## Perché

Chi legge, e chi ascolta all'orale, deve sapere come funziona Kubernetes per capire perché i guasti si riparano in tempi diversi. Le tre minacce cambiano il modo di fare il reset e di calcolare il fermo, quindi vanno nel documento e non solo nel diario.

## Comandi e configurazione

```bash
cd docs
make controlla
make            # documento di architettura
latexmk -pdf main-sintesi.tex
```

## Risultato

I due PDF compilano senza errori né rimandi rotti; pagina del grafico dei moduli controllata a vista.

## Problemi e soluzioni

Nessuno.

## Limiti dello strumento emersi

Nessuno.
