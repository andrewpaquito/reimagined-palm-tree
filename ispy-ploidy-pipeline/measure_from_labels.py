"""
measure_from_labels.py   (OPTIONAL - only if you have segmented label images)
=============================================================================

The ploidy pipeline needs a CSV where each row is one nucleus, with its summed
fluorescence and (ideally) which cell it belongs to. This script builds that
CSV directly from images, so you can skip ilastik's spreadsheet export if you
already have segmentation masks.

YOU NEED (as image files - TIFF works well; 2D or 3D both fine):
  --nuclei-labels   A "label image" of nuclei: background = 0, and every nucleus
                    painted with its own unique integer (nucleus 1 = 1s,
                    nucleus 2 = 2s, ...). This is what CellPose, StarDist,
                    ilastik object-segmentation, or Fiji's "Analyze Particles"
                    (with labeled output) produce.
  --intensity       The raw fluorescence image (same shape as the label image)
                    whose brightness is your DNA/ploidy signal.
  --cell-labels     (optional) A label image of the PARENT CELLS, same idea.
                    If given, each nucleus is assigned to the cell it overlaps
                    most, filling the Cell_ID column you need for the
                    within-cell analysis.

IT WRITES a CSV with columns:
  nucleus_id, Cell_ID (if cell labels given), Total_Intensity, Nuclear_Volume,
  Mean_Intensity, centroid coordinates
which is exactly what ploidy_pipeline.py expects.

EXAMPLE:
  python3 measure_from_labels.py \
      --nuclei-labels nuclei_mask.tif \
      --intensity dapi.tif \
      --cell-labels cell_mask.tif \
      --out data/my_nuclei.csv
"""

import argparse
import numpy as np
import pandas as pd
import tifffile
from skimage.measure import regionprops_table


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nuclei-labels", required=True,
                    help="Label image of nuclei (0 = background).")
    ap.add_argument("--intensity", required=True,
                    help="Raw fluorescence image (same shape as labels).")
    ap.add_argument("--cell-labels", default=None,
                    help="Optional label image of parent cells.")
    ap.add_argument("--require-cell", action="store_true",
                    help="Drop nuclei that fall inside NO cell in --cell-labels. "
                         "Use this when the cell mask marks only your cell type "
                         "of interest (e.g. a membrane marker on specific cells), "
                         "so nuclei from other cell types are excluded.")
    ap.add_argument("--out", default="data/my_nuclei.csv",
                    help="Where to write the CSV.")
    args = ap.parse_args()

    labels = tifffile.imread(args.nuclei_labels)
    signal = tifffile.imread(args.intensity)
    if labels.shape != signal.shape:
        raise SystemExit(
            f"Shape mismatch: nuclei labels {labels.shape} vs intensity "
            f"{signal.shape}. They must be the same image dimensions.")

    # regionprops does the heavy lifting: for every labelled nucleus it measures
    # area (= pixel/voxel count = volume) and intensity statistics.
    props = regionprops_table(
        labels, intensity_image=signal,
        properties=["label", "area", "mean_intensity", "centroid"],
    )
    df = pd.DataFrame(props)

    # Total intensity isn't a built-in property, so compute it: mean * area.
    df["Total_Intensity"] = df["mean_intensity"] * df["area"]
    df = df.rename(columns={
        "label": "nucleus_id",
        "area": "Nuclear_Volume",
        "mean_intensity": "Mean_Intensity",
    })

    # If parent-cell labels were given, assign each nucleus to the cell it sits
    # in (the cell label most common under that nucleus's pixels).
    if args.cell_labels:
        cells = tifffile.imread(args.cell_labels)
        if cells.shape != labels.shape:
            raise SystemExit("Cell-label image shape must match the nuclei labels.")
        cell_of = {}
        for lab in df["nucleus_id"]:
            overlap = cells[labels == lab]
            overlap = overlap[overlap > 0]          # ignore background
            if overlap.size:
                vals, counts = np.unique(overlap, return_counts=True)
                cell_of[lab] = int(vals[np.argmax(counts)])
            else:
                cell_of[lab] = -1                   # nucleus not inside any cell
        df["Cell_ID"] = df["nucleus_id"].map(cell_of)

        # If the cell mask marks only the cell type of interest, drop nuclei
        # that aren't inside any of those cells (they're other cell types).
        if args.require_cell:
            before = len(df)
            df = df[df["Cell_ID"] > 0].copy()
            print(f"  --require-cell: kept {len(df)} of {before} nuclei "
                  f"(dropped {before - len(df)} not inside any cell).")

    # Tidy column order.
    front = ["nucleus_id"] + (["Cell_ID"] if args.cell_labels else [])
    cols = front + ["Total_Intensity", "Nuclear_Volume", "Mean_Intensity"]
    cols += [c for c in df.columns if c not in cols]
    df = df[cols]

    df.to_csv(args.out, index=False)
    print(f"Wrote {args.out}: {len(df)} nuclei measured.")
    if args.cell_labels:
        n_cells = df.loc[df['Cell_ID'] > 0, 'Cell_ID'].nunique()
        print(f"  assigned to {n_cells} parent cells.")
    print("Next: run the pipeline on it, e.g.:")
    cell_flag = " --cell-col Cell_ID" if args.cell_labels else " --cell-col none"
    print(f"  python3 ploidy_pipeline.py --csv {args.out} "
          f"--intensity-col Total_Intensity{cell_flag}")


if __name__ == "__main__":
    main()
