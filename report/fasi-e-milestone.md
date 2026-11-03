# Fasi e milestone

*Pianificazione del progetto: WBS di primo livello (fasi F0-F8), roadmap su 12 settimane e milestone M1-M7 con i criteri di passaggio. Le milestone sono le stesse create su GitHub (Issues → Milestones).*

Ogni milestone è un **punto di controllo**: chiude una o più fasi e ha un criterio verificabile. Se il criterio non è soddisfatto non si passa alla fase successiva.

## Percorso in breve

Progettare e scrivere le previsioni (M1) → costruire l'app (M2) → portarla su Kubernetes (M3) → costruire il banco di misura (M4) → misurare (M5) → ripetere su AWS (M3b, M6) → analizzare e scrivere il report (M7).

## Milestone

| Milestone | Scadenza | Fasi che chiude | Criterio di passaggio | Se non passa |
|---|---|---|---|---|
| **M1** Architettura e previsioni | S2 · 04/11/2026 | F0, F1 | Decisioni scritte, parametri fissati, previsioni committate | Non si inizia F3 |
| **M2** App minima | S3 · 11/11/2026 | F2 | I quattro criteri di F2 soddisfatti | Non si tocca Kubernetes |
| **M3** Kubernetes locale | S5 · 25/11/2026 | F3 | V1-V3 su kind a 3 nodi; l'harness minimo misura un crash F1 iniettato dal nodo con risoluzione sotto il secondo | Rivedere il metodo di misura prima di proseguire |
| **M3b** Prova AWS | S6 · 02/12/2026 | F6 (prova) | Account con allarme di budget attivo; cluster creato e distrutto, costi e limiti noti | Ripianificare (o ridurre) subito la fase AWS, non in S9 |
| **M4** Banco di prova | S7 · 09/12/2026 | F4 | I criteri di F4 soddisfatti, compresi failover di V4 e scalatura di V5 | **Non parte la campagna F5** |
| **M5** Campagna locale | S8 · 16/12/2026 | F5 | 220 run validi. **Decisione sulla fase AWS:** sessioni complete, una sola sessione o solo la prova di S6 | Applicare il piano di taglio; mai sotto 10 ripetizioni per F1-F4 e F7 |
| **M6** Sessioni AWS | S10 · 30/12/2026 | F6 (sessioni) | Sessioni fatte, risorse distrutte, costi annotati | Ridurre a una sola sessione |
| **M7** Consegna | S12 · 13/01/2027 | F7, F8 | Report, diario, repository e orale pronti | — |

## Roadmap

| Fase | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 | S11 | S12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **F0** Preparazione | ■ | | | | | | | | | | | |
| **F1** Architettura e protocollo | ■ | ■ | | | | | | | | | | |
| **F2** App minima | | ■ | ■ | | | | | | | | | |
| **F3** Kubernetes locale + harness minimo | | | ■ | ■ | ■ | | | | | | | |
| **F4** Osservabilità e banco completo | | | | | ■ | ■ | ■ | | | | | |
| **F5** Campagna locale | | | | | | | ■ | ■ | | | | |
| **F6** AWS (prova, poi sessioni) | | | | | | ■ | | | ■ | ■ | | |
| **F7** Analisi | | | | | | | | | | ■ | ■ | |
| **F8** Report e orale | | | | | | | | | | | ■ | ■ |
| Diario e registro decisioni | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ | ■ |
| **Milestone** | | M1 | M2 | | M3 | M3b | M4 | M5 | | M6 | | M7 |

**Inizio di S1: giovedì 22/10/2026.** Ogni settimana va da giovedì a mercoledì; la scadenza di una milestone è l'ultimo giorno della sua settimana. Le stesse scadenze sono impostate sulle milestone di GitHub.

| S1 | S2 | S3 | S4 | S5 | S6 |
|---|---|---|---|---|---|
| 22/10-28/10 | 29/10-04/11 | 05/11-11/11 | 12/11-18/11 | 19/11-25/11 | 26/11-02/12 |

| S7 | S8 | S9 | S10 | S11 | S12 |
|---|---|---|---|---|---|
| 03/12-09/12 | 10/12-16/12 | 17/12-23/12 | 24/12-30/12 | 31/12-06/01 | 07/01-13/01 |

**Attenzione alle feste:** S9-S11 cadono tra il 17/12 e il 06/01. Le sessioni AWS (S9-S10) e l'analisi (S10-S11) sono le attività più esposte: vanno confermate o ripianificate a M5 (16/12) in base alla disponibilità reale dei due.

## Fasi

