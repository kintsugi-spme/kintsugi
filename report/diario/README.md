# Diario di bordo

Una voce per sessione di lavoro e per ogni commit rilevante, in un file `AAAA-MM-GG-argomento.md` scritto copiando `_template.md`. Per un commit, basta un riassunto schematico breve: cosa è cambiato e perché, poche righe. È la base della "descrizione dettagliata delle operazioni, con limiti e difficoltà degli strumenti" richiesta dal professore: si scrive a ridosso del lavoro, non a memoria dopo.

I **limiti degli strumenti** emersi si raccolgono anche nella tabella qui sotto, che confluisce nel documento di architettura (`docs/`).

## Limiti degli strumenti emersi

| Data | Strumento | Limite | Impatto sulle misure | Voce del diario |
|---|---|---|---|---|
| 27/10/2026 | TikZ (`patterns`) con pdfTeX | Il riempimento tratteggiato produce un PDF che i lettori basati su Poppler non leggono | Nessuno sulle misure; figure del documento da compilare senza `patterns` | [2026-10-27](2026-10-27-revisione-documento.md) |
| 27/10/2026 | Mac ARM (locale) contro istanze `m5` x86 (AWS) | I due ambienti hanno architetture di CPU diverse | Nessuno sulle misure locali; da dichiarare nel confronto locale/AWS (RQ6) | [2026-10-27](2026-10-27-accettazione-decisioni.md) |
| 05/11/2026 | Docker Desktop (archivio di immagini classico) | Non costruisce né conserva in locale un'immagine con più architetture (`Multi-platform build is not supported for the docker driver`) | Nessuno sulle misure: in locale si usa solo arm64; arm64 e amd64 si verificano nella CI | [2026-11-05](2026-11-05-immagine.md) |
