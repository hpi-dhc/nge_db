"""A module containing a basic frontend (i.e. the evidence browser)."""

from typing import Any, Literal

import streamlit as st
from requests.exceptions import ConnectionError

from api.models import EvidenceQuery
from api.utils import (
    evidence_to_df,
    query_api_for_evidence,
    query_api_for_supported_guidelines,
)
from frontend.table import display_evidence

st.set_page_config(layout="wide")

st.header("Evidence Browser")

supported_guidelines = []

with st.spinner("Waiting for API response..."):
    try:
        supported_guidelines = query_api_for_supported_guidelines()
    except ConnectionError:
        st.error("No response from the API, is it running?")
        st.info("If not, start it using `poetry run api`")
        st.stop()

query_sources: list[
    Literal["civic", "clinicaltrials", "pubmed"]
] = st.multiselect(
    "Select source. If none selected, all sources will be queried.",
    options=["civic", "clinicaltrials", "pubmed"],
    format_func=lambda x: x.capitalize(),
    default=["pubmed"],
)

query_guideline = st.selectbox(
    "Search by GGPONC guideline",
    options=sorted(supported_guidelines),
    index=None,
    placeholder="Leave empty to search across all guidelines",
)

with st.expander("Search by additional population CUIs", expanded=False):
    query_cuis = [
        cui.strip()
        for cui in st.text_input(
            "Search by CUI(s)",
            placeholder="Enter UMLS CUI or list of CUIs (comma separated)",
        ).split(",")
    ]


@st.cache_data(show_spinner=False)
def request_evidence(
    guideline_id: str | None,
    cuis: list[str] = [],
    sources: list[
        Literal[
            "civic",
            "clinicaltrials",
            "pubmed",
        ]
    ] = [],
) -> dict[str, Any]:
    """Retrieve evidence for the selected guideline."""
    query = EvidenceQuery(
        sources=sources, guideline_id=guideline_id, cuis_population=cuis
    )
    return query_api_for_evidence(query=query)


# Build an API query from the user input
query = EvidenceQuery(sources=query_sources, guideline_id=query_guideline)

# Define a session_state variable to store the previous source selection
if "previous_query" not in st.session_state:
    st.session_state.previous_query = query.model_dump_json()

# Check if the source selection has changed
source_selection_changed = query != st.session_state.previous_query
st.session_state.previous_query = query

# Define a session_state variable to store whether a query has been made
query_made = st.button("Retrieve evidence", type="primary")

if "query_made" not in st.session_state:
    st.session_state.query_made = False

if query_made or st.session_state.query_made:
    st.session_state.query_made = True
    if source_selection_changed:
        st.write(
            "Query parameters have changed. Click 'Retrieve evidence' to update the data."
        )
        st.stop()
    else:
        if query_sources is not None:
            with st.spinner("Waiting for API response..."):
                try:
                    retrieved_evidence = request_evidence(
                        guideline_id=query_guideline,
                        cuis=query_cuis,
                        sources=query_sources,
                    )
                    df = evidence_to_df(retrieved_evidence)
                    display_evidence(df, query_guideline, query_cuis)
                except ConnectionError:
                    st.error("No response from the API, is it running?")
                    st.info("If not, start it using `poetry run api`")
                    st.stop()
