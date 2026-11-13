# Řízená segmentace jader a cytoplazmy

**Datum:** 2026-11-13 · **Verdikt:** ✅ cesta potvrzena, ale diplomku jsem nepřekonal

## Co jsme chtěli zjistit

Z [nuclei-watershed](../2026-11-11-nuclei-watershed/) vyšlo, že neřízené
shlukování dá jen IoU 0,50, zatímco klasické ML z diplomové práce uživatele
dosáhlo Jaccardu 0,812. Úkol zněl: **zreprodukovat to a zkusit něco lepšího
než Random Forest.**

## Setup

Stejný protokol jako diplomka, ověřeno v jejím kódu:

- **5-fold cross-validation dělená po snímcích** (`k_fold.split(paths)`), ne po
  pixelech — pixelový split by prosakoval mezi tréninkem a testem.
- **Jaccard `average='macro'`** přes tři třídy, stejně jako
  `Scripts/Workflow_Testing/Full_Effect/full_effect.py:86`. Ověřeno, aby čísla
  šla porovnat přímo.
- Ground truth: 50 anotovaných snímků z `Fido18246/ing_thesis`, 2012×1518.

Dvě sázky navíc proti diplomce:

1. **Barevná dekonvoluce.** MGG je dvoubarvivové barvení, takže optická hustota
   odděluje jádro od cytoplazmy na fyzikálním základě, zatímco syrové RGB ne.
   Právě na RGB uvázlo neřízené shlukování na 0,50.
2. **Histogram gradient boosting**, který na tabulkových datech obvykle poráží
   les a na CPU zůstává levný.

Příznaků celkem **27**: RGB (3), optická hustota (3), šedotón (1) a pro
σ ∈ {1, 2, 4, 8} Gauss, Sobel, Laplace a dvě vlastní čísla Hessiánu (20).

## Co z toho vyšlo

### Lepší model než Random Forest neexistuje

| Model | Jaccard (makro) | Accuracy | Jádro | Trénink |
|---|---|---|---|---|
| ExtraTrees | 0,7718 ± 0,0139 | 0,9551 | 0,744 | 49 s |
| RandomForest | 0,7699 ± 0,0133 | 0,9548 | 0,740 | 246 s |
| HistGradientBoosting | 0,7676 ± 0,0124 | 0,9539 | 0,738 | **11 s** |

Rozpětí mezi modely je **0,004 při směrodatné odchylce 0,013** napříč foldy.
To je šum. **Volba modelu tady nerozhoduje** a sázka na gradient boosting
nevyšla.

Jediný skutečný rozdíl je cena: HistGradientBoosting dá stejnou kvalitu
**22× levněji** než RF a **23 000× levněji** než SVC z diplomky, který za
71 hodin tréninku koupil +0,007 Jaccardu. Pro iterování je to zásadní.

### Našla se chyba v metodice a stála 0,05

První běh trénoval na **vyváženém vzorku** — 10 000 pixelů na třídu — jenže
skutečné rozložení je 88 % pozadí / 7 % cytoplazma / 5 % jádro. Model naučený
na 33/33/33 pak systematicky přestřeluje vzácné třídy.

| Model | Balanced | Natural | Rozdíl |
|---|---|---|---|
| RandomForest | 0,7183 | 0,7699 | **+0,0516** |
| HistGradientBoosting | 0,7163 | 0,7676 | +0,0513 |
| ExtraTrees | 0,7191 | 0,7718 | +0,0527 |

Accuracy přitom vyskočila z 0,917 na 0,955 a rozptyl mezi foldy klesl
z ±0,041 na ±0,013. Odhalila to právě ta accuracy: propad na 0,885 při
Jaccardu kolem 0,72 je typický podpis posunutých priorů, ne slabších příznaků.

**Poučení:** trénovací vzorek musí držet skutečné rozložení tříd, pokud se
vyhodnocuje na skutečném rozložení.

### Proti diplomce chybí 0,04

| | Jaccard | Accuracy | Příznaků |
|---|---|---|---|
| Diplomka, SVC | 0,819 | 0,967 | stovky |
| Diplomka, **RF** | **0,812** | 0,965 | stovky |
| Diplomka, LinearSVC | 0,793 | 0,964 | stovky |
| **Tento experiment, ExtraTrees** | **0,772** | 0,955 | **27** |

Reprodukce se **nepovedla** — chybí 0,040 Jaccardu. Příčina je nejspíš v
příznacích: diplomka používá barevné prostory (RGB, Lab, HSV, YCrCb, YUV),
šest hranových filtrů, osm filtrů barevné konstantnosti, NLM, TV, BM, osm
enhancement filtrů, morfologii a filtry z cv2. Její README uvádí paměťovou
náročnost řádově **100 GB**.

Na to se dá dívat dvěma způsoby a oba jsou pravdivé:

- **Negativně:** 27 ručně vybraných příznaků s barevnou dekonvolucí na
  bohatý filter bank nestačí.
- **Pozitivně:** 27 příznaků se dostane na 95 % jeho výsledku za zlomek
  paměti a času. Pro iterování je to lepší pracovní nástroj než pipeline
  vyžadující 100 GB.

## Verdikt

✅ **Řízená segmentace je potvrzená cesta pro fázi 1.** Jaccard 0,77 proti 0,50
u neřízeného shlukování, a to bez GPU.

- ❌ „Lepší model než RF" **zamítnuto** — tři modely jsou statisticky
  nerozlišitelné.
- ✅ **HistGradientBoosting jako pracovní model**: stejná kvalita, 11 s místo
  246 s. Na iterování se používá on.
- ⚠️ Reprodukce 0,812 **se nepovedla**, chybí 0,040. Dluh je v příznacích.
- ✅ **Oprava vzorkování** je obecné poučení, ne jen detail tohoto běhu.

## Co dál

1. Doplnit příznaky z diplomky k barevné dekonvoluci a zjistit, jestli se
   těch 0,040 dožene — a jestli dekonvoluce něco přidá i nad plným bankem.
2. Napojit watershed na předpovězená jádra a získat **instanční** masky.
3. Porovnat s Cellpose na stejných snímcích.

## Co tenhle experiment neříká

- **IoU je odhadnuté z rovnoměrného vzorku 300 000 pixelů** na testovací
  snímek, ne ze všech 3 milionů. Průnik i sjednocení škálují stejně, takže
  poměr drží, ale je to odhad.
- Čísla z diplomky jsou **převzatá z jejích výsledkových souborů**,
  nepřepočítaná na stejném hardwaru.
- Měřeno na 2012×1518, projekt pracuje s 4024×3036.
- **Instanční kvalita se neměřila** — tohle je pořád semantická segmentace.
- Příspěvek samotné barevné dekonvoluce **není izolovaný**; chtělo by to
  ablaci bez ní.
