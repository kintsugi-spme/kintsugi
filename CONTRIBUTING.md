# Come contribuire

Grazie dell'interesse. Kintsugi è un progetto d'esame (*Software Project Management & Evolution*, Federico II): le decisioni di architettura, le previsioni e le misure sono degli autori. Secondo il regolamento universitario l'aiuto esterno è ammesso solo **dopo la presentazione del progetto**: fino ad allora non accettiamo pull request da chi non è un autore. Segnalazioni, domande e idee sono invece benvenute fin da subito nelle [Discussions](https://github.com/kintsugi-spme/kintsugi/discussions) e nelle issue. Dopo la presentazione apriremo il repository anche alle modifiche e rimetteremo le etichette `good first issue` e `help wanted` sulle issue adatte; per una modifica più grande conviene aprire prima una discussione, così ci mettiamo d'accordo prima che tu lavori.

Partecipando accetti il [codice di condotta](CODE_OF_CONDUCT.md).

## Domande, idee, problemi

- **Domande e idee:** [Discussions](https://github.com/kintsugi-spme/kintsugi/discussions).
- **Un comportamento inatteso:** issue con il modulo «Problema».
- **Un'attività da fare:** issue con il modulo «Attività», assegnata a una milestone.

## Come proporre una modifica

1. **Parti da un'issue.** Cerca una issue aperta o aprine una. Ogni PR ne chiude una.
2. **Crea un branch dal `main` aggiornato.** Gli esterni lavorano su un fork, gli autori su un branch del repository. Il nome ha un prefisso e un argomento breve, in minuscolo e con i trattini: `feat/`, `fix/`, `docs/`, `ci/`, `exp/` (per esempio `docs/guasto-f6`).
3. **Fai commit piccoli**, con un messaggio breve in italiano che dice cosa cambia.
4. **Apri la PR verso `main`.** Fa eccezione solo lo stack di PR, descritto sotto. Compila il modulo e scrivi `Closes #n` con il numero dell'issue.
5. **Aggiorna il diario.** Sempre una riga in `report/diario/registro.md`, con le ore. Una voce in `report/diario/` (parti da `_template.md`) solo se c'è una misura, un limite di uno strumento, un problema che ha fatto perdere tempo, una scelta non ovvia, un run scartato o un'anomalia nei dati, o lo scarto da una previsione: i casi sono in `report/diario/README.md`.
6. **Aspetta la revisione.** Serve l'approvazione di un autore diverso da chi ha scritto la PR e tutte le discussioni risolte. Dopo un nuovo push l'approvazione va richiesta di nuovo.

## Controlli automatici (CI)

Ogni PR fa partire i controlli di `.github/workflows/controlli.yml`: base della PR, test dell'app, numeri coerenti, PDF, immagine e manifest Kubernetes. **Chi scrive il codice o i manifest di una PR aggiunge in quella stessa PR anche il controllo che li verifica**: un test, oppure un passo nel workflow. Non c'è una issue che lo faccia dopo. Esempi: una cartella nuova di test (per esempio `harness/jmeter`) non gira finché non c'è il suo passo di `pytest` nel workflow; una cartella nuova di manifest va aggiunta al passo «Manifest Kubernetes» (gli overlay di `deploy/k8s/overlays/` sono già presi dalla cartella). Se il controllo non serve, o non si può fare senza un account esterno (per esempio AWS), si scrive il motivo nella PR.

## PR impilate (stack)

Quando hai da aprire più PR (1, 2, …, n) e ognuna ha bisogno della precedente per funzionare (la 2 della 1, la 3 della 2, …), le apri tutte subito, una sopra l'altra:

- **Un solo proprietario.** Tutte le PR dello stack sono della stessa persona: non vale «la 1 a me, la 2 a te, la 3 a me». Così una persona sola decide l'ordine, risolve i conflitti e sa a che punto è lo stack. L'altro autore rivede tutte le PR come sempre.
- **Basi.** La PR 1 punta a `main`. Ogni PR successiva punta al branch della PR da cui dipende (la 2 al branch della 1, la 3 al branch della 2). Due PR che dipendono dalla stessa possono puntare entrambe al suo branch.
- **Descrizione.** Ogni PR dice da quale PR dipende (con il link), cosa diceva la sua issue e come è stata risolta, così si legge da sola. Nella PR 1 si elencano le PR che le stanno sopra e si scrive un `Closes #n` per ogni issue della pila: `Closes` chiude l'issue solo quando la PR entra in `main`, e una PR fusa nel branch di un'altra non la chiude.
- **Fusione, in ordine crescente.** Una PR della pila si fonde nella sua base solo dopo l'approvazione dell'altro autore e con le discussioni risolte: fuori da `main` GitHub non lo impone, quindi lo si rispetta a mano. La si fonde nel branch su cui punta (la 2 nella 1, poi la 3 nella 2 già fusa, e così via). Quando la PR 1 contiene tutto ed è completa, si fonde la 1 in `main`. Ogni fusione aggiunge commit alla PR 1 e GitHub ne annulla l'approvazione: prima di fonderla in `main` serve un'ultima approvazione, che vale per tutta la pila. Mai una PR di mezzo in `main` saltando quelle sotto. Dopo una fusione le PR successive devono puntare al branch giusto: se GitHub non le ridirige da solo, cambia la base a mano.
- **Controllo della base.** La verifica «La PR punta a main» accetta una base diversa da `main` solo se è il branch di un'altra PR aperta dello stesso autore.

## Documenti

```bash
cd docs
make            # compila il documento di architettura e la relazione di sintesi
make controlla  # verifica che i numeri scritti nei file Markdown coincidano
```

I numeri che compaiono in più punti (run, tempi, soglie) sono scritti **una sola volta** in `config/parametri.yaml`: non ripeterli a mano, vedi `config/README.md`.

Ogni decisione di architettura diventa una scheda in `docs/chapters/decisioni/` (copia una esistente).

## Cosa non si tocca

- **Le previsioni.** La tabella delle previsioni (`docs/chapters/08-previsioni.tex`) è fissata dal tag `m1`. Una previsione non si riscrive dopo aver visto una misura: se un valore cambia, lo si spiega nel diario e nei limiti.
- **Il tag `m1`.** Non si sposta e non si cancella.
- **`main`.** Non si scrive direttamente e non si forza: tutto passa da una PR rivista.

## Licenza

Contribuendo accetti che il tuo lavoro sia rilasciato con le stesse licenze del progetto: [MIT](LICENSE) per il codice, [CC BY 4.0](LICENSE-DOCS.md) per la documentazione.
