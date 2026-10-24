from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pandas as pd


BASE_NAMES = [
    "Northstar Marine Holdings", "Alderbrook Capital Partners", "Vela Biotechnologies",
    "Cairnfield Energy Group", "Lindenport Foods", "Orchid Harbor Systems",
    "Bluehaven Logistics", "Westbridge Components", "Crownridge Logistics",
    "Crown Ridge Logistics", "Meridian Field Services", "Pinewell Manufacturing",
    "Silverstrand Materials", "Granite Peak Consulting", "Solstice Renewables",
    "Ashford Data Works", "Evermere Trading", "Fairwater Medical Group",
    "Redfern Equipment", "Highland Orbit Technologies", "Stonegate Supply",
    "Brightmere Aviation", "Keystone Orchard Group", "Ternwell Industries",
    "Newhaven Textiles", "Brookfield Process Systems", "Arborline Mobility",
    "Mariner's Gate Ventures", "Westvale Packaging", "Summit Lantern Labs",
    "Willowbank Infrastructure", "Clearpath Industrial", "Harborfield Analytics",
    "Harbor Field Analytics", "Juniper Crest Foods", "Cedarline Networks",
    "Windward Estates", "Mosaic River Products", "Northpoint Precision", "Fieldstone Digital",
]

COUNTRY_CITIES = {
    "GB": ("United Kingdom", "Leeds", "Bristol", "London"),
    "US": ("United States", "Boston", "Austin", "Seattle"),
    "SG": ("Singapore", "Singapore"),
    "IE": ("Ireland", "Dublin", "Cork"),
}


def _date_text(value: date) -> str:
    return value.isoformat()


