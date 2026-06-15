#!/usr/bin/env bash
# One command to reproduce the whole demo from scratch.
# Usage:  bash run_demo.sh
set -e

echo "[1/3] Installing Python packages (one-time)..."
python3 -m pip install -q -r requirements.txt

echo "[2/3] Generating the demo dataset..."
python3 make_demo_data.py

echo "[3/3] Running the ploidy pipeline..."
python3 ploidy_pipeline.py

echo
echo "All done. Look in the 'example_outputs/' folder:"
echo "  - summary.txt                  (every headline number in words)"
echo "  - fig1_intensity_gmm.png       (the ploidy peaks)"
echo "  - fig4_within_cell.png         (do nuclei in a cell share a ploidy?)"
echo "  - per_nucleus_classified.csv   (your data + a ploidy label per nucleus)"
echo "  - per_cell_summary.csv         (one row per cell: uniform vs mixed)"
