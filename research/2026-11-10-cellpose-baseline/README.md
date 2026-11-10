# Cellpose baseline na CPU

**Datum:** 2026-11-10 · **Verdikt:** ✅ jde dál

## Co jsme chtěli zjistit

Fáze 1 projektu stojí na předtrénovaném segmentačním modelu — trénink vlastního
je bez GPU mimo hru. Odtud dvě otázky:

1. Zvládne předtrénovaný Cellpose snímky BALF, a v jakém čase na CPU?
2. Dá se to zlevnit předzmenšením snímku, aniž by se změnil výsledek?

Druhá otázka vznikla až během měření, viz níže.

## Setup

- **Cellpose 4.2.1.1** (Cellpose-SAM), torch 2.15 na CPU, 4 vlákna.
- Správa závislostí `uv`, viz `pyproject.toml` a `uv.lock`.
- Data: po jednom snímku z každého z 5 vzorků, 4024×3036 RGB.
- Skript: `run_baseline.py`, výstupy v `outputs/`.

Testované strategie: segmentace v **plném rozlišení** proti **předzmenšení**
na průměr, na který si Cellpose stejně interně škáluje (~30 px).

## Co z toho vyšlo

### Čas a shoda

Na `sample_1_2122_23/2023_12_14_image_1.png`:

| Strategie | Rozlišení inference | Čas | Objektů | Medián průměru |
|---|---|---|---|---|
| `cells_full` | 4024×3036 | 378,3 s | 513 | 120,6 px |
| `cells_prescaled` | 1006×759 | **32,6 s** | 513 | 120,4 px |

**IoU popředí mezi oběma = 0,97**, počet objektů je shodný na kus.
Předzmenšení dává **11,6× zrychlení prakticky zadarmo**.

Pro celý dataset to znamená rozdíl mezi ~13 hodinami a **~69 minutami**.

### Kvalita segmentace

Model najde většinu buněk a **dotýkající se buňky od sebe odděluje** — což byla
ta těžká část úlohy, protože prahování popředí je na těchto snímcích triviální.
Obrysy sledují hranici cytoplazmy.

| | |
|---|---|
| Buněk na snímek | 513 |
| Pokrytí plochy | 49,4 % |
| Medián průměru | 120,4 px (p10 80,2 · p90 153,1) |

Změřený medián 120 px nezávisle potvrzuje odhad velikosti buňky odvozený dřív
z průměru jader (~69 px).

Náhled: `outputs/sample_1_2122_23_cells_prescaled.jpg`

### Parametr `diameter` neřídí, co se segmentuje

Strategie `nuclei_prescaled` měla najít **jádra** (~69 px). Našla 521 objektů
s mediánem **119,9 px**, tedy prakticky totéž co `cells_prescaled` (513 / 120,4).

Cellpose-SAM je trénovaný jako scale-invariant — `diameter` řídí jen přeškálování
vstupu, ne cíl segmentace. Vrací vždy celé buňky.

Plánované srovnání „jádra vs. buňky" tím **padá**: obě varianty dávají buňky a
`nuclei_prescaled` je jen 3,5× pomalejší cesta ke stejné odpovědi.

### Konzistence napříč vzorky — tady je problém

Po jednom snímku z každého vzorku, `cells_prescaled`:

| Vzorek | Objektů | Pokrytí | Medián | p10 | p90 |
|---|---|---|---|---|---|
| sample_1_2122_23 | 513 | 49,4 % | 120,4 | 80,2 | 153,1 |
| sample_2_2122_23 | 502 | 30,6 % | **76,5** | **43,1** | 143,6 |
| sample_3_2285_23 | 88 | 9,5 % | 124,6 | 68,4 | 180,4 |
| sample_4_2285_23 | 129 | 15,2 % | 135,3 | 68,9 | 170,3 |
| sample_5_2123_23 | 268 | 28,9 % | 129,4 | 77,1 | 157,5 |

