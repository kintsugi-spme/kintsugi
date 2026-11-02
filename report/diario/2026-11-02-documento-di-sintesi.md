# 2026-11-02 — Prima bozza della relazione di sintesi

**Chi:** Francesco · **Fase:** F1 · **Durata:** ? h · **Issue:** nessuna ancora (proposta di Francesco: affiancare al documento tecnico una versione breve per i docenti)

## Cosa abbiamo fatto

Creato il branch `docs/sintesi` (da `docs/issue-20-incoerenze`, per avere i numeri aggiornati: 220 run, 22 ore) e scritta una prima bozza di una **relazione di sintesi** da affiancare al documento di architettura. Il documento tecnico (`docs/main.pdf`) non è stato toccato.

L'idea è avere due documenti con ruoli diversi:

| | Documento tecnico | Relazione di sintesi |
|---|---|---|
| Per chi | noi due e chi deve riprodurre gli esperimenti | i docenti |
| Lunghezza | 51 pagine | 16 pagine (copertina e indice compresi) |
| Contenuto | tutto: 17 ADR, parametri, diagrammi, calcoli, appendici | l'essenziale, con **numeri e formule** ma presentati meglio |
| Sorgente | `docs/main.tex` e `docs/chapters/` | `docs/main-sintesi.tex` e `docs/sintesi/` |

Il file `docs/main-sintesi.tex` riusa configurazione, stile e frontespizio del documento tecnico; per il resto la sintesi ha i propri sorgenti in `docs/sintesi/`, un file per sezione.

## Perché

Il documento tecnico è completo ma molto lungo, e ha parti che servono a noi (revisione del piano, schede di decisione complete, tabella completa dei parametri) più che a chi lo valuta. La sintesi risponde a una domanda: «se un docente legge solo questo, capisce cosa abbiamo fatto, perché e cosa ci aspettiamo?»

Scelte di impostazione:
- **Si parte dal corso:** la sezione 1 contiene una tabella «concetto del corso → dove lo misuriamo» (scalabilità e bilanciamento, disponibilità e numero di nove, failover attivo-attivo e attivo-passivo, replica del database, sincrono e asincrono, elasticità, IaaS). I concetti sono verificati sulle slide T06 e T12.
- **Numeri e formule restano:** previsioni, modello del fermo, esempi di calcolo, budget di errore. Si taglia il «come si ottiene» di ogni riga, che resta nel documento tecnico.
- **Una sola figura per idea:** metodo, derivazione delle versioni, panoramica dei componenti (nuova, sostituisce i cinque diagrammi per versione), anatomia di un fermo, categorie degli ordini, struttura di un run, matrice dei run.
- **Sezioni al posto dei capitoli**, senza pagine vuote tra una e l'altra.

| Sezione | Cosa contiene | Cosa si è tagliato |
|---|---|---|
| 1 Il progetto in breve | scopo, RQ, metodo, tabella dei concetti del corso | struttura del documento, ipotesi H1–H5 (assorbite dalle relazioni attese) |
| 2 Le cinque architetture | derivazione, panoramica, tabella con punti unici di guasto, ambienti | un diagramma per ogni versione, percorso di un ordine come figura, dettagli di kind |
| 3 I guasti | tabella F1–F7, crash e blocco, anatomia, iniezione | dettagli sul PID 1 e su V4 |
| 4 Come misuriamo | misure, categorie, run, carichi, 220 run, statistica | tabella dei parametri, motivazioni di ogni tetto |
| 5 Che cosa ci aspettiamo | grandezze, esempi, modello, previsioni, relazioni per RQ, budget di errore | spiegazione riga per riga della tabella, ipotesi minori |
| 6 Le decisioni principali | una tabella «scelta e motivo» con tutte le decisioni | le schede complete |
| 7 I limiti | tabella delle minacce con contromisure | tre minacce minori |
| 8 Piano di lavoro | milestone, piano di taglio, rischi | Gantt, ore per fase |

## Comandi e configurazione

```bash
cd docs
latexmk -pdf main-sintesi.tex
```

Aggiunto `make sintesi` al `Makefile`; `make` ora compila entrambi i PDF.

## Risultato

`docs/main-sintesi.pdf`, 16 pagine con copertina, senza errori né riferimenti mancanti né righe fuori margine. Controllato a vista pagina per pagina.

## Problemi e soluzioni

- **Spazi bianchi tra le tabelle:** i riquadri flottanti lasciavano mezze pagine vuote. Risolto fissandoli dove sono scritti (pacchetto `float`, posizione `H`).
- **Etichette sovrapposte nella panoramica dei componenti:** accorciate e spostate.

## Limiti dello strumento emersi

- **Numeri duplicati:** gli stessi valori (220 run, 22 ore, 2 s, 15 s, i fermi previsti) ora stanno in due documenti. Se cambiano, vanno aggiornati in entrambi, e prima o poi uno resterà indietro. Soluzione da valutare: spostare i valori condivisi in un file di macro (`docs/config/parametri.tex`) usato da entrambi i documenti.
- **Previsioni:** la tabella delle previsioni è copiata dal capitolo 8 senza modifiche. Dopo il tag `m1` non si possono cambiare, quindi la copia non diverge, ma fino ad allora va tenuta allineata.
- **Da decidere con Gianmarco:** se la sintesi diventa il documento principale da consegnare e cosa deve contenere; se serve un'issue e una milestone dedicate.
