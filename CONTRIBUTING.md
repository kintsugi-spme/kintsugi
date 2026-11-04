# Come contribuire

Grazie dell'interesse. Kintsugi è un progetto d'esame (*Software Project Management & Evolution*, Federico II): le decisioni di architettura, le previsioni e le misure sono degli autori. Gli aiuti più utili sono **segnalazioni, revisioni e correzioni**; per le issue con `good first issue` e `help wanted` va bene anche il codice. Per una modifica più grande apri prima una [discussione](https://github.com/kintsugi-spme/kintsugi/discussions) o un'issue, così ci mettiamo d'accordo prima che tu lavori.

## Domande, idee, problemi

- **Domande e idee:** [Discussions](https://github.com/kintsugi-spme/kintsugi/discussions).
- **Un comportamento inatteso:** issue con il modulo «Problema».
- **Un'attività da fare:** issue con il modulo «Attività», assegnata a una milestone.

## Come proporre una modifica

1. **Parti da un'issue.** Cerca una issue aperta o aprine una. Ogni PR ne chiude una.
2. **Crea un branch dal `main` aggiornato.** Gli esterni lavorano su un fork, gli autori su un branch del repository. Il nome ha un prefisso e un argomento breve, in minuscolo e con i trattini: `feat/`, `fix/`, `docs/`, `exp/` (per esempio `docs/guasto-f6`).
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
