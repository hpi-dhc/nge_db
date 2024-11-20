from integration.orm import pubmed, aact
from sqlalchemy import select
from sqlalchemy.orm import Session
import numpy as np
import io
import pandas as pd
from pathlib import Path
from Bio import Entrez
from rapidfuzz import distance, process
import datetime
import re
import requests
import json
from functools import cache

@cache
def get_title_to_id_mapping_pubmed(session) -> pd.DataFrame:
    """Return a mapping of titles to Pubmed IDs for the Pubmed data."""
    query = select(
        pubmed.Trial.title.label("title"),
        pubmed.Trial.pm_id,
    )
    result = session.execute(query).all()
    return pd.DataFrame(result).drop_duplicates("title", keep=False)


def get_title_to_id_mapping_clinicaltrials(session) -> pd.DataFrame:
    """Return a mapping of titles to NCT IDs and Pubmed IDs for the AACT data."""
    query = select(
        aact.Trial.title_brief.label("title"),
        aact.Trial.nct_id,
    )
    result = session.execute(query).all()
    return pd.DataFrame(result).drop_duplicates("title", keep=False)


HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36\
     (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36"
}
PATTERNS = {
    "pm_id": re.compile(r"pubmed\/(\d{1,8})"),
    "pmc_id": re.compile(r"(PMC\d{1,8})"),
    "nct_id": re.compile(r"(NCT\d{8})"),
}


def doi_to_pm_id(
    doi: str, email: str, api_key: str, cache_path: str | Path
) -> int | None:
    """Return the Pubmed ID of a given DOI."""
    pm_id = None
    if pd.isnull(doi):
        return pm_id
    cache_dict = {}
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            cache_dict = json.load(f)
    if doi in cache_dict:
        pm_id = int(cache_dict[doi])
    else:
        Entrez.email = email
        Entrez.api_key = api_key
        handle = Entrez.esearch(db="pubmed", term=doi, idtype="doi")
        record = Entrez.read(handle)
        handle.close()
        if isinstance(record, dict):
            ids = record.get("IdList", [])
            if ids:
                pm_id = int(ids[0])
                cache_dict[doi] = pm_id
                with open(cache_path, "w") as f:
                    json.dump(cache_dict, f, indent=4)
    return pm_id


def cochrane_id_to_pm_info(
    cn_id: str,
    cache_path: str | Path,
    patterns=PATTERNS,
    headers=HEADERS,
) -> dict[str, str]:
    """Return a mapping of Cochrane ID to Pubmed information."""
    pm_info_dict: dict[str, str] = {}
    if pd.isnull(cn_id):
        return pm_info_dict
    cache_dict = {}
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            cache_dict = json.load(f)
    try:
        pm_info_dict = cache_dict[cn_id]
    except KeyError:
        response = requests.get(
            f"https://www.cochranelibrary.com/central/doi/10.1002/central/{cn_id}/full",
            headers=headers,
        )
        pm_info_dict = {"cn_id": cn_id}
        for name, pat in patterns.items():
            match = re.search(pat, response.text)
            if match:
                pm_info_dict[name] = match.group(1)
            else:
                continue
        cache_dict[cn_id] = pm_info_dict
        with open(cache_path, "w") as f:
            json.dump(cache_dict, f, indent=4)
    return pm_info_dict


def retrieve_all_identifiers(
    row: pd.Series,
    entrez_email: str,
    entrez_api_key: str,
    doi_pm_id_cache: str | Path,
    cn_pm_id_cache: str | Path,
    title_pm_id_cache: str | Path,
    title_nct_id_cache: str | Path,
    df_pm: pd.DataFrame,
    df_ct: pd.DataFrame,
    fuzzy_cutoff: float = 0.95,
) -> pd.Series:
    """Retrieve all available identifiers for a piece of evidence."""
    row["pm_id_doi"] = doi_to_pm_id(
        doi=row["doi"],
        email=entrez_email,
        api_key=entrez_api_key,
        cache_path=doi_pm_id_cache,
    )
    cochrane_info = cochrane_id_to_pm_info(
        cn_id=row["cn_id"], cache_path=cn_pm_id_cache
    )
    row["pm_id_cn"] = pd.to_numeric(cochrane_info.get("pm_id"), errors="coerce")  # type: ignore
    row["nct_id_cn"] = cochrane_info.get("nct_id")
    row["pmc_id_cn"] = cochrane_info.get("pmc_id")
    row["nct_id_db"] = title_to_id_from_db(
        title=row["title"],
        df_db=df_ct,
        title_col="title",
        id_col="nct_id",
        cache_path=title_nct_id_cache,
        score_cutoff=fuzzy_cutoff,
    )
    row["pm_id_db"] = title_to_id_from_db(
        title=row["title"],
        df_db=df_pm,
        title_col="title",
        id_col="pm_id",
        cache_path=title_pm_id_cache,
        score_cutoff=fuzzy_cutoff,
    )
    if pd.isnull(row["pm_id"]):
        row["pm_id"] = row[["pm_id_doi", "pm_id_cn", "pm_id_db"]].ffill().iloc[-1]
    if pd.isnull(row["nct_id"]):
        row["nct_id"] = row[["nct_id_cn", "nct_id_db"]].ffill().iloc[-1]
    return row


