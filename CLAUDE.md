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

**Masky ani anotace neexistují.** Nepiš kód, který je načítá, dokud nevznikne
anotační formát — ten nejdřív dohodni s uživatelem.

Stahování: `huggingface_hub.hf_hub_download(..., repo_type='dataset')`.
Netahej celých 1,8 GB kvůli vývoji. **Data necommituj do gitu** — předchozí
verze tím nafoukla `.git` na 412 MB.

## Git

- Default větev `main`. Historie začíná prázdným orphan commitem `e981290`.
- Vývoj na zadané branchi, do `main` jen po dohodě.
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

## Komunikace

Uživatel píše česky, odpovídej česky. Technické termíny a identifikátory
nepřekládej.

## Otevřené otázky

Nerozhodnuto — než na tom začneš stavět, zeptej se:

- Co je výstup modelu (boxy / instanční masky / počty / klasifikace typů buněk)?
- Rozlišují se typy buněk, nebo jen buňka vs. pozadí?
- Jak vzniknou anotace a kdo je udělá?
- Jaká metrika rozhoduje o úspěchu a jaká hodnota je „dost dobrá"?
- Dostupný hardware (GPU / CPU)?
