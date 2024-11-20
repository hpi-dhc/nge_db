"""A module containing some plotting logic for LaTeX output."""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import figure
from matplotlib.ticker import MaxNLocator
from matplotlib_venn import venn3


def set_size(width, fraction=1, subplots=(1, 1)):
    """Set figure dimensions to avoid scaling in LaTeX.

    # Kindly taken from https://jwalton.info/Embed-Publication-Matplotlib-Latex/

    Parameters
    ----------
    width: float or string
            Document width in points, or string of predined document type
    fraction: float, optional
            Fraction of the width which you wish the figure to occupy
    subplots: array-like, optional
            The number of rows and columns of subplots.
    Returns
    -------
    fig_dim: tuple
            Dimensions of figure in inches
    """
    if width == "thesis":
        width_pt = 398.33858
    else:
        width_pt = width

    # Width of figure (in pts)
    fig_width_pt = width_pt * fraction
    # Convert from pt to inches
    inches_per_pt = 1 / 72.27

    # Golden ratio to set aesthetic figure height
    # https://disq.us/p/2940ij3
    golden_ratio = (5**0.5 - 1) / 2

    # Figure width in inches
    fig_width_in = fig_width_pt * inches_per_pt
    # Figure height in inches
    fig_height_in = fig_width_in * golden_ratio * (subplots[0] / subplots[1])

    return (fig_width_in, fig_height_in)


def draw_venn_rsi(
    title: str | None,
    ids_retrieved: set[int | str],
    ids_screened: set[int | str],
    ids_screened_relevant: set[int | str],
    add_pn_labels: bool = False,
    circle_label_size: int | None = None,
    label_size: int | None = None,
    label_offsets: dict[str, tuple[float, float]] | None = None,
) -> tuple[figure.Figure, plt.Axes]:
    """Return a Venn diagram of the screened and relevant evidence items."""
    fig, ax = plt.subplots(figsize=set_size("thesis"), layout="constrained")
    venn = venn3(
        subsets=[ids_retrieved, ids_screened, ids_screened_relevant],
        set_labels=["Retrieved", "Screened", "Relevant"],
        set_colors=["green", "red", "blue"],
        ax=ax,
    )
    if add_pn_labels:
        pn_labels = {
            "TP": "111",
            "FP": "110",
            "TN": "010",
            "FN": "011",
            "?": "100",
        }
        for name, area_id in pn_labels.items():
            area = venn.get_label_by_id(area_id)
            if area:
                area.set_text(f"{area.get_text()} ({name})")
                if label_size is not None:
                    area.set_fontsize(label_size)
                if label_offsets is not None:
                    if name in label_offsets:
                        offset = np.array(label_offsets.get(name, [0, 0]))
                        area.set_position((area.get_position() + offset))
    if title is not None:
        ax.set_title(title)
    if circle_label_size is not None:
        for set_id in ["A", "B", "C"]:
            label = venn.get_label_by_id(set_id)
            label.set_fontsize(circle_label_size)
    return fig, ax


def draw_docs_by_publication_date(
    df_screened: pd.DataFrame,
    col_date: str,
    col_relevant: str,
    output_dir: str | Path,
    file_name: str,
) -> None:
    """Save a plot of screened documents by publication year to output dir."""
    fig, ax = plt.subplots(figsize=set_size("thesis"), layout="constrained")
    output_dir = Path(output_dir)

    df_screened.groupby(
        [pd.Grouper(key=col_date, freq="y"), col_relevant]
    ).size().rename(index=lambda i: (i.year), level=0).unstack().plot(
        kind="bar",
        xlabel="Year of the Systematic Review Time Frame",
        ylabel="Number of Screened Publications",
        rot=0,
        stacked=True,
        ax=ax,
    )
    ax.legend(["Not Relevant", "Relevant"])
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    fig.savefig(str(output_dir / file_name))


def draw_docs_publication_types(
    df_screened: pd.DataFrame,
    n_most_common: int,
    col_ptypes: str,
    col_relevant: str,
    output_dir: str | Path,
    file_name: str,
) -> None:
    """Save a plot of documents' publication types to output dir."""
    fig, ax = plt.subplots(figsize=set_size("thesis"), layout="constrained")
    output_dir = Path(output_dir)

    df_screened.query(col_relevant)[col_ptypes].explode().value_counts().nlargest(
        n_most_common
    ).sort_values().plot(
        kind="barh",
        xlabel="Tag Count (a document can have multiple tags)",
        ylabel="Pubmed Publication Type Tag",
        ax=ax,
    )
    fig.savefig(str(output_dir / file_name))


def draw_time_lag_analysis(
    df_time_lag: pd.DataFrame,
    output_dir: str | Path,
    file_name: str,
    col_date_diff_days: str = "date_diff_days_abs",
    col_desc: str = "latex_desc",
    col_ct_then_pm: str = "ct_then_pm",
):
    """Save a plot of the difference in days between CT and PM publication."""
    fig, ax = plt.subplots(figsize=set_size("thesis"), layout="constrained")
    output_dir = Path(output_dir)

    colors_from_scheme = [
        list(d.values())[0] for d in list(mpl.rcParams["axes.prop_cycle"])
    ]

    df_time_lag.sort_values([col_ct_then_pm, col_date_diff_days]).plot(
        kind="barh",
        x=col_desc,
        y=col_date_diff_days,
        ylabel="Identified Record Pairs",
        xlabel="Days between Posting of Results and Publication on PubMed",
        legend=False,
        ax=ax,
        color=(
            df_time_lag.sort_values([col_ct_then_pm, col_date_diff_days])[
                col_ct_then_pm
            ]
        ).map({True: colors_from_scheme[1], False: colors_from_scheme[0]}),
    )

    bars = ax.patches
    for bar, idx in zip(bars, df_time_lag.index):
        bar.set_edgecolor("black")
        if idx == "HL (Retro.)":
            bar.set_linestyle("dotted")
        if idx == "HL":
            bar.set_linestyle("dashed")
        if idx == "EC":
            bar.set_linestyle("solid")

    handles = [
        mpl.lines.Line2D(
            [0],
            [0],
            color=colors_from_scheme[1],
            lw=4,
            label="Results on ClinicalTrials.gov before PubMed Publication",
        ),
        mpl.lines.Line2D(
            [0],
            [0],
            color=colors_from_scheme[0],
            lw=4,
            label="PubMed Publication before Results on ClinicalTrials.gov",
        ),
    ]
    ax.legend(
        handles=handles,
        handlelength=0.3,
    )
    fig.savefig(str(output_dir / file_name))
