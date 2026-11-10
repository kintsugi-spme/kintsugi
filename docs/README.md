# Documento di architettura

Progetto LaTeX che compila in due PDF: il documento di architettura (`main.pdf`: architettura, diagrammi, decisioni e protocollo di misura di Kintsugi, impostato come documentazione software) e la relazione di sintesi (`main-sintesi.pdf`, vedi sotto).

## Struttura

```
docs/
  main.tex                 documento di architettura: include tutto il resto tranne sintesi/
  main-sintesi.tex         relazione di sintesi: include sintesi/
  Makefile                 make = compila, make clean = pulisce, make controlla = verifica i numeri
  config/
    preambolo.tex          pacchetti
    metadati.tex           titolo, versione, autori, corso: si cambiano solo qui
    stile.tex              colori, intestazioni, titoli, ambiente "decisione"
    parametri.tex          macro \parametro{chiave} generate da ../config/parametri.yaml (non versionato)
  scripts/
    parametri.py           genera le macro e controlla i numeri nei file Markdown
  frontmatter/
    frontespizio.tex       frontespizio Federico II
    scheda-documento.tex   scheda, storico delle revisioni, convenzioni
    acronimi.tex           acronimi e termini
  chapters/
    01-introduzione.tex … 09-validita.tex
    decisioni/             un ADR per file (D0005-..., D0007-..., ...)
  sintesi/                 le sezioni della relazione di sintesi, una per file
  appendices/
    a-pianificazione.tex   milestone, stima dello sforzo, piano di taglio
    b-revisione.tex        revisione critica del piano: problemi e correzioni
  figures/                 immagini esterne (logo del frontespizio)
```

## Relazione di sintesi

Oltre al documento tecnico c'è una versione breve per la lettura dei docenti, `main-sintesi.tex`, con i sorgenti in `sintesi/` (una sezione per file). Riusa `config/` e `frontmatter/frontespizio.tex`, ma non i capitoli: i numeri comuni ai due documenti vanno tenuti allineati.

## Compilare

```bash
make            # entrambi i PDF (prima rigenera config/parametri.tex)
make sintesi    # solo la relazione di sintesi
make parametri  # solo config/parametri.tex
make controlla  # verifica i numeri marcati nei file Markdown
```

oppure `latexmk -pdf main.tex` e `latexmk -pdf main-sintesi.tex`, dopo aver creato `config/parametri.tex` con `make parametri`. Serve PyYAML (`pip install pyyaml`). I PDF, i file intermedi e `config/parametri.tex` non sono versionati.

## Controlli automatici

`.github/workflows/controlli.yml` parte a ogni pull request e a ogni fusione su `main`. Per i documenti: la PR punta a `main`, i numeri marcati nei Markdown coincidono con `config/parametri.yaml` (`make controlla`), i due PDF compilano. Lo stesso file esegue anche i test dell'app e la costruzione dell'immagine per le due architetture. I PDF restano scaricabili dalla pagina del controllo (artefatto `pdf`).

## Numeri del progetto

I numeri che compaiono in più punti, o che cambieranno dopo la fase F4 (misura della capacità), stanno in un solo file, [`../config/parametri.yaml`](../config/parametri.yaml). Le regole sono in testa al file e il perché sta in [`../config/README.md`](../config/README.md). Qui l'uso nel documento:

- **File LaTeX:** si scrive `\parametro{chiave}` al posto del numero. `make` rigenera `config/parametri.tex` (non versionato) prima di compilare. Una chiave sbagliata dà errore.
- **File Markdown** (README, piano): il numero va tra due marcatori, che `make controlla` verifica:

  ```
  Campagna di <!-- num:run_totali -->220<!-- /num --> run
  ```

- **Dove non si usano le macro:** previsioni (`chapters/08-previsioni.tex`, `sintesi/05-previsioni.tex`), schede delle decisioni (`chapters/decisioni/`), storico delle revisioni (`frontmatter/scheda-documento.tex`) e diario. Sono congelati dal tag `m1` oppure raccontano cosa era vero in quel momento: non devono cambiare se cambia un parametro.

`python3 scripts/parametri.py elenca` mostra chiavi e valori; `python3 scripts/parametri.py controlla --fix` riscrive i numeri marcati che non coincidono.

## Operazioni frequenti

- **Nuova versione del documento:** aggiorna `\versionedoc` in `config/metadati.tex` e aggiungi una riga allo storico in `frontmatter/scheda-documento.tex`.
- **Nuova decisione:** crea `chapters/decisioni/Dnnnn-titolo.tex` copiando un ADR esistente (ambiente `decisione`), aggiungi `\input` in `chapters/06-decisioni.tex` e aggiorna lo stato nella tabella del registro.
- **Nuovo parametro:** aggiungi la chiave in `../config/parametri.yaml` seguendo le regole in testa al file, poi usala con `\parametro{chiave}`.
- **Logo:** metti `logo-unina.pdf` (o `.png`) in `figures/`; il frontespizio lo usa da solo.
