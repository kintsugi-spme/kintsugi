# 2026-11-03 — Una sola fonte per i numeri del progetto

**Chi:** Gianmarco · **Fase:** F1 · **Durata:** 4 h · **Issue:** #41

## Cosa abbiamo fatto

Messo i numeri che definiscono gli esperimenti in un solo file e fatto in modo che documento, relazione di sintesi e piano li leggano da lì, invece di ripeterli a mano.

| Cosa | Dove |
|---|---|
| File dei valori: 30 numeri più la matrice dei run | `config/parametri.yaml` |
| Perché sta lì e dove si usa | `config/README.md` |
| Script (circa 170 righe): `genera` scrive le macro LaTeX, `controlla [--fix]` verifica i numeri nei Markdown, `elenca` mostra chiavi e valori | `docs/scripts/parametri.py` |
| `make` rigenera le macro prima di compilare; `make controlla` | `docs/Makefile` |
| Caricamento delle macro | `docs/config/preambolo.tex` |
| Le macro generate non si versionano | `.gitignore` |
| Uso e regole | `docs/README.md`, riga `config/` nel `README.md` |

**Sostituzioni:** 53 in 12 file. Nei file LaTeX il numero è diventato `\parametro{chiave}`; in `README.md` (6 punti) e `report/fasi-e-milestone.md` (2 punti) il numero è tra due marcatori (`<!-- num:chiave -->…<!-- /num -->`) che lo script confronta con il file dei valori.

| Valore | Punti collegati |
|---|---|
| Totale dei run (220) | 6 file (il settimo, lo storico delle revisioni, è escluso) |
| Ore della campagna (22) | 3 file |
| Timeout del client (2 s), deadline dell'API (1,5 s), limite di completamento (2 s) | 3 + 5 + 4 punti |
| Soglia del 99% al secondo | 7 punti |
| Obiettivo di disponibilità (99,9% su 30 giorni) e budget di errore (43,2 minuti, ora calcolato) | 3 file |
| Tetti dei run (10 e 15 minuti) | 5 + 5 punti |
| Carichi W1, W2, W3 (50%, 500%, 150%) e durata del picco di W2 (60 s) | 10 + 4 punti |
| Valori di KEDA (15 s, 30 s, 2 s di lavoro per worker, attesa di 60 s) | 7 punti |

Non toccati, di proposito: previsioni (`08-previsioni.tex`, `sintesi/05-previsioni.tex`), schede delle decisioni, storico delle revisioni (`scheda-documento.tex`) e diario.

## Perché

Le incoerenze dell'issue #20 e di gran parte della PR #23 avevano una sola causa: lo stesso numero scritto a mano in molti file. Il totale dei run (220) compariva in 7 file, le ore della campagna in 4; passando da 245 a 250 a 220 in due giorni bisognava cercarli tutti. Inoltre molti valori si fissano dopo F4 (capacità misurata, ritmo di W1, soglia di KEDA, soglia di CPU, forse la durata del riscaldamento) e cambieranno ancora.

