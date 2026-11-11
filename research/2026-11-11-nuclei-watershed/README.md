# Jádra jako vodítko pro instanční segmentaci

**Datum:** 2026-11-11 · **Verdikt:** ✅ cesta jde dál, ale jinudy, než jsme čekali

## Co jsme chtěli zjistit

Z předchozího experimentu ([cellpose-baseline](../2026-11-10-cellpose-baseline/))
vyšlo, že Cellpose v hustých shlucích přechází na segmentaci jader a počty
objektů nejsou mezi vzorky srovnatelné. Nápad uživatele: dát modelu navíc
informaci, **kde je cytoplazma a kde jsou jádra**, a nechat ho jádra přiřadit
k cytoplazmám.

Tři otázky:

1. Jak dobře zvládne **neřízené shlukování** obnovit jádra a cytoplazmu? To
   rozhoduje, jestli má smysl vyrábět syntetický nukleární kanál.
2. Rozdělí **marker-controlled watershed** seedovaný jádry dotýkající se buňky?
3. Jak často má jedna souvislá oblast cytoplazmy víc jader, a jde o skutečnou
   vícejadernost, nebo jen o dotýkající se buňky?

## Setup

Ground truth: **50 pixelově anotovaných snímků** z diplomové práce uživatele
(`github.com/Fido18246/ing_thesis`, `Data/{Images,Labels}_ALL`), 2012×1518,
třídy pozadí / cytoplazma / jádro. Ověřeno, že to nejsou tytéž snímky jako na
HF (korelace obsahu 0,09–0,41), ale pocházejí ze stejné série.

Shlukování: `MiniBatchKMeans` nad syrovým RGB, 3 clustery, přeznačené podle
pořadí průměrné intenzity — zjednodušená verze postupu z repozitáře
`UnsupervisedCellImageSegmentation`.

## Co z toho vyšlo

### 1. Neřízené shlukování na syrovém RGB nestačí

Průměr přes 50 snímků:

| | IoU |
|---|---|
| Jádra | **0,498** |
| Cytoplazma | 0,426 |
| Popředí (cytoplazma + jádro) | 0,674 |

Navíc je to **nestabilní**. Na části snímků se to rozpadne úplně:
`image_044` dalo IoU cytoplazmy 0,061 a popředí 0,146, snímky 019–023 mají
IoU cytoplazmy kolem 0,20. Pravděpodobně kolísání barvení a expozice, kterému
prahování podle intenzity nerozumí.

Nukleární kanál v téhle kvalitě by modelu spíš uškodil než pomohl.

**Poctivá výhrada:** testovala se jen `MiniBatchKMeans`, ne plný ensemble pěti
algoritmů s majority votingem z repozitáře uživatele. Ten by mohl být lepší —
ale o 0,3 IoU sotva.

### 2. Diplomová práce tenhle problém řeší řádově líp

Ve `Results/Workflow_Testing/Full_effect_exploring_PoC/results.csv` jsou
**naměřené výsledky uživatele** pro klasické ML nad filter-bank features
(nepřepočítáno, převzato):

| Metoda | Accuracy | Jaccard | Dice | Čas trénování |
|---|---|---|---|---|
| LinearSVC | 0,964 | 0,793 | 0,877 | 3 012 s |
| **RF** | 0,965 | **0,812** | 0,891 | **3 007 s** |
| SVC | 0,967 | 0,819 | 0,895 | 255 312 s (71 h) |

Proti 0,50 z neřízeného shlukování je to jiná liga. A **RF se trénuje 50 minut
na CPU** — tedy v dosahu bez GPU. SVC je o 0,007 Jaccardu lepší za 85×
delší trénink, což je špatný obchod.

### 3. Watershed z dobrých jader odděluje buňky čistě

Watershed seedovaný **ground truth jádry** rozdělil shluky přesvědčivě, viz
`outputs/*_watershed.jpg`. Z 881 oblastí cytoplazmy vzniklo výrazně víc
instancí, protože se rozdělily právě ty vícejaderné.

**Toto je horní mez, ne dosažitelný výsledek.** Markery byly dokonalé.
Skutečná kvalita bude taková, jakou dá detektor jader — proto na něm záleží.

### 4. Vícejaderné oblasti: 30,8 %

Přes 881 oblastí cytoplazmy z 50 snímků:

| Jader v oblasti | Oblastí | Podíl |
|---|---|---|
| 1 | 610 | 69,2 % |
| 2 | 157 | 17,8 % |
| 3 | 65 | 7,4 % |
| 4 | 18 | 2,0 % |
| 5+ | 31 | 3,5 % |

**Co toto číslo neznamená:** že je 30,8 % buněk vícejaderných. Třítřídní
anotace nemají instanční ID, takže nerozliší jednu vícejadernou buňku od
několika dotýkajících se. Namátková kontrola tří oblastí se dvěma jádry
ukázala ve všech případech **dotýkající se samostatné buňky**, ale tři případy
nejsou měření.

Dlouhý ocas (oblasti s 5–10 jádry) téměř jistě jsou shluky, ne obří buňky.

## Verdikt

✅ **Cesta „jádra → watershed" je správná, ale detektor jader musí být řízený.**

- ❌ Neřízené shlukování na RGB zamítnuto — IoU 0,50 a nestabilní.
- ✅ Klasické ML nad filter-bank features dává IoU 0,81 za 50 minut CPU
  tréninku. To je kandidát na fázi 1.
- ✅ Watershed z dobrých jader odděluje dotýkající se buňky.
- ⚠️ Watershed **nesmí** být tvrdé pravidlo — rozdělil by vícejadernou buňku.
  Identitu určuje cytoplazma, počet jader je příznak. Viz CLAUDE.md.

## Co dál

1. Zreprodukovat RF z diplomky na těchto 50 snímcích a ověřit Jaccard 0,81.
2. Napojit na něj watershed a získat **instanční** masky.
3. Porovnat s Cellpose na stejných snímcích — kdo lépe zvládá husté shluky.
4. Vymyslet pojistku proti dělení vícejaderných buněk.

## Co tenhle experiment neříká

- **Instanční kvalita není změřená.** Ground truth nemá instanční ID, takže
  „watershed odděluje čistě" je vizuální soud, ne číslo.
- Čísla z diplomky jsou **převzatá z jejích výsledkových souborů**, nepřepočítaná.
- Shlukování reprezentovala jedna metoda, ne ensemble z původního repozitáře.
- Anotace jsou na 2012×1518, projekt pracuje s 4024×3036.
