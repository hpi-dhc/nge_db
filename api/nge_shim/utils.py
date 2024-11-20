"""Helper functions for the NGE shim."""

from api.models import Evidence
from api.nge_shim.models import Intervention, Population, Topic, TopicsResponse, Trial
import re
import pandas as pd


def filter_by_sample_size(
    evidence: Evidence, sample_range_min: int | None, sample_range_max: int | None
) -> bool:
    """Filter evidence by sample size."""
    if evidence.sample_size is not None:
        if sample_range_min is not None and evidence.sample_size < sample_range_min:
            return True
        if sample_range_max is not None and evidence.sample_size > sample_range_max:
            return True
    return False


def filter_by_year(
    evidence: Evidence, year_range_min: int | None, year_range_max: int | None
) -> bool:
    """Filter evidence by publication year."""
    if evidence.publication_date is not None:
        if (
            year_range_min is not None
            and evidence.publication_date.year < year_range_min
        ):
            return True
        if (
            year_range_max is not None
            and evidence.publication_date.year > year_range_max
        ):
            return True
        """Filter evidence by publication year."""
    if evidence.date_start is not None:
        if (
            year_range_min is not None
            and evidence.date_start.year < year_range_min
        ):
            return True
        if (
            year_range_max is not None
            and evidence.date_start.year > year_range_max
        ):
            return True
    return False


def filter_by_phase(evidence: Evidence, phase: list[int]) -> bool:
    """Filter evidence by trial phase."""
    for p in phase:
        if p in evidence.phases_all:
            return True
    if -1 in phase:
        for p in evidence.phases_all:
            if p in [1, 2, 3, 4]:
                return False
        return True
    return False


def apply_trialsearch_filters(
    evidence: list[Evidence],
    sample_range_min: int | None,
    sample_range_max: int | None,
    year_range_min: int | None,
    year_range_max: int | None,
    max_results: int | None,
    has_unknown_intervention: bool | None,
    has_known_intervention: bool | None,
    has_not_recommended_intervention: bool | None,
    has_recommended_intervention: bool | None,
    exclude_children: bool = False,
    phase: list[int] | None = None,
    significant_results: bool | None = None,
    results_available: bool | None = None,
    strict_rct_filter: bool | None = True,
) -> list[Evidence]:
    """Apply filters to evidence."""
    evidence_filtered: list[Evidence] = []
    for e in evidence:
        if max_results is not None and len(evidence_filtered) >= max_results:
            break
        if strict_rct_filter and e.source == "Pubmed" and not e.is_rct:
            continue
        if filter_by_sample_size(e, sample_range_min, sample_range_max):
            continue
        if (
            results_available
            and e.source == "ClinicalTrials"
            and not e.results_available
        ):
            continue
        if filter_by_year(e, year_range_min, year_range_max):
            continue
        if phase is not None and not filter_by_phase(e, phase):
            continue
        if exclude_children and e.has_pediatric_population is True:
            continue
        if has_unknown_intervention and e.has_unknown_intervention is not True:
            continue
        if has_known_intervention and e.has_known_intervention is not True:
            continue
        if (
            has_not_recommended_intervention
            and e.has_not_recommended_intervention is not True
        ):
            continue
        if has_recommended_intervention and e.has_recommended_intervention is not True:
            continue
        if significant_results and e.has_significant_finding is not True:
            continue
        evidence_filtered.append(e)
    return evidence_filtered


