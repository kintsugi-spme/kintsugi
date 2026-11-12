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
| Docker Compose (`deploy/compose/`) | il `Makefile` legge la deadline dell'API (`tempi.deadline_api_s`) e la passa ai container come `DEADLINE_S` | in uso |
| Client provvisorio (`harness/client/`) | legge il timeout del client (`tempi.timeout_client_s`), se non si passa `--timeout` | in uso |
| Manifest Kubernetes (`deploy/k8s/`) | `deploy/k8s/parametri.py` scrive `base/parametri.env` e un ConfigMap generato dà la deadline dell'API (`tempi.deadline_api_s`) ai pod | in uso |
| Manifest Kubernetes: copie, worker, sonde e KEDA (fase F3) | `copie_api`, `worker_v3`, i valori delle sonde e di KEDA, con lo stesso meccanismo | previsto |
| Analisi: fermo e ripristino (`analysis/fermo.py`) | legge i secondi consecutivi (`run.ripristino_secondi_consecutivi`) e la soglia del 99% (`tempi.soglia_secondo_disponibile_percentuale`) | in uso |
| Analisi: calcoli di fine campagna (`analysis/`) | limite di completamento e sensibilità a 1 s e 5 s | previsto |

Le righe «previsto» e «da decidere» sono possibilità, non ancora scelte.

## Regole

Sono in testa a `parametri.yaml`: una chiave per significato, un numero entra solo se compare in più punti o cambia dopo F4, niente macro dove il testo è congelato o è storia.

## Come si usa

- Cambiare un numero: si modifica `parametri.yaml`, poi `make` in `docs/` rigenera le macro e `python3 docs/scripts/parametri.py controlla` verifica i Markdown (con `--fix` li corregge).
- Vedere chiavi e valori: `python3 docs/scripts/parametri.py elenca`.
- Serve PyYAML: `pip install pyyaml`.
