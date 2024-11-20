"""Module responsible for rendering the data table."""

import pandas as pd
import streamlit as st
from st_aggrid import (
    AgGrid,
    ColumnsAutoSizeMode,
    GridOptionsBuilder,
    GridUpdateMode,
    JsCode,
)

cell_renderer_multiline_scrollable = JsCode(
    """
    class MultiLineScrollableRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.style.whiteSpace = 'pre-line';
            this.eGui.style.maxHeight = '100px';
            this.eGui.style.overflow = 'auto';
            this.eGui.innerText = params.value;
        }

        getGui() {
            return this.eGui;
        }
    }
    """
)

cell_renderer_bullet_points = JsCode(
    """
    class BulletPointsRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.style.whiteSpace = 'pre-line';
            this.eGui.style.maxHeight = '100px';
            this.eGui.style.overflow = 'auto';
            this.eGui.innerHTML = this.createBulletList(params.value);
        }

        createBulletList(items) {
            if (items && Array.isArray(items)) {
                const listItems = items.map(item => `<li>${item}</li>`).join('');
                return `<ul>${listItems}</ul>`;
            } else {
                return items;
            }
        }

        getGui() {
            return this.eGui;
        }
    }
    """
)

cell_renderer_bullet_points_with_links = JsCode(
    """
    class BulletPointsWithLinksRenderer {
        init(params) {
            this.eGui = document.createElement('div');
            this.eGui.style.whiteSpace = 'pre-line';
            this.eGui.style.maxHeight = '100px';
            this.eGui.style.overflow = 'auto';
            this.eGui.innerHTML = this.createBulletList(params.value, params.colDef.field);
        }

        createBulletList(items, field) {
            if (items && Array.isArray(items)) {
                const listItems = items.map(item => {
                    return `<li><a href="${this.getLink(item, field)}" target="_blank">${item}</a></li>`;
                }).join('');
                return `<ul>${listItems}</ul>`;
            } else {
                return items;
            }
        }

        getLink(item, field) {
            // Add your logic to generate links based on the item (e.g., PMID or NCTID)
            if (field === 'referenced_pm_ids') {
                return 'https://pubmed.ncbi.nlm.nih.gov/' + item;
            } else if (field === 'referenced_nct_ids') {
                return 'https://clinicaltrials.gov/ct2/show/' + item;
            }
        }

        getGui() {
            return this.eGui;
        }
    }
    """  # noqa E501
)

cell_renderer_links = JsCode(
    """
    class UrlCellRenderer {
    init(params) {
        this.eGui = document.createElement('a');
        this.eGui.innerText = params.value;
        if (params.colDef.field === 'pm_id') {
            this.eGui.setAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/' + params.value);
        } else if (params.colDef.field === 'pmc_id') {
            this.eGui.setAttribute('href', 'https://www.ncbi.nlm.nih.gov/pmc/articles/' + params.value);
        } else if (params.colDef.field === 'nct_id') {
            this.eGui.setAttribute('href', 'https://clinicaltrials.gov/ct2/show/' + params.value);
        }
        this.eGui.setAttribute('style', 'text-decoration:none');
        this.eGui.setAttribute('target', '_blank');
    }
    getGui() {
        return this.eGui;
    }
    }
    """  # noqa E501
)


def display_evidence(
    df: pd.DataFrame, query_guideline: str | None, query_cuis: list[str]
) -> None:
    """Display the retrieved evidence in a dataframe."""
    if not df.empty:
        st.write(f"Found a total of {len(df)} evidence items.")
        builder = GridOptionsBuilder.from_dataframe(df)
        other_options = {"suppressColumnVirtualisation": True}
        builder.configure_grid_options(
            **other_options,
            rowHeight=100,
        )
        builder.configure_pagination(
            enabled=True,
            paginationPageSize=10,
            paginationAutoPageSize=False,
        )
        builder.configure_side_bar()

        builder.configure_column(
            "publication_date",
            type=["customDateTimeFormat"],
            custom_format_string="dd.MM.yyyy",
        )
        builder.configure_column(
            "date_last_update",
            type=["customDateTimeFormat"],
            custom_format_string="dd.MM.yyyy",
        )
        builder.configure_column(
            "title", maxWidth=300, cellRenderer=cell_renderer_multiline_scrollable
        )
        builder.configure_column(
            "abstract",
            maxWidth=300,
            cellRenderer=cell_renderer_multiline_scrollable,
        )

        builder.configure_column(
            "outcomes",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "eligibility",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "publication_types",
            cellRenderer=cell_renderer_bullet_points,
        )

        builder.configure_column(
            "population",
            cellRenderer=cell_renderer_bullet_points,
        )

        builder.configure_column(
            "interventions",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "interventions_unknown",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "interventions_known",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "interventions_recommended",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "interventions_not_recommended",
            cellRenderer=cell_renderer_bullet_points,
            maxWidth=250,
        )

        builder.configure_column(
            "referenced_pm_ids",
            cellRenderer=cell_renderer_bullet_points_with_links,
        )

        builder.configure_column(
            "referenced_nct_ids",
            cellRenderer=cell_renderer_bullet_points_with_links,
        )

        builder.configure_column(
            "pm_id", headerName="pm_id", cellRenderer=cell_renderer_links
        )

        builder.configure_column(
            "pmc_id", headerName="pmc_id", cellRenderer=cell_renderer_links
        )

        builder.configure_column(
            "nct_id", headerName="nct_id", cellRenderer=cell_renderer_links
        )

        # Define columns to be hidden by default
        columns_default_hidden = [
            "is_rct_mt",
            "is_rct",
            "number_of_groups",
            "number_of_arms",
            "study_type",
            "enrollment_type",
            "why_stopped",
            "referenced_pm_ids_results",
            "evidence_type",
            "evidence_level",
            "evidence_direction",
            "evidence_rating",
            "evidence_significance",
            "evidence_status",
            "overall_status",
            "cpg_matches_population",
            "cpg_matches_intervention",
            "concepts_population",
            "concepts_intervention",
            "concepts_intervention_known",
            "concepts_intervention_unknown",
            "concepts_intervention_recommended",
            "concepts_intervention_not_recommended",
        ]

        grid_options = builder.build()
        column_defs = grid_options["columnDefs"]

        for col in column_defs:
            if col["headerName"] in columns_default_hidden:
                col["hide"] = True

        AgGrid(
            df,
            update_mode=GridUpdateMode.NO_UPDATE,
            enable_enterprise_modules=True,
            theme="streamlit",
            enable_quicksearch=True,
            key="aggrid",
            gridOptions=grid_options,
            columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
            allow_unsafe_jscode=True,
        )
    else:
        st.write("No matches found for the query. Was looking for the following:")
        st.json({"guideline_id": query_guideline, "cuis": query_cuis})
