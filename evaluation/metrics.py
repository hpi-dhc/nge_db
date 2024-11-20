"""A module containing code for metrics and plots in the evaluation notebooks."""

import itertools
from pathlib import Path
from typing import Any, Iterator, Mapping

import numpy as np
import pandas as pd
from pandas.io.formats import style
from tqdm.auto import tqdm

from evaluation.matching import find_trial_publication_matches

metrics_dict_like = dict[str, int | np.float64 | set[int | str]]

filters_dict_like = Mapping[str, str | None]
filters_hierarchy_like = dict[str, Any]

FILTERS_SCREENED = {"All": None, "Only RCTs": "is_rct_api"}

FILTERS_RETRIEVED = {
    "All": None,
    "Is RCT": "is_rct_pt == True",
    "Non-empty Abstract": "abstract.str.len() > 1",
    "Non-pediatric population": "has_pediatric_population == False",
    "Phase >= 2": "phase_int >= 2",
    "Phase >= 3": "phase_int >= 3",
    "Sample Size >= 5": "~(sample_size < 5)",
    "Sample Size >= 10": "~(sample_size < 10)",
    "Sample Size >= 15": "~(sample_size < 15)",
    "Known Intervention": "has_known_intervention == True",
    "Unknown Intervention": "has_unknown_intervention == True",
    "K+U Intervention": "(has_known_intervention == True) & (has_unknown_intervention == True)",
    "Significant Finding": "has_significant_finding == True",
    "No Significant Finding": "has_significant_finding == False",
}


# Queries for combinations table
Q_RCTS = "is_rct_pt == True"
Q_RCTS_ANC = Q_RCTS + " & abstract.str.len() > 1 & has_pediatric_population == False"
Q_RCTS_ANC_P2 = Q_RCTS_ANC + " & phase_int >= 2"
Q_RCTS_ANC_P3 = Q_RCTS_ANC + " & phase_int >= 3"
Q_RCTS_ANC_P3_SIG = Q_RCTS_ANC_P3 + " & (has_significant_finding == True)"
Q_RCTS_ANC_P3_NOT_SIG = Q_RCTS_ANC_P3 + " & (has_significant_finding == False)"
Q_KNOWN = "(has_known_intervention == True)"
Q_UNKNOWN = "(has_unknown_intervention == True)"
Q_K_AND_U = "((has_known_intervention == True) & (has_unknown_intervention == True))"

# Filters for combinations table
FILTERS_COMBINATIONS = {
    "RCTs": Q_RCTS,
    "Abstr., NC": Q_RCTS_ANC,
    "Phase >= 2": Q_RCTS_ANC_P2,
    "Phase >= 3": Q_RCTS_ANC_P3,
    "Significant Finding": Q_RCTS_ANC_P3_SIG,
    "S_Known Intervention": Q_RCTS_ANC_P3_SIG + " & " + Q_KNOWN,
    "S_Unknown Intervention": Q_RCTS_ANC_P3_SIG + " & " + Q_UNKNOWN,
    "S_K+U Intervention": Q_RCTS_ANC_P3_SIG + " & " + Q_K_AND_U,
    "No Significant Finding": Q_RCTS_ANC_P3_NOT_SIG,
    "N_Known Intervention": Q_RCTS_ANC_P3_NOT_SIG + " & " + Q_KNOWN,
    "N_Unknown Intervention": Q_RCTS_ANC_P3_NOT_SIG + " & " + Q_UNKNOWN,
    "N_K+U Intervention": Q_RCTS_ANC_P3_NOT_SIG + " & " + Q_K_AND_U,
}

# Hierarchy for combinations table
FILTERS_HIERARCHY = {
    "RCTs": {
        "Abstr., NC": {
            "Phase >= 2": {
                "Phase >= 3": {
                    "Significant Finding": [
                        "S_Known Intervention",
                        "S_Unknown Intervention",
                        "S_K+U Intervention",
                    ],
                    "No Significant Finding": [
                        "N_Known Intervention",
                        "N_Unknown Intervention",
                        "N_K+U Intervention",
                    ],
                }
            }
        }
    }
}

