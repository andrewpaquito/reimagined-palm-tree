# Ploidy from fluorescence images — a friendly pipeline (and an iSPy decoder ring)

You have fluorescence images of cells. The cells contain several nuclei. You want to know:

1. **What ploidy are the cells?** (2C, 4C, 8C, …) using fluorescence intensity as a stand‑in for DNA amount.
2. **Do the nuclei *inside the same cell* share a ploidy, or do they differ?**

Your collaborator's tool, **iSPy** (*inferring spatial ploidy*), does #1. It does **not** directly do #2, and its GitLab page is a wall of files. This folder gives you:

- a **plain‑English explanation** of what iSPy is actually doing (below), so the real repo stops looking scary;
- a **small, self‑contained pipeline** (`ploidy_pipeline.py`) that does the *same core method as iSPy* **plus** your within‑cell question, and makes presentation‑ready figures;
- a **demo dataset** so you can see the whole thing work in ~30 seconds before your own data is even ready;
- **exact fixes** for two bugs in iSPy's notebooks, in case you want to run their actual tool (see `ISPY_NOTEBOOK_FIXES.md`).

You do **not** need to be good at Python to use this. You run two commands and read the pictures.

---

## TL;DR — run the demo right now

```bash
cd ispy-ploidy-pipeline
python3 -m pip install -r requirements.txt   # one time
python3 make_demo_data.py                    # makes a fake dataset
python3 ploidy_pipeline.py                    # analyses it -> example_outputs/
```

(or just `bash run_demo.sh`). Then open the **`example_outputs/`** folder. You'll get the figures and tables described at the bottom of this file. Everything you see there was produced by exactly these commands — when your real data is ready you change one filename and rerun.

---

## The idea in one minute (this is all iSPy really is)

The trick everything rests on:

> **Fluorescence intensity ∝ amount of DNA. DNA *doubles* at each ploidy step (2C → 4C → 8C → 16C). So if you take `log₂` of intensity, the ploidy levels line up as evenly‑spaced bumps.**

Once you see the bumps, classifying ploidy is just "which bump does this nucleus belong to?" A **Gaussian Mixture Model (GMM)** answers that: it fits *K* bell curves to the bumps, and each bell curve **is** a ploidy class. Two honest questions follow, and the method has an answer for each:

- *How many bumps (ploidy levels) are there?* → try several values of *K*, keep the one the data likes best using a score called **BIC** (lower = better). That's the `fig2_model_selection.png` plot.
- *Are these really ploidy doublings?* → check that each class's mean intensity is ≈ **2×** the one below it. The pipeline prints this (it came out `1.93×, 1.94×, 2.03×` on the demo — i.e. yes, real doublings).

That's the entire scientific core. iSPy wraps it in lots of plotting, file‑naming, normalization options, and an optional step that paints your original image with the ploidy colors. The wrapping is what makes the repo look like "100000000 files."

```
   microscope image
        │   (segment nuclei: CellPose / StarDist / ilastik / Fiji …)
        ▼
   a CSV, one row per NUCLEUS  ── intensity, volume, which-cell-id
        │   (log2 + Gaussian Mixture Model)  ← this pipeline, and iSPy
        ▼
   each nucleus gets a ploidy class (2C/4C/8C/…)
        │
        ├──► ploidy distribution across cells        ← your question #1
        └──► group nuclei by cell → uniform vs mixed ← your question #2 (iSPy doesn't do this; this pipeline does)
```

---

## The real iSPy repo, demystified

It only has **five** Python files and **two** notebooks. Here's the whole map:

| File in the iSPy repo | What it actually does | Plain English |
| --- | --- | --- |
| `Two_Characteristics.ipynb` | The notebook you edit and run (no pre‑labelled cell types). | "Control panel": you set filenames + options at the top, hit run. |
| `Two_Characteristics_With_Objects.ipynb` | Same, but for data where you pre‑tagged cell types (e.g. *stomata* vs *nuclei*). | Use this one only if your CSV has a category column. |
| `tools/basics/Character_Class.py` | Defines `Characteristic` (one measured feature) and `Plotting` (your display settings). | Bookkeeping classes. You never edit it. |
| `tools/basics/Plotting_Definitions_Class.py` | The `Plot()` function: reads CSVs, makes the scatter + histograms. | The "draw the basic graphs" code. |
| `tools/curve_fitting/Curve_Fitting_SKLearn.py` | `Full_CurveFits()`: the GMM fitting + BIC/AIC search. | **The actual ploidy brain.** |
| `tools/curve_fitting/Curve_Fitting_Plotting.py` | Draws the fitted peaks, the class %s, writes the predictions CSV. | "Make the curve‑fit figures." |
| `tools/image_output/Image_Output.py` | `PredictionImage()`: paints your segmentation image by ploidy class. | Optional pretty "spatial map." |

**The output you most care about from iSPy** is the file it writes to
`Results/<your_name>/Curve_Fitting/Char_<intensity>/Data/Predictions_output.csv` —
that's your CSV with a **ploidy class added per nucleus**. (This pipeline writes the same thing as `example_outputs/per_nucleus_classified.csv`.)

> ⚠️ **Two real bugs in iSPy's notebooks** will stop you on the first run. They're easy to fix and I wrote out exactly how in **`ISPY_NOTEBOOK_FIXES.md`**. The short version: the plain notebook is missing one argument in a function call, and *both* notebooks forget to import the image‑painting function. If you only need the numbers/figures, you can skip iSPy entirely and use this pipeline.

---

## Use this pipeline on YOUR data

### Step 1 — get a per‑nucleus CSV

