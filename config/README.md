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
| Docker Compose (`deploy/compose/`) | il `Makefile` legge la deadline dell'API (`tempi.deadline_api_s`) e il tempo di servizio (`tempi.tempo_servizio_s`) e li passa ai container come `DEADLINE_S` e `SERVICE_TIME_S` | in uso |
| Client provvisorio (`harness/client/`) | legge il timeout del client (`tempi.timeout_client_s`), se non si passa `--timeout` | in uso |
| Reset prima di ogni run (`harness/reset/reset.py`) | legge le copie dell'API (`versioni.copie_api`) e dei worker (`versioni.worker_v3`) per sapere come deve essere la versione dopo il reset | in uso |
| Manifest Kubernetes (`deploy/k8s/`) | `deploy/k8s/parametri.py` scrive `base/parametri.env` e un ConfigMap generato dà ai pod la deadline dell'API (`tempi.deadline_api_s`) e il tempo di servizio di API e worker (`tempi.tempo_servizio_s`, D0018); gli overlay V2 e V3 leggono da lì le copie dell'API (`versioni.copie_api`) e dei worker (`versioni.worker_v3`) | in uso |
| Manifest Kubernetes: sonde dell'API (`deploy/k8s/base/`) | `deploy/k8s/parametri.py` scrive nello stesso `parametri.env` timeout, soglia e periodi (`sonde.*`); `base/kustomization.yaml` li copia nelle sonde dell'API con `replacements`. Si usa la configurazione «veloce»; la «standard» è già nel ConfigMap, per il guasto F7 | in uso |
| Manifest Kubernetes: KEDA (`deploy/k8s/overlays/v5/`) | `deploy/k8s/parametri.py` scrive nello stesso `parametri.env` i worker da 1 a 10 (`versioni.worker_v5_*`) e i valori di KEDA (`keda.*`); `overlays/v5/kustomization.yaml` li copia nello ScaledObject con `replacements`. La soglia in ordini per worker è provvisoria fino a F4 | in uso |
| Manifest Kubernetes: osservabilità (`deploy/k8s/osservabilita/`) | `deploy/k8s/parametri.py` scrive `osservabilita/prometheus.yml` da `prometheus.modello.yml`, con l'intervallo di raccolta (`osservabilita.intervallo_raccolta_s`, D0019) | in uso |
| Guasto F5 (`harness/faults/latenza.py`) | legge latenza e durata (`guasti.f5_latenza_ms`, `guasti.f5_durata_s`), se non si passano `--latenza-ms` e `--durata` | in uso |
| Analisi: fermo e ripristino (`analysis/fermo.py`) | legge i secondi consecutivi (`run.ripristino_secondi_consecutivi`) e la soglia del 99% (`tempi.soglia_secondo_disponibile_percentuale`); per il completamento anche il limite (`tempi.limite_completamento_s`) e quelli della sensibilità (`tempi.limite_completamento_sensibilita_s`, con `--sensibilita`) | in uso |
| Run completo (`harness/run/run.py`) | legge la sezione `run` (riscaldamento, riferimento, minuto del guasto, osservazione dopo il ripristino, tetti, durata senza guasti) e la soglia del 99% per riconoscere il ripristino durante il run | in uso |
| Esportazione di fine run (`harness/esporta/esporta.py`) | legge l'intervallo di raccolta di Prometheus (`osservabilita.intervallo_raccolta_s`) come passo delle serie esportate | in uso |
| Analisi: ritmo inviato (`analysis/ritmo.py`) | legge la tolleranza sul ritmo del client (`carichi.ritmo_tolleranza_percentuale`), se non si passa `--tolleranza` | in uso |
| Analisi: calcoli di fine campagna (`analysis/`) | limite di completamento e sensibilità a 1 s e 5 s | previsto |

Le righe «previsto» e «da decidere» sono possibilità, non ancora scelte.

## Regole

Sono in testa a `parametri.yaml`: una chiave per significato, un numero entra solo se compare in più punti o cambia dopo F4, niente macro dove il testo è congelato o è storia.

## Come si usa

- Cambiare un numero: si modifica `parametri.yaml`, poi `make` in `docs/` rigenera le macro e `python3 docs/scripts/parametri.py controlla` verifica i Markdown (con `--fix` li corregge).
- Vedere chiavi e valori: `python3 docs/scripts/parametri.py elenca`.
- Serve PyYAML: `pip install pyyaml`.
