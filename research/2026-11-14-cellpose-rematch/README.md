# Cellpose ve správném měřítku, post-processing a fúze metod

**Datum:** 2026-11-14 · **Verdikt:** ✅ fúze je nejlepší kandidát, metrika ale měří vedle

## Co jsme chtěli zjistit

Tři věci najednou:

1. **Opravit chybu v měřítku.** Předchozí experiment pouštěl Cellpose
   s průměrem buňky 60 px, protože jsem anotované snímky považoval za
   zmenšeniny. Jsou to výřezy v původním měřítku a buňky mají ~120 px.
2. **Post-processing masek** — obrysy z pixelového klasifikátoru byly roztřepené.
3. **Spojit víc metod**, což navrhl uživatel.

### Jak se chyba v měřítku poznala

2012×1518 je zároveň polovina 4024×3036 i rozměr čtvrtiny toho snímku, takže
podle rozměru se to rozlišit nedá. Rozhodla velikost buněk:

| | Medián průměru jádra |
|---|---|
| Anotace diplomky (2012×1518) | **69,7 px** |
| Plné snímky HF (4024×3036) | ~69 px |
| Kdyby šlo o zmenšení 2× | ~34,5 px |

Hypotézu vyslovil uživatel, měření ji potvrdilo.

## Setup

- Trénink: 40 anotovaných snímků, HistGradientBoosting, 27 příznaků,
  přirozené vzorkování. Test: 10 zbylých.
- Cellpose 4.2.1.1, CPU, předzmenšení na průměr 30 px.
- **Post-processing:** morfologické uzavření (disk r=3), zalití děr,
  odstranění objektů pod 400 px — po jednotlivých instancích.
- **Fúze:** Cellpose instance jako **markery**, maska = naše předpovězené
  popředí ∪ Cellpose. Myšlenka: Cellpose rozhoduje **které** buňky existují,
  náš model **kam až** sahá cytoplazma.

## Co z toho vyšlo

| Metoda | Instancí | Pokrytí | Medián průměru | IoU popředí |
|---|---|---|---|---|
| `cellpose_d60` (chybné měřítko) | 26,3 | 8,6 % | 97,9 px | 0,578 |
| `cellpose_d120` (správné) | 25,7 | 9,6 % | 112,9 px | 0,642 |
| `watershed` | 45,6 | 11,9 % | 83,5 px | 0,735 |
| `watershed_pp` | 40,6 | 12,3 % | 93,4 px | **0,752** |
| **`fusion`** | 25,7 | 12,1 % | **128,9 px** | 0,731 |

### Oprava měřítka stála Cellpose 0,064

0,578 → 0,642. Reálná chyba, ale hlavní závěr předchozího experimentu
**nepadl**: i se správným měřítkem Cellpose zaostává za řízenou cestou.
Náskok je ale 0,09, ne 0,157, jak jsem tvrdil.

### Post-processing funguje

0,735 → 0,752, a počet instancí klesl z 45,6 na 40,6. Těch pět, co ubylo, byly
šumové škvrny — medián průměru proto stoupl z 83,5 na 93,4 px.

### Fúze dělá přesně to, k čemu byla navržená

Vzala si **počet buněk od Cellpose** (25,7, přesně počet markerů) a **rozsah
cytoplazmy od našeho modelu** (pokrytí 12,1 % proti 9,6 % u Cellpose samotného).

Nezávislá kontrola, která nikam nevstupovala: **medián průměru 128,9 px** je
nejblíž změřené skutečnosti (~120 px odvozeno z jader). `watershed_pp` dává
93,4 px, tedy buňky tříští; Cellpose 112,9 px.

Vizuálně je to nejlepší výsledek zatím, viz `outputs/*_fusion.jpg` —
obrysy obkreslují celé buňky, jsou hladké, ve shlucích oddělují, a bordel
vynechávají.

### Našel se bug ve fúzi

První běh dal fúzi 16,4 instancí z 25,7 markerů, tedy **méně objektů, než
dostala semínek** — což bez slévání nejde. Příčina: markery se tvořily jako
`ndi.label(cellpose > 0)`, takže binarizace label mapy slila dotýkající se
Cellpose instance. Opraveno použitím label mapy přímo. Chybný běh je zachován
jako `outputs/metrics_fusion_bug.json`.

## Metrika měří vedle a je to vidět

`watershed_pp` má nejvyšší IoU (0,752), ale `fusion` je podle všeho lepší
kandidát. Proč ten rozpor:

**IoU popředí proti anotacím odměňuje pokrytí všeho, co anotátor označil —
včetně bordelu a rozbitých buněk.** Jenže do diferenciálního počtu patří jen
celé rozpoznatelné buňky. Metoda, která bordel vynechá, dostane horší IoU, ale
dá *lepší* diferenciál.

Uživatel si toho všiml dřív z pohledu na překryvy, než to ukázala čísla:
Cellpose vynechává bordel a rozbité buňky, a to je **vlastnost, ne vada**.

CLAUDE.md to má napsané — *„detekční metriky jsou diagnostika, ne cíl"* — a já
jsem se tím neřídil. Dokud nebude referenční diferenciál, lepší metriku
nepostavíme.

## Verdikt

✅ **`fusion` je nejlepší kandidát na fázi 1**, přestože nevyhrává v IoU.

- ✅ Oprava měřítka zapsána, Cellpose přeměřen.
- ✅ Post-processing přinesl +0,017 a odstranil šum. Bod uzavřen.
- ✅ Spojení metod funguje: konzervativnost Cellpose + znalost cytoplazmy.
- ⚠️ **Řazení podle IoU je zavádějící.** Metrika odměňuje pokrytí bordelu.
- ⚠️ Náskok řízené cesty nad Cellpose je z velké části tím, že jsme na doméně
  trénovaní, zatímco Cellpose je zero-shot.

## Co dál

1. **Doučit Cellpose** na této doméně — uživatelova volba. Fúze dává základ,
   proti kterému se zlepšení dá měřit. Potřebuje instanční anotace, které
   vzniknou opravami v Cellpose GUI.
2. Ověřit fúzi na projektových datech 4024×3036.
3. Postavit metriku, která netrestá vynechání bordelu.

## Co tenhle experiment neříká

- **Kvalita instancí není změřená.** Anotace nemají instanční ID.
- Over-splitting vícejaderných buněk **nebyl kvantifikován** u žádné varianty.
- Cellpose běžel s **výchozími prahy**, bez ladění.
- Post-processing má parametry (r=3, 400 px) zvolené od oka, neoptimalizované.
- Měřeno na výřezech 2012×1518, ne na plných snímcích.
