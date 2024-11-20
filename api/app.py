"""A module that contains the API implementation."""

import datetime
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator, Literal, Annotated

from fastapi.responses import FileResponse
import uvicorn
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from sqlalchemy.orm import Session, sessionmaker
import yaml

import tempfile, uuid

from api.viz.timelines import create_timeline_figure

import api.nge_shim.models as shim_models
import api.nge_shim.utils as shim_utils
from api.models import (
    ConceptsQuery,
    Evidence,
    EvidenceQuery,
    UmlsConcept,
    UmlsConceptParser,
)
from api.queries import aact, civic, ggponc, pubmed, versions
from api.utils import get_previous_guideline_versions

from integration.config import load_config, parse_config_list
from integration.db import get_engine
from integration.umls.parser import MetaThesaurusParser
from integration.umls.relationship_mapping import RelationshipMapper

from cachetools import LRUCache, cached

from api.utils import get_previous_guideline_versions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    filename="api.log",
)
logger = logging.getLogger(__name__)

# TODO make configurable
debug = False

cache = LRUCache(maxsize=1024)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run logic that is only executed on app start and shutdown."""
    app.state.config = load_config()
    for filter_param, list_str in app.state.config["API"].items():
        app.state.__setattr__(filter_param, parse_config_list(list_str))
    db_config = app.state.config["DB"]
    app.state.engine = get_engine(
        db_config["url"],
        echo=debug,
        pool_size=db_config.getint("pool_size"),
        max_overflow=db_config.getint("max_overflow"),
    )
    app.state.session = sessionmaker(bind=app.state.engine)
    with app.state.session() as s:
        umls_parser = MetaThesaurusParser(**app.state.config["MetaThesaurusParser"])
        app.state.concept_parser = UmlsConceptParser(
            umls_parser=umls_parser,
            cache_dir="cache/",
            cui_to_cpg_map_population=ggponc.get_population_to_guideline_mapping(s),
            cui_to_cpg_map_intervention=ggponc.get_intervention_to_guideline_mapping(s),
            cui_to_cpg_map_intervention_recommended=ggponc.get_intervention_to_guideline_mapping(
                s, recommended_only=True
            ),
        )
        app.state.relationship_mapper = RelationshipMapper(
            umls_parser=umls_parser, **app.state.config["RelationshipMapper"]
        )
    # load UMLS dataframe cached properties
    app.state.concept_parser.umls_parser.df_mrconso
    app.state.concept_parser.umls_parser.df_mrsty
    # set default sources
    app.state.default_sources = ["pubmed", "clinicaltrials", "civic"]
    with open(app.state.config["GGPONC"]["topic_yaml_path"], "r") as fh:
        app.state.topic_config = yaml.safe_load(fh)
    # set source to query constructor / parser mapping
    app.state.source_query_parser_map = {
        "pubmed": (pubmed.get_evidence_by_population, Evidence.from_pubmed_trial),
        "clinicaltrials": (aact.get_evidence_by_population, Evidence.from_aact_trial),
        "civic": (civic.get_evidence_by_population, Evidence.from_civic_evidence),
    }
    yield
    app.state.concept_parser.cache.close()


def prepare_session() -> Iterator[Session]:
    """Establish a connection to the DB and return a session."""
    with app.state.session() as session:
        yield session 


app = FastAPI(lifespan=lifespan)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=100000)


def parse_population_cuis_from_query(
    query_api: EvidenceQuery, session: Session = Depends(prepare_session)
) -> list[str]:
    """Parse the population CUIs from the query."""
    population_cuis = []
    query_db = ggponc.resolve_guideline_id_to_population_cuis(query_api.guideline_id)
    population_cuis = list(session.scalars(query_db).all())
    if query_api.cuis_population:
        population_cuis.extend(query_api.cuis_population)
    logger.info(f"Query resolved to {len(population_cuis)} population CUIs")
    return list(set(population_cuis))


def parse_intervention_cuis_from_query(
    query_api: EvidenceQuery, session: Session = Depends(prepare_session)
) -> list[str]:
    """Parse the intervention CUIs from the query."""
    if not query_api.cuis_intervention:
        return query_api.cuis_intervention
    cuis_intervention = [c for c in query_api.cuis_intervention]  # copy
    for c in query_api.cuis_intervention:
        cuis_intervention += app.state.relationship_mapper.get_related_concepts(
            c, direction="broad2narrow"
        )
    logger.info(f"Query resolved to {len(cuis_intervention)} intervention CUIs")
    return list(set(cuis_intervention))


def parse_intervention_names_from_query(
    query_api: EvidenceQuery, session: Session = Depends(prepare_session)
) -> list[str]:
    return list(set(query_api.intervention_names))


def set_query_defaults(query_api: EvidenceQuery) -> EvidenceQuery:
    """Set default STN filters if none are specified in the query."""
    if query_api.filter_stns_population is None:
        query_api.filter_stns_population = app.state.filter_stns_population
    if query_api.ignore_cuis_interventions is None:
        query_api.ignore_cuis_interventions = app.state.ignore_cuis_interventions
    if query_api.filter_stns_interventions is None:
        query_api.filter_stns_interventions = app.state.filter_stns_interventions
    if query_api.filter_stns_interventions_unknown is None:
        query_api.filter_stns_interventions_unknown = (
            app.state.filter_stns_interventions_unknown
        )
    if query_api.filter_stns_interventions_known is None:
        query_api.filter_stns_interventions_known = (
            app.state.filter_stns_interventions_known
        )
    if query_api.filter_cuis_pediatric_population is None:
        query_api.filter_cuis_pediatric_population = (
            app.state.filter_cuis_pediatric_population
        )
    return query_api


@app.post("/evidence/by/population", response_model=list[Evidence])
def get_evidence_by_population(
    query_api: EvidenceQuery, session: Session = Depends(prepare_session)
) -> list[Evidence]:
    """Return evidence filtered by population CUIs."""
    logger.info(f"HTTP POST Query received: {query_api.model_dump()}")
    query_api = set_query_defaults(query_api)
    population_cuis = parse_population_cuis_from_query(query_api, session)
    intervention_cuis = parse_intervention_cuis_from_query(query_api, session)
    intervention_names = parse_intervention_names_from_query(query_api, session)
    sources = app.state.default_sources if not query_api.sources else query_api.sources

    evidence = []
    guideline_id = query_api.guideline_id

    for source in sources:
        
        trials = _get_evidence_by_population(source, population_cuis, intervention_cuis, intervention_names, session)
        _, evidence_parser = app.state.source_query_parser_map[source]

        guideline_pmids = {}
        if (
            source == "pubmed" and guideline_id
        ):  # TODO: should work for all kinds of queries by population
            guideline_pmids = _get_guideline_pmids(guideline_id, session)
        
        for t in trials:
            e = evidence_parser(t, app.state.concept_parser, query_api)
            if type(e.pm_id) == int and e.pm_id in guideline_pmids:
                e.citing_guidelines.append(guideline_id)
            if apply_filter(e, query_api):
                evidence.append(e)
        _fill_evidence_metadata(evidence, population_cuis)
        logger.info(f"{source} - Parsed trials to API Evidence Items")

    logger.info(f"Retrieved a total of {len(evidence)} evidence items")
    return evidence

@cached(cache, key=lambda args, _: args[0])
def _get_guideline_pmids(guideline_id, session):
    query_cited_ids = ggponc.get_cited_pmids(guideline_id)
    guideline_pmids = set(session.scalars(query_cited_ids).unique().all())
    return guideline_pmids

def _evidence_cache_key(*args, **kwargs):
    # Convert each list argument to a tuple and hash the rest directly
    source, population_cuis, intervention_cuis, intervention_names, session = args
    return (source, tuple(population_cuis), tuple(intervention_cuis), tuple(intervention_names))

@cached(cache, key=_evidence_cache_key)
def _get_evidence_by_population(source, population_cuis, intervention_cuis, intervention_names, session):
    query_constructor, _ = app.state.source_query_parser_map[source]

    logger.info(f"{source} - Retrieving evidence")
    query_db = query_constructor(
        population_cuis=population_cuis,
        intervention_cuis=intervention_cuis,
        intervention_names=intervention_names,
    )
    trials = session.scalars(query_db).unique().all()
    logger.info(f"{source} - Retrieved {len(trials)} trials from DB")
    return trials

def _fill_evidence_metadata(evidence: list[Evidence], population_cuis: list[str]):
    population_cuis_set = set(population_cuis)
    for e in evidence:
        if e.concepts_population:
            e.concepts_matching_population = [
                p for p in e.concepts_population if p.cui in population_cuis_set
            ]


def apply_filter(evidence: Evidence, query_api: EvidenceQuery) -> bool:
    """Apply filters to evidence based on computed metadata."""
    if evidence.is_review and query_api.filter_reviews:
        return False
    if evidence.is_protocol and query_api.filter_protocols:
        return False
    return True


@app.get("/guidelines", response_model=list[str])
def get_supported_guidelines() -> list[str]:
    """Return a list of supported guidelines."""
    return list(
        set().union(*app.state.concept_parser.cui_to_cpg_map_population.values())
    )


@cached(cache, key=lambda _:'Interventions')
@app.get("/interventions", response_model=list[shim_models.InterventionItem])
def get_interventions(session: Session = Depends(prepare_session)):
    """Return a list of all interventions."""
    query_db = pubmed.get_all_interventions()
    intervention_cuis = list(session.scalars(query_db).all())

    result = []
    for c in intervention_cuis:
        term = app.state.concept_parser.umls_parser.get_umls_text(c)
        if not term:
            continue
        result.append(
            shim_models.InterventionItem(
                cui=c,
                umls_term=term,
                guideline_ids=app.state.concept_parser.cui_to_cpg_map_intervention[c],
            )
        )
    return sorted(
        [r for r in result if r.umls_term and r.cui], key=lambda r: r.umls_term
    )

def get_image_dir():
    return Path(tempfile.gettempdir())


@app.get("/timelines", response_model=shim_models.TimelineResponse)
def get_timeline(
    guideline_id: str,
    cui_intervention: str,
    sources: Annotated[list[Literal["civic", "clinicaltrials", "pubmed"]], Query()] = [
        "pubmed",
        "clinicaltrials",
    ],
    include_children: bool = False,
    include_unfinished_trials: bool = False,
    session: Session = Depends(prepare_session),
):
    query_api = EvidenceQuery(
        guideline_id=guideline_id, cuis_intervention=[cui_intervention], sources=sources
    )
    evidence_grouped_df = get_evidence_grouped_df(
        query_api, include_unfinished_trials, session
    )

    if evidence_grouped_df is not None and not include_children:
        evidence_grouped_df = evidence_grouped_df[
            evidence_grouped_df._ev.map(lambda e: not e.has_pediatric_population)
        ]

    if evidence_grouped_df is None or len(evidence_grouped_df) == 0:  # empty response
        return shim_models.TimelineResponse(
            grouped_trials=[],
            image_url=None,
        )

    topic = query_api.guideline_id
    meta = get_meta(session)

    versions = get_previous_guideline_versions(
        app.state.topic_config, query_api.guideline_id, meta.versions["ggponc"][0]
    )

    fig = create_timeline_figure(
        evidence_grouped_df,
        versions=versions,
    )

    file_name = get_image_dir() / f"timeline_{uuid.uuid4()}.png"
    fig.savefig(file_name, bbox_inches="tight", dpi=300)
    logger.info(f"Image saved as {file_name}")

    grouped_trials = []
    for g in evidence_grouped_df.group.unique():
        trials_group = []
        for _, row in evidence_grouped_df[evidence_grouped_df.group == g].iterrows():
            ev = row._ev
            trial = shim_utils.parse_evidence_to_trial(ev, topic_id=topic)
            trials_group.append(trial)
        grouped_trials.append((str(g), trials_group))

    return shim_models.TimelineResponse(
        grouped_trials=grouped_trials,
        image_url="image/" + file_name.name,
    )


def get_evidence_grouped_df(
    query_api: EvidenceQuery, include_unfinished_trials, session: Session
) -> list[Evidence]:
    evidence = get_evidence_by_population(query_api, session)
    # Find additional references by tracing NCT references
    nct_ids = {e.nct_id for e in evidence if e.nct_id}
    references = {nct_id for e in evidence for nct_id in e.referenced_nct_ids}
    new_refs = list(references.difference(nct_ids))
    query_ids = aact.get_trials_by_ids(new_refs)
    trials = session.scalars(query_ids).unique().all()
    logger.info(f"Retrieved additional {len(trials)} trials through references from DB")
    evidence.extend(
        [
            Evidence.from_aact_trial(t, app.state.concept_parser, query_api)
            for t in trials
        ]
    )
    if not evidence:
        return None
    return shim_utils.evidence_to_grouped_df(evidence, include_unfinished_trials)


@app.post("/concepts", response_model=list[tuple[str | int, UmlsConcept]])
def get_population_concepts_by_id(
    query_api: ConceptsQuery, session: Session = Depends(prepare_session)
) -> list[tuple[str | int, UmlsConcept]]:
    """Return a mapping of IDs to attached concepts."""
    query_db = None
    if query_api.kind == "interventions":
        raise NotImplementedError("The interventions endpoint is not yet implemented!")
    if query_api.source == "clinicaltrials":
        query_db = aact.get_population_concepts_by_id([str(id) for id in query_api.ids])
    elif query_api.source == "pubmed":
        query_db = pubmed.get_population_concepts_by_id([int(i) for i in query_api.ids])
    query_results = session.execute(query_db).fetchall()  # type: ignore
    return [
        (
            row.id,
            app.state.concept_parser.parse_population(
                row.cui, row.term, EvidenceQuery()
            ),
        )
        for row in query_results
        if row.cui is not None
    ]


@app.get("/image/{file_name}")
def get_image(file_name: str):
    return FileResponse(get_image_dir() / file_name)


# Shim routes for NGE Browser compatibility
@app.get("/topics")
def get_topics(session: Session = Depends(prepare_session)):
    """Return a list of topics."""
    n_aact = session.scalar(aact.get_number_of_records()) or 0
    n_pubmed = session.scalar(pubmed.get_number_of_records()) or 0
    n_civic = session.scalar(civic.get_number_of_records()) or 0
    guidelines = ggponc.get_guideline_names(session)
    valid_guideline_ids = get_supported_guidelines()
    valid_topics = {}
    ggponc_version = get_meta(session).versions["ggponc"][0]
    for k, values in guidelines.items():
        if k in valid_guideline_ids:
            values["latest_version"] = None
            values["latest_version_date"] = None
            prev_versions = get_previous_guideline_versions(
                app.state.topic_config, k, ggponc_version
            )
            if prev_versions:
                values["latest_version"] = prev_versions[0][0]
                values["latest_version_date"] = prev_versions[0][1]["date"]
            valid_topics[k] = values
    return shim_utils.prepare_topics_response(
        valid_topics=valid_topics,
        # default_topic=None,
        max_n=n_aact + n_pubmed + n_civic,
        year_max=datetime.datetime.now().year,
        year_min=1959,  # TODO: make dynamic
    )


@app.get("/meta")
def get_meta(session: Session = Depends(prepare_session)):
    """Return metadata about the API."""
    v_result = session.scalars(versions.get_versions())
    v_result_dict = {v.source: (v.version, v.import_date) for v in v_result}

    return shim_models.MetaResponse(
        versions=v_result_dict,
        umls_version=app.state.concept_parser.umls_parser.version,
    )


@app.get("/trialsearch")
def get_trials(
    topic: str | None = None,
    sample_range_min: int | None = None,
    sample_range_max: int | None = None,
    year_range_min: int | None = None,
    year_range_max: int | None = None,
    max_results: int | None = None,
    has_unknown_intervention: bool = False,
    has_known_intervention: bool = False,
    has_recommended_intervention: bool = False,
    has_not_recommended_intervention: bool = False,
    exclude_children: bool = False,
    phase: Annotated[list[int] | None, Query()] = None,
    significant_results: bool | None = None,
    results_available: bool | None = None,
    sources: Annotated[list[Literal["civic", "clinicaltrials", "pubmed"]], Query()] = [
        "civic",
        "clinicaltrials",
        "pubmed",
    ],
    strict_rct_filter: bool | None = True,
    session: Session = Depends(prepare_session),
):
    """Return a list of trials in the NGE Browser format."""
    evidence_query = EvidenceQuery(
        guideline_id=topic, sources=sources, limit=max_results
    )
    evidence_retrieved = get_evidence_by_population(evidence_query, session=session)
    evidence_filtered = shim_utils.apply_trialsearch_filters(
        evidence=evidence_retrieved,
        max_results=max_results,
        sample_range_min=sample_range_min,
        sample_range_max=sample_range_max,
        year_range_min=year_range_min,
        year_range_max=year_range_max,
        # controversial_intervention=False,
        exclude_children=exclude_children,
        phase=phase,
        significant_results=significant_results,
        results_available=results_available,
        has_unknown_intervention=has_unknown_intervention,
        has_known_intervention=has_known_intervention,
        has_recommended_intervention=has_recommended_intervention,
        has_not_recommended_intervention=has_not_recommended_intervention,
        strict_rct_filter=strict_rct_filter,
    )
    return [
        shim_utils.parse_evidence_to_trial(e, topic_id=topic) for e in evidence_filtered
    ]


@app.get("/details")
def get_details(
    topic: str | None = None,
    pm_id: str | None = None,
    nct_id: str | None = None,
    session: Session = Depends(prepare_session),
):
    """Return details (abstract, etc.) for a single trial + related trials."""
    related = []
    result = None
    nct_refs = []
    evidence_query = EvidenceQuery(guideline_id=topic)
    population_cuis = parse_population_cuis_from_query(evidence_query, session)
    if nct_id:
        nct_refs.append(nct_id)
    if pm_id:
        query = pubmed.get_trials_by_ids([pm_id])
        result = Evidence.from_pubmed_trial(
            session.scalars(query).unique().first(),
            app.state.concept_parser,
            evidence_query,
        )
        nct_refs += result.referenced_nct_ids
    if nct_refs:
        query = aact.get_trials_by_ids(nct_refs)
        nct_results = [
            Evidence.from_aact_trial(t, app.state.concept_parser, evidence_query)
            for t in session.scalars(query).unique().all()
        ]
        for r in nct_results:
            if nct_id and not result and r.nct_id == nct_id:
                result = r
            else:
                related.append(r)
        query_related = pubmed.get_trials_by_nct_ids(nct_refs)
        related += [
            Evidence.from_pubmed_trial(t, app.state.concept_parser, evidence_query)
            for t in session.scalars(query_related).unique().all()
            if t.pm_id != int(pm_id)
        ]
    _fill_evidence_metadata([result] + related, population_cuis)
    return shim_models.DetailsResponse(
        result=(
            shim_utils.parse_evidence_to_trial(result, topic, full_details=True)
            if result
            else None
        ),
        related=[shim_utils.parse_evidence_to_trial(r, topic) for r in related],
    )


def main() -> None:
    """Run the API."""
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
