# batch_match

Classifies which production batch (Batch_1, Batch_2, Batch_3) an SEM image comes from, and
answers "unsure" when the evidence is not strong enough.

## How the classifier works

`batch_classifier.py` combines four steps (its module docstring has the details):

1. **Known-location matcher.** Every reference image is stored as a binned edge map. A query
   image (any detector, or a crop) that shows a spot already in the reference set is found by
   phase correlation and gets that location's batch with certainty.
2. **Image-only models** for unseen locations, one per view (BSE, SE, InLens):
   - an *imaging fingerprint* (noise per phase, noise correlation, contrast ratios, sharpness,
     stripes, clipping) classified with shrinkage LDA;
   - *texture* features on 12.8 um tiles (power spectrum, local binary patterns, co-occurrence
     texture) classified with logistic regression.
   Both are temperature-calibrated and their probabilities averaged.
3. **Material range rule** (BSE only). Pore / graphite / bright-phase fractions with the 95%
   error bars from `get4.py`; if they fall in only Batch_1's or only Batch_2's range, that is
   the answer (unless the models point to Batch_3).
4. **Unsure.** A model answer is only given above the confidence at which held-out locations
   were at least 90% correct. `--forced` always answers using a two-step model instead.

Accuracy is measured with nested leave-one-location-out cross-validation. The batches share
the same measurable microstructure, so the models mostly recognise how each batch was imaged;
this only carries over to new images from the same imaging sessions.

## Layout

| Path | Contents |
| --- | --- |
| `batch_classifier.py` | Production classifier: features, models, calibration, `train` / `evaluate` / `predict` CLI. |
| `get4.py` | Phase-fraction uncertainty (GET4) used for the material range rule: a thin shim over the repository's single implementation, `analysis/get4/` (adds the old name `segment_bse`); `python get4.py` runs its command line. |
| `experiments/` | Exploratory research scripts that led to the current design (see `experiments/README.md`). |
| `scripts/fetch_missing.py` | Downloads the images listed in `scripts/drive_files.json` from Google Drive. |

## Usage

### From the main project (recommended)

Run from the repository root. `analysis/batch_match.py` imports `batch_classifier` unchanged,
points it at the project's reference images (`data/raw/batch_N/`) and keeps its caches, model and
results in `data/processed/batch_match/`:

```bash
python -m analysis.batch_match train      # one-off: fingerprints, textures, get4 materials, models (~40 min)
python -m analysis.batch_match evaluate   # leave-one-location-out accuracy, default + forced mode
python -m analysis.batch_match predict    # classify data/raw/unknown -> data/processed/batch_match/unknown.json
```

### Standalone

Run from this folder. Images are expected as `data/batches/<Batch_n>/img_<location>_<view>.tif`
(`python scripts/fetch_missing.py` downloads them); models, caches and reports are written to
`out/classifier/`.

```bash
python batch_classifier.py evaluate                 # honest accuracy (about 5 minutes once features are cached)
python batch_classifier.py train                    # fit on everything, save out/classifier/batch_model.pkl
python batch_classifier.py predict IMG.tif ...      # which batch? (view read from the file name)
python batch_classifier.py predict --forced IMG.tif # always answer (two-step model)
python batch_classifier.py train --exclude ID       # leave location ID out, then predict it as a fair spot check
```

`predict` refuses images that are part of the training data: a model tested on its own training
images gives a meaningless result.

## Experiments

`experiments/` holds the exploratory scripts used to choose features, models and decision rules.
They are kept for provenance, are not part of the production path and are linted with relaxed
rules. They add this folder to `sys.path` themselves and read / write `out/` here, so run them
from anywhere, e.g. `python experiments/explore_compare.py`.
