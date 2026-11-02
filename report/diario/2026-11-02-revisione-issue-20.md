# 2026-11-02 — Correzione delle incoerenze del documento (issue #20)

**Chi:** Francesco · **Fase:** F1 · **Durata:** ? h · **Issue:** #20, #22 (documentazione AWS) e, in parte, #10 (valori principali)

## Cosa abbiamo fatto

Corretti uno alla volta i punti rimasti aperti dell'issue #20 (i punti 1–3 erano già chiusi con la PR #21), su un branch unico `docs/issue-20-incoerenze` e con una sola pull request, da far approvare a Gianmarco.

| Punto | Esito |
|---|---|
| 4 — V5 con meno ripetizioni dei suoi riferimenti | V5 sotto W2 passa a **10 ripetizioni**, come V3 con 1 e con 10 worker fissi. Run totali da 245 a **250**, durata della campagna da circa 23 a circa 23,5 ore |
| 5 — Limite di completamento solo «proposto: 2 s» | Fissato a **2 s** (come il timeout del generatore di carico) nella tabella dei parametri; nelle definizioni tolto «proposto». Chiarito che la categoria «completato in tempo» si riferisce alla risposta al client e non al limite. Sensibilità a 1 s e 5 s prevista nell'analisi (F7) |
| 6 — F6 elencato tra i guasti AWS ma facoltativo e senza previsione | F6 resta possibile su AWS ma è dichiarato **facoltativo**, con previsione scritta e committata prima del primo run (in locale e su AWS). Tolto dall'elenco obbligatorio delle sessioni (F1, F2, F3). Il limite «perdita di nodo simulata» nel capitolo sulla validità diventa condizionale |

Modificati per il punto 4: `docs/chapters/07-misura.tex` (tabella e figura della matrice, testo sotto la tabella, frase sulla statistica, ore di macchina), `README.md`, `report/fasi-e-milestone.md`, `docs/appendices/a-pianificazione.tex` (da 245 a 250 run).

Modificati per il punto 6: `docs/chapters/04-deployment.tex` (guasti delle sessioni AWS), `docs/chapters/08-previsioni.tex` (previsione di F6 anche per AWS), `docs/chapters/09-validita.tex` (contromisura condizionale), `report/fasi-e-milestone.md` (F6: sessioni e attività prima delle sessioni).

Modificati per il punto 5: `docs/chapters/06-decisioni.tex` (nuova riga nella tabella dei parametri), `docs/chapters/07-misura.tex` (definizione di disponibilità di completamento, categoria «completato in tempo», paragrafo sulla sensibilità), `docs/chapters/decisioni/D0008-timeout-deadline.tex` (frase nelle conseguenze, marcata come chiarimento), `report/fasi-e-milestone.md` (F7).

## Seconda issue: documentazione AWS dopo lo spostamento da M1 a M3b