Scelte:
- **Una sola macro `\parametro{chiave}`** invece di una macro per numero: i nomi di macro LaTeX non possono contenere cifre né `_`, e inventarne 30 diversi sarebbe stato fragile. La chiave è la stessa del file dei valori; una chiave sbagliata dà errore alla compilazione.
- **Una chiave per significato, non per numero.** Il «2 s» è tre valori diversi (timeout del client, limite di completamento, soglia di KEDA) e il «60 s» ne è altri due: potrebbero cambiare separatamente. Per lo stesso motivo non sono collegati i numeri uguali ma con un altro significato (l'«1,5 s» di `05-guasti.tex`, i «10 minuti» della finestra di costo di W2).
- **Il totale dei run non è scritto:** lo script lo calcola sommando ripetizioni × configurazioni di ogni gruppo. Lo stesso vale per il budget di errore.
- **Il file sta in `config/` alla radice**, non in `docs/`: sono parametri degli esperimenti, e in F4 potrebbe leggerli anche il banco di misura.
- **Niente macro dove il testo è congelato o è storia:** le previsioni sono scritte prima di misurare e non devono cambiare se cambia un parametro; le schede delle decisioni e lo storico delle revisioni registrano cosa era vero in quel momento (un «run da 250 a 220» non deve diventare «da 250 a 200»). Per previsioni e diario l'accordo c'è; per decisioni e storico è una proposta da confermare con Francesco.
- **Script e sostituzione nella stessa PR:** sono la stessa attività.
- **Le macro generate non si versionano** (come i PDF): `make` le rigenera.

## Comandi e configurazione

```bash
git switch -c docs/parametri-fonte-unica --no-track origin/main
python3 -m venv .venv && source .venv/bin/activate  # ambiente isolato, ignorato da git
pip install pyyaml                                  # serve allo script; una volta sola
export PATH=/opt/homebrew/Cellar/texlive/20260301_2/bin:$PATH
make -C docs                                        # rigenera parametri.tex e compila i due PDF
make -C docs controlla                              # confronta i numeri marcati nei Markdown
python3 docs/scripts/parametri.py elenca            # chiavi e valori
pdftotext -layout docs/main.pdf prima.txt           # testo del PDF, per il confronto prima/dopo
```

## Risultato

- I due PDF escono con testo **identico** a prima (confronto con `pdftotext` su entrambi); gli avvisi di LaTeX rimasti sono 4, tutti sulla dimensione delle figure.
- `make controlla` verifica 9 numeri (6 nel README, 2 nel piano, 1 nell'esempio di `docs/README.md`): tutti corretti. Provato anche con un numero sbagliato (viene segnalato con file e riga) e con `--fix` (lo riscrive; un «220 mm» fuori dai marcatori non viene toccato).
- Prova con PyYAML vero (6.0.3, in un ambiente `.venv`): `make clean` e poi `make` ricostruiscono da zero i due PDF, il testo è ancora identico a quello di partenza e `make controlla` verifica 9 numeri corretti.
- Una chiave inesistente dà errore sia in LaTeX («Parametro sconosciuto») sia nel controllo dei Markdown.
- Il branch è stato aggiornato con `main` dopo l'unione della PR #40 (licenze) con un avanzamento rapido, senza conflitti.

Restano scritti a mano, e sono candidati a nuove chiavi: «database fermo per 60 s» (3 punti), latenza del guasto F5, «200 ms per 60 s» (3 punti), sonde «ogni 2 s» (4 punti). La matrice, in F4, potrà essere letta dal banco di misura.

## Problemi e soluzioni

- Un esempio di marcatore scritto in un Markdown viene letto come un marcatore vero. Quello in `docs/README.md` è controllato come gli altri (e oggi è corretto); nel `config/README.md` l'esempio è stato riformulato per non farsi leggere come un numero con una chiave inesistente.
- Stesso numero, significati diversi (vedi sopra): ogni punto è stato letto nel suo contesto prima di collegarlo, non sostituito in blocco.

## Limiti dello strumento emersi

- **PyYAML non fa parte della libreria standard di Python** e sul Mac non era installato: serve un `pip install pyyaml` (in un ambiente `.venv`, perché fuori da un ambiente `pip` di solito rifiuta). Per Python 3.15, molto recente, non c'era un pacchetto già pronto e `pip` lo ha compilato da solo. Prima dell'installazione lo script era stato provato con un sostituto basato su Ruby; poi è stato ripetuto con PyYAML vero.
- **Il controllo dei Markdown vede solo i numeri marcati:** un numero scritto a mano senza marcatori non viene controllato. Per questo servono i marcatori su tutti i punti noti.
- **Il percorso di LaTeX non è nel `PATH` della shell:** va aggiunto prima di `make`.