def parse_evidence_to_trial(evidence: Evidence, topic_id: str, full_details : bool =False) -> Trial:
    """Parse Evidence object to an NGE Trial object."""
    return Trial(
        pmid=evidence.pm_id,
        nct_id=evidence.nct_id,
        ti=evidence.title,
        authors=evidence.authors,
        journal=evidence.journal,
        phases=evidence.phases_all,
        citing_guidelines=evidence.citing_guidelines,
        abstract=evidence.abstract if full_details else None,
        topic_id=topic_id,
        has_unknown_intervention=evidence.has_unknown_intervention,
        has_known_intervention=evidence.has_known_intervention,
        has_not_recommended_intervention=evidence.has_not_recommended_intervention,
        has_recommended_intervention=evidence.has_recommended_intervention,
        populations=(
            [
                Population(text=c.text, umls_term=c.text_umls, cui=c.cui)
                for c in evidence.concepts_matching_population
                if c.text_umls is not None
            ]
            if evidence.concepts_matching_population
            else []
        ),
        interventions=(
            [
                Intervention(
                    known_intervention=c.is_known,
                    recommended_intervention=c.is_recommended,
                    text=c.text,
                    umls_term=c.text_umls,
                    cui=c.cui,
                )
                for c in {c.text: c for c in evidence.concepts_intervention}.values()
                if not c.is_hidden_by_filter
                # De-duplicate interventions by text
            ]
            if evidence.concepts_intervention
            else []
        ),
        outcomes=evidence.outcomes,
        source=evidence.source,
        result_available=evidence.results_available,
        publication_date=evidence.publication_date,
        start_date=evidence.date_start
    )


def prepare_topics_response(
    valid_topics: dict[str, dict[str, str]],
    max_n: int,
    year_max: int,
    year_min: int,
) -> TopicsResponse:
    """Prepare a TopicsResponse object."""
    topics = []
    for id, names in valid_topics.items():
        topics.append(
            Topic(
                topic_id=id,
                topic_de=names["name_de"],
                topic_en=names["name_en"],
                version=names["latest_version"],
                version_date=names["latest_version_date"],
            )
        )
    return TopicsResponse(
        max_n=max_n,
        topics=topics,
        year_max=year_max,
        year_min=year_min,
    )


def _is_nct(ev):
    return ev.source == "ClinicalTrials"


def _evidence_to_dict(ev: Evidence):
    return {
        "id": ev.nct_id if _is_nct(ev) else ev.pm_id,
        "source": ev.source,
        "title" : ev.title,
        "result_date": ev.publication_date,
        "max_phase": max(ev.phases_all) if ev.phases_all else None,
        "cited_in_guideline": ev.query.guideline_id in ev.citing_guidelines,
        "referenced_nct_ids": ev.referenced_nct_ids,
        "referenced_pm_ids": ev.referenced_pm_ids,
        "start_date": ev.date_start if _is_nct(ev) else ev.publication_date,        
        "overall_status": ev.overall_status,
        "_ev" : ev,
    }


def evidence_to_grouped_df(evidence: list[Evidence], include_unfinished_trials):
    grouped_evidence = pd.DataFrame([_evidence_to_dict(ev) for ev in evidence]).dropna(subset=["start_date"])    
    grouped_evidence["group"] = grouped_evidence.id
    duplicates = []
    for i, r in grouped_evidence.query('source == "Pubmed"').iterrows():
        if not type(r.referenced_nct_ids) == float and len(r.referenced_nct_ids) > 0:
            nct_id = r.referenced_nct_ids[0]
            grouped_evidence.loc[i, "group"] = nct_id
            if len(r.referenced_nct_ids) > 1:
                for nct_id in r.referenced_nct_ids[1:]:
                    dupl = r.copy()
                    dupl["group"] = nct_id
                    duplicates.append(dupl)

    if duplicates:
        grouped_evidence = pd.concat(
            [grouped_evidence, pd.DataFrame(duplicates)]
        ).reset_index()

    grp2idx = {
        grp: i
        for i, grp in enumerate(
            grouped_evidence.groupby("group")[["max_phase", "start_date"]]
            .min()
            .sort_values(["max_phase", "start_date"], ascending=[False, False])
            .index
        )
    }
    exclude_groups = []
    if not include_unfinished_trials:
        for grp in grp2idx.keys():
            group_trials = grouped_evidence.query(f"group == @grp")
            if len(group_trials) == 1 and not group_trials.iloc[0].result_date:
                exclude_groups.append(grp)
        grouped_evidence = grouped_evidence[~grouped_evidence.group.isin(exclude_groups)]
    return grouped_evidence.sort_values(
        "group", key=lambda s: s.apply(lambda x: grp2idx[x])
    )
