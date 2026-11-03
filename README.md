<div align="center">

# 🏺 Kintsugi
### Laboratorio di affidabilità e asincronia su Kubernetes e AWS

*Cinque architetture, sette guasti, 220 esperimenti: come ridondanza, code asincrone, replica dei dati ed elasticità cambiano l'impatto dei guasti su un servizio distribuito*

![Kubernetes](https://img.shields.io/badge/Kubernetes-kind%20%7C%20EKS-326CE5?logo=kubernetes&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EKS%20%2B%20ALB-FF9900?logo=amazonwebservices&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-CloudNativePG-4169E1?logo=postgresql&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-Broker-FF6600?logo=rabbitmq&logoColor=white)
![KEDA](https://img.shields.io/badge/KEDA-Autoscaling-0F3F71)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![JMeter](https://img.shields.io/badge/JMeter-Open%20model-D22128?logo=apachejmeter&logoColor=white)
![Status](https://img.shields.io/badge/Status-F1%20Architettura-yellow)

**Autori:** Terrecuso Francesco (DE5000005), Vellotti Gianmarco (DE5000041)
**Corso:** Software Project Management & Evolution — Università degli Studi di Napoli Federico II
**Docenti:** Prof. Sergio Di Martino, Prof. Luigi Libero Lucio Starace

</div>

## 1. Obiettivo

Kintsugi è un **servizio di ordini volutamente semplice**, usato come veicolo per esperimenti di affidabilità. Si iniettano guasti controllati e si misura come reagiscono cinque architetture, confrontando i risultati con **previsioni scritte prima di misurare**. Oggetto della valutazione è l'architettura, non il codice.

| | Domanda di ricerca | Confronto |
|---|---|---|
| **RQ1** | Ridondanza senza stato: quanto downtime si evita passando da 1 a N repliche? | V1 / V2 |
| **RQ2** | Sincrono o asincrono: cosa cambia in latenza end-to-end, ordini persi e recupero? | V2 / V3 |
| **RQ3** | Rilevamento: quanto dipende il ripristino dal tipo di guasto e dai parametri delle sonde? | tutte |
| **RQ4** | Ridondanza con stato: quanto downtime evita il failover, e quanti dati si perdono? | V2 / V4 |
| **RQ5** | Elasticità: l'autoscaling sulla coda dà un compromesso migliore tra coda massima e costo, durante un picco? | V3 / V5 |
| **RQ6** | Trasferibilità: quali risultati si ripetono su AWS, e perché gli altri cambiano? | locale / AWS |

> Il nome viene dall'arte giapponese di riparare la ceramica rotta con l'oro, mettendo in evidenza le crepe invece di nasconderle: ogni guasto misurato mostra dove l'architettura cede e come si ricompone.

---

## 2. Architetture

Ogni versione cambia **un solo fattore** rispetto a quella da cui deriva, così ogni differenza misurata ha una causa attribuibile. Tutte sono configurazioni dello stesso codice.

```
V1  sincrona, 1 istanza
 │  + repliche dell'API
 ▼
V2  sincrona, N repliche ─────────────────────┐
 │  + coda asincrona                          │  + database replicato
 ▼                                            ▼
V3  asincrona                                V4  failover automatico
 │  + autoscaling sulla coda                     (V4a replica asincrona · V4s sincrona)
 ▼
V5  asincrona elastica
```

| Versione | Cosa cambia | Domanda |
|---|---|---|
| **V1** | Riferimento: l'API scrive nel database e risponde | RQ1 |
| **V2** | N repliche dell'API dietro un bilanciatore | RQ1, RQ2 |
| **V3** | L'API pubblica su RabbitMQ; i worker scrivono nel database | RQ2 |
| **V4** | PostgreSQL primario + standby con failover (CloudNativePG) | RQ4 |
| **V5** | Worker scalati da KEDA sulla lunghezza della coda (confrontata anche con V3 a 1 e a 10 worker fissi) | RQ5 |

```
                  ┌─────────────────────┐
 JMeter ─────────▶│  Service / Ingress  │  (AWS: ALB)
 (modello aperto) └──────────┬──────────┘
                             ▼
                  ┌─────────────────────┐  V1 · V2 · V4: scrittura sincrona
                  │      API  × N       │────────────────────────────┐
                  └──────────┬──────────┘                            ▼
                             │ V3 · V5: publish + conferma    ┌──────────────────┐
                             ▼                                │    PostgreSQL    │
                  ┌─────────────────────┐   ┌────────────┐    │  V4: primario    │
                  │  RabbitMQ  (+ DLQ)  │──▶│ Worker × M │───▶│    └▶ standby    │
                  └──────────┬──────────┘   └─────▲──────┘    └──────────────────┘
                             │ lunghezza coda     │ V5: scala 1…M
                             └──────▶  KEDA  ─────┘
```

### L'applicazione

Un solo programma Python (FastAPI) e una sola immagine Docker, che parte come API o come worker a seconda della configurazione. Non c'è frontend: il client è JMeter, e la demo dal vivo è la dashboard Grafana.

| Endpoint | Funzione |
|---|---|
| `POST /ordini` | Riceve un ordine con ID generato dal client; `201` (sincrono), `202` (asincrono) o `503` immediato se scatta la deadline |
| `GET /healthz` | Liveness: il processo risponde (nessuna dipendenza) |
| `GET /readyz` | Readiness: l'avvio è completato |
| `GET /metrics` | Metriche per Prometheus |

---

## 3. Esperimenti

| Guasto | Descrizione | Classe | Versioni |
|---|---|---|---|
| **F1** | Crash di un'istanza dell'API | crash | V1, V2, V3 |
| **F2** | Crash di tutti i worker | crash | V3 |
| **F3** | Crash del broker | crash | V3 |
| **F4** | Crash del database (V4: del primario) | crash | V1–V4 |
| **F5** | Latenza verso il database (Toxiproxy) | degrado | V2, V3 |
| **F6** | Perdita di un nodo *(opzionale)* | nodo | V2, V3 |
| **F7** | Blocco di un'istanza dell'API, con due configurazioni delle sonde | blocco | V2 |

- **Iniezione realistica:** `SIGKILL` e `SIGSTOP` inviati dal nodo, non `kubectl delete pod` (che è una terminazione ordinata).
- **Carico a modello aperto** (W1 costante, W2 picco, W3 sovraccarico), per evitare la *coordinated omission*.
- **220 run** in ordine casuale (circa 22 ore di macchina), con reset verificato prima di ogni run.

| Ambiente | Infrastruttura |
|---|---|
| **A — locale** | kind a 3 nodi (control plane + 2 worker) su Docker Desktop |
| **B — AWS** | EKS su 2–3 zone, ALB con pod readiness gate, generatore di carico su EC2 nella stessa regione |

---

## 4. Metodo

- **SLI e SLO:** disponibilità di accettazione e di completamento con obiettivo del 99,9% su 30 giorni; ogni guasto si legge come quota del budget di errore consumata.
- **Previsioni preregistrate:** downtime, richieste fallite e ordini persi si prevedono con modelli espliciti e si committano prima della campagna.
- **Minacce alla validità:** interne, di costrutto, esterne e delle conclusioni, ognuna con la sua mitigazione.
- **Decisioni tracciate:** ogni scelta è un ADR nel documento di architettura.

---

## 5. Struttura del repository

```
kintsugi/
├── app/                  # API e worker (un solo codice, MODE=sync|async)
├── deploy/
│   ├── k8s/
│   │   ├── base/         # manifest comuni
│   │   └── overlays/     # v1/ … v5/
│   └── aws/              # infrastruttura come codice per EKS
├── harness/
│   ├── jmeter/           # piani di carico W1–W3
│   └── faults/           # iniezione dei guasti F1–F7
├── analysis/             # categorizzazione degli ordini e statistiche
├── data/                 # risultati dei run (non versionati)
├── docs/                 # documento di architettura (LaTeX → PDF)
└── report/
    ├── fasi-e-milestone.md
    ├── diario/           # diario delle operazioni
    └── diagrammi/        # grafici dei risultati
```

---

## 6. Guida rapida

### 6.1 Prerequisiti

| Strumento | Uso |
|---|---|
| Docker Desktop | Runtime dei container (5–8 GB di memoria) |
| kind, kubectl, Helm | Cluster Kubernetes locale |
| JMeter 5.5+ | Generazione del carico a modello aperto |
| Python 3.10+ | Applicazione e analisi |
| TeX Live + `latexmk` | Documentazione |

### 6.2 Documento di architettura

```bash
cd docs
make
```

Genera `docs/main.pdf`: architettura, decisioni (ADR), modello dei guasti, protocollo di misura, previsioni e minacce alla validità.

### 6.3 Cluster ed esperimenti

*In arrivo con le milestone M2–M4.*

---

## 7. Roadmap

| Milestone | Scadenza | Obiettivo |
|---|---|---|
| **M1** | 04/11/2026 | Architettura, decisioni, previsioni |
| **M2** | 11/11/2026 | Applicazione minima V1–V3 |
| **M3** | 25/11/2026 | V1–V3 su kind a 3 nodi; primo guasto misurato |
| **M3b** | 02/12/2026 | Prova AWS: account e allarme di budget, cluster creato e distrutto, costi noti |
| **M4** | 09/12/2026 | Banco di prova completo; failover di V4 e scalatura di V5 verificati |
| **M5** | 16/12/2026 | Campagna di misura locale (220 run) |
| **M6** | 30/12/2026 | Sessioni su AWS |
| **M7** | 13/01/2027 | Consegna |

Avanzamento: [milestone su GitHub](https://github.com/terrecruis/kintsugi/milestones).

---

## 8. Contribuire

1. Ogni attività parte da una **issue** assegnata a una milestone.
2. Lo sviluppo avviene su un branch breve (`feat/`, `fix/`, `docs/`, `exp/`).
3. Le modifiche rientrano in `main` tramite **pull request** rivista dall'altro autore.
4. Ogni decisione architetturale diventa un **ADR** in `docs/chapters/decisioni/`.