def title_to_id_from_db(
    title: str,
    df_db: pd.DataFrame,
    title_col: str,
    id_col: str,
    cache_path: str | Path,
    char_count_range: int = 5,
    score_cutoff: float = 0.95,
) -> int | str | None:
    """Look up an ID by title (fuzzy matching using Levenshtein distance)."""
    id_from_db = None
    if pd.isnull(title):
        return id_from_db
    if df_db.index.duplicated().any():
        raise ValueError("Right index must be unique, consider resetting it!")
    cache_dict = {}
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            cache_dict = json.load(f)
    if title in cache_dict:
        return cache_dict[title]
    title_length = len(title)
    df_subset = df_db[
        (df_db[title_col].str.len() > (title_length - char_count_range))
        & (df_db[title_col].str.len() < (title_length + char_count_range))
    ]
    choices = df_subset[title_col].values
    if len(choices) >= 0:
        match = process.extractOne(
            query=title,
            choices=choices,
            scorer=distance.Levenshtein.normalized_similarity,
            score_cutoff=score_cutoff,
        )
        if match:
            title_db, ratio, idx = match
            try:
                id_from_db = df_subset[id_col].iloc[idx]
                if isinstance(id_from_db, np.generic):
                    id_from_db = id_from_db.item()
            except KeyError:
                pass
    cache_dict[title] = id_from_db
    with open(cache_path, "w") as f:
        json.dump(cache_dict, f, indent=4)
    return id_from_db  # type: ignore


def get_all_pm_ids_in_db(session: Session) -> set[int]:
    """Return the set of all Pubmed IDs in the database."""
    mapping = get_title_to_id_mapping_pubmed(session)
    return set(mapping["pm_id"])


def get_all_nct_ids_in_db(session: Session) -> set[str]:
    """Return the set of all NCT IDs in the database."""
    mapping = get_title_to_id_mapping_clinicaltrials(session)
    return set(mapping["nct_id"])


def pm_id_to_entrez_xml(
    pm_id: int, email: str, api_key: str, cache_path: str | Path
) -> str | None:
    """Fetch the XML string associated with the Pubmed ID."""
    xml = None
    if pd.isnull(pm_id):
        return xml
    cache_dict = {}
    cache_path = Path(cache_path)
    if cache_path.exists():
        with open(cache_path, "r") as f:
            cache_dict = json.load(f)
    if str(pm_id) in cache_dict:
        xml = cache_dict[str(pm_id)]
    else:
        try:
            Entrez.email = email
            Entrez.api_key = api_key
            response = Entrez.efetch(db="pubmed", id=pm_id, retmode="xml")
            if response:
                content = response.read()
                if not isinstance(content, str):
                    xml = content.decode("utf-8")
                else:
                    xml = content
                cache_dict[pm_id] = xml
                with open(cache_path, "w") as f:
                    cache_path.write_text(json.dumps(cache_dict, indent=4))
        except requests.HTTPError:
            print(f"Encountered HTTP error for {pm_id}")
    return xml


def pm_id_to_publication_date(
    pm_id: int, email: str, api_key: str, cache_path: str | Path
) -> datetime.date | None:
    """Return the article's publication date."""
    date = None
    if pd.isnull(pm_id):
        return date
    xml = pm_id_to_entrez_xml(pm_id, email, api_key, cache_path)
    if xml:
        record = Entrez.read(io.BytesIO(xml.encode("utf-8")))
        try:
            date_dict = record["PubmedArticle"][0]["MedlineCitation"]["Article"][  # type: ignore
                "ArticleDate"
            ][
                0
            ]
            date = datetime.date(
                year=int(date_dict["Year"]),
                month=int(date_dict["Month"]),
                day=int(date_dict["Day"]),
            )
        except (KeyError, IndexError):
            print(f"Couldn't find article date for {pm_id}")
    return date


def pm_id_to_publication_types(
    pm_id: int, email: str, api_key: str, cache_path: str | Path
) -> list[str]:
    """Return a list of document tags listed on Pubmed for the pm_id."""
    publication_types: list[str] = []
    if pd.isnull(pm_id):
        return publication_types
    xml = pm_id_to_entrez_xml(pm_id, email, api_key, cache_path)
    if xml:
        record = Entrez.read(io.BytesIO(xml.encode("utf-8")))
        try:
            publication_types_list = record["PubmedArticle"][0][  # type: ignore
                "MedlineCitation"
            ]["Article"]["PublicationTypeList"]
            if isinstance(publication_types_list, list):
                publication_types = [str(e) for e in publication_types_list]
        except (KeyError, IndexError):
            print(f"Couldn't find document types for {pm_id}")
    return publication_types


def set_rct_flag(row: pd.Series) -> pd.Series:
    """Return True if the RCT tag is among the publication types."""
    ptypes = row["publication_types"]
    row["is_rct_api"] = False
    if pd.notnull(ptypes).any() and isinstance(ptypes, list):
        row["is_rct_api"] = any(["randomized" in t.lower() for t in ptypes])
    return row
