"""A module containing helpful functions for interacting with the API."""

import json
from functools import lru_cache
from typing import Any

import pandas as pd
import requests
import re

from api.models import ConceptsQuery, EvidenceQuery


def _get_ggponc_date(v_string):
    if not v_string:
        return None
    return re.search("\d{4}_\d{2}_\d{2}", v_string).group(0)


def get_previous_guideline_versions(
    topic_config: dict, guideline_id: str, ggponc_version: str, include_non_ggponc_versions = False,
) -> tuple[str, dict]:
    result = []
    if tc := topic_config.get(guideline_id):
        if versions := tc.get("versions"):
            for k, v in versions.items():
                if (not v["ggponc"] and not include_non_ggponc_versions):
                    continue
                if not v["ggponc"] or (_get_ggponc_date(ggponc_version) >= _get_ggponc_date(v["ggponc"])):
                    result.append((k, v))
    return sorted(result, key=lambda x: (x[1].get("date"), _get_ggponc_date(x[1]["ggponc"])))[-1::-1]


def flatten_lists_of_lists(
    list_of_lists: list[list[Any]], unique: bool = True
) -> list[Any]:
    """Flatten a list of lists."""
    flattened = [item for sublist in list_of_lists for item in sublist]
    if unique:
        flattened = list(set(flattened))
    return flattened


def evidence_to_df(retrieved_evidence: dict[str, Any]) -> pd.DataFrame:
    """Return the retrieved evidence as a dataframe."""
    df = pd.DataFrame(retrieved_evidence)

    def extract_text(concepts):
        return [c["text"] for c in concepts]

    def extract_cpgs(concepts):
        return [c["matching_cpgs"] for c in concepts if c["matching_cpgs"]]

    if not df.empty:
        df["population"] = df["concepts_population_filtered"].apply(extract_text)
        df["interventions"] = df["concepts_intervention_filtered"].apply(extract_text)
        df["interventions_unknown"] = df["concepts_intervention_unknown"].apply(
            extract_text
        )
        df["interventions_known"] = df["concepts_intervention_known"].apply(
            extract_text
        )
        df["interventions_recommended"] = df["concepts_intervention_recommended"].apply(
            extract_text
        )
        df["interventions_not_recommended"] = df[
            "concepts_intervention_not_recommended"
        ].apply(extract_text)
        df["cpg_matches_population"] = (
            df["concepts_population_filtered"]
            .apply(extract_cpgs)
            .apply(flatten_lists_of_lists)
        )
        df["cpg_matches_intervention"] = (
            df["concepts_intervention_filtered"]
            .apply(extract_cpgs)
            .apply(flatten_lists_of_lists)
        )
        #  df.drop(columns=["concepts_population", "concepts_intervention"], inplace=True)
        df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
        if "date_last_update" in df.columns:
            df["date_last_update"] = pd.to_datetime(
                df["date_last_update"], errors="coerce"
            )
        df = df.astype({"pm_id": "Int64", "sample_size": "Int64", "phase_int": "Int64"})
        df.drop(
            columns=[
                "query",
                "concepts_intervention_filtered",
                "concepts_population_filtered",
            ],
            inplace=True,
        )
    return df


def concepts_to_df(retrieved_concepts: list[tuple[str | int, dict[str, Any]]]):
    """Return the retrieved concepts as a dataframe."""
    return (
        pd.DataFrame(
            [
                (e_id, c["cui"], c["text"], c["text_umls"], c["semantic_types"])
                for e_id, c in retrieved_concepts
            ],
            columns=["id", "cui", "term", "text_umls", "semantic_types"],
        )
        .drop_duplicates(subset=["id", "cui"])
        .set_index("id")
    )


@lru_cache
def query_api_for_supported_guidelines() -> list[str]:
    """Return a list of supported guidelines."""
    response = requests.get(url="http://localhost:8000/guidelines")
    return response.json()


def query_api_for_evidence(query: EvidenceQuery) -> dict[str, Any]:
    """Return the API response as a Python dictionary."""
    response = requests.post(
        url="http://localhost:8000/evidence/by/population",
        json=json.loads(query.model_dump_json()),
    )
    return response.json()


def query_api_for_concepts(
    query: ConceptsQuery,
) -> list[tuple[str | int, dict[str, Any]]]:
    """Return the API response as a Python dictionary."""
    response = requests.post(
        url="http://localhost:8000/concepts",
        json=json.loads(query.model_dump_json()),
    )
    return response.json()
