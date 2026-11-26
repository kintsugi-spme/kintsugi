# Registro delle PR

Una riga per ogni PR fusa (#70): chi l'ha fatta, in che fase, quante ore e cosa cambia, in una frase. Il racconto sta nella PR: descrizione, commenti della revisione, prove. Le ore servono a confrontare, alla fine, lo sforzo previsto con quello reale.

La riga la aggiunge l'autore nella PR stessa, prima della fusione. Le ore comprendono il lavoro e le correzioni dopo la revisione; le ore di chi rivede si scrivono nella riga della PR rivista, tra parentesi (per esempio `2 (+0,5 rev.)`). Una PR impilata ha la sua riga, con la PR in cui è stata fusa.

Le righe fino alla #102 sono state ricostruite il 21/11 dalle PR e dalle voci del diario: «—» vuol dire che le ore non erano scritte da nessuna parte. Le fasi seguono `report/fasi-e-milestone.md` (F0 è la preparazione).

Il numero della PR è un link: la descrizione, la revisione e le prove sono lì. Per la consegna (M7) le descrizioni delle PR si esportano in un file del repository, così il racconto non resta solo su GitHub.

| Data | Chi | Fase | PR | Ore | Cosa |
|---|---|---|---|---|---|
| 23/10 | Francesco | F1 | [#12](https://github.com/kintsugi-spme/kintsugi/pull/12) | — | Decisioni D0001-D0004: sincrono o con coda, coda, riprova, doppi |
| 25/10 | Gianmarco | F0 | [#15](https://github.com/kintsugi-spme/kintsugi/pull/15) | 1 | Diario: la macchina di Gianmarco |
| 26/10 | Gianmarco | F1 | [#16](https://github.com/kintsugi-spme/kintsugi/pull/16) | — | Riferimenti dei documenti e approvazioni aggiornati |
| 27/10 | Francesco | F1 | [#18](https://github.com/kintsugi-spme/kintsugi/pull/18) | 3 | Documento v0.8: revisione formale, definizioni di misura e nuovi diagrammi |
| 27/10 | Gianmarco | F1 | [#19](https://github.com/kintsugi-spme/kintsugi/pull/19) | 2 | Decisioni di architettura e di deployment accettate |
| 01/11 | Francesco | F1 | [#21](https://github.com/kintsugi-spme/kintsugi/pull/21) | 3 | Documento v0.9: previsioni complete e valori dei carichi |
| 02/11 | Francesco | F1 | [#24](https://github.com/kintsugi-spme/kintsugi/pull/24) (nella [#23](https://github.com/kintsugi-spme/kintsugi/pull/23)) | 1 | Relazione di sintesi per i docenti (prima bozza) |
| 03/11 | Francesco | F1 | [#39](https://github.com/kintsugi-spme/kintsugi/pull/39) | — | data/README: istante di scrittura come in D0005 |
| 03/11 | Francesco | F1 | [#23](https://github.com/kintsugi-spme/kintsugi/pull/23) | 1 | Incoerenze di #20, documentazione AWS (#22), valori di KEDA, 220 run e relazione di sintesi |
| 03/11 | Francesco | F1 | [#40](https://github.com/kintsugi-spme/kintsugi/pull/40) | — | Licenze: MIT per il codice, CC BY 4.0 per la documentazione |
| 04/11 | Gianmarco | F1 | [#43](https://github.com/kintsugi-spme/kintsugi/pull/43) | 4 | Diario: review delle PR #21, #23, #39 e #40 |
| 04/11 | Gianmarco | F1 | [#45](https://github.com/kintsugi-spme/kintsugi/pull/45) | — | Penultimo controllo prima del tag m1 |
| 04/11 | Gianmarco | F1 | [#42](https://github.com/kintsugi-spme/kintsugi/pull/42) | 4 | Parametri del progetto in un file solo |
| 04/11 | Gianmarco | F1 | [#44](https://github.com/kintsugi-spme/kintsugi/pull/44) | — | Riferimenti al repository aggiornati |
| 04/11 | Francesco | F0 | [#47](https://github.com/kintsugi-spme/kintsugi/pull/47) | 2 | Repository pronto per i contributi esterni |
| 04/11 | Francesco | F1 | [#48](https://github.com/kintsugi-spme/kintsugi/pull/48) | 1,5 | Controlli automatici sulle PR: base main, numeri coerenti, PDF che compilano |
| 04/11 | Gianmarco | F1 | [#50](https://github.com/kintsugi-spme/kintsugi/pull/50) | 4 | Diario: controllo finale e tag m1 |
| 04/11 | Francesco | F1 | [#49](https://github.com/kintsugi-spme/kintsugi/pull/49) | 0,5 | Diario: tag m1 e chiusura di M1 |
| 05/11 | Gianmarco | F2 | [#51](https://github.com/kintsugi-spme/kintsugi/pull/51) | 3 | App: scheletro con modalità sync/async |
| 06/11 | Gianmarco | F2 | [#52](https://github.com/kintsugi-spme/kintsugi/pull/52) | 0,5 | Database: tabella degli ordini |
| 06/11 | Francesco | F2 | [#53](https://github.com/kintsugi-spme/kintsugi/pull/53) | 1 | App: sonde /healthz e /readyz senza dipendenze (D0007) |
| 06/11 | Francesco | F2 | [#54](https://github.com/kintsugi-spme/kintsugi/pull/54) | 1,5 | App: Dockerfile e immagine unica per API e worker (D0012) |
| 07/11 | Gianmarco | F2 | [#58](https://github.com/kintsugi-spme/kintsugi/pull/58) | 0,5 | Python 3.14 in tutti gli ambienti |
| 07/11 | Gianmarco | F2 | [#59](https://github.com/kintsugi-spme/kintsugi/pull/59) | 1,5 | Client minimo per inviare ordini |
| 07/11 | Gianmarco | F2 | [#56](https://github.com/kintsugi-spme/kintsugi/pull/56) | 2 | API asincrona: pubblicazione su RabbitMQ (V3) |
| 07/11 | Gianmarco | F2 | [#57](https://github.com/kintsugi-spme/kintsugi/pull/57) | 0,5 | Database: vincolo di unicità e tabella dei doppi |
| 08/11 | Francesco | F2 | [#60](https://github.com/kintsugi-spme/kintsugi/pull/60) | 2,5 | Worker: consumo dalla coda e salvataggio |
| 08/11 | Francesco | F2 | [#62](https://github.com/kintsugi-spme/kintsugi/pull/62) | 2 | API sincrona e deadline lato server: V1 e V2 (#30, #31) |
| 08/11 | Francesco | F2 | [#61](https://github.com/kintsugi-spme/kintsugi/pull/61) | 1 | Sintesi: sezione sul codice e sull'ambiente di prova |
| 09/11 | Gianmarco | F2 | [#65](https://github.com/kintsugi-spme/kintsugi/pull/65) | 0,5 | Worker: riprova e coda dei falliti |
| 09/11 | Gianmarco | F2 | [#64](https://github.com/kintsugi-spme/kintsugi/pull/64) | 2 | docker-compose per V1, V2 e V3 |
| 09/11 | Gianmarco | F2 | [#63](https://github.com/kintsugi-spme/kintsugi/pull/63) | 3 | Diario: revisione delle PR #60, #62 e #61 |
| 09/11 | Francesco | F2 | [#66](https://github.com/kintsugi-spme/kintsugi/pull/66) | 2 | Analisi: script delle categorie degli ordini |
| 10/11 | Gianmarco | F2 | [#67](https://github.com/kintsugi-spme/kintsugi/pull/67) | 1 | CI: test con PostgreSQL e RabbitMQ veri |
| 10/11 | Francesco | F2 | [#71](https://github.com/kintsugi-spme/kintsugi/pull/71) | 0,5 | Documenti rimasti indietro: README, docs/README, config/README |
| 11/11 | Gianmarco | F2 | [#68](https://github.com/kintsugi-spme/kintsugi/pull/68) | 0,5 | Verifica dei criteri di M2 |
| 12/11 | Gianmarco | F3 | [#88](https://github.com/kintsugi-spme/kintsugi/pull/88) | 1 | Kubernetes: manifest comuni e parametri dal file unico |
| 12/11 | Gianmarco | F3 | [#87](https://github.com/kintsugi-spme/kintsugi/pull/87) | 1 | Kubernetes: cluster kind e immagine dell'app nei nodi |
| 12/11 | Gianmarco | F3 | [#89](https://github.com/kintsugi-spme/kintsugi/pull/89) | 0,5 | Analisi: calcolo di fermo e ripristino |
| 12/11 | Francesco | F3 | [#90](https://github.com/kintsugi-spme/kintsugi/pull/90) | 2 | Guasti: SIGKILL dal nodo per il guasto F1 |
| 13/11 | Francesco | F3 | [#92](https://github.com/kintsugi-spme/kintsugi/pull/92) | 2 | Documenti: Kubernetes in breve, minacce del guasto F1, grafici per la presentazione |
| 15/11 | Gianmarco | F3 | [#95](https://github.com/kintsugi-spme/kintsugi/pull/95) | 0,5 | Diario: revisione della PR #94 |
| 15/11 | Francesco | F3 | [#94](https://github.com/kintsugi-spme/kintsugi/pull/94) | 1 | Kubernetes: overlay V1 e comandi per avviarla e toglierla |
| 16/11 | Gianmarco | F3 | [#96](https://github.com/kintsugi-spme/kintsugi/pull/96) | 1 | Harness minimo: controllo del ritmo inviato e --durata nel client |
| 16/11 | Gianmarco | F3 | [#97](https://github.com/kintsugi-spme/kintsugi/pull/97) | 1 | Kubernetes: overlay V2 con più copie dell'API e make v2 |
| 17/11 | Gianmarco | F3 | [#100](https://github.com/kintsugi-spme/kintsugi/pull/100) (nella [#98](https://github.com/kintsugi-spme/kintsugi/pull/98)) | 1 | Kubernetes: posizione dei pod sui nodi, D0006 |
| 18/11 | Gianmarco | F3 | [#99](https://github.com/kintsugi-spme/kintsugi/pull/99) | 0,5 | CONTRIBUTING: PR impilate con un solo proprietario, verifica della base in CI |
| 18/11 | Gianmarco | F3 | [#98](https://github.com/kintsugi-spme/kintsugi/pull/98) | 2 | Kubernetes: overlay V3 con RabbitMQ, API asincrona e worker |
| 18/11 | Gianmarco | F3 | [#101](https://github.com/kintsugi-spme/kintsugi/pull/101) | 1 | Kubernetes: sonde di liveness e readiness dell'API, valori da parametri.yaml |
| 20/11 | Gianmarco | F3 | [#103](https://github.com/kintsugi-spme/kintsugi/pull/103) (nella [#102](https://github.com/kintsugi-spme/kintsugi/pull/102)) | 1,5 | Misura a vuoto dei tempi di avvio: avvio.py e tabella nel diario |
| 20/11 | Gianmarco | F3 | [#104](https://github.com/kintsugi-spme/kintsugi/pull/104) (nella [#102](https://github.com/kintsugi-spme/kintsugi/pull/102)) | 2 | Kubernetes: KEDA e overlay V5, make keda e make v5 |
| 21/11 | Gianmarco | F3 | [#102](https://github.com/kintsugi-spme/kintsugi/pull/102) | 2 | Kubernetes: richieste e limiti di CPU e memoria per ogni pod |
| 22/11 | Francesco | F3 | [#105](https://github.com/kintsugi-spme/kintsugi/pull/105) | 3,5 | Kubernetes: V4a e V4s con CloudNativePG, make v4a, make v4s e make cnpg |
| 22/11 | Francesco | F3 | [#106](https://github.com/kintsugi-spme/kintsugi/pull/106) | 1,5 | Diario più leggero: registro delle PR, voce solo quando serve, niente diari delle revisioni |
| 24/11 | Gianmarco | F3 | [#107](https://github.com/kintsugi-spme/kintsugi/pull/107) | 3 | Kubernetes: verifica dei criteri di F3 con make verifica |
| 24/11 | Francesco | F4 | [#134](https://github.com/kintsugi-spme/kintsugi/pull/134) | 1,5 | Banco di prova: tempo di servizio di 0,05 s in tutte le versioni, decisione D0018 |
| 24/11 | Francesco | F4 | [#135](https://github.com/kintsugi-spme/kintsugi/pull/135) (nella [#134](https://github.com/kintsugi-spme/kintsugi/pull/134)) | 3 | Banco di prova: Toxiproxy tra applicazione e database in tutte le versioni |
| 24/11 | Francesco | F4 | [#136](https://github.com/kintsugi-spme/kintsugi/pull/136) (nella [#134](https://github.com/kintsugi-spme/kintsugi/pull/134)) | 2,5 | Banco di prova: Prometheus e kube-state-metrics sul nodo dati, decisione D0019 |
| 25/11 | Gianmarco | F4 | [#137](https://github.com/kintsugi-spme/kintsugi/pull/137) | 2 | CI: controllo dei manifest Kubernetes e regola sui controlli di ogni PR |
| 26/11 | Gianmarco | F4 | [#138](https://github.com/kintsugi-spme/kintsugi/pull/138) | 1 | Harness: reset verificato prima di ogni run (V1, V2, V3), make reset |
| 26/11 | Francesco | F4 | [#139](https://github.com/kintsugi-spme/kintsugi/pull/139) | 3 | Banco di prova: JMeter a ritmo costante per W1 e W3, decisione D0020 |
| 26/11 | Francesco | F4 | [#140](https://github.com/kintsugi-spme/kintsugi/pull/140) (nella [#139](https://github.com/kintsugi-spme/kintsugi/pull/139)) | 3 | Banco di prova: profilo W2 con JMeter e controllo del ritmo per un profilo |
| 26/11 | Francesco | F4 | [#NNN](https://github.com/kintsugi-spme/kintsugi/pull/NNN) (nella [#139](https://github.com/kintsugi-spme/kintsugi/pull/139)) | 2 | Banco di prova: guasti F2, F3 e F4 dal nodo, criterio 2 di F4 (ritmo con il database fermo su V1) |
