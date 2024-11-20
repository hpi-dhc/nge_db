"""Pydantic models to match Florian's NGE API responses."""

import datetime

from pydantic import BaseModel


class Topic(BaseModel):
    """Guideline topic."""

    topic_id: str
    topic_de: str
    topic_en: str
    version: str | None
    version_date: datetime.datetime | None


class TopicsResponse(BaseModel):
    """Response for the /topics endpoint."""

    # default_topic: str
    max_n: int
    topics: list[Topic]
    year_max: int
    year_min: int


class MetaResponse(BaseModel):
    """Response for the /meta endpoint."""

    versions: dict[str, tuple[str, datetime.datetime]]
    umls_version: str


class Intervention(BaseModel):
    """Intervention in a trial."""

    known_intervention: bool | None
    recommended_intervention: bool | None
    text: str | None
    umls_term: str | None
    cui: str | None

class Population(BaseModel):
    """Population in a trial."""

    text: str | None
    umls_term: str | None
    cui: str | None

class Trial(BaseModel):
    """A trial."""

    pmid: int | None
    nct_id: str | None
    authors: list[dict[str, str]] | None
    journal: str | None
    abstract: str | None
    publication_date: datetime.datetime | None
    start_date: datetime.datetime | None
    ti: str | None
    topic_id: str | None
    has_unknown_intervention: bool | None
    has_known_intervention: bool | None
    has_not_recommended_intervention: bool | None
    has_recommended_intervention: bool | None
    populations: list[Population]
    phases: list[int]
    result_available: bool | None
    interventions: list[Intervention]
    # outcomes: list[str]
    source: str | None
    citing_guidelines: list[str]


class DetailsResponse(BaseModel):
    """Details response for the /details endpoint."""

    result: Trial | None
    related: list[Trial] | None


class TimelineResponse(BaseModel):
    """Response for the /timeline endpoint."""

    grouped_trials: list[tuple[str, list[Trial]]] | None
    image_url: str | None


class InterventionItem(BaseModel):
    """Response for the /interventions endpoint."""

    cui: str | None
    umls_term: str | None
    guideline_ids: list[str] | None
