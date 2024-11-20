"""A module for retrieving evidence from GGPONC CPGs."""

from collections import defaultdict

from sqlalchemy import CompoundSelect, Result, select, union, and_
from sqlalchemy.orm import Session, aliased

from integration.orm import ggponc, ggponc_literature

from functools import cache

def _build_cui_to_cpg_mapping(
    mapping_query_results: Result[tuple[str, str, str]]
) -> dict[str, set[str]]:
    """Parse the results from the SQL query to a CUI->CPG ID dictionary."""
    cui_to_cpg_mapping = defaultdict(set)
    for ggponc_id, cui, relation_mapped_cui in mapping_query_results:
        cui_to_cpg_mapping[cui].add(ggponc_id)
        cui_to_cpg_mapping[relation_mapped_cui].add(ggponc_id)
    return cui_to_cpg_mapping


@cache
def get_guideline_names(
    session: Session,
) -> dict[str, dict[str, str]]:
    """Return a mapping of GGPONC ID to guideline name."""
    return {
        gg.ggponc_id: {"name_de": gg.name, "name_en": gg.name_en}
        for gg in session.scalars(select(ggponc.Guideline))
    }


@cache
def get_population_to_guideline_mapping(
    session: Session,
) -> dict[str, set[str]]:
    """Return a mapping of population CUI to GGPONC ID(s)."""
    query = (
        select(
            ggponc.Guideline.ggponc_id, ggponc.Population.cui, ggponc.SubPopulation.cui
        )
        .select_from(ggponc.Guideline)
        .join(ggponc.Population)
        .join(ggponc.SubPopulation, isouter=True)
    )
    results = session.execute(query)
    return _build_cui_to_cpg_mapping(results)


@cache
def get_intervention_to_guideline_mapping(
    session: Session, recommended_only: bool = False
) -> dict[str, set[str]]:
    """Return a mapping of intervention CUI to GGPONC ID(s)."""
    query = (
        select(ggponc.Guideline.ggponc_id, ggponc.Entity.cui, ggponc.SuperConcept.cui)
        .select_from(ggponc.Guideline)
        .join(ggponc.TextBlock, isouter=True)
        .join(ggponc.Entity, isouter=True)
        .join(ggponc.SuperConcept, isouter=True)
    )
    if recommended_only:
        query = query.where(ggponc.TextBlock.recommendation.is_(True))  # noqa
    results = session.execute(query)
    return _build_cui_to_cpg_mapping(results)


def resolve_guideline_id_to_population_cuis(
    guideline_id: str | None = None,
) -> CompoundSelect:
    """Return the union of all GGPONC population CUIs and their mapped sub-populations."""
    query_population = select(ggponc.Population.id, ggponc.Population.cui)
    if guideline_id is not None:
        query_population = query_population.join(ggponc.Guideline).where(
            ggponc.Guideline.ggponc_id == guideline_id
        )
    relevant_population = aliased(ggponc.Population, query_population.subquery())
    return union(
        select(relevant_population.cui),
        select(ggponc.SubPopulation.cui).join(relevant_population),
    )


def resolve_guideline_id_to_intervention_cuis(
    guideline_id: str | None = None,
) -> CompoundSelect:
    """Return the union of all GGPONC entity cuis and their mapped sub-concepts."""
    query_entities = select(ggponc.Entity.id, ggponc.Entity.cui)
    if guideline_id is not None:
        query_entities = (
            query_entities.join(ggponc.TextBlock)
            .join(ggponc.Guideline)
            .where(ggponc.Guideline.ggponc_id == guideline_id)
        )
    relevant_entities = aliased(ggponc.Entity, query_entities.subquery())
    return union(
        select(relevant_entities.cui),
        select(ggponc.SuperConcept.cui).join(relevant_entities),
    )


def get_cited_pmids(guideline_id: str) -> CompoundSelect:
    """Return a mapping of GGPONC ID to cited PMIDs."""
    return select(ggponc_literature.GgponcLiteratureReference.pm_id).where(
            ggponc_literature.GgponcLiteratureReference.guideline_id == guideline_id,
            ggponc_literature.GgponcLiteratureReference.pm_id != None,
        )