The pipeline (like iSPy) starts from a **CSV where each row is one nucleus**. You need at minimum:

| Column | What it is | Example value |
| --- | --- | --- |
| an **intensity** column | summed fluorescence of the nucleus (DNA proxy) | `Total_Intensity` = `5792.8` |
| a **cell‑id** column | which parent cell the nucleus is in (so #2 works) | `Cell_ID` = `1` |
| *(optional)* a **volume** column | nuclear size, an independent ploidy check | `Nuclear_Volume` = `101.3` |

Open `data/demo_nuclei.csv` to see the exact shape your file should have. Two ways to make yours:

- **You already use ilastik / a spreadsheet export?** Great — your CSV already has columns like `Total Intensity` and `Size in pixels`. Just note their exact names. (To get a `Cell_ID`, you need a segmentation of the *cells* as well as the *nuclei* — see below.)
- **You have segmentation *mask* images (from CellPose, StarDist, ilastik, Fiji)?** Use the included helper to build the CSV directly:
  ```bash
  python3 measure_from_labels.py \
      --nuclei-labels nuclei_mask.tif \
      --intensity     dapi.tif \
      --cell-labels   cell_mask.tif \      # optional but needed for question #2
      --out data/my_nuclei.csv
  ```
  (Needs the two optional packages — uncomment them in `requirements.txt` first.)

> **The honest hard part:** turning a raw microscope image into those masks (segmentation) is a separate step done in a GUI tool (CellPose/StarDist/ilastik/Fiji). This pipeline can't do that for you, and neither can iSPy — both *start* after segmentation. If you tell me what your images look like (channels, 2D vs 3D, file type, and whether you've segmented yet), I can point you to the fastest segmentation route.

### Step 2 — run the pipeline

```bash
python3 ploidy_pipeline.py \
    --csv data/my_nuclei.csv \
    --intensity-col Total_Intensity \
    --cell-col Cell_ID \
    --volume-col Nuclear_Volume
```

Useful options (run `python3 ploidy_pipeline.py --help` for all):

| Option | Use it when… |
| --- | --- |
| `--n-classes 4` | you *know* how many ploidy levels to expect (otherwise BIC auto‑picks). |
| `--base-ploidy 2` | your lowest class is 2C (the default). Set to 1 if it's 1C. |
| `--group-col genotype` | you want each genotype/condition analysed separately. |
| `--mixed-fold-threshold 1.5` | how strict "mixed" is (see note below). |
| `--cell-col none` | you have no cell grouping (skips question #2). |

---

## Your two questions → which output answers them

**Q1 — Ploidy across cells.**
`fig1_intensity_gmm.png` (the peaks), `fig3_class_percentages.png` (the %), and `summary.txt`. On the demo: 4 ploidy levels at 33.9% / 35.2% / 21.2% / 9.7% (2C/4C/8C/16C).

**Q2 — Do nuclei within a cell match?**
`fig4_within_cell.png` and `per_cell_summary.csv`. On the demo: ~60% of cells are **uniform** (all nuclei one ploidy) and ~33% are **confidently mixed**.

> **A subtlety worth knowing for your talk.** Calling a cell "mixed" just because its nuclei landed in two classes slightly *over‑counts*, because a nucleus sitting right on a class boundary can flip from noise alone. So the pipeline reports a second, stricter number: a cell is **confidently mixed** only if its brightest nucleus is ≥ `1.5×` its dimmest (between "no change" = 1× and "a real doubling" = 2×). The right‑hand panel of `fig4` shows this cleanly: uniform cells pile up near 1×, genuinely mixed cells sit out near 2×+. Report the stricter number; mention the simple one for completeness.

---

## What's in `example_outputs/`

| File | What it shows |
| --- | --- |
| `summary.txt` | Every headline number, in words. Read this first. |
| `fig1_intensity_gmm.png` | Intensity histogram with the fitted ploidy peaks. |
| `fig2_model_selection.png` | BIC/AIC vs number of classes — how *K* was chosen. |
| `fig3_class_percentages.png` | % of nuclei at each ploidy level. |
| `fig4_within_cell.png` | **Q2:** uniform vs mixed cells (two views). |
| `fig5_intensity_vs_volume.png` | Sanity check: bigger nuclei = higher class. |
| `fig6_validation.png` | Demo only: recovered ploidy vs the truth we built in (clean diagonal = it works). |
| `per_nucleus_classified.csv` | Your data + a `ploidy_class` / `ploidy_label` per nucleus. |
| `per_cell_summary.csv` | One row per cell: how many nuclei, uniform or mixed. |

---

## FAQ / gotchas

- **"Is this the same as iSPy?"** The ploidy‑classification math is the same recipe (log₂ → scikit‑learn `GaussianMixture` → pick *K* by BIC → order classes low→high → check ~2× steps). This pipeline adds the within‑cell grouping iSPy lacks and auto‑picks *K* for you. iSPy additionally can paint your *image* with ploidy colors — if you want that specific picture, run iSPy (with the fixes) and set `Prediction_Outputs = 1`.
- **"My intensities are huge / tiny."** Doesn't matter — only ratios matter, and the `log₂` step handles scale. Don't pre‑normalize.
- **"It found too many/few classes."** Force it with `--n-classes`, or widen/narrow `--min-classes/--max-classes`.
- **"Some nuclei have intensity 0 or blank."** They're dropped automatically (you can't take a log of 0); the count is reported.
- **Reproducibility.** Results are deterministic (fixed random seed). Change `--seed` to test robustness.

Questions, or want me to adapt this to your real CSV/columns or set up the segmentation step? Send a few rows of your actual file and I'll wire it up.