FILTERS_HIERARCHY_TEX = {
    "RCTs": {
        "A+NC": {
            r"P$\geq$2": {
                r"P$\geq$3": {
                    "S": ["S-K", "S-UK", "S-K+U"],
                    "N": ["N-K", "N-UK", "N-K+U"],
                }
            }
        }
    }
}


def precision_recall(
    ids_screened_relevant: set[int | str],
    ids_screened: set[int | str],
    ids_retrieved: set[int | str],
) -> metrics_dict_like:
    """Return a dictionary with the relevant metrics."""
    ids_screened_not_relevant = ids_screened - ids_screened_relevant
    ids_retrieved_not_screened = ids_retrieved - ids_screened

    ids_retrieved_relevant = ids_retrieved.intersection(ids_screened_relevant)
    ids_retrieved_not_relevant = ids_retrieved.intersection(ids_screened_not_relevant)
    ids_not_retrieved_relevant = ids_screened_relevant - ids_retrieved
    ids_not_retrieved_not_relevant = ids_screened_not_relevant - ids_retrieved
    tp = len(ids_retrieved_relevant)
    fp = len(ids_retrieved_not_relevant)
    fn = len(ids_not_retrieved_relevant)
    tn = len(ids_not_retrieved_not_relevant)
    questionmark = len(ids_retrieved_not_screened)

    assert (tp + fp + fn + tn) == len(ids_screened)
    assert (tn + fp) == len(ids_screened_not_relevant)
    assert (tp + fn) == len(ids_screened_relevant)
    assert (tp + fp + questionmark) == len(ids_retrieved)

    return {
        "precision": (np.float64(tp) / (tp + fp)) if (tp + fp) > 0 else 0,
        "recall": (np.float64(tp) / (tp + fn)) if (tp + fn) > 0 else 0,
        "f1": np.float64(2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) > 0 else 0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "?": len(ids_retrieved_not_screened),
        "n_retrieved": len(ids_retrieved),
        "n_screened": len(ids_screened),
        "n_relevant": len(ids_screened_relevant),
        "ids_retrieved": ids_retrieved,
        "ids_screened": ids_screened,
        "ids_screened_relevant": ids_screened_relevant,
        "ids_fp": ids_retrieved_not_relevant,
        "ids_fn": ids_not_retrieved_relevant,
    }


def filter_screened_documents(
    df_screened: pd.DataFrame,
    filters: dict[str, str | None],
    col_relevant: str = "is_relevant",
    col_id: str = "pm_id",
) -> Iterator[tuple[str, set[int | str], set[int | str]]]:
    """Apply the filters to the screened documents and return the resulting dataframes."""
    for desc, query in filters.items():
        if query is not None:
            df_filtered = df_screened.query(query)
        else:
            df_filtered = df_screened
        ids_screened = set(df_filtered[col_id].dropna())
        ids_screened_relevant = set(df_filtered.query(col_relevant)[col_id].dropna())
        yield desc, ids_screened, ids_screened_relevant


def filter_retrieved_documents(
    df_retrieved: pd.DataFrame, filters: dict[str, str | None], col_id: str = "pm_id"
) -> Iterator[tuple[str, set[int | str]]]:
    """Apply the filters to the retrieved documents and return the resulting dataframes."""
    for desc, query in filters.items():
        if query is not None:
            df_filtered = df_retrieved.query(query)
        else:
            df_filtered = df_retrieved
        ids_retrieved = set(df_filtered[col_id].dropna())
        yield desc, ids_retrieved


def expand_filters(
    filters: dict[str, str | None], include_combos_with_or: bool = True
) -> dict[str, str | None]:
    """Expand the filters to include all combinations of filters."""
    expanded_filters: dict[str, str] = {}
    filters_without_none = {k: v for k, v in filters.items() if v is not None}
    filters_with_none = {k: v for k, v in filters.items() if v is None}
    for r in range(1, len(filters) + 1):
        for combo in itertools.combinations(filters_without_none.items(), r):
            desc, queries = zip(*combo)
            combined_query = " & ".join(q for q in queries if q is not None)
            expanded_filters[" & ".join(desc)] = combined_query

            if include_combos_with_or:
                combined_query_or = " | ".join(q for q in queries if q is not None)
                expanded_filters[" | ".join(desc)] = combined_query_or

    all_filters: dict[str, str | None] = {**filters_with_none, **expanded_filters}
    return all_filters


