import pandas as pd
import pytest

from kyc_quality.synthetic_data import generate_synthetic_dataset


def test_generation_is_reproducible_and_explicitly_synthetic():
    first = generate_synthetic_dataset(n_clients=40, seed=51)
    second = generate_synthetic_dataset(n_clients=40, seed=51)
    for key in ("clients", "beneficial_owners", "documents", "seeded_defects"):
        pd.testing.assert_frame_equal(first[key], second[key])
    assert first["clients"]["synthetic"].all()
    assert len(first["clients"]) == 40
    assert first["seeded_defects"]["defect_type"].eq("validation").sum() == 9


def test_all_seeded_entity_labels_are_synthetic():
    dataset = generate_synthetic_dataset()
    assert dataset["clients"]["client_id"].str.startswith("SYN-").all()
    assert dataset["beneficial_owners"]["owner_name"].str.startswith("Sample Owner ").all()
    assert dataset["documents"]["document_reference"].str.startswith("SYN-DOC-").all()


def test_rejects_dataset_too_small_to_include_all_scenarios():
    with pytest.raises(ValueError, match="at least 34"):
        generate_synthetic_dataset(n_clients=33)
