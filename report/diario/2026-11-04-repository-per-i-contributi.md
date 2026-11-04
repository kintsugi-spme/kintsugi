# 2026-11-04 — Repository pronto per i contributi esterni

**Chi:** Francesco · **Fase:** F0 · **Durata:** 2 h · **Issue:** #46

## Cosa abbiamo fatto

Dopo lo spostamento nell'organizzazione `kintsugi-spme` e la richiesta di aiuto alla community, abbiamo analizzato regole e impostazioni del repository e preparato quello che serve a chi non è uno degli autori.

**Nei file (questa PR):**
- `CONTRIBUTING.md`: flusso issue → fork o branch → PR verso `main` → revisione → diario; nomi dei branch; cosa non si tocca dopo il tag `m1` (previsioni, tag, `main`).
- `.github/CODEOWNERS`: ogni PR chiede in automatico la revisione di entrambi gli autori; `config/parametri.yaml` e il capitolo delle previsioni sono elencati a parte.
- `.github/ISSUE_TEMPLATE/config.yml`: issue vuote disattivate, rimando alle Discussions.
- Template della PR: nuova voce «La PR punta a `main`».
- README, sezione «Contribuire»: rimando a `CONTRIBUTING.md` e alle Discussions.
- `CODE_OF_CONDUCT.md`: codice di condotta breve, adattato dal Contributor Covenant 2.1 (CC BY 4.0). Le segnalazioni vanno in privato a Francesco all'indirizzo `terrecuso.francesco@libero.it`, pubblicato nel file su sua indicazione (nessuno dei due autori ha un'email pubblica sul profilo GitHub). Manca ancora il contatto di Gianmarco.

**Sulle impostazioni di GitHub (non versionate):**
- Discussions attivate.
- Tolte le etichette `invalid`, `duplicate`, `wontfix`, `accessibility` (non usate da nessuna issue); tenute `good first issue` e `help wanted`.
- `good first issue` su #26, #28, #36 e `help wanted` su #27, #29 erano state applicate alle issue di M2 più piccole, ma **sono state tolte dopo la revisione di Gianmarco**: il regolamento universitario ammette l'aiuto esterno solo dopo la presentazione del progetto, e con le etichette le issue sarebbero state trovabili. Si rimettono dopo la presentazione.
- Descrizione di `F0-preparazione` corretta (non parla più di «account AWS»).

## Perché

Le regole del repository (una sola regola su `main`: 1 approvazione, discussioni risolte, niente force-push) impediscono di fondere senza revisione, ma non dicevano agli esterni come proporre una modifica, non assegnavano il revisore e lasciavano aprire issue vuote. Le PR impilate (base diversa da `main`) sfuggono alla regola, come successo con la #24: ora il flusso lo dice esplicitamente.

## Comandi e configurazione

```bash
gh label delete invalid duplicate wontfix accessibility --yes   # una alla volta
gh issue edit 26 28 36 --add-label "good first issue"
gh issue edit 26 28 36 --remove-label "good first issue"   # dopo la revisione
gh issue edit 27 29 --remove-label "help wanted"           # dopo la revisione
gh api -X PATCH repos/kintsugi-spme/kintsugi -f has_discussions=true
git remote set-url origin https://github.com/kintsugi-spme/kintsugi.git
```

## Risultato

Il repository ha le regole di contributo scritte, il revisore automatico e un punto per domande e idee. Le modifiche esterne si accettano solo dopo la presentazione del progetto: fino ad allora nessuna issue è marcata come adatta a chi arriva da fuori.

## Problemi e soluzioni

- Per errore ho attivato anche «Elimina il branch alla fusione», che non era stato confermato: rimesso com'era. Resta da decidere.
- Il remoto locale puntava ancora a `terrecruis/kintsugi` (GitHub reindirizza, ma conviene l'indirizzo nuovo): aggiornato.

## Limiti dello strumento emersi

- **Il tag `m1` non è ancora protetto:** non esiste una regola sui tag. Va creata insieme al tag.
- **Nessun controllo impedisce una PR verso un branch diverso da `main`:** le regole valgono solo per il branch protetto. Per ora lo dice solo `CONTRIBUTING.md`.
- **Impostazioni non versionate:** Discussions, etichette e regole stanno su GitHub e non in Git; questa voce di diario le documenta.
- **Da fare ancora:** controlli automatici (PR #48, per la #41), tag `m1` e release con i PDF, invito di Gianmarco come membro dell'organizzazione, profilo dell'organizzazione, annuncio del repository (da rimandare a dopo la presentazione, per chiedere aiuto con le modifiche) e il contatto di Gianmarco per le segnalazioni del codice di condotta.