def run_evaluation(
    df_screened,
    df_retrieved,
    filters_screened,
    filters_retrieved,
    col_id="pm_id",
    col_relevant="is_relevant",
    include_combos_with_or: bool = True,
    compute_combinations: bool = True,
) -> dict[str, dict[str, metrics_dict_like]]:
    """Run the evaluation and return the metrics."""
    metrics: dict[str, dict[str, metrics_dict_like]] = {}

    if compute_combinations:
        filters_retrieved_expanded = expand_filters(
            filters_retrieved, include_combos_with_or
        )
    else:
        filters_retrieved_expanded = filters_retrieved

    for desc_s, ids_screened, ids_screened_relevant in filter_screened_documents(
        df_screened, filters_screened, col_relevant=col_relevant, col_id=col_id
    ):
        tqdm.write(f"Evaluating screened document subset '{desc_s}'")
        metrics[desc_s] = {}
        for desc_r, filtered_ids_retrieved in tqdm(
            filter_retrieved_documents(df_retrieved, filters_retrieved_expanded),
            desc="Evaluating filter combinations",
            total=len(filters_retrieved_expanded),
        ):
            metrics[desc_s][desc_r] = precision_recall(
                ids_screened=ids_screened,
                ids_screened_relevant=ids_screened_relevant,
                ids_retrieved=filtered_ids_retrieved,
            )

    return metrics


def metrics_to_df(
    metrics_dict: dict[str, Any],
    drop_zero_tp: bool = True,
    drop_columns=[
        "ids_retrieved",
        "ids_screened",
        "ids_screened_relevant",
        "ids_fp",
        "ids_fn",
    ],
    use_abbreviations: bool = False,
) -> pd.DataFrame:
    """Convert the metrics dictionary to a dataframe."""
    df = pd.DataFrame(metrics_dict).T
    if drop_zero_tp:
        df = df[df["tp"] > 0]
    df.drop(columns=drop_columns, inplace=True)
    df.rename(columns=lambda c: c.replace("n_", ""), inplace=True)
    cols_to_float = ["precision", "recall", "f1"]
    cols_to_int = ["tp", "fp", "fn", "tn", "?", "retrieved", "screened", "relevant"]
    cols_to_all_caps = ["tp", "fp", "fn", "tn", "f1"]
    df = df.astype({col: float for col in cols_to_float}, errors="raise")
    df = df.round({col: 4 for col in cols_to_float})
    df = df.astype(
        {col: "Int64" for col in cols_to_int},
        errors="raise",
    )
    df.rename(
        columns={
            **{
                col: col.capitalize() for col in set(df.columns) - set(cols_to_all_caps)
            },
            **{col: col.upper() for col in cols_to_all_caps},
        },
        inplace=True,
    )
    df.rename(columns={"F1": "$F_1$"}, inplace=True)
    if use_abbreviations:
        df.rename(
            columns={
                "Precision": "Prec.",
                "Recall": "Rec.",
                "Retrieved": "Retr.",
                "Screened": "Scr.",
                "Relevant": "Rel.",
            },
            inplace=True,
        )
    return df


def highlight_metrics(
    metrics_df: pd.DataFrame,
    decimals={"Precision": "{:.4f}", "Recall": "{:.4f}", "F1": "{:.4f}"},
) -> style.Styler:
    """Highlight the metrics in the dataframe dataframe."""
    df = metrics_df.style.format(decimals).highlight_min(
        subset=["FP", "FN"], props="font-weight:bold", axis=0
    )
    if "Precision" in metrics_df.columns:
        max_cols = ["Precision", "Recall", "$F_1$", "TP"]
    else:
        max_cols = ["Prec.", "Rec.", "$F_1$", "TP"]
    return df.highlight_max(subset=max_cols, props="font-weight:bold", axis=0)


