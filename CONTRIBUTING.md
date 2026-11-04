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
4. **Apri la PR verso `main`.** Mai verso un altro branch: se il tuo lavoro dipende da un'altra PR, aspetta che sia fusa. Compila il modulo e scrivi `Closes #n` con il numero dell'issue.
5. **Scrivi il diario.** Una voce in `report/diario/` (parti da `_template.md`) con cosa è stato fatto, i comandi, i problemi e i limiti degli strumenti.
6. **Aspetta la revisione.** Serve l'approvazione di un autore diverso da chi ha scritto la PR e tutte le discussioni risolte. Dopo un nuovo push l'approvazione va richiesta di nuovo.

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
