import io
from pathlib import Path

from pypdf import PdfWriter

from app.research.baselines import attach_profiles, reference_records
from app.research.facts import decode
from app.research.sources import extract

ROOT = Path(__file__).resolve().parents[1]


def test_all_reference_exports_decode_and_remain_unchanged():
    records, version = reference_records(ROOT / "sem_pipeline/outputs/batchid")
    assert len(records) == 31 and len(version) == 64
    document = decode(records)
    before = len(document.samples[0].facts)
    attach_profiles(document, records)
    assert len(document.samples) == 31 and len(document.samples[0].facts) > before
    counts = [
        f.value
        for f in document.samples[0].facts
        if f.pointer.startswith("/reference_profiles/") and f.pointer.endswith("/locations")
    ]
    assert counts and all(1 < value < 31 for value in counts)
    assert any("not classifier distances" in warning for warning in document.samples[0].warnings)


def test_reference_profiles_exclude_the_query_location():
    records = [
        {
            "sample_id": f"loc_{i}",
            "true_batch": batch,
            "predicted_batch": batch,
            "material_model": {"features_S": {"siox_frac": {"value": value}}},
        }
        for i, (batch, value) in enumerate(
            [("Batch_1", 100), ("Batch_1", 2), ("Batch_1", 4), ("Batch_2", 8), ("Batch_2", 10)]
        )
    ]
    query = {**records[0], "sample_id": "img_loc_0"}
    document = decode(query)
    attach_profiles(document, records)
    facts = {fact.pointer: fact for fact in document.samples[0].facts}
    assert facts["/reference_profiles/siox_frac/Batch_1/median"].value == 3
    assert facts["/reference_profiles/siox_frac/Batch_1/locations"].value == 2


def test_image_only_pdf_is_quarantined():
    import pytest

    from app.research.sources import SourceError

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(SourceError, match="review"):
        extract(output.getvalue(), "application/pdf")
