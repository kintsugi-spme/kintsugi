# Valori numerici del progetto

`parametri.yaml` contiene i numeri che definiscono gli esperimenti: tempi e soglie, carichi, struttura di un run, matrice dei run, obiettivo di disponibilità, valori di KEDA. Ogni numero è scritto qui una sola volta e il resto del progetto lo legge, invece di ripeterlo a mano nei vari file.

## Perché sta qui e non in `docs/`

Perché questi numeri non sono solo del documento: sono i parametri degli esperimenti. Il documento li descrive, ma li devono usare anche gli strumenti che li eseguono. Tenerli in `docs/` farebbe sembrare che servano soltanto al PDF.

## Dove si usa

| Dove | Come | Stato |
|---|---|---|
| Documento di architettura e relazione di sintesi (`docs/`) | `\parametro{chiave}` nei file LaTeX; `docs/scripts/parametri.py` scrive le macro a ogni `make` | in uso |
| `README.md` e `report/fasi-e-milestone.md` | numero tra due marcatori (esempio in `docs/README.md`); `make controlla` (in `docs/`) verifica che coincida | in uso |
| Banco di misura (`harness/`, fase F4) | legge la matrice per sapere quali run lanciare e la struttura di un run (riscaldamento, guasto al minuto 2, tetti) | previsto |
| Applicazione e manifest (`app/`, `deploy/`) | timeout e deadline passati come variabili d'ambiente; repliche, worker e valori di KEDA nei manifest | da decidere |
| Analisi (`analysis/`) | limite di completamento e soglie (99%, sensibilità a 1 s e 5 s) per i calcoli di fine campagna | previsto |

Le righe «previsto» e «da decidere» sono possibilità, non ancora scelte.

## Regole

Sono in testa a `parametri.yaml`: una chiave per significato, un numero entra solo se compare in più punti o cambia dopo F4, niente macro dove il testo è congelato o è storia.

## Come si usa

- Cambiare un numero: si modifica `parametri.yaml`, poi `make` in `docs/` rigenera le macro e `python3 docs/scripts/parametri.py controlla` verifica i Markdown (con `--fix` li corregge).
- Vedere chiavi e valori: `python3 docs/scripts/parametri.py elenca`.
- Serve PyYAML: `pip install pyyaml`.