def generate_multiindex_from_hierarchy(input_dict: dict[str, Any]):
    """Generate Pandas Multiindex from a nested dictionary."""

    def get_max_depth(input_dict):
        if isinstance(input_dict, dict):
            return 1 + max(get_max_depth(value) for value in input_dict.values())
        else:
            return 1

    def generate_tuples(input_dict, current_tuple=(), max_depth=None):
        if max_depth is None:
            max_depth = get_max_depth(input_dict)
        tuples = []
        for key, value in input_dict.items():
            new_tuple = current_tuple + (key,)
            tuples.append(new_tuple + ("",) * (max_depth - len(new_tuple)))
            if isinstance(value, dict):
                tuples.extend(generate_tuples(value, new_tuple, max_depth))
            else:
                for item in value:
                    tuples.append(
                        new_tuple + (item,) + ("",) * (max_depth - len(new_tuple) - 1)
                    )
        return tuples

    tuples = generate_tuples(input_dict)
    return pd.MultiIndex.from_tuples(tuples)


def infer_table_format(s: pd.Series):
    """Infer table-format for siunitx from a Pandas Series."""
    if pd.api.types.is_numeric_dtype(s):
        max_val = s.abs().max()
        integer_part = int(np.floor(np.log10(max_val)) + 1) if max_val > 0 else 1
        s_float = s.astype(float)
        decimal_part = (
            s_float.apply(
                lambda x: 0 if x.is_integer() else np.maximum(-np.log10(x % 1), 0)
            )
            .max()
            .astype(int)
        )
        return f"S[table-format={integer_part}.{decimal_part}]"
    else:
        return "l"


def prepare_missing_rcts_concepts_df(missing_rcts_df: pd.DataFrame) -> pd.DataFrame:
    """Return a dataframe containing the missing Pubmed IDs and their concepts."""
    if len(missing_rcts_df) == 0:
        return pd.DataFrame([{"UMLS Term": None}])
    missing_rcts_df["tree_numbers"] = missing_rcts_df["semantic_types"].apply(
        lambda sts: [st["tree_number"] for st in sts]
    )
    missing_rcts_df["type"] = (
        missing_rcts_df["semantic_types"]
        .apply(lambda sts: [st["name"] for st in sts])
        .str[0]
    )
    missing_rcts_df.index.name = "Pubmed ID"
    missing_rcts_df_np_cuis = missing_rcts_df[
        missing_rcts_df["tree_numbers"].apply(
            lambda tns: any([tn.startswith(("B2.2.1.2.1", "B1.3.1.3")) for tn in tns])
        )
    ]
    missing_rcts_df_np_cuis = (
        missing_rcts_df_np_cuis.rename(
            columns={
                "cui": "CUI",
                "text_umls": "UMLS Term",
                "type": "Semantic Type",
            }
        )
        .set_index("CUI", append=True)
        .sort_values("UMLS Term")
        .sort_index(level=0, sort_remaining=False)
    )[["UMLS Term"]]
    return missing_rcts_df_np_cuis


def prepare_time_lag_dataframe(df_retrieved: pd.DataFrame) -> pd.DataFrame:
    """Prepare a dataframe showing the time between PM and CT publication."""
    pm_ids_retrieved = set(df_retrieved["pm_id"].dropna())
    nct_ids_retrieved = set(df_retrieved["nct_id"].dropna())

    df_time_lag = (
        df_retrieved[
            [
                "pm_id",
                "nct_id",
                "referenced_pm_ids",
                "referenced_pm_ids_results",
                "referenced_nct_ids",
            ]
        ]
        .dropna(subset=["referenced_pm_ids", "referenced_nct_ids"], how="all")
        .apply(
            lambda row: find_trial_publication_matches(
                df_retrieved=df_retrieved,
                pm_id=row["pm_id"],
                nct_id=row["nct_id"],
                referenced_nct_ids=row["referenced_nct_ids"],
                referenced_pm_ids=row["referenced_pm_ids"],
                referenced_pm_ids_results=row["referenced_pm_ids_results"],
                retrieved_nct_ids=nct_ids_retrieved,
                retrieved_pm_ids=pm_ids_retrieved,
            ),
            axis=1,
        )
        .explode()
        .dropna()
        .apply(pd.Series)
    )

    df_time_lag["date_diff"] = df_time_lag["date_pm"] - df_time_lag["date_nct"]
    df_time_lag["date_diff_days"] = df_time_lag["date_diff"].dt.days
    df_time_lag["date_diff_days_abs"] = df_time_lag["date_diff_days"].abs()
    df_time_lag["ct_then_pm"] = df_time_lag["date_diff_days"].apply(lambda x: x > 0)
    df_time_lag["latex_desc"] = df_time_lag.apply(
        lambda row: rf"{row['nct_id']} $\rightarrow$ {row['pm_id']}"
        if row["date_diff_days"] > 0
        else rf"{row['pm_id']} $\rightarrow$ {row['nct_id']}",
        axis=1,
    )
    df_time_lag["pm_id_is_rct_pt"] = df_time_lag["pm_id"].map(
        df_retrieved.query("source == 'Pubmed'")
        .set_index("pm_id")["is_rct_pt"]
        .to_dict()
    )
    df_time_lag = df_time_lag.sort_values(
        ["nct_id", "date_pm", "link_type"]
    ).drop_duplicates(subset="nct_id", keep="first")

    return df_time_lag