### F0 — Preparazione · S1 · ~10 h · → M1
**Attività:** repository Git, diario e registro delle decisioni · Docker Desktop (5 GB sul Mac da 8 GB, ~8 GB sulla macchina delle misure; D0013), kind, kubectl, Helm, JMeter 5.5+ · linguaggio (default Python) · ruoli. L'account AWS non si crea in F0: è un prerequisito della prova di F6 (M3b).
**Fatto quando:** `kubectl get nodes` risponde sul cluster locale.

### F1 — Architettura e protocollo di misura · S1-S2 · ~32 h · → M1
**Attività:** decisioni D0001-D0017 nel documento di architettura (`docs/`) · tabella unica dei parametri · protocollo sperimentale (domande, matrice, indicatori e SLO, ripetizioni, validità dei run) · previsioni per V1-V5 e F1-F7.
**Fatto quando:** entrambi sappiamo spiegare ogni diagramma e ogni decisione, e le previsioni sono scritte e committate **prima** di qualsiasi misura (tag `m1`).

### F2 — Applicazione minima e tre versioni · S2-S3 · ~20 h · → M2
**Attività:** API con un endpoint ordini, worker, PostgreSQL · V1, V2, V3 (V4 e V5 non richiedono codice nuovo) · tempo di servizio regolabile da variabile d'ambiente · ID ordine generato dal client · `ts_ricezione` e `ts_scrittura` con `clock_timestamp()` (D0005) · deadline lato server (D0008) · vincolo di unicità e duplicati registrati in una tabella · RabbitMQ e politica di riprova (D0002, D0003) · endpoint di liveness e readiness senza dipendenze (D0007) · immagini Docker · `docker-compose` per verificare · script che assegna ogni ID a una categoria.
**Fatto quando:**
1. con 100 ordini inviati ne risultano 100 "completati in tempo" in tutte e tre le versioni;
2. senza carico, il tempo end-to-end è pari al tempo di servizio configurato, entro pochi millisecondi;
3. rimandando due volte lo stesso messaggio in V3, il duplicato è rifiutato **e contato**;
4. con il database fermo per 60 s in V3, a fine run gli ordini persi sono 0.

### F3 — Kubernetes locale e harness minimo · S3-S5 · ~48 h · → M3
**Attività:** cluster kind a 3 nodi (control plane + 2 worker) · manifest con base comune e overlay V1-V5 · DB e broker fissati a worker1 · punto di ingresso NodePort sul control plane · sonde (D0007) · richieste e limiti di risorse · repliche · installazione di CloudNativePG (V4) e KEDA (V5) · misura a vuoto dei tempi di avvio · **harness minimo in S4**: carico a modello aperto con log per richiesta e crash F1 iniettato dal nodo.
**Fatto quando:** V1-V3 funzionano su Kubernetes; con un crash F1 l'harness minimo restituisce downtime e istante di ripristino con risoluzione sotto il secondo.

### F4 — Osservabilità e banco di prova completo · S5-S7 · ~55 h · → M4
**Attività:** Prometheus e Grafana leggeri · piani JMeter con Open Model Thread Group per W1-W3, da riga di comando · script dei guasti F1-F7 (segnali dal nodo, istante registrato su host e cluster; D0016) · Toxiproxy sempre nel percorso verso il DB · harness completo (reset che ricrea i pod e verifica topologia di V4 e worker di V5, struttura del run, raccolta di client, database, eventi e Prometheus, criteri di validità, CSV, ordine casuale) · misura della capacità di base e della soglia di CPU dell'host.
**Fatto quando:**
1. due ripetizioni dello stesso test sono entro una tolleranza dichiarata (es. 10% sulla mediana), anche con un run con guasto in mezzo;
2. durante un guasto il ritmo inviato resta entro ±5%, anche con F4 su V1;
3. F1 su V2 produce un downtime coerente con la previsione, oppure la differenza è spiegata;
4. il failover di V4 avviene e il reset ripristina la topologia; KEDA scala i worker di V5 sotto W2 e il reset li riporta al minimo;
5. misurata la capacità con 1, 3 e 10 worker; se con 10 è sotto 10×μ1, si annota quale componente satura.

