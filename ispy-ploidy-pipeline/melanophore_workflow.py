"""
melanophore_workflow.py
=======================

A workflow tailored to the roommate's actual assay: epinephrine-treated
melanophores (pigment cells whose melanin balls up into a compact spot at the
cell centre), imaged with:

  * a DNA / nuclear stain  (her GREEN channel)
  * BRIGHTFIELD            (melanin reads as a clean dark spot here)
  * (also a red channel that looks like xanthophore autofluorescence - not used)

It solves the three problems we discovered while looking at her image:

  1. WHICH cells are the melanophores?  -> find the dark central pigment spots in
     BRIGHTFIELD (one per melanophore). Brightfield is unambiguous; the
     fluorescence "darkness" trick was not.
  2. WHICH green objects are real nuclei vs xanthophores?  -> xanthophores are
     large, bright, autofluorescent green blobs sitting AWAY from any melanophore.
     We assign each green object to the nearest melanophore centre; objects with
     no nearby melanophore that are also large are flagged as xanthophores and set
     aside (they can serve as an assumed-2C reference).
  3. HOW to group nuclei into cells when a cell's 1-2 nuclei can sit on opposite
     sides?  -> both nuclei orbit the same central pigment spot, so "nearest
     melanophore centre" groups them correctly.

OUTPUT: a per-nucleus CSV (Cell_ID = which melanophore, Nuclear_Volume, intensity,
cell_type) that feeds straight into ploidy_pipeline.py, plus a QC overlay image so
you can SEE whether the melanophore detection is right before trusting the numbers.

  python3 ploidy_pipeline.py --csv data/melanophore_nuclei.csv \
      --intensity-col Nuclear_Volume --cell-col Cell_ID   # ploidy by size (melanin-proof)

IMPORTANT: the brightfield must be the SAME field of view as the green image (so
they overlay). The pigment-detection thresholds below WILL need a little tuning
on your real brightfield - run it, open the QC image, adjust, repeat.

INPUTS
------
  --brightfield BF.tif     brightfield image (melanin = dark). 2D; RGB is averaged.
  --dna GREEN.tif          the DNA/nuclear-stain channel (same shape as BF).
  --nuclei-labels NUC.tif  label image of nuclei segmented from the DNA channel
                           (e.g. from: `python -m cellpose --dir . --save_tif`).

KEY KNOBS (tune on the QC image)
  --pixel-size 0.54        microns per pixel (sets all the µm-based sizes).
  --pigment-min-um 1.5     smallest central pigment spot to accept (µm diameter).
  --pigment-max-um 12      largest.
  --assign-radius-um 18    a nucleus joins a melanophore if within this distance
                           of its pigment centre.
  --xantho-min-um 9        green objects this big (and unassigned) are called
                           xanthophores, not nuclei.
"""

import argparse
import os
import numpy as np
import pandas as pd
import tifffile
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.filters import gaussian, threshold_otsu
from skimage.measure import label, regionprops
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_gray(path):
    """Read an image; average colour channels if it's RGB brightfield."""
    im = tifffile.imread(path).astype(float)
    if im.ndim == 3 and im.shape[-1] in (3, 4):   # RGB(A)
        im = im[..., :3].mean(axis=-1)
    if im.ndim != 2:
        raise SystemExit(f"{path}: expected a 2D image, got shape {im.shape}.")
    return im


