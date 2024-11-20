"""A module for retrieving evidence from AACT."""

from sqlalchemy import Select, desc, func, join, select, and_, or_
from sqlalchemy.orm import selectinload

from integration.orm import aact


from sqlalchemy import CompoundSelect, Select, desc, func, or_, and_, select, union, join
from sqlalchemy.orm import aliased, selectinload

from integration.orm import pubmed, aact

def get_evidence_by_population(
    population_cuis: list[str],
    intervention_cuis: list[str] | None = None,
    intervention_names: list[str] | None = None,
) -> Select:
    """Return a list of Trials connected to the provided evidence CUI."""
    population_subq = select(aact.MeshCondition.trial_id).where(aact.MeshCondition.cui.in_(population_cuis))
    
    if not intervention_cuis:
        join_clause = population_subq.distinct().subquery()
    else:
        subquery_mesh_interventions = select(aact.MeshIntervention.trial_id).where(
            aact.MeshIntervention.cui.in_(intervention_cuis)
        )
        if not intervention_names:
            intervention_subq = subquery_mesh_interventions.subquery()
        else:
            subquery_intervention_name = select(aact.Intervention.trial_id).where(aact.Intervention.intervention.in_(intervention_names))
            intervention_subq = union(
                subquery_mesh_interventions,
                subquery_intervention_name,
            ).subquery()
        population_subq = population_subq.subquery()
        join_clause = select(population_subq.c.trial_id).join(intervention_subq, population_subq.c.trial_id == intervention_subq.c.trial_id).distinct().subquery()
    
    query = (
        select(aact.Trial)
        .join(join_clause, aact.Trial.id == join_clause.c.trial_id)
        .order_by(desc(aact.Trial.date_results_first_posted))
        .options(
            selectinload(aact.Trial.mesh_conditions),
            selectinload(aact.Trial.mesh_interventions),
            selectinload(aact.Trial.references),
            selectinload(aact.Trial.eligibilities),
            selectinload(aact.Trial.outcomes).selectinload(aact.Outcome.analyses),
            selectinload(aact.Trial.flags),
        )
    )
    return query


def get_trials_by_ids(nct_ids: list[str]) -> Select:
    """Return a list of Trials for the provided NCT IDs."""
    query = select(aact.Trial).where(aact.Trial.nct_id.in_(nct_ids))
    return query


def get_population_concepts_by_id(nct_ids: list[str]) -> Select:
    """Return tuples of NCT ID, CUI, and term for the provided NCT IDs."""
    query = (
        select(
            aact.Trial.nct_id.label("id"),
            aact.MeshCondition.cui.label("cui"),
            aact.MeshCondition.mesh_term.label("term"),
        )
        .join(aact.MeshCondition, isouter=True)
        .where(aact.Trial.nct_id.in_(nct_ids))
    )
    return query

def get_number_of_records() -> Select:
    """Return the number of trials in the AACT database."""
    query = select(func.count()).select_from(aact.Trial)
    return query

def get_year_min() -> Select:
    """Return the earliest year of a trial in the AACT database."""
    query = (
        select(func.min(aact.Trial.date_results_first_posted))
        .select_from(aact.Trial)
        .where(aact.Trial.date_results_first_posted.isnot(None))
    )
    return query

def get_year_max() -> Select:
    """Return the latest year of a trial in the AACT database."""
    query = (
        select(func.max(aact.Trial.date_results_first_posted))
        .select_from(aact.Trial)
        .where(aact.Trial.date_results_first_posted.isnot(None))
    )
    return query
