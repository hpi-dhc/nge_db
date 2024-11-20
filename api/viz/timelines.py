from matplotlib import pyplot as plt

from matplotlib import patches
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from datetime import timedelta, datetime

def create_timeline_figure(
    grouped_trials: pd.DataFrame,
    intervention_name: str | None = None,
    population_name: str | None = None,
    versions: list[tuple[str, dict]] = None,
    verbose: bool = False,
    min_date : datetime = None
):

    def get_dates(df):
        return np.hstack(
            [df.start_date.dropna().values, df.result_date.dropna().values]
        )

    gl_date = versions[0][1].get("date") if versions else None

    dates = (
        np.hstack([gl_date, get_dates(grouped_trials)])
        if gl_date
        else get_dates(grouped_trials)
    )

    if not min_date:
        min_date = dates.min() - timedelta(days=900)
    max_date = dates.max() + timedelta(days=90)

    row_height = 0.8
    x_margin = 50

    phase_colors = ["#FFFFF0", "#FFFFE0", "#FFFFCC", "#FFFFAA"]

    trials_per_group = grouped_trials.groupby("max_phase")["group"].unique()
    for phase in [1, 2, 3]:
        if not phase in trials_per_group.index:
            trials_per_group.loc[phase] = [None]

    n_groups = trials_per_group.map(len).sum() + 2

    has_phase_4 = 4 in trials_per_group.index
    if has_phase_4:
        n_groups += 1

    fig, ax = plt.subplots(1, 1, figsize=(10, 0.3 * n_groups))

    y_offsets = np.arange(n_groups, -1, -1)

    grouped_trials["start_date"] = grouped_trials["start_date"].fillna(
        grouped_trials["result_date"]
    )

    i = 0
    phase_mean_idx = {}
    for phase, color in zip([[4], [3], [1, 2]], phase_colors):
        i += 1
        if phase == [4] and not has_phase_4:
            continue
        phase_results = grouped_trials[grouped_trials.max_phase.isin(phase)]
        phase_groups = phase_results.group.unique()
        group_size = max(1, len(phase_groups))
        ytop, ybottom = 0, 0
        if phase == [1, 2]:
            ybottom = 1
        if phase == [3] and not has_phase_4 or phase == [4] and has_phase_4:
            ytop = 1
        lane_x = mdates.date2num(min_date)
        lane_y = n_groups - i - group_size - ybottom
        lane_height = group_size + 0.5 + ytop + ybottom
        phase_lane_rect = patches.Rectangle(
            (lane_x, lane_y),
            mdates.date2num(max_date) - mdates.date2num(min_date),  # width
            lane_height,  # height
            linewidth=1,
            edgecolor="gray",
            facecolor=color,
        )
        ax.add_patch(phase_lane_rect)
        ax.text(
            lane_x + x_margin / 2,
            lane_y + lane_height - 0.75,
            f'Phase {"/".join([str(p) for p in phase])}',
            color="grey",
            weight="bold",
        )
        mean_idx = n_groups - i - float(len(phase_groups)) / 2
        if len(phase_groups) > 0 or phase != [4]:
            phase_mean_idx[tuple(phase)] = mean_idx
        if len(phase_groups) == 0 and phase != [4]:
            i += 1
        for grp_id in phase_groups:
            y = y_offsets[i]  # phase + offset
            grp = phase_results[phase_results.group == grp_id]
            grp_dates = get_dates(grp)
            if len(set(grp_dates)) > 1:
                grp_min_date = grp_dates.min()
                grp_max_date = grp_dates.max()
                grp_rect = patches.FancyBboxPatch(
                    (mdates.date2num(grp_min_date) - x_margin, y - row_height / 2),
                    mdates.date2num(grp_max_date)
                    - mdates.date2num(grp_min_date)
                    + x_margin * 2,  # width
                    row_height,  # height
                    mutation_aspect=0.001,
                    boxstyle=patches.BoxStyle("round", pad=0),
                    linewidth=1,
                    edgecolor="black",
                    facecolor="#F0F0F0",
                )
                ax.add_patch(grp_rect)
            else:
                ax.plot(get_dates(grp)[0], y, "o", color="#F0F0F0", markersize=12)
            for _, t in grp.iterrows():
                if t.source == "Pubmed":
                    if verbose or t.group == t.id:  # No attached NCT ID -> Use PMID
                        ax.text(
                            mdates.date2num(t.result_date) - x_margin * 2,
                            y,
                            f"PMID: {t.id}",
                            rotation=0,
                            verticalalignment="center",
                            horizontalalignment="right",
                        )
                    x = t.result_date
                    # ax.text(x, y, t.id, rotation=0, verticalalignment='center', horizontalalignment='right')
                    if t.cited_in_guideline:
                        ax.plot(x, y, "*", color="green", markersize=12)
                    else:
                        ax.plot(x, y, ".", color="green", markersize=10)
                elif t.source == "ClinicalTrials":
                    # print(t.id, t.title)
                    ax.text(
                        mdates.date2num(t.start_date) - x_margin * 2,
                        y,
                        t.id,
                        rotation=0,
                        verticalalignment="center",
                        horizontalalignment="right",
                    )
                    # ä#print(t.status)
                    if t.overall_status in (["Withdrawn", "Suspended"]):
                        # pass
                        ax.plot(t.start_date, y, color="red", marker="x", markersize=8)
                    else:
                        ax.plot(t.start_date, y, color="blue", marker="D", markersize=5)
                    if t.result_date:
                        ax.plot(
                            t.result_date, y, color="blue", marker="s", markersize=5
                        )
            i += 1

    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator())

    search_end = None
    prev_version_date = None
    if versions:
        if gl_date:
            ax.axvline(
                gl_date, color="magenta", linestyle="--", marker=".", linewidth=2
            )
        if version_name := versions[0][0]:
            ax.text(
                gl_date,
                n_groups,
                version_name,
                color="magenta",
                horizontalalignment="center",
                bbox=dict(facecolor="white", edgecolor="magenta"),
            )
        if search_end := versions[0][1].get("search_end"):
            ax.axvline(
                search_end,
                color="magenta",
                linestyle="-.",
                marker=".",
                linewidth=1,
            )
        for version, version_data in versions[1:]:
            if prev_version_date := version_data.get("date"):
                if version:
                    ax.text(
                        prev_version_date,
                        n_groups,
                        version,
                        color="gray",
                        horizontalalignment="center",
                        bbox=dict(facecolor="white", edgecolor="gray"),
                    )
                ax.axvline(
                    prev_version_date,
                    color="gray",
                    linestyle="--",
                    marker=".",
                    linewidth=2,
                )

    if intervention_name or population_name:
        ax.set_title(
            f'{intervention_name if intervention_name else ""}{" - " if (intervention_name and population_name) else ""}{population_name if population_name else ""}'.title(),
            loc='left'
        )

    ax.set_yticks([])
    ax.set_ylim(-1, n_groups - 0.5)
    plt.xticks(rotation=90)
    ax.set_xlim(min_date, max_date)

    ax.grid(axis="x", linewidth=0.5)

    legend_elements = [
        Line2D(
            [0], [0], color="b", lw=0, label="ClinicalTrials.gov (Started)", marker="D"
        ),
        Line2D(
            [0],
            [0],
            color="b",
            lw=0,
            label="ClinicalTrials.gov (Results Posted)",
            marker="s",
        ),
        Line2D([0], [0], color="g", lw=0, label="PubMed Article", marker="o"),
        Line2D(
            [0],
            [0],
            color="g",
            lw=0,
            label="PubMed Article (Cited in Guideline)",
            marker="*",
        ),
    ]
    if gl_date:
        legend_elements.append(
            Line2D(
                [0],
                [1],
                color="magenta",
                lw=2,
                label="Current Version (Publication)",
                linestyle="--",
            )
        )
    if search_end:
        legend_elements.append(
            Line2D(
                [0],
                [1],
                color="magenta",
                lw=1,
                label="End of Literature Search",
                linestyle="-.",
            )
        )
    if prev_version_date:
        legend_elements.append(
            Line2D(
                [0], [1], color="gray", lw=2, label="Previous Version", linestyle="--"
            ),
        )

    ax.legend(handles=legend_elements, 
              ncol=(len(legend_elements) + 1) / 2, 
              fontsize='small',
              columnspacing=1.0,
              bbox_to_anchor=(0.5, 1 + 1.5 / n_groups),
              loc="lower center")
    return fig