# Research — index experimentů

Chronologický přehled toho, co se zkoušelo. **Čti jako první**, ušetří otevírání
jednotlivých složek. Aktualizuje se při uzavření každého experimentu.

Neúspěchy zůstávají — „zkusili jsme X, nefungovalo, protože Y" má často větší
cenu než to, co vyšlo.

| Datum | Experiment | Otázka | Verdikt |
|---|---|---|---|
| 2026-11-10 | [cellpose-baseline](2026-11-10-cellpose-baseline/) | Zvládne předtrénovaný Cellpose tyhle snímky na CPU, a v jakém čase? | ✅ ano — s předzmenšením 33 s/snímek, IoU 0,97 proti plnému rozlišení |

**Legenda:** ✅ jde dál · ❌ zamítnuto · 🔄 běží · ⏸️ odloženo

## Co z dosavadních experimentů platí

- **Fáze 1 = Cellpose-SAM s předzmenšením** na průměr ~30 px. Plné rozlišení
  stojí 11,6× víc času za IoU 0,97, tedy za nic.
- **`diameter` v Cellpose-SAM neřídí cíl segmentace**, jen přeškálování vstupu.
  Model vrací vždy celé buňky, jádra z něj nedostaneme.
- **Neextrapoluj časy z malých výřezů** — Cellpose si snímek interně dlaždicuje,
  takže škálování z výřezů 512²/1024² přestřelilo 3×.
- **Recall zatím není změřený.** Bez ručních anotací je „najde většinu buněk"
  vizuální soud, ne číslo.
