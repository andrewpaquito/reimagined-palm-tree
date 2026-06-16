# Running the *real* iSPy notebooks — the two fixes you need

You only need this file if you want to run the collaborator's actual tool
(for example, to get the **spatial colored ploidy map** of your segmentation,
which this folder's pipeline doesn't draw). For just the numbers and the ploidy
histograms, `ploidy_pipeline.py` is the faster path and you can ignore iSPy.

Both problems below are real and were confirmed by running their code. Both are
one‑line fixes.

---

## First: use their pinned environment

The iSPy repo ships `ispy_conda_env_linux.yml` and `ispy_conda_env_mac.yml`.
Use one — it installs the **exact** package versions iSPy was tested with
(numpy 1.26, pandas 2.2, scikit‑learn 1.5, etc.). Newer versions can break it in
unrelated ways, so don't skip this.

```bash
# in the iSPy repo folder:
conda env create -f ispy_conda_env_linux.yml      # or ..._mac.yml
conda activate ispy_env_linux                      # name is inside the yml
jupyter notebook
```

(Heads‑up, harmless: inside `Character_Class.py` and `Plotting_Definitions_Class.py`
the top comment lines are swapped — each says it's the *other* file. It does not
affect anything; Python loads by filename. Ignore it.)

---

## Bug 1 — `Two_Characteristics.ipynb` crashes with a `TypeError` immediately

**Why:** the `Characteristic(...)` class now takes **16** settings, the last being
`Column_ID_Label`, but this notebook only passes **15**. (The
`Two_Characteristics_With_Objects.ipynb` notebook was updated and passes 16 — the
plain one was left behind.) You'll see something like:

```
TypeError: Characteristic.__init__() missing 1 required positional argument: 'Column_ID_Label'
```

**Fix (3 small edits in `Two_Characteristics.ipynb`):**

**(a)** In the "Optional: Raw Image Files" block, where it currently says:

```python
Prediction_Outputs = 0
RawImageFiles = []
```

add two lines so it reads:

```python
Prediction_Outputs = 0
Prediction_Outputs_3D = 0          # <-- add
RawImageFiles = []
Column_ID_Label = ''               # <-- add  (for ilastik, use 'labelimage_oid')
```

**(b)** In the `MAIN SCRIPT` block, both `Char1 =` and `Char2 =` calls end with
`...High_Threshold1,RawImageFiles)`. Add `,Column_ID_Label` before the closing
parenthesis on **each**:

```python
Char1 = Class.Characteristic(Char1_Name,Char1_Norm,Char1_NormAtt,
                            Char1_Scale,Char1_Base,
                            Char1_BinType,Char1_BinValue,
                            Char1_Label,denChar1,1,
                            Low_Threshold_YN1,Low_Threshold1,
                            High_Threshold_YN1,High_Threshold1,RawImageFiles,Column_ID_Label)   # <-- added

Char2 = Class.Characteristic(Char2_Name,Char2_Norm,Char2_NormAtt,
                            Char2_Scale,Char2_Base,
                            Char2_BinType,Char2_BinValue,
                            Char2_Label,denChar2,2,
                            Low_Threshold_YN2,Low_Threshold2,
                            High_Threshold_YN2,High_Threshold2,RawImageFiles,Column_ID_Label)   # <-- added
```

That's it — the notebook now runs. (The `With_Objects` notebook does **not** need
this edit; it already passes 16.)

---

## Bug 2 — the spatial map feature (`Prediction_Outputs = 1`) crashes with `NameError`

**Why:** both notebooks *call* `PredictionImage(...)` at the very end, but
**neither imports it**. As long as `Prediction_Outputs = 0` you never hit it, so
it stays hidden — but the moment you turn the colored‑image feature on:

```
NameError: name 'PredictionImage' is not defined
```

**Fix (in *both* notebooks):** in the very first code cell, with the other
imports, add one line:

```python
import tools.basics.Character_Class as Class
from tools.basics.Plotting_Definitions_Class import Plot
from tools.curve_fitting.Curve_Fitting_SKLearn import Full_CurveFits
from tools.image_output.Image_Output import PredictionImage          # <-- add this
```

To then actually produce the colored image you also need to:

- set `Prediction_Outputs = 1`;
- put your nuclei **label image(s)** (ilastik "Object Identities" `.h5`, or a
  `.tif`/`.h5` where each voxel's value is its nucleus id) in `RawImageFiles`,
  one per CSV, in the **same order** as `Files`;
- set `Column_ID_Label = 'labelimage_oid'` (ilastik's column that ties each CSV
  row to its label in the image);
- make sure curve fitting actually ran (`curvefit_1d = 1` and/or
  `curvefit_2d = 1`), since the colors come from those predictions.

The colored maps are written under
`Results/<exp_str>/Curve_Fitting/.../Prediction_Images/`.

---

## Quick reference: the few settings you'll actually change in iSPy

Everything else in those long notebooks can stay at its default. To reproduce
the kind of analysis this folder's pipeline does, you'd set roughly:

```python
exp_str      = 'MyExperiment'          # output subfolder name
Char1_Name   = 'Total Intensity'       # <- your intensity column (match the CSV exactly)
Char2_Name   = 'Size in pixels'        # <- your volume column (optional second feature)
Files        = ['data/my_nuclei.csv']  # your CSV(s)
Legends      = ['Sample 1']
dims         = 2                        # 2 for 2D images, 3 for z-stacks
curvefit_1d  = 1                        # do the 1D (intensity-only) ploidy fit
BIC          = 1                        # pick best number of classes by BIC
LowN1d, HighN1d = 2, 8                  # search 2..8 ploidy classes
numPlots     = 1                        # how many best-fit plots to save
pngs         = 1                        # save figures as PNG
```

Your per‑nucleus ploidy classes land in
`Results/MyExperiment/Curve_Fitting/Char_Total Intensity/Data/Predictions_output.csv`.
That file is the iSPy equivalent of this pipeline's `per_nucleus_classified.csv`.
(iSPy has no built‑in "do nuclei within a cell agree?" step — feed that
`Predictions_output.csv`, which has your `Cell_ID` column carried through, back
into the within‑cell logic, or just use `ploidy_pipeline.py` from the start.)
