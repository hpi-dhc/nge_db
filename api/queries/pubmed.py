"""A module for retrieving evidence from annotated Pubmed evidence."""

from sqlalchemy import CompoundSelect, Select, desc, func, or_, and_, select, union
from sqlalchemy.orm import aliased, selectinload

from integration.orm import pubmed

def get_evidence_by_population(
    population_cuis: list[str],
    intervention_cuis: list[str] | None = None,
    intervention_names: list[str] | None = None,
    consider_mesh_terms: bool = True,
) -> Select:
    """Return a list of Trials connected to the provided population CUI."""
    subquery_mesh_terms = select(pubmed.MeshTerm.trial_id).where(
        pubmed.MeshTerm.cui.in_(population_cuis)
    )
    subquery_umls_population = select(pubmed.UmlsPopulation.trial_id).where(
        pubmed.UmlsPopulation.cui.in_(population_cuis)
    )
    if consider_mesh_terms:
        population_clause = union(subquery_mesh_terms, subquery_umls_population)       
    else:
        population_clause = subquery_umls_population
    if not intervention_cuis:
        join_clause = population_clause.subquery()
    else:
        subquery_umls_interventions = select(pubmed.UmlsIntervention.trial_id).where(
            pubmed.UmlsIntervention.cui.in_(intervention_cuis)
        )
        subquery_mesh_interventions = select(pubmed.MeshTerm.trial_id).where(
            pubmed.MeshTerm.cui.in_(intervention_cuis)
        )
        if not intervention_names:
            intervention_subq =  union(
                subquery_umls_interventions,
                subquery_mesh_interventions,
            ).subquery()
        else:
            subquery_intervention_name = select(pubmed.Intervention.trial_id).where(pubmed.Intervention.intervention.in_(intervention_names))
            intervention_subq = union(
                subquery_umls_interventions,
                subquery_intervention_name,
                subquery_mesh_interventions,
            ).subquery()
        population_subq = population_clause.subquery()
        join_clause = select(population_subq.c.trial_id).join(intervention_subq, population_subq.c.trial_id == intervention_subq.c.trial_id).distinct().subquery()
    query = (
        select(pubmed.Trial)
        .join(join_clause, pubmed.Trial.id == join_clause.c.trial_id)
        .order_by(desc(pubmed.Trial.publication_date))
        .options(
            selectinload(pubmed.Trial.umls_population),
            selectinload(pubmed.Trial.umls_interventions),
            selectinload(pubmed.Trial.publication_types),
            selectinload(pubmed.Trial.mesh_terms),
            selectinload(pubmed.Trial.references),
            selectinload(pubmed.Trial.outcomes),
            selectinload(pubmed.Trial.flags),
        )
    )
    return query

def get_all_interventions() -> Select:
    """Return a list of all interventions in the Pubmed database."""
    return select(pubmed.UmlsIntervention.cui).distinct()

def get_population_concepts_by_id(pm_ids: list[int]) -> CompoundSelect:
    """Return tuples of PMID, CUI, and term for the provided PMID."""
    mesh_alias = aliased(pubmed.MeshTerm)
    umls_alias = aliased(pubmed.UmlsPopulation)

    query_mesh_concepts = (
        select(
            pubmed.Trial.pm_id.label("id"),
            mesh_alias.cui.label("cui"),
            mesh_alias.mesh_term.label("term"),
        )
        .join(pubmed.MeshTerm, isouter=True)
        .where(pubmed.MeshTerm.cui.isnot(None))
        .join_from(pubmed.Trial, mesh_alias, mesh_alias.trial_id == pubmed.Trial.id)
        .where(pubmed.Trial.pm_id.in_(pm_ids))
    )

    query_umls_concepts = (
        select(
            pubmed.Trial.pm_id.label("id"),
            umls_alias.cui.label("cui"),
            umls_alias.cui_term.label("term"),
        )
        .join(pubmed.UmlsPopulation, isouter=True)
        .join_from(pubmed.Trial, umls_alias, umls_alias.trial_id == pubmed.Trial.id)
        .where(pubmed.Trial.pm_id.in_(pm_ids))
    )

    return union(query_mesh_concepts, query_umls_concepts)

def get_number_of_records() -> Select:
    """Return the number of trials in the Pubmed database."""
    query = select(func.count()).select_from(pubmed.Trial)
    return query

def get_year_min() -> Select:
    """Return the earliest year of a trial in the Pubmed database."""
    query = (
        select(func.min(pubmed.Trial.publication_date))
        .select_from(pubmed.Trial)
        .where(pubmed.Trial.publication_date.isnot(None))
    )
    return query

def get_trials_by_ids(pm_ids: list[str]) -> Select:
    """Return a list of trials for the provided Pubmed IDs."""
    query = select(pubmed.Trial).where(pubmed.Trial.pm_id.in_(pm_ids))
    return query

def get_trials_by_nct_ids(nct_ids: list[str]) -> Select:
    """Return a list of trials referencing the provided NCT ID."""
    subquery_references = select(pubmed.Reference.trial_id).where(
            pubmed.Reference.nct_id.in_(nct_ids)
    )
    query = select(pubmed.Trial).where(pubmed.Trial.id.in_(subquery_references))
    return query

def get_year_max() -> Select:
    """Return the latest year of a trial in the Pubmed database."""
    query = (
        select(func.max(pubmed.Trial.publication_date))
        .select_from(pubmed.Trial)
        .where(pubmed.Trial.publication_date.isnot(None))
    )
    return query
