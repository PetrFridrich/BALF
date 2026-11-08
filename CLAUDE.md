# BALF

Detekce a segmentace buněk v bronchoalveolární lavage. Python 3.12, Poetry,
PyTorch Lightning.

## Stav projektu (k 2026-11-08)

Projekt se staví **od začátku**. Větev `main` byla záměrně resetována na
prázdnou historii (orphan commit, 0 souborů). Starší prototyp je archivovaný,
viz Git níže.

Co existuje: surová data na HuggingFace. Co neexistuje: masky, anotace,
jakýkoli kód na `main`.

## Na začátku každé session

1. **Zkontroluj prostředí.** Zavolej `get_environment`. Když session neběží na
   prostředí `BALF` (`env_01M7mZbXNWpduTZgkgwqwLa3`), přepni se na něj přes
   `switch_environment` s `mode: "network_only"`. Na `Default` není povolený
   žádný host, takže HuggingFace je odtud nedostupný (proxy vrací
   `CONNECT tunnel failed, 403`).
2. **Neověřuj HF token ručně.** Je uložený v network secrets prostředí BALF a
   proxy ho vkládá do requestů na `huggingface.co` sám. Ověřeno: `huggingface_hub`
   funguje bez `HF_TOKEN`, žádný placeholder není potřeba. Hodnotu tokenu nikdy
   nevidíš ani ji nepotřebuješ.
3. **Nepředpokládej write přístup do GitHubu.** Zápis do `PetrFridrich/BALF`
   dosud selhává s 403. Před pushem to ověř a při selhání předej změny uživateli
   místo opakovaných pokusů.

## Data

Private dataset **`Fido18246/BALF`** na HuggingFace (pozor, HF jméno je
`Fido18246`, ne `PetrFridrich`).

| | |
|---|---|
| Souborů | 126 (125 PNG + `.gitattributes`) |
| Celkem | 1,8 GB |
| Struktura | 5 adresářů `sample_N_<id>/`, v každém `2023_12_14_image_{1..25}.png` |
| Snímek | 4024 × 3036, RGB, uint8, ~15 MB |

Vzorky: `sample_1_2122_23`, `sample_2_2122_23`, `sample_3_2285_23`,
`sample_4_2285_23`, `sample_5_2123_23`. Dvojice vzorků sdílejí ID pacienta
(2122, 2285) — **při train/test splitu děl po vzorcích, ne po snímcích**, jinak
vznikne leakage mezi snímky stejného pacienta.

**Masky ani anotace zatím neexistují.** Nepiš kód, který je načítá, dokud
nevznikne anotační formát — a ten nejdřív dohodni s uživatelem.

Stahování: `huggingface_hub.hf_hub_download(..., repo_type='dataset')`.
Netahej celých 1,8 GB kvůli vývoji — vezmi jeden vzorek nebo pár snímků.
Data **necommituj do gitu** (předchozí verze tím nafoukla `.git` na 412 MB).

## Git

- Default větev: `main`, aktuálně prázdná historie (orphan `e981290`).
- **`idea` je archiv** původního prototypu (`acc2f13`, 281 souborů, ~1 GB dat).
  Je to jediná kopie staré práce na GitHubu — **nemazat, nepřepisovat**.
- Vývoj probíhá na zadané branchi, ne přímo na `main`.
- Data, `.venv/`, `results/`, `tb_logs/`, `__pycache__/` patří do `.gitignore`.

## Komunikace

Uživatel píše česky, odpovídej česky. Technické termíny a identifikátory
nepřekládej.

## Poznatky ze starého prototypu

Archiv na `idea` obsahoval Faster R-CNN (`fasterrcnn_resnet50_fpn`) nad
Lightning modulem. Chyby, které v něm byly — při psaní nové verze je nezaveď
znovu:

- `target['boxes']` se tvořily jako `torch.int64`; torchvision detekční modely
  chtějí **float**.
- Device byl hardcoded na `cpu` místo detekce CUDA.
- `__pycache__/*.pyc` byly commitnuté v gitu.
- Train/val/test split byl náhodný přes snímky, bez ohledu na vzorek a pacienta.
