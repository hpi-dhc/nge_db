"""A module for retrieving evidence from Civic."""

from sqlalchemy import Select, desc, func, select, union
from sqlalchemy.orm import aliased, selectinload

from integration.orm import civic

def get_evidence_by_population(population_cuis: list[str], 
                               # TODO : filter by intervention not yet implemented
                               intervention_cuis: list[str] | None = None,
                               intervention_names: list[str] | None = None) -> Select:
    """Return a list of Sources with matching CUI in either diseases or phenotype."""
    # define subqueries for matching population
    evidence_with_matching_disease = aliased(
        civic.Evidence,
        select(civic.Evidence).where(civic.Evidence.disease_cui.in_(population_cuis)).subquery(),
    )
    evidence_with_matching_phenotype = aliased(
        civic.Evidence,
        select(civic.Evidence)
        .join(civic.Phenotype)
        .where(civic.Phenotype.cui.in_(population_cuis))
        .subquery(),
    )

    # combine subqueries
    query = (
        select(civic.Evidence)
        .join(civic.Source)
        .where(
            civic.Evidence.id.in_(
                union(
                    select(evidence_with_matching_disease.id),
                    select(evidence_with_matching_phenotype.id),
                )
            )
        )
        .options(
            selectinload(civic.Evidence.source).selectinload(
                civic.Source.clinical_trials
            ),
            selectinload(civic.Evidence.phenotypes),
            selectinload(civic.Evidence.therapies),
        )
        .order_by(desc(civic.Source.date_publication))
    )

    return query

def get_number_of_records() -> Select:
    """Return the number of trials in the Civic database."""
    query = select(func.count()).select_from(civic.Evidence)
    return query

def get_year_min() -> Select:
    """Return the earliest year of a trial in the Civic database."""
    query = (
        select(func.min(civic.Source.date_publication))
        .select_from(civic.Source)
        .where(civic.Source.date_publication.isnot(None))
    )
    return query

def get_year_max() -> Select:
    """Return the latest year of a trial in the Civic database."""
    query = (
        select(func.max(civic.Source.date_publication))
        .select_from(civic.Source)
        .where(civic.Source.date_publication.isnot(None))
    )
    return query
