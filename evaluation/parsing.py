"""A module containing parsing functions for the RIS files for evaluation."""

import re
from pathlib import Path

import pandas as pd
import rispy

RIS_COLUMNS_COMMON = [
    "title",
    "abstract",
    "pm_id",
    "nct_id",
    "cn_id",
    "doi",
    "ris_id",
    "publication_date",
    "article_date_api",
    "guideline_id",
    "guideline_name",
    "publication_types",
    "exclusion_reason",
    "is_rct_api",
    "is_included",
    "is_excluded",
    "is_relevant",
    "is_not_relevant",
    "is_in_db",
    "is_in_ggponc",
    "screening_origin",
]

REGEX = {
    "pm_id": r"(\d{8})",
    "pm_id_start_end": r"^(\d{8})$",
    "pm_id_from_query": r"pmid:(\d{8})",
    "cn_id": r"(CN-\d{8})",
    "doi": r"(\b10\.\d{4,9}/[-.;()/:\w]+)",
    "doi_from_query": r"doi:(\b10\.\d{4,9}/[-.;()/:\w]+)&",
}


def parse_kg_ris_file(
    ris_file_in: str | Path, parser: rispy.BaseParser
) -> pd.DataFrame:
    """Recursively parse all RIS files in a directory to a dataframe."""
    with open(ris_file_in, "r") as file:
        ris_content = file.readlines()
    fixed_content = []
    tag_line_regex = re.compile(r"(:?\w{2}\s{2}-\s+)")
    tag_empty_regex = re.compile(r"\w{2}\s{2}-\s*\n")
    usual_indentation = "      "
    for line in ris_content:
        if line.startswith("ID -"):
            # The ID lines are all missing a space, add it
            line = line.replace("ID -", "ID  -")
        if tag_line_regex.search(line):
            # Fix lines with tags that are indented
            if line.startswith(" "):
                line = line.lstrip()
            # Add trailing space to files that are missing it (RIS convention)
            if tag_empty_regex.search(line):
                line = line.rstrip() + " \n"
        elif not line.startswith(usual_indentation):
            line = usual_indentation + line
        fixed_content.append(line)

    fixed_text = "".join(fixed_content)
    parsed_ris_content = parser.parse(text=fixed_text)
    df = pd.DataFrame(parsed_ris_content)
    df["path"] = ris_file_in
    return df


def parse_ris_date_to_datetime(df, col_year, col_date) -> pd.Series:
    """Parse the information from the year and date columns to a datetime column."""
    month_mapping = {
        "Jan": 1,
        "Feb": 2,
        "Mar": 3,
        "Apr": 4,
        "May": 5,
        "Jun": 6,
        "Jul": 7,
        "Aug": 8,
        "Sep": 9,
        "Oct": 10,
        "Nov": 11,
        "Dec": 12,
    }

    return pd.to_datetime(
        df[[col_year, col_date]]
        .apply(list, axis=1)
        .apply(lambda yd: " ".join([e for e in yd if pd.notnull(e)]))
        .str.split()
        .apply(
            lambda ls: [month_mapping.get(s, s) for s in ls]
            if isinstance(ls, list)
            else ls
        )
        .apply(
            lambda items: list(dict.fromkeys([int(i) for i in items]))
        )  # remove duplicated year entries
        .apply(
            lambda ls: "/".join([str(s) for s in ls]) if isinstance(ls, list) else ls
        )
    )


def save_parsed_ris_content(
    df: pd.DataFrame,
    guideline_id: str,
    guideline_name: str,
    csv_path: str | Path,
    cols_additional: list[str] = [],
    cols_common: list[str] = RIS_COLUMNS_COMMON,
) -> None:
    """Store the parsed RIS dataset."""
    csv_path = Path(csv_path)
    df["guideline_id"] = guideline_id
    df["guideline_name"] = guideline_name
    df["is_excluded"] = ~df["is_included"]
    df = df[cols_common + cols_additional]
    df.reset_index(drop=True).to_csv(csv_path, index=False)
