# Fáze 1 — buňky jako instanční masky

Co vzešlo z `research/`. Podrobnosti a čísla jsou v
[cellpose-rematch](../research/2026-11-14-cellpose-rematch/), tady je jen
návod k použití.

## Jak to funguje

```
                 ┌─ Cellpose ──────────────┐
                 │  KTERÉ buňky existují   │  konzervativní, vynechá bordel
snímek ─────────▶┤                         ├──▶ watershed ──▶ instanční masky
                 │  KAM AŽ sahá cytoplazma │  řízený model na této doméně
                 └─ HistGradientBoosting ──┘
```

Cellpose instance jsou **markery**, předpovězené popředí je **maska**. Každá
metoda dodá to, v čem je silná. Medián průměru buňky vychází 129–135 px proti
změřeným ~120 px, nejblíž ze všech zkoušených variant.

## Soubory

| | |
|---|---|
| `balf_pipeline.py` | příznaky, semantický model, fúze, post-processing |
| `make_annotation_batch.py` | vyrobí dávku návrhů masek pro Cellpose GUI |

## Vyrobení dávky k anotaci

```bash
uv run python make_annotation_batch.py --samples sample_1_2122_23 --images 1 --quadrants tl
```

Volby: `--samples` (adresáře na HF), `--images` (čísla 1–25), `--quadrants`
z `tl tr bl br`, `--out` (kam).

Snímky se krájí na **čtvrtiny**. Celý snímek 4024×3036 se v GUI edituje
mizerně; čtvrtina má 2012×1518 a buňky v ní pořád ~120 px — stejný formát,
jaký měly anotace v diplomce.

Model se při prvním spuštění naučí (~2 min) a uloží do `../models/`. Potřebuje
naklonovaný `github.com/Fido18246/ing_thesis` kvůli anotacím.

Na každý výřez vzniknou tři soubory:

```
<název>.png            výřez, ten se otevírá v GUI
<název>_seg.npy        navržené masky, GUI je načte samo vedle snímku
<název>_overlay.jpg    náhled pro rychlou kontrolu bez GUI
```

## Oprava masek v Cellpose GUI na Windows

### Instalace

```powershell
py -m venv cellpose-env
```

```powershell
cellpose-env\Scripts\activate
```

```powershell
pip install "cellpose[gui]"
```

### Spuštění

```powershell
python -m cellpose
```

### Postup

1. **File → Load image** a vyber `<název>.png`. Soubor `_seg.npy` se načte
   automaticky, protože leží vedle a má stejný název — masky se objeví rovnou.
2. Projdi návrhy a oprav je:
   - **smazat masku:** `Ctrl` + klik na ni
   - **nakreslit masku:** levým tlačítkem obtáhni buňku a uzavři smyčku
   - **zpět:** `Ctrl+Z`
   - **skrýt/zobrazit masky:** `X`, obrysy `Z`
3. **Ulož přes `Ctrl+S`.** Přepíše se `_seg.npy` vedle snímku.
4. Pošli zpátky `_seg.npy` (PNG posílat nemusíš, ty mám).

### Na co si dát pozor

- **Vícejaderné buňky nerozděluj.** Když má jedna cytoplazma víc jader, je to
  jedna buňka a má diagnostický význam. Pipeline je rozdělit může — tohle je
  přesně to, co od tebe potřebujeme vědět.
- **Bordel a rozbité buňky nech bez masky.** Do diferenciálního počtu nepatří.
  Když je model označil, smaž je.
- **Nedokonalé obrysy nech být.** Zajímá nás hlavně *kolik buněk a kde*, ne
  přesnost hranice na pixel.
- **Buňky na okraji výřezu** — rozhodni se pro jedno pravidlo a drž se ho.
  Doporučení: ponechat, pokud je vidět aspoň jádro.

## K čemu to je

Z oprav vznikne první **instanční ground truth**, který projekt nemá. Tím se
odemknou dvě věci, co jsou teď zablokované:

- **doučení Cellpose** na této doméně,
- **poctivé měření** — dosud nešlo říct, jestli se shluk rozdělil správně, jen
  jestli sedí plocha.
