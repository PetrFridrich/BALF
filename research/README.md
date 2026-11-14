# Research — index experimentů

Chronologický přehled toho, co se zkoušelo. **Čti jako první**, ušetří otevírání
jednotlivých složek. Aktualizuje se při uzavření každého experimentu.

Neúspěchy zůstávají — „zkusili jsme X, nefungovalo, protože Y" má často větší
cenu než to, co vyšlo.

| Datum | Experiment | Otázka | Verdikt |
|---|---|---|---|
| 2026-11-10 | [cellpose-baseline](2026-11-10-cellpose-baseline/) | Zvládne předtrénovaný Cellpose tyhle snímky na CPU, a v jakém čase? | ✅ ano — s předzmenšením 33 s/snímek, IoU 0,97 proti plnému rozlišení |

| 2026-11-11 | [nuclei-watershed](2026-11-11-nuclei-watershed/) | Pomůže segmentaci, když modelu dáme mapu jader a cytoplazmy? | ✅ ano, ale detektor jader musí být řízený — neřízené shlukování má IoU 0,50 |

| 2026-11-13 | [supervised-nuclei](2026-11-13-supervised-nuclei/) | Zreprodukovat RF z diplomky a zkusit lepší model | ⚠️ Jaccard 0,772 místo 0,812; lepší model než RF neexistuje, ale HGB je 22× levnější |

| 2026-11-13 | [instance-watershed](2026-11-13-instance-watershed/) | Dá se semantická mapa převést na instance, a obstojí proti Cellpose? | ✅ ano — IoU popředí 0,735 vs 0,578, 15 s vs 35 s; obrysy ale surové |

| 2026-11-14 | [cellpose-rematch](2026-11-14-cellpose-rematch/) | Cellpose ve správném měřítku, post-processing, a spojení metod | ✅ `fusion` (Cellpose jako markery + naše popředí) je nejlepší kandidát, byť nevyhrává v IoU |

**Legenda:** ✅ jde dál · ❌ zamítnuto · 🔄 běží · ⏸️ odloženo

## Co z dosavadních experimentů platí

- **Fáze 1 = Cellpose-SAM s předzmenšením** na průměr ~30 px. Plné rozlišení
  stojí 11,6× víc času za IoU 0,97, tedy za nic.
- **`diameter` v Cellpose-SAM neřídí cíl segmentace**, jen přeškálování vstupu.
  Model vrací vždy celé buňky, jádra z něj nedostaneme.
- **Neextrapoluj časy z malých výřezů** — Cellpose si snímek interně dlaždicuje,
  takže škálování z výřezů 512²/1024² přestřelilo 3×.
- **Máme ground truth!** 50 pixelově anotovaných snímků v diplomce uživatele
  (`Fido18246/ing_thesis`), stejná série, 2012×1518, třídy pozadí/cytoplazma/jádro.
  Nejsou instanční, ale pro semantickou segmentaci stačí.
- **Klasické ML nad filter-bank features dává IoU 0,81** (RF, 50 min trénink na
  CPU) — proti 0,50 u neřízeného shlukování. Měřeno uživatelem v diplomce.
- **Watershed z dobrých jader odděluje dotýkající se buňky**, ale nesmí být
  tvrdé pravidlo kvůli vícejaderným buňkám.
- **Volba modelu u semantické segmentace nerozhoduje** — RF, ExtraTrees a
  HistGradientBoosting jsou statisticky nerozlišitelné (rozpětí 0,004 při σ 0,013).
  Pracovní model je **HistGradientBoosting**, protože dá totéž za 11 s místo 246 s.
- **Trénovací vzorek musí držet skutečné rozložení tříd.** Vyvážené vzorkování
  (33/33/33 proti reálným 88/7/5) stálo 0,05 Jaccardu a ztrojnásobilo rozptyl
  mezi foldy. Pozná se to podle propadlé accuracy při zachovalém Jaccardu.
- **Fáze 1 má kandidáta: `fusion`** — Cellpose instance jako markery, naše
  předpovězené popředí jako maska. Bere konzervativnost Cellpose (vynechá
  bordel) a znalost rozsahu cytoplazmy od řízeného modelu. Medián průměru
  128,9 px je nejblíž změřeným ~120 px.
- **Pozor na měřítko:** anotované snímky jsou **výřezy, ne zmenšeniny**, buňky
  mají ~120 px. Chybných 60 px stálo Cellpose 0,064 IoU.
- **IoU popředí je zavádějící metrika** — odměňuje pokrytí bordelu a rozbitých
  buněk, které do diferenciálního počtu nepatří. Řazení metod podle ní
  nesleduj.
- **Dřívější kandidát:** HistGradientBoosting → semantická mapa → watershed
  z předpovězených jader. 15 s na snímek na CPU, trénink 120 s, IoU popředí
  0,735 proti 0,578 u Cellpose. Pozor: náskok je z velké části tím, že jsme
  na doméně trénovaní, zatímco Cellpose je zero-shot.
- **Cellpose a náš model odpovídají na různé otázky** — Cellpose obkresluje
  jádra a husté části buněk, náš model hranici cytoplazmy včetně bledé.
- **Recall zatím není změřený.** Bez ručních anotací je „najde většinu buněk"
  vizuální soud, ne číslo.
- **V hustých shlucích model přechází na segmentaci jader** místo celých buněk,
  takže „počet objektů" není „počet buněk" a mezi vzorky se nedá srovnávat.
  Nejdůležitější otevřený problém — ohrožuje přímo metriku diferenciálního počtu.