Čas byl u všech 27,5–32,6 s, tedy stabilní.

**Rozptyl počtu 88 až 513 je zčásti skutečný.** `sample_3` je vizuálně opravdu
řídký — na skle je málo buněk, takže 88 objektů odpovídá realitě, ne selhání.

**Ale `sample_2` odhaluje vadu.** Je to hustý shluk. Po obvodu model obkresluje
celé buňky (~120 px), zatímco **uvnitř shluku obkresluje jádra** (~45–70 px),
protože hranice cytoplazmy tam nejsou rozlišitelné. Odtud medián 76,5 px a p10
43,1 px proti 68–80 px u ostatních, při zachovaném p90. Rozdělení je bimodální:
jeden výstup míchá objekty na úrovni buněk a na úrovni jader.

Důsledek, který je potřeba brát vážně:

> **„Počet objektů" není „počet buněk"** a mezi vzorky se nedá přímo srovnávat.

Pro metriku projektu — přesnost diferenciálního počtu — je to zásadní: pokud se
v hustých oblastech počítají jádra místo buněk, bude diferenciál systematicky
vychýlený ve prospěch vzorků s jiným rozložením hustoty. A systematické
vychýlení je přesně to, co má metrika trestat nejvíc.

Tohle **neřeší žádné doladění rychlosti** a je to hlavní věc k vyřešení dřív,
než se postaví fáze 2.

## Čemu jsme se spletli

Dvě chyby, obě stojí za zapamatování:

1. **Překryv se vykresloval špatně.** Hranice se kreslily 1 px do plného
   rozlišení a obrázek se pak zmenšoval ~3×, takže se obrysy vytratily a dobrá
   segmentace vypadala děravě. Na základě toho padl chybný závěr, že model
   vynechává spoustu buněk. Hranice se teď počítají až nad zmenšeným náhledem.
2. **Extrapolace z malých výřezů přestřelila.** Z výřezů 512² a 1024² vycházelo
   nadlineární škálování (exponent ~1,5) a odhad ~20 min na plný snímek.
   Skutečnost byla 6,3 min — Cellpose si snímek interně dlaždicuje, takže se
   chování při větších velikostech vrací k lineárnímu. **Neextrapoluj časy
   z malých výřezů.**

## Verdikt

✅ **Jde dál.** Cellpose-SAM s předzmenšením je použitelný základ fáze 1:
~33 s na snímek na 4 vláknech CPU, odděluje dotýkající se buňky, IoU 0,97 proti
plnému rozlišení.

Co z toho plyne pro další práci:

- Fáze 1 = **Cellpose-SAM, předzmenšení na průměr ~30 px.** Plné rozlišení
  nemá důvod.
- Segmentaci jader tímhle modelem nedostaneme. Pro dvoufázový plán to nevadí —
  fáze 2 pracuje s výřezy celých buněk.
- **Konzistence napříč vzorky je problém**, viz výše. V hustých shlucích model
  přechází na jádra, takže počty objektů nejsou srovnatelné. Vyřešit dřív než
  fázi 2.

## Co tenhle experiment neříká

- **Nezměřili jsme recall proti pravdě.** Žádné ruční anotace neexistují, takže
  „najde většinu buněk" je vizuální soud, ne číslo. To změří až porovnání
  s ručně opravenými maskami.
- Pokrytí 49,4 % je popis výstupu, ne metrika kvality.
- Časy platí pro 4 vlákna v tomhle kontejneru, ne pro uživatelův Windows stroj.
- Měřil se **jeden snímek z každého vzorku**, ne všech 25. Rozptyl uvnitř vzorku
  tedy neznáme.
- IoU 0,97 mezi `full` a `prescaled` je ověřené jen na `sample_1`. U hustého
  `sample_2` může být předzmenšení horší — menší buňky se po zmenšení 4× dostanou
  pod rozlišení, na kterém Cellpose pracuje.