def detect_pigment_centres(img, px, min_um, max_um, source="brightfield",
                           dark_percentile=8.0):
    """Find melanophore central pigment spots = compact DARK blobs.

    Two sources:
      'brightfield' - melanin is unambiguously dark; flatten the illumination
                      (subtract a large blur) and Otsu-threshold the darkness.
      'dna'         - no aligned brightfield, so use the dark melanin VOIDS in the
                      DNA channel: smooth, then keep the darkest `dark_percentile`
                      of pixels. Noisier than brightfield (tune via the QC image).
    Keeps blobs whose size matches a pigment aggregate. Returns (y, x) centres.
    """
    if source == "brightfield":
        flat = img - gaussian(img, sigma=max(20, int(8 / px)), preserve_range=True)
        darkness = -flat
        darkness[darkness < 0] = 0
        thr = threshold_otsu(darkness) if darkness.max() > 0 else 0
        mask = darkness > thr
    else:  # 'dna': darkest patches of the smoothed DNA image are the melanin voids
        sm = gaussian(img, sigma=1.5, preserve_range=True)
        mask = sm < np.percentile(sm, dark_percentile)
    mask = ndi.binary_fill_holes(ndi.binary_opening(mask, iterations=1))

    min_area = np.pi * (0.5 * min_um / px) ** 2
    max_area = np.pi * (0.5 * max_um / px) ** 2
    centres = [r.centroid for r in regionprops(label(mask))
               if min_area <= r.area <= max_area and r.solidity > 0.6]
    return np.array(centres) if centres else np.empty((0, 2))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brightfield", default=None,
                    help="Brightfield image (melanin = dark), ALREADY registered to "
                         "the DNA grid (same shape). If your brightfield is a "
                         "different camera/size, either resample it to match first "
                         "or omit this and melanophores are found from the DNA "
                         "channel's melanin voids instead.")
    ap.add_argument("--dna", required=True, help="DNA/nuclear-stain channel image.")
    ap.add_argument("--nuclei-labels", required=True,
                    help="Label image of nuclei segmented from the DNA channel.")
    ap.add_argument("--centers-csv", default=None,
                    help="MOST RELIABLE option: a CSV of melanophore centre "
                         "coordinates you marked by hand in Fiji (multi-point tool "
                         "-> Measure), in DNA-image pixels. Needs x/y columns "
                         "(Fiji's X,Y or XM,YM work). If given, auto-detection is "
                         "skipped. Mark them on the fluorescence using the "
                         "brightfield as your guide.")
    ap.add_argument("--pixel-size", type=float, default=0.54, help="microns/pixel")
    ap.add_argument("--pigment-min-um", type=float, default=1.5)
    ap.add_argument("--pigment-max-um", type=float, default=12.0)
    ap.add_argument("--assign-radius-um", type=float, default=18.0)
    ap.add_argument("--dark-percentile", type=float, default=8.0,
                    help="Only used without --brightfield: the darkest this %% of "
                         "the DNA image is treated as melanin voids. Tune via QC.")
    ap.add_argument("--xantho-min-um", type=float, default=9.0,
                    help="Unassigned green objects bigger than this (µm diameter) "
                         "are called xanthophores, not nuclei.")
    ap.add_argument("--background", default="auto",
                    help="DNA background to subtract ('auto', 'none', or a number).")
    ap.add_argument("--out", default="data/melanophore_nuclei.csv")
    ap.add_argument("--qc", default="data/melanophore_qc.png",
                    help="Where to save the QC overlay you should eyeball.")
    args = ap.parse_args()

    px = args.pixel_size
    dna = load_gray(args.dna)
    nuc = tifffile.imread(args.nuclei_labels)
    if dna.shape != nuc.shape[-2:]:
        raise SystemExit(f"DNA image {dna.shape} and nuclei labels {nuc.shape} "
                         f"must be the same size.")

    # --- 1. melanophore centres: hand-marked > brightfield > DNA voids ---
    if args.centers_csv:
        cc = pd.read_csv(args.centers_csv)
        low = {c.lower(): c for c in cc.columns}
        xcol = next((low[k] for k in ("x", "xm", "centroid_x", "x_px") if k in low), None)
        ycol = next((low[k] for k in ("y", "ym", "centroid_y", "y_px") if k in low), None)
        if not xcol or not ycol:
            raise SystemExit(f"--centers-csv needs x and y columns; found {list(cc.columns)}")
        centres = np.column_stack([cc[ycol].to_numpy(float), cc[xcol].to_numpy(float)])
        ref_img, ref_name = dna, "DNA + hand-marked centres"
        print(f"using {len(centres)} hand-marked melanophore centres from {args.centers_csv}")
    elif args.brightfield:
        bf = load_gray(args.brightfield)
        if bf.shape != dna.shape:
            raise SystemExit(
                f"Brightfield {bf.shape} != DNA {dna.shape}. Your brightfield is a "
                f"different camera/size, so it must be REGISTERED and resampled onto "
                f"the DNA grid before use (cross-modality registration). For now, "
                f"omit --brightfield to detect melanophores from the DNA channel's "
                f"melanin voids instead.")
        ref_img, ref_name = bf, "brightfield"
        centres = detect_pigment_centres(bf, px, args.pigment_min_um,
                                         args.pigment_max_um, source="brightfield")
    else:
        ref_img, ref_name = dna, "DNA melanin-voids"
        centres = detect_pigment_centres(dna, px, args.pigment_min_um,
                                         args.pigment_max_um, source="dna",
                                         dark_percentile=args.dark_percentile)
    print(f"melanophore centres ({ref_name}): {len(centres)}")
    if len(centres) == 0:
        print("  No centres detected - tune --pigment-min-um/--pigment-max-um"
              + ("/--dark-percentile" if not args.brightfield else "")
              + " and check the QC image.")

    # --- 2. measure every green object, then classify it ---
    bg = (float(np.median(dna[nuc == 0])) if args.background == "auto"
          else 0.0 if args.background == "none" else float(args.background))
    props = regionprops(nuc, intensity_image=dna)
    rows = []
    cents = np.array([p.centroid for p in props]) if props else np.empty((0, 2))
    if len(centres) and len(cents):
        dist, idx = cKDTree(centres).query(cents)
    else:
        dist = np.full(len(cents), np.inf); idx = np.zeros(len(cents), int)

    radius_px = args.assign_radius_um / px
    xantho_min_area = np.pi * (0.5 * args.xantho_min_um / px) ** 2
    for i, p in enumerate(props):
        area = p.area
        total = max(p.intensity_mean - bg, 0.0) * area     # bg-subtracted DNA
        if dist[i] <= radius_px:
            ctype, cell_id = "melanophore_nucleus", int(idx[i] + 1)
        elif area >= xantho_min_area:
            ctype, cell_id = "xanthophore", -1            # 2C reference candidate
        else:
            ctype, cell_id = "other", -1                  # unassigned, excluded
        rows.append(dict(nucleus_id=p.label, Cell_ID=cell_id,
                         Nuclear_Volume=area, Total_Intensity=total,
                         Mean_Intensity=p.intensity_mean, cell_type=ctype,
                         dist_to_pigment_um=round(float(dist[i] * px), 2),
                         centroid_y=round(p.centroid[0], 1),
                         centroid_x=round(p.centroid[1], 1)))
    df = pd.DataFrame(rows)

    mel = df[df.cell_type == "melanophore_nucleus"]
    xan = df[df.cell_type == "xanthophore"]
    n_cells = mel.Cell_ID.nunique()
    print(f"green objects: {len(df)}  ->  melanophore nuclei: {len(mel)} "
          f"in {n_cells} cells | xanthophores (2C ref): {len(xan)} | other: "
          f"{(df.cell_type=='other').sum()}")
    if n_cells:
        per = mel.groupby("Cell_ID").size()
        print(f"  nuclei per melanophore: median {int(per.median())}, max {per.max()}, "
              f"binucleate+ {int((per>=2).sum())}")
    if len(xan):
        print(f"  xanthophore size (assumed 2C ref): median {xan.Nuclear_Volume.median():.0f}px "
              f"(NB: this is the autofluorescent body; for a true nuclear 2C anchor, "
              f"measure the xanthophore's nucleus)")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # Main output is analysis-ready: ONLY melanophore nuclei (so ploidy_pipeline
    # can be pointed straight at it). The full classification (incl. xanthophores)
    # is saved alongside for reference.
    mel.to_csv(args.out, index=False)
    all_path = args.out.replace(".csv", "_all_objects.csv")
    df.to_csv(all_path, index=False)
    print(f"wrote {args.out} (melanophore nuclei only) and {all_path} (everything)")

    # --- 3. QC overlay: trust nothing until this looks right ---
    def st(x, lo=2, hi=99.7):
        a, b = np.percentile(x, [lo, hi]); b = max(b, a + 1)
        return np.clip((x - a) / (b - a), 0, 1)
    fig, ax = plt.subplots(1, 2, figsize=(15, 8))
    ax[0].imshow(st(ref_img), cmap="gray")
    if len(centres):
        ax[0].scatter(centres[:, 1], centres[:, 0], s=40, marker="x",
                      c="red", linewidths=1.3)
    ax[0].set_title(f"{ref_name} + detected melanophore centres ({len(centres)})")
    ax[1].imshow(st(dna), cmap="gray")
    colors = {"melanophore_nucleus": "lime", "xanthophore": "magenta", "other": "yellow"}
    for ct, c in colors.items():
        sub = df[df.cell_type == ct]
        if len(sub):
            ax[1].scatter(sub.centroid_x, sub.centroid_y, s=12, c=c,
                          label=f"{ct} ({len(sub)})")
    if len(centres):
        ax[1].scatter(centres[:, 1], centres[:, 0], s=30, marker="x", c="red",
                      linewidths=1.0, label="pigment centre")
    ax[1].legend(fontsize=8, loc="lower center")
    ax[1].set_title("DNA channel + classified green objects")
    for a in ax: a.axis("off")
    fig.tight_layout(); fig.savefig(args.qc, dpi=120); plt.close(fig)
    print(f"wrote {args.qc}  <-- OPEN THIS and check the red x's sit on melanophores")
    print("\nNext:  python3 ploidy_pipeline.py --csv {0} "
          "--intensity-col Nuclear_Volume --cell-col Cell_ID".format(args.out))


if __name__ == "__main__":
    main()
