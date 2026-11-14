# Instanční masky z předpovězených jader, proti Cellpose

> ⚠️ **OPRAVA (2026-11-14): srovnání s Cellpose v tomto experimentu je neplatné.**
> Vycházel jsem z toho, že anotované snímky jsou zmenšeniny, a dosadil průměr
> buňky 60 px. Ve skutečnosti jsou to **výřezy v původním měřítku** a buňky mají
> ~120 px — změřeno podle průměru jader (69,7 px v anotacích proti ~69 px na
> plných snímcích). Cellpose tedy běžel s polovičním měřítkem, což podle jeho
> dokumentace vede k over-splittingu. Čísla pro `watershed` platí, čísla pro
> `cellpose` ne. Přeměřeno v [cellpose-rematch](../2026-11-14-cellpose-rematch/).

**Datum:** 2026-11-13 · **Verdikt:** ✅ řízená cesta dává lepší masky, ale obrysy jsou surové

## Co jsme chtěli zjistit

[supervised-nuclei](../2026-11-13-supervised-nuclei/) skončil u semantické mapy
(pozadí / cytoplazma / jádro) s Jaccardem 0,77. Projekt ale potřebuje
**instanční** masky — jeden obrys na buňku. Dvě otázky:

1. Dá se semantická mapa převést na instance watershedem seedovaným
   **předpovězenými** jádry? (Minule byly markery ground truth, tedy horní mez.)
2. Jak si to vede proti Cellpose na týchž snímcích?

## Setup

- **Trénink:** 40 anotovaných snímků z `ing_thesis`, HistGradientBoosting,
  27 příznaků včetně barevné dekonvoluce, přirozené vzorkování 30 000 px/snímek.
  Natrénováno za **120 s** na 1,2 M pixelech.
- **Test:** 10 zbylých snímků, 2012×1518.
- **Watershed:** markery = předpovězená jádra nad 50 px, maska = předpovězené
  popředí, hřeben = distanční transformace.
- **Cellpose:** 4.2.1.1, CPU, předzmenšení na průměr 30 px.

Důležitý detail: **průměr buňky 60 px, ne 120.** Anotace jsou na polovičním
rozlišení oproti projektovým datům, takže i buňky jsou poloviční. Se 120 px by
Cellpose zmenšoval čtyřikrát místo dvakrát.

## Co z toho vyšlo

### Čísla

Průměr přes 10 testovacích snímků:

| Metoda | Instancí | Pokrytí | Medián průměru | IoU popředí | Čas |
|---|---|---|---|---|---|
| **watershed** | **45,6** | 11,9 % | 83,5 px | **0,735** | **15 s** |
| Cellpose | 26,3 | 8,6 % | 97,9 px | 0,578 | 35 s |

Řízená cesta pokrývá správnou plochu výrazně líp (+0,157 IoU), najde o 73 %
víc objektů a je 2,3× rychlejší.

### Ale metody odpovídají na různé otázky

Tohle je podstatnější než ta čísla, viz
`outputs/2023_12_14_image_002_{watershed,cellpose}.jpg`:

- **Cellpose obkresluje jádra a husté části buněk.** Obrysy jsou hladké, ale
  bledou cytoplazmu nechává venku a řadu buněk vynechá úplně. Odtud nižší
  pokrytí (8,6 %) a paradoxně **větší** medián průměru — obkroužená věc je
  velké jádro, ne buňka.
- **Náš watershed sleduje hranici cytoplazmy** včetně bledé. To odpovídá tomu,
  jak je definovaná anotace.

### Výhrada, která to celé relativizuje

**Srovnání není férové a nelze ho číst jako „porazili jsme Cellpose".**

Náš model je natrénovaný na 40 snímcích **z téže série**, stejný mikroskop,
stejné barvení, stejný den. Cellpose tahle data nikdy neviděl. Navíc je
referencí anotace z diplomky, tedy přesně ta definice popředí, na kterou je náš
model fitovaný.

Poctivější formulace: **model natrénovaný na doméně sedí anotacím té domény
líp než zero-shot generalista.** To je očekávané. Užitečné zjištění je, že ta
řízená cesta je levná a dává obrysy na úrovni cytoplazmy, což je to, co
anotace i klinická definice buňky chtějí.

### Co je na našich maskách špatně

- **Roztřepené obrysy.** Pixelový klasifikátor nemá žádnou prostorovou
  hladkost, takže hranice jsou zubaté a uvnitř buněk zůstává šum.
- **Geometrické hrany ve shlucích.** Watershed nad distanční transformací
  dělí husté oblasti rovnými čarami, které neodpovídají ničemu v obraze.
- Obojí volá po post-processingu: morfologické vyhlazení, zalití děr,
  odstranění drobných objektů.

## Verdikt

✅ **Řízená segmentace + watershed je životaschopná fáze 1** a na těchto datech
předčí Cellpose v pokrytí i rychlosti.

- ✅ Převod semantické mapy na instance **funguje i s předpovězenými jádry**,
  ne jen s ground truth.
- ✅ Celá pipeline běží **15 s na snímek na CPU**, trénink 120 s.
- ⚠️ Obrysy jsou surové a potřebují post-processing.
- ⚠️ Náskok proti Cellpose je z velké části tím, že jsme na doméně trénovaní.

## Co dál

1. **Post-processing masek** — vyhlazení, zalití děr, odstranění drobtů.
2. **Pojistka proti over-splittingu** — watershed dělí i tam, kde pro hranici
   není důkaz v obraze.
3. **Ověřit na projektových datech** (4024×3036), ne jen na anotovaných.
4. Doplnit příznaky z diplomky a zjistit, jestli se dožene těch 0,040.

## Co tenhle experiment neříká

- **Kvalita instancí není změřená.** Anotace nemají instanční ID, takže
  nelze říct, jestli watershed rozdělil shluk *správně*. Těch 45,6 vs 26,3
  instancí neříká, kdo má pravdu — jen že se liší.
- Over-splitting vícejaderných buněk **nebyl kvantifikován**.
- IoU popředí měří plochu, ne oddělení buněk. Metoda, která slije celý shluk
  do jedné instance, by měla stejné IoU jako ta, co ho rozdělí správně.
- Měřeno na 2012×1518, projekt pracuje s 4024×3036.
- Cellpose běžel s **výchozími prahy**, bez jakéhokoli ladění.