def generate_synthetic_dataset(n_clients: int = 40, seed: int = 2026) -> dict[str, pd.DataFrame]:
    """Return deterministic synthetic entities plus explicit seeded-defect truth labels.

    All entity labels and identifiers are generated for this demo. No live client or person
    records are used. At least 34 clients are required to retain every fixed seed scenario.
    """
    if n_clients < 34:
        raise ValueError("n_clients must be at least 34 to include all seeded scenarios")
    rng = random.Random(seed)
    as_of = date(2026, 10, 24)
    clients: list[dict[str, Any]] = []
    owners: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []

    for index in range(n_clients):
        client_id = f"SYN-{index + 1:04d}"
        country = rng.choice(list(COUNTRY_CITIES))
        country_name, *cities = COUNTRY_CITIES[country]
        city = rng.choice(cities)
        legal_name = BASE_NAMES[index] if index < len(BASE_NAMES) else f"Sample Enterprise {index + 1:03d}"
        jurisdiction = country
        incorporation = date(rng.randint(2002, 2020), rng.randint(1, 12), rng.randint(1, 28))
        onboarding = date(rng.randint(2020, 2025), rng.randint(1, 12), rng.randint(1, 28))
        due = as_of + timedelta(days=rng.randint(35, 700))
        clients.append({
            "client_id": client_id,
            "legal_name": f"{legal_name} Ltd",
            "registration_number": f"{country}-{7000000 + index:08d}",
            "jurisdiction": jurisdiction,
            "registered_address": f"{10 + index} Sample Quay, {city}",
            "country": country,
            "incorporation_date": _date_text(incorporation),
            "onboarding_date": _date_text(onboarding),
            "periodic_review_due": _date_text(due),
            "review_status": "onboarding",
            "synthetic": True,
        })
        if index not in {5}:  # SYN-0006 is intentionally missing owner rows.
            owners.append({
                "owner_id": f"OWN-{index + 1:04d}-A",
                "client_id": client_id,
                "owner_name": f"Sample Owner {index + 1:04d}-A",
                "ownership_percent": 60.0,
                "identity_reference": f"SYN-ID-{index + 1:04d}-A",
            })
            owners.append({
                "owner_id": f"OWN-{index + 1:04d}-B",
                "client_id": client_id,
                "owner_name": f"Sample Owner {index + 1:04d}-B",
                "ownership_percent": 40.0,
                "identity_reference": f"SYN-ID-{index + 1:04d}-B",
            })
        if index != 9:  # SYN-0010 is intentionally missing supporting documents.
            documents.append({
                "document_id": f"DOC-{index + 1:04d}-INC",
                "client_id": client_id,
                "document_type": "certificate_of_incorporation",
                "issue_date": "2023-01-10",
                "expiry_date": "2028-01-10",
                "document_reference": f"SYN-DOC-{index + 1:04d}-INC",
            })

    # Controlled validation defects: one rule-targeted defect per expected detection.
    clients[1]["legal_name"] = ""
    clients[2]["registration_number"] = "??INVALID"
    clients[3]["incorporation_date"] = "2028-01-01"
    clients[8]["onboarding_date"] = "2020-01-01"
    clients[8]["periodic_review_due"] = "2024-01-01"
    documents = [d for d in documents if d["client_id"] != "SYN-0005"]
    documents.append({
        "document_id": "DOC-0005-INC", "client_id": "SYN-0005",
        "document_type": "certificate_of_incorporation", "issue_date": "2020-01-01",
        "expiry_date": "2024-01-01", "document_reference": "SYN-DOC-0005-INC",
    })
    clients[6]["jurisdiction"] = "GB" if clients[6]["country"] != "GB" else "US"
    clients[7]["registered_address"] = "London"
    clients[10]["registration_number"] = clients[11]["registration_number"]
    # Similar but legitimate entities are kept as separate synthetic records.
    clients[32]["legal_name"] = "Harborfield Analytics Ltd"
    clients[33]["legal_name"] = "Harbor Field Analytics Inc"

    client_df = pd.DataFrame(clients)
    owner_df = pd.DataFrame(owners, columns=["owner_id", "client_id", "owner_name", "ownership_percent", "identity_reference"])
    document_df = pd.DataFrame(documents, columns=["document_id", "client_id", "document_type", "issue_date", "expiry_date", "document_reference"])

    seeded = [
        ("SYN-0002", "REQ-001", "validation", "Legal entity name intentionally absent"),
        ("SYN-0003", "REG-001", "validation", "Registration number intentionally malformed"),
        ("SYN-0004", "INC-001", "validation", "Incorporation date intentionally in the future"),
        ("SYN-0005", "DOC-002", "validation", "Supporting document intentionally expired"),
        ("SYN-0006", "BO-001", "validation", "Beneficial-owner rows intentionally absent"),
        ("SYN-0007", "ATTR-001", "validation", "Jurisdiction intentionally conflicts with country"),
        ("SYN-0008", "ADDR-001", "validation", "Address intentionally incomplete"),
        ("SYN-0009", "REV-001", "validation", "Periodic review due date intentionally overdue"),
        ("SYN-0010", "DOC-001", "validation", "Supporting documents intentionally absent"),
    ]
    defect_rows = [{"defect_id": f"{client_id}:{rule_id}", "client_id": client_id, "client_id_2": "", "rule_id": rule_id, "defect_type": kind, "description": description} for client_id, rule_id, kind, description in seeded]
    defect_rows.extend([
        {"defect_id": "DUP-EXACT-SYN-0011-SYN-0012", "client_id": "SYN-0011", "client_id_2": "SYN-0012", "rule_id": "DUP-EXACT", "defect_type": "duplicate_exact", "description": "Registration identifier duplicated across separate client rows"},
        {"defect_id": "DUP-FUZZY-SYN-0009-SYN-0010", "client_id": "SYN-0009", "client_id_2": "SYN-0010", "rule_id": "DUP-FUZZY", "defect_type": "duplicate_fuzzy", "description": "Name variant seeded for human review; not automatically confirmed"},
    ])
    return {
        "clients": client_df,
        "beneficial_owners": owner_df,
        "documents": document_df,
        "seeded_defects": pd.DataFrame(defect_rows),
    }
