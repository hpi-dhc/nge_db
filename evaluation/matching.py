"""A module containing logic for fuzzy title matching."""

from typing import Sequence

import numpy as np
import pandas as pd
from rapidfuzz import distance, process

list_like = Sequence | np.ndarray


def is_in_db(row: pd.Series, db_pm_ids: set[int], db_nct_ids: set[str]) -> pd.Series:
    """Add columns to row which show if the record is in the database."""
    row["is_in_db_pm"] = (
        int(row["pm_id"]) in db_pm_ids if pd.notnull(row["pm_id"]) else False
    )
    row["is_in_db_ct"] = (
        row["nct_id"] in db_nct_ids if pd.notnull(row["nct_id"]) else False
    )
    row["is_in_db_title"] = pd.notnull(row["pm_id_db"]) or pd.notnull(row["nct_id_db"])
    row["is_in_db"] = any(
        [row["is_in_db_pm"], row["is_in_db_ct"], row["is_in_db_title"]]
    )
    return row


def has_fuzzy_title_match(
    title: str, choices: list[str] | set[str], fuzzy_cutoff: float = 0.95
) -> bool:
    """Return True if the title has a match among the choices."""
    match = process.extractOne(
        query=title,
        choices=choices,
        scorer=distance.Levenshtein.normalized_similarity,
        score_cutoff=fuzzy_cutoff,
    )
    return match is not None


def is_in_ggponc(
    row: pd.Series,
    ggponc_pm_ids: set[int],
    ggponc_titles: set[str],
    fuzzy_cutoff: float = 0.95,
) -> pd.Series:
    """Add a 'is_in_ggponc' flag if the Pubmed ID or a very close title match is in GGPONC."""
    row["is_in_ggponc"] = False
    if row["pm_id"] in ggponc_pm_ids:
        row["is_in_ggponc"] = True
    else:
        row["is_in_ggponc"] = has_fuzzy_title_match(
            title=row["title"], choices=ggponc_titles, fuzzy_cutoff=fuzzy_cutoff
        )
    return row


def check_for_matches_in_screened(
    df_query: pd.DataFrame, df_screened: pd.DataFrame
) -> pd.DataFrame:
    """Add flags for excluding already screened evidence."""
    df_query["is_screened"] = df_query.apply(
        lambda row: (
            row["pm_id"] in df_screened["pm_id"].dropna().values
            if pd.notnull(row["pm_id"])
            else False
        )
        or (
            (
                row["nct_id"] in df_screened["nct_id"].dropna().values
                if pd.notnull(row["nct_id"])
                else False
            )
        ),
        axis=1,
    )

    # Check if any title matches occur with the screened data (missing /mismatched IDs)
    df_query["has_title_match_in_screened"] = df_query.apply(
        lambda row: has_fuzzy_title_match(
            title=row["title"], choices=df_screened["title"].to_list()
        ),
        axis=1,
    )
    return df_query


def find_trial_publication_matches(
    df_retrieved: pd.DataFrame,
    pm_id: int,
    nct_id: str,
    referenced_pm_ids: list[int] | None,
    referenced_pm_ids_results: list[int] | None,
    referenced_nct_ids: list[str] | None,
    retrieved_nct_ids: set[str],
    retrieved_pm_ids: set[int],
):
    """Return results from Pubmed and Clinicaltrials which reference each other."""
    output = []
    # check if we find the trial referenced by the Pubmed publication in the query results
    if pd.notnull(pm_id) and isinstance(referenced_nct_ids, list_like):
        for nct_id in referenced_nct_ids:
            if nct_id in retrieved_nct_ids:
                output.append(
                    {
                        "nct_id": nct_id,
                        "pm_id": pm_id,
                        "date_pm": df_retrieved.query("pm_id == @pm_id")[
                            "publication_date_combined"
                        ].item(),
                        "date_nct": df_retrieved.query("nct_id == @nct_id")[
                            "publication_date_combined"
                        ].item(),
                        "link_type": "pm->nct",
                        "tagged_as_result": pm_id
                        in [int(p) for p in referenced_pm_ids_results]
                        if isinstance(referenced_pm_ids_results, list_like)
                        else False,
                    }
                )
    # check if we find a Pubmed publication on the trial's results in the query results
    if pd.notnull(nct_id) and isinstance(referenced_pm_ids, list_like):
        for pm_id in referenced_pm_ids:
            if pm_id in retrieved_pm_ids:
                output.append(
                    {
                        "nct_id": nct_id,
                        "pm_id": pm_id,
                        "date_pm": df_retrieved.query("pm_id == @pm_id")[
                            "publication_date_combined"
                        ].item(),
                        "date_nct": df_retrieved.query("nct_id == @nct_id")[
                            "publication_date_combined"
                        ].item(),
                        "link_type": "nct->pm",
                        "tagged_as_result": pm_id
                        in [int(p) for p in referenced_pm_ids_results]
                        if isinstance(referenced_pm_ids_results, list_like)
                        else False,
                    }
                )
    return output


def remove_non_null_duplicates(
    df,
    col_id: str = "pm_id",
    col_source: str = "source",
    categories: list[str] = ["Pubmed", "Civic", "ClinicalTrials"],
):
    """Remove duplicate records from a dataframe, keeping the first non-null record."""
    df_ddp = df.reset_index(drop=True).copy()
    df_ddp[col_source] = pd.Categorical(df_ddp[col_source], categories=categories)
    return df_ddp[
        (
            ~df_ddp.sort_values([col_id, col_source]).duplicated(
                subset=col_id, keep="first"
            )
        )
        | (df_ddp[col_id].isnull())
    ]


def add_unscreened_ggponc_citations(
    df_screened: pd.DataFrame, df_retrieved: pd.DataFrame
) -> pd.DataFrame:
    """Add unscreened citations from GGPONC to the screened data."""
    cols_from_retrieved = [
        "title",
        "abstract",
        "source",
        "publication_date_combined",
        "pm_id",
        "is_rct_pt",
        "is_in_ggponc",
    ]
    unscreened_but_in_ggponc = df_retrieved.query("is_in_ggponc == True")[
        cols_from_retrieved
    ]
    unscreened_but_in_ggponc["screening_origin"] = "ggponc"
    unscreened_but_in_ggponc["is_in_db"] = True
    unscreened_but_in_ggponc["is_relevant"] = True
    unscreened_but_in_ggponc["is_not_relevant"] = False
    unscreened_but_in_ggponc["is_rct_api"] = unscreened_but_in_ggponc[
        "is_rct_pt"
    ].astype(bool)
    unscreened_but_in_ggponc["is_screened"] = False
    return (
        pd.concat(
            [df_screened, unscreened_but_in_ggponc.drop(columns="is_rct_pt")],
            ignore_index=True,
        )
        .query("~pm_id.duplicated(keep='first') | pm_id.isnull()")
        .fillna({"is_screened": True})
    )
