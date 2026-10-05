"""Golden tests on one real location of batch_1 (marker `realdata`; skipped when the images are absent, e.g. in CI).

Golden files are keyed by image name under tests/golden/realdata/; a missing golden file skips the test.
Point SEM_RAW_DATA_DIR at a folder containing batch_1/ if the images are not in data/raw/ or data/.
"""

import pytest
from _get4_cases import get4_args
from _support import check_golden

from analysis import get4, kpi_single

pytestmark = pytest.mark.realdata


def test_get4_pipeline_on_real_bse(real_image, tmp_path):
    """analyse_image + analyse_batch (fast mode, image's own pixel size x 2) on one real BSE image."""
    args = get4_args(tmp_path)
    meta = get4.read_meta(real_image)
    target, note = get4.resolve_target([meta], args, None)
    result = get4.analyse_image(real_image, meta, target, args)
    batch = get4.analyse_batch([result])
    check_golden(
        f"realdata/get4_{real_image.stem}", {"target": [target, note], "image": result, "batch": batch}, missing="skip"
    )


def test_get4_copies_agree_on_real_bse(real_image, batch_match_modules, sem_get4):
    """batch_classifier's GET4 material step on the real image is identical in all three copies."""
    from _get4_cases import material_outputs
    from _support import compare, jsonable

    ref = jsonable(material_outputs(get4, real_image))
    for g4 in (batch_match_modules.get4, sem_get4):
        diffs = compare(ref, jsonable(material_outputs(g4, real_image)), rtol=0.0, atol=0.0)
        assert not diffs, "\n".join(diffs[:20])
    check_golden(f"realdata/material_{real_image.stem}", ref, missing="skip")


def test_kpi_single_measure_on_real_triplet(real_triplet):
    kp, info = kpi_single.measure(real_triplet["BSE"], {"ETD": real_triplet["ETD"], "InLens": real_triplet["Inlens"]})
    check_golden(f"realdata/kpi_single_{real_triplet['BSE'].stem}", {"kpis": kp, "info": info}, missing="skip")


def test_batch_classifier_fingerprint_on_real_bse(real_image, batch_match_modules):
    bc = batch_match_modules.batch_classifier
    fingerprint = bc.fingerprint(bc.load_u8(real_image))
    check_golden(f"realdata/fingerprint_{real_image.stem}", fingerprint, missing="skip")