L'issue sull'account AWS, che era in M1 (#6), è stata eliminata e il lavoro spostato in M3b (prova AWS, 02/12/2026). La documentazione non era stata aggiornata: la correggiamo nella stessa pull request.

| Dove | Prima | Dopo |
|---|---|---|
| `report/fasi-e-milestone.md`, F0 | Attività con «account AWS, 2FA, utente non amministratore, allarmi di budget»; «fatto quando» con l'allarme di budget attivo | Tolti da F0; il «fatto quando» è solo `kubectl get nodes` |
| `report/fasi-e-milestone.md`, F6 | La prova partiva dal cluster | Nuova riga «Account» da aprire in S5: 2FA, utente non amministratore, allarme di budget, piano Paid |
| `report/fasi-e-milestone.md` e `docs/appendices/a-pianificazione.tex`, M3b | «Cluster creato e distrutto, costi e limiti noti» | Aggiunto «account con allarme di budget attivo» |
| `docs/chapters/04-deployment.tex`, Costi | «un allarme di budget è attivo» (non era vero) | L'account si apre in S5; l'allarme si attiva prima della prova; i crediti sono da verificare perché il piano gratuito potrebbe non includere EKS |
| `README.md`, roadmap | M3b mancava | Aggiunta la riga M3b |

Le ore delle fasi non sono ridistribuite: aprire l'account è poco lavoro rispetto alle 10 ore di F0 e alle 40 di F6. La voce del diario del 27/10 («Da fare per M1: … #6») è storica e resta com'è.

## Valori di KEDA (primo dei tre `\todo` aperti, parte di #10)

Letta la documentazione di KEDA 2.22 e di Kubernetes per fissare i tre valori di V5. Due cose che si credevano diverse:
- l'intervallo di controllo di KEDA (30 s) vale solo da 0 a 1 worker; da 1 a N decide l'autoscaler di Kubernetes, circa ogni 15 s, e il suo ritmo è del control plane (su EKS non si cambia);
- il `cooldownPeriod` di KEDA (300 s) vale solo per scendere a 0 worker; da N a 1 decide la finestra di stabilità dell'autoscaler, 300 s di default.

| Valore | Scelta | Alternativa scartata |
|---|---|---|
| Controllo della coda | **Predefinito** (circa 15 s) | Accorciarlo nella configurazione di kind: su EKS non è possibile, i due ambienti sarebbero diversi (RQ6) |
| Soglia per worker | **μ₁ × 2 s** ordini per worker, calcolati in F4 come il ritmo di W1; 2 s come il limite di completamento | Un numero fisso (per esempio 100): arbitrario |
| Attesa prima di toglierli | **60 s** | 300 s (predefinito: V5 resterebbe a 10 worker per 5 minuti e il costo non mostrerebbe l'elasticità); 30 s (rischio di togliere worker a metà picco) |

Ritardo di reazione previsto (ipotesi, tabella del cap. 8): primi worker **3–20 s** (fino a 15 s per il controllo dell'autoscaler più 2–5 s di avvio), tutti e 10 **18–35 s** (l'autoscaler aggiunge al più 4 worker o il 100% ogni 15 s: da 1 a 5, poi a 10). Durante la reazione la coda cresce di circa 4μ₁ al secondo.

Modificati: `docs/chapters/06-decisioni.tex` (tre righe di parametri al posto del `\todo`), `docs/chapters/decisioni/D0015-autoscaling.tex` (valori, motivazioni e ritardo previsto), `docs/chapters/08-previsioni.tex` (nuova ipotesi $T_{\text{KEDA}}$ e relazione attesa di RQ5).

Da verificare: la compatibilità della versione di KEDA con Kubernetes 1.37 (all'installazione) e i 2–5 s di avvio di un worker (misura a vuoto di F3). Restano due `\todo`: durata del picco di W2 (collegata all'attesa di 60 s: se dopo il picco il run finisce prima, la riduzione non si vede) ed elenco delle configurazioni senza guasti.

## Perché

- RQ5 confronta tre configurazioni sotto W2: V5, V3 con 1 worker e V3 con 10 worker. Le due V3 avevano 10 ripetizioni, V5 solo 5, e con 5 ripetizioni non si calcola l'intervallo di confidenza bootstrap (cap. 7, «Statistica»). La previsione di RQ5 è che V5 stia *tra* le due V3: il confronto richiede la stessa precisione su tutte e tre.
- Costo contenuto: +5 run (circa 30 minuti di macchina). Il piano di taglio resta valido: V5 è già il secondo elemento da tagliare in caso di ritardo, e con lei cadono le ripetizioni aggiunte.
- **Limite di 2 s:** supera la deadline dell'API (1,5 s), quindi in V1, V2 e V4 la disponibilità di completamento resta quasi uguale a quella di accettazione (la frase del cap. 7 continua a valere); con 1 s non sarebbe vero. Un solo valore preregistrato; la robustezza si dimostra in analisi ripetendo il calcolo con 1 s e 5 s, perché `ts_ricezione` e `ts_scrittura` sono registrati per ogni ordine. Scartati: 5 s (valore senza motivo, rende V3 più favorevole di quanto sia), 1 s (sotto la deadline), limite relativo al tempo di riferimento (non fissato prima delle misure e diverso per versione).
- **F6 facoltativo anche su AWS:** F6 è l'unico guasto che sfrutta davvero le macchine reali, ed è la contromisura dichiarata al limite «la perdita di un nodo è simulata in locale» (cap. 9). Toglierlo del tutto avrebbe lasciato quella contromisura senza contenuto; renderlo obbligatorio avrebbe richiesto una previsione nuova prima del tag `m1` (ricollocamento dei pod, rilevamento dei nodi su EKS, disco EBS legato alla zona) e contraddetto il piano di taglio, dove F6 è il primo da tagliare. Scelta: stesso statuto in locale e su AWS, previsione scritta prima del primo run. Se viene tagliato, il limite resta non mitigato e il report lo dichiara.
- Alternative scartate per il punto 4: ridurre a 5 i due riferimenti V3 (−10 run, ma la statistica di RQ5 resta debole proprio dove il confronto è delicato); lasciare V5 a 5 dichiarando RQ5 esplorativa (poco coerente con il metodo delle previsioni preregistrate).

## Comandi e configurazione

```bash
cd docs && make
```

## Risultato

- Matrice: 80 run senza guasti (16 configurazioni × 5) + 100 + 20 + 20 + 30 (V5 e riferimenti, 10 ripetizioni) = **250**.
- Ipotesi di lavoro: V5 sotto W2 era già una delle 17 configurazioni senza guasti da 5 ripetizioni (come da piano precedente); ora è contata nel gruppo da 10. Se così non fosse, il totale sarebbe 255. L'elenco delle configurazioni senza guasti resta un `\todo` del capitolo 7, da chiudere separatamente.

## Problemi e soluzioni

- Il numero 85 (17 × 5) non aveva un calcolo nel documento (già segnalato nel diario del 23/10): ora è 80 + V5 sotto W2, ma l'elenco completo delle configurazioni non è ancora scritto.

## Limiti dello strumento emersi

