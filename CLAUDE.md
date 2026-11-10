# BALF

Výzkumný projekt nad snímky bronchoalveolární lavage. Staví se od začátku,
společně, výzkumným postupem.

## Jak pracujeme

**Research-first.** Nic se nestaví „rovnou správně". Každý nápad dostane vlastní
složku v `research/`, vyhodnotí se, a teprve co obstojí, jde do `src/`.

```
research/
  README.md                      index všech experimentů + verdikty
  YYYY-MM-DD-slug/
    README.md                    otázka → setup → výsledek → verdikt
    <kód, configy>
src/                             to, co ve research vyhrálo
```

Pravidla, která drží záznam použitelný:

1. **`research/README.md` je index.** Tabulka: datum, co se zkoušelo, verdikt,
   odkaz na složku. Čti ho na začátku práce — ušetří otevírání všech podsložek.
   Aktualizuj ho při uzavření každého experimentu.
2. **Neúspěchy zůstávají.** „Zkusili jsme X, nefungovalo, protože Y" má často
   větší cenu než to, co vyšlo. Zahozené experimenty se nemažou.
3. **Uzavřený experiment se needituje.** Nový nápad = nová složka.
4. **Datum v názvu složky**, ne pořadové číslo — řadí se samo a je vidět vývoj.
5. Každý `README.md` experimentu odpovídá na: co jsme chtěli zjistit, jak jsme to
   postavili, co z toho vyšlo, a **jaký je verdikt** (jde dál / zamítnuto a proč).

## Pracovní postup

### Jazyk

- **Anglicky:** kód, identifikátory, komentáře v kódu, commit messages.
- **Česky:** README, CLAUDE.md, závěry a verdikty experimentů, komunikace
  s uživatelem.
- Technické termíny a identifikátory nepřekládej ani v českém textu.

### Autonomie

Experimenty **plánuj, spouštěj a vyhodnocuj sám** a přijď až se závěrem. Neptej
se na svolení ke každému pokusu — většina je laciná a odpověď je zajímavější
než plán.

Zeptej se vždy před:

- zápisem nebo mazáním v HF datasetu,
- přepsáním historie gitu nebo mazáním větví,
- rozhodnutím, které zásadně mění směr projektu.

### Výstupy experimentů

- **Do gitu**, ke složce experimentu: metriky, tabulky, pár náhledových obrázků.
  Jsou pak vidět přímo v README bez stahování.
- **Na HF dataset:** vygenerované masky a velké artefakty.
- Orientační hranice: cokoli nad ~1 MB patří na HF, ne do gitu.

## Cíl a zadání

Dvoufázová pipeline nad snímky BALF:

1. **Detekce** — najdi všechny buňky bez ohledu na typ. Výstup jsou **instanční
   masky**, tedy obrys každé buňky zvlášť. Z masek se dopočítají počty, bounding
   boxy i morfologie (velikost, tvar), takže maska je nadmnožina ostatních výstupů.
2. **Klasifikace** — typ buňky se určuje **zvlášť**, na výřezech z fáze 1.
   Rozlišované typy: **makrofágy, lymfocyty, neutrofily, eozinofily**.
   Počítej s velkou nevyvážeností: v normálním BALF tvoří makrofágy běžně přes
   80 % buněk, eozinofily bývají vzácné. Stratifikuj a nevyhodnocuj podle
   celkové accuracy — ta je při takovém rozložení bezcenná.

Každá fáze se ladí a vyhodnocuje samostatně. Detekce musí fungovat i předtím, než
existují anotace typů buněk — to je hlavní důvod pro dvoufázové rozdělení.

### Metrika úspěchu

Rozhoduje **přesnost diferenciálního počtu** — procentuální zastoupení typů
buněk ve vzorku proti referenci. Model smí chybovat na jednotlivých buňkách,
pokud agregovaný poměr sedí. Důsledky:

- Vyhodnocuj **na úrovni vzorku**, ne jednotlivého snímku.
- Systematické vychýlení jednoho typu je dražší než náhodný šum, který se
  vyruší. Sleduj bias, ne jen průměrnou odchylku.
- Detekční metriky (F1, IoU) jsou **diagnostika, ne cíl.** Měř je, ale
  neoptimalizuj podle nich.

### Anotace

Vznikají **poloautomaticky**: předtrénovaný model vygeneruje návrhy masek a
uživatel je opravuje a doplňuje v **Cellpose GUI** (má tenhle cyklus zabudovaný
jako hlavní scénář použití). Ruční kreslení od nuly je mimo hru — jeden snímek
4024×3036 může obsahovat tisíce buněk.

Vedlejší efekt, který je potřeba vytěžit: kvalita těch návrhů je **sama o sobě
výsledek**. Změř ji a zapiš, než se začne cokoli dolaďovat.

### Hardware: jen CPU

Žádná GPU, ani lokální, ani cloudová. Důsledky:

- **Trénink segmentačního modelu od nuly je mimo hru.** Fáze 1 stojí na
  předtrénovaném modelu a inferenci. Sázíme na to, že předtrénovaný model
  zgeneralizuje na tyhle snímky — pokud ne, prostor řešení se výrazně zužuje a
  je to potřeba zjistit co nejdřív.