### F5 — Campagna locale · S7-S8 · ~48 h · → M5
**Attività:** 220 run sul MacBook M5 da 16 GB (D0013), in blocchi automatici (matrice nel capitolo "Protocollo di misura" del documento; F6 se c'è tempo) · controllo periodico dei dati e della coerenza delle categorie · ogni run scartato e ogni anomalia nel diario · analisi preliminare di RQ1-RQ5.
**Fatto quando:** ogni configurazione ha il numero previsto di run validi e ogni run supera il controllo di coerenza.

### F6 — Fase AWS · prova in S6, sessioni in S9-S10 · ~40 h · → M3b, M6
**Account (da aprire in S5, prima della prova):** account AWS con autenticazione a due fattori, utente non amministratore e allarme di budget attivo. Il piano gratuito di un account nuovo potrebbe non includere EKS: alla creazione scegliere il piano Paid e verificare i servizi inclusi.
**Prova (S6):** creare e distruggere il cluster con infrastruttura come codice (eksctl, D0009) per scoprire limiti, permessi e costi reali.
**Prima delle sessioni:** manifest parametrizzati, tabella dei parametri allineata (ALB compreso), piano delle 2-3 sessioni, previsione del guasto F6 se si decide di eseguirlo (scritta e committata prima del primo run). Si fanno solo se confermate a M5.
**Sessioni:** EKS su 2-3 zone, ALB con pod readiness gate, DB e broker in una zona, JMeter su EC2 nella stessa regione · V2 e V3 con W1 e il guasto F1 (e F6, facoltativo); V3 anche con i guasti F2 e F3 e, senza guasti, con W2.
**Dopo ogni sessione:** distruggere tutto e verificare che non restino risorse a pagamento (load balancer, NAT gateway, volumi, IP elastici).
**Fatto quando:** risultati per RQ6 raccolti con la tabella delle differenze tra ambienti, console AWS pulita, costi annotati.

### F7 — Analisi e confronto con la teoria · S10-S11 · ~26 h · → M7
**Attività:** downtime, richieste fallite e ordini persi previsti contro misurati · budget di errore consumato per guasto e disponibilità proiettata in "nove" · mediane, intervalli interquartili, intervalli di confidenza bootstrap, analisi di sensibilità (compreso il limite di completamento a 1 s e 5 s) · sincrono contro asincrono · crash contro blocco · failover con replica asincrona e sincrona · V5 contro V3 su coda massima e costo · pod pronto contro servizio ripristinato · locale contro AWS · risposta a ogni domanda · cosa non possiamo concludere.
**Fatto quando:** ogni RQ ha una risposta con dati, incertezza e limiti dichiarati.

### F8 — Report, diario e orale · S11-S12 · ~27 h · → M7
**Consegna:** repository · report (architettura A1-A6 → protocollo → risultati → risposte alle RQ → limiti e difficoltà degli strumenti) · diario delle operazioni.
**Fatto quando:** una terza persona, seguendo il README, riesce a rifare un esperimento locale.

## Priorità e piano di taglio

| | |
|---|---|
| **Indispensabile** | Protocollo di misura · V1-V3 su Kubernetes locale · guasti F1-F4 e F7 · RQ1-RQ3 · decisioni, previsioni, minacce alla validità · diario |
| **Auspicabile** | V4 (RQ4) · V5 (RQ5) · guasto F5 · sessioni AWS (RQ6), da confermare a M5 |
| **Facoltativo** | Guasto F6 · V4 su AWS con standby in un'altra zona |

**Ordine dei tagli in caso di ritardo:** guasto F6 → V5 → guasto F5 → sessioni AWS ridotte a una (o alla sola prova di S6, con RQ6 dichiarata come non risposta) → V4 ridotta alla sola replica asincrona. Non si tagliano mai il protocollo di misura, le 10 ripetizioni dei guasti F1-F4 e F7, RQ1-RQ3, le previsioni e il diario.

**Sforzo stimato:** circa 306 ore (da 265), cioè ~12,7 ore a settimana a testa. Dettaglio per fase nell'appendice "Pianificazione" del documento.

## Ripartizione del lavoro

Uno dei due svolge l'attività, l'altro la legge e la approva. **Nulla viene accettato senza l'approvazione dell'altro.**

| Cosa | Chi lo fa | Chi lo legge e approva | Quando è accettato |
|---|---|---|---|
| Attività (issue) | chi la prende | l'altro | quando l'altro ha approvato il risultato |
| Modifiche al repository (pull request) | l'autore | l'altro | dopo l'approvazione dell'altro; nessuno unisce una propria pull request senza di essa |
| Decisioni architetturali (ADR) | chi le propone | l'altro | quando lo stato passa ad «accettata» dopo la lettura e l'approvazione dell'altro |
| Previsioni e valori dei parametri | chi li scrive | l'altro | prima di eseguire i run, con data e approvazione |
| Esecuzione e analisi dei run (F5, F7) | insieme | entrambi | quando entrambi hanno letto i risultati |
| Report e diario | chi scrive la sezione | l'altro | dopo la lettura dell'altro |
