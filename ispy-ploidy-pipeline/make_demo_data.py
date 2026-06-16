"""
make_demo_data.py
=================

Creates a *fake* dataset that looks like what you would get after segmenting a
fluorescence image of multinucleate cells. It exists for two reasons:

  1. So you can run `ploidy_pipeline.py` end-to-end TODAY, before you have
     finished segmenting your own images, and see exactly what the figures and
     tables will look like.

  2. As a TEMPLATE. The columns produced here are the columns the pipeline
     expects. When your real data is ready, just make a CSV with these same
     column names (the values come from your images) and point the pipeline at
     it instead.

WHAT EACH ROW IS
----------------
One row = one NUCLEUS (not one cell). This matters: your cells contain several
nuclei, so a single cell shows up as several rows that share the same Cell_ID.

THE COLUMNS
-----------
  nucleus_id      A unique number for every nucleus (1, 2, 3, ...).
                  (In ilastik this is usually the column 'labelimage_oid'.)
  Cell_ID         Which parent cell this nucleus belongs to. Nuclei in the same
                  cell share a Cell_ID. THIS is what lets us ask "do the nuclei
                  inside one cell have the same ploidy?".
  Total_Intensity Summed fluorescence of the nucleus = our proxy for DNA amount
                  = our proxy for ploidy. This is the main measurement.
  Nuclear_Volume  Size of the nucleus. Higher-ploidy nuclei tend to be bigger,
                  so this is a useful second, independent check.
  true_ploidy     The ground-truth ploidy (2, 4, 8, ...) we used to build the
                  fake data. REAL data will NOT have this column - it is only
                  here so you can confirm the pipeline recovers the right answer.

The science we are faking: fluorescence intensity is proportional to DNA
content, and DNA content doubles with each ploidy step (2C -> 4C -> 8C ...).
So on a log-2 axis the ploidy classes sit at evenly spaced peaks. That even
spacing is the whole reason the Gaussian-mixture method works.
"""

import numpy as np
import pandas as pd

# A fixed random seed means you get the SAME demo data every time you run this.
# Change the number if you want a different random draw.
rng = np.random.default_rng(7)

# ----------------------------------------------------------------------------
# Knobs you can play with
# ----------------------------------------------------------------------------
N_CELLS = 220                  # how many parent cells to simulate

# The ploidy levels present in the tissue, and how common each is.
PLOIDY_LEVELS = np.array([2, 4, 8, 16])
PLOIDY_WEIGHTS = np.array([0.35, 0.35, 0.22, 0.08])  # must sum to 1

# Fraction of cells whose nuclei are NOT all the same ploidy. These "mixed"
# cells are exactly the thing your within-cell analysis is meant to detect.
FRACTION_MIXED_CELLS = 0.40

# Measurement model: one ploidy unit ("1C") of DNA gives this much fluorescence,
# on average. The exact number is arbitrary - only ratios matter.
INTENSITY_PER_C = 850.0
# Biological + imaging noise. 0.18 means roughly +/-18% spread within a ploidy
# class (lognormal). This is what gives each peak its width.
INTENSITY_NOISE = 0.18

VOLUME_PER_C = 14.0            # microns^3 of nuclear volume per ploidy unit
VOLUME_NOISE = 0.22

# ----------------------------------------------------------------------------
# Build the table, one cell at a time
# ----------------------------------------------------------------------------
rows = []
nucleus_id = 0

for cell_id in range(1, N_CELLS + 1):
    # Each cell has between 2 and 4 nuclei (your "multinucleate" cells).
    n_nuclei = rng.integers(2, 5)

    # Pick this cell's baseline ploidy from the tissue-wide distribution.
    base_ploidy = rng.choice(PLOIDY_LEVELS, p=PLOIDY_WEIGHTS)

    is_mixed = rng.random() < FRACTION_MIXED_CELLS

    for _ in range(n_nuclei):
        if is_mixed:
            # In a mixed cell, a nucleus may sit one ploidy step above or below
            # the cell's baseline (e.g. one nucleus underwent an extra round of
            # endoreduplication). np.clip keeps us inside PLOIDY_LEVELS.
            step = rng.choice([-1, 0, 1], p=[0.25, 0.4, 0.35])
            idx = np.clip(np.where(PLOIDY_LEVELS == base_ploidy)[0][0] + step,
                          0, len(PLOIDY_LEVELS) - 1)
            ploidy = PLOIDY_LEVELS[idx]
        else:
            # In a uniform cell, every nucleus is the cell's baseline ploidy.
            ploidy = base_ploidy

        nucleus_id += 1

        # Intensity proportional to DNA, times lognormal noise.
        intensity = (ploidy * INTENSITY_PER_C
                     * rng.lognormal(mean=0.0, sigma=INTENSITY_NOISE))
        # Volume also grows with ploidy, with its own independent noise.
        volume = (ploidy * VOLUME_PER_C
                  * rng.lognormal(mean=0.0, sigma=VOLUME_NOISE))

        rows.append({
            "nucleus_id": nucleus_id,
            "Cell_ID": cell_id,
            "Total_Intensity": round(float(intensity), 2),
            "Nuclear_Volume": round(float(volume), 3),
            "true_ploidy": int(ploidy),
        })

df = pd.DataFrame(rows)

out_path = "data/demo_nuclei.csv"
df.to_csv(out_path, index=False)

# A short, friendly summary so you can sanity-check the file you just made.
n_mixed = (
    df.groupby("Cell_ID")["true_ploidy"].nunique().gt(1).sum()
)
print(f"Wrote {out_path}")
print(f"  {len(df)} nuclei across {df['Cell_ID'].nunique()} cells")
print(f"  nuclei per cell: {df.groupby('Cell_ID').size().min()}"
      f"-{df.groupby('Cell_ID').size().max()}")
print(f"  cells with mixed ploidy (ground truth): {n_mixed} "
      f"({100*n_mixed/df['Cell_ID'].nunique():.0f}%)")
print(f"  ploidy levels present: {sorted(df['true_ploidy'].unique())}")