- **Klasifikátor ve fázi 2 na CPU reálný je** — pracuje na malých výřezech buněk,
  ne na celých snímcích.
- Inference na snímku 4024×3036 bude na CPU pomalá. **Změř ji jako první věc**,
  než se na tom začne stavět cokoli dalšího.
- Preferuj dlaždicování (tiling) a dávkové offline zpracování před čímkoli
  interaktivním.

## Technologie

**Nejsou předem dané.** Volba nástrojů je otevřená a rozhoduje se podle toho, co
se pro daný problém hodí nejlépe — ne podle toho, co bylo v předchozím prototypu.
PyTorch, Faster R-CNN ani cokoli jiného ze staré verze není závazek.

Výjimka, kde rozhodnutí padlo: **správa závislostí = `uv`**, ne Poetry.

Když volíš technologii, napiš proč, a zapiš to do README daného experimentu.

## Na začátku každé session

1. **Zkontroluj prostředí.** Zavolej `get_environment`. Když session neběží na
   prostředí `BALF` (`env_01M7mZbXNWpduTZgkgwqwLa3`), přepni se na něj přes
   `switch_environment` s `mode: "network_only"`. Na `Default` není povolený
   žádný host, takže HuggingFace je odtud nedostupný (proxy vrací
   `CONNECT tunnel failed, 403`).
2. **HF token neověřuj ručně.** Je v network secrets prostředí BALF a proxy ho
   vkládá do requestů na `huggingface.co` sám. Ověřeno: `huggingface_hub` funguje
   bez `HF_TOKEN`, placeholder není potřeba. Token je fine-grained, rozsah
   read+write **jen** na dataset `Fido18246/BALF`.
3. **Přečti `research/README.md`**, pokud existuje — co už se zkoušelo.

## Data

Private dataset **`Fido18246/BALF`** na HuggingFace (HF jméno je `Fido18246`,
ne `PetrFridrich`).

| | |
|---|---|
| Souborů | 126 (125 PNG + `.gitattributes`) |
| Celkem | 1,8 GB |
| Struktura | 5 adresářů `sample_N_<id>/`, v každém `2023_12_14_image_{1..25}.png` |
| Snímek | 4024 × 3036, RGB, uint8, ~15 MB |

Vzorky: `sample_1_2122_23`, `sample_2_2122_23`, `sample_3_2285_23`,
`sample_4_2285_23`, `sample_5_2123_23`.

**Změřeno** na `sample_1_2122_23/2023_12_14_image_1.png` (zatím jediný snímek,
ber jako řádový odhad):

| | |
|---|---|
| Průměr jádra, medián | ~69 px |
| Rozsah jader (10.–90. percentil) | 39–95 px |
| Odhad průměru celé buňky | ~100–140 px |
| Popředí | ~19 % plochy |

Pozadí je světlé a čisté, kontrast velký — prahování najde popředí triviálně.
Těžká část je **oddělit dotýkající se buňky ve shlucích**, proto instanční masky.

Praktický důsledek pro Cellpose: jeho výchozí modely jsou trénované na objektech
o průměru ~30 px, takže si snímek sám přeškáluje zhruba 4× dolů. To je pro CPU
dobrá zpráva — nepracuje se s plnými 12 Mpx.

**Masky ani anotace neexistují.** Nepiš kód, který je načítá, dokud nevznikne
anotační formát — ten nejdřív dohodni s uživatelem.

Stahování: `huggingface_hub.hf_hub_download(..., repo_type='dataset')`.
Netahej celých 1,8 GB kvůli vývoji. **Data necommituj do gitu** — předchozí
verze tím nafoukla `.git` na 412 MB.

## Git

- Default větev `main`. Historie začíná prázdným orphan commitem `e981290`.
- **Pushuj přímo na `main`**, bez PR a bez ptaní. Když se něco nepovede,
  revertuje se.
- **`idea` je archiv** původního prototypu (`acc2f13`). Jediná kopie staré práce
  na GitHubu — **nemazat, nepřepisovat**.
- Do `.gitignore` patří data, `.venv/`, `results/`, `__pycache__/`.

## Větev `idea` — reference, ne mantinel

`idea` ukazuje, co a jak se dělalo předtím. Je to **zdroj kontextu, ne zadání.**
Neomezuj se jejími volbami a nepřebírej její architekturu jen proto, že tam je.

Co v ní nefungovalo a nemá cenu zavádět znovu:

- `target['boxes']` jako `torch.int64`; torchvision detekční modely chtějí float.
- Device hardcoded na `cpu` místo detekce CUDA.
- `__pycache__/*.pyc` commitnuté v gitu.

## Otevřené otázky

Nerozhodnuto — než na tom začneš stavět, zeptej se:

- **Odkud vezmeme referenční diferenciál?** Metrika je přesnost diferenciálního
  počtu, ale žádné referenční hodnoty pro těchto 5 vzorků zatím neexistují. Bez
  nich se úspěch nedá změřit.
- Jaká odchylka diferenciálu je ještě „dost dobrá"?
- Kolik snímků se bude anotovat a v jakém horizontu?