def build_filter_combinations_table(
    df_screened: pd.DataFrame,
    df_retrieved: pd.DataFrame,
    latex_output_path: Path | str,
    overwrite_latex_output: bool = False,
    column_format: str | None = None,
    filters_screened: filters_dict_like = FILTERS_SCREENED,
    filters_retrieved: filters_dict_like = FILTERS_COMBINATIONS,
    filters_retrieved_hierarchy: filters_hierarchy_like = FILTERS_HIERARCHY,
    filters_retrieved_hierarchy_tex: filters_hierarchy_like = FILTERS_HIERARCHY_TEX,
    metrics_filter_key: str = "Only RCTs",
    drop_zero_tp: bool = False,
    use_abbreviations: bool = False,
    stop_at_line: int | None = None,
):
    """Return a dataframe containing the filter combinations table."""
    # Run evaluation
    metrics_final = run_evaluation(
        df_screened,
        df_retrieved,
        filters_screened=filters_screened,
        filters_retrieved=filters_retrieved,
        col_id="pm_id",
        col_relevant="is_relevant",
        compute_combinations=False,
    )

    # Convert metrics to DataFrame
    rct_metrics_final_df = metrics_to_df(
        metrics_final[metrics_filter_key],
        drop_zero_tp=drop_zero_tp,
        use_abbreviations=use_abbreviations,
    )

    # Generate MultiIndex
    multiindex = generate_multiindex_from_hierarchy(filters_retrieved_hierarchy)

    # Assign MultiIndex to DataFrame
    rct_metrics_final_df.index = multiindex

    # write latex output

    if overwrite_latex_output:
        mux_tex = generate_multiindex_from_hierarchy(filters_retrieved_hierarchy_tex)
        rct_metrics_final_df_tex_idx = rct_metrics_final_df.copy()
        rct_metrics_final_df_tex_idx.index = mux_tex
        if use_abbreviations:
            cols_to_drop = ["Scr.", "Rel."]
        else:
            cols_to_drop = ["Screened", "Relevant"]
        if stop_at_line:
            rct_metrics_final_df_tex_idx = rct_metrics_final_df_tex_idx.iloc[
                :stop_at_line, :
            ]
            rct_metrics_final_df = rct_metrics_final_df.iloc[:stop_at_line, :]
        highlight_metrics(
            rct_metrics_final_df_tex_idx.drop(columns=cols_to_drop)
        ).applymap_index(lambda v: "font-weight: bold;", axis="columns").to_latex(
            latex_output_path,
            siunitx=True,
            hrules=True,
            convert_css=True,
            clines="skip-last;data",
            multirow_align="t",
            column_format=column_format,
        )
        remove_last_cline_from_tex_table(latex_output_path)

    return rct_metrics_final_df, metrics_final


def remove_last_cline_from_tex_table(tex_table_path: Path | str):
    """Remove the last occurence of cline from a LaTeX table."""
    table_path = Path(tex_table_path)
    lines = table_path.read_text().split("\n")
    lines = lines[::-1]
    for i in range(len(lines)):
        if "\\cline" in lines[i]:
            del lines[i]
            break
    lines = lines[::-1]
    table_path.write_text("\n".join(lines))
