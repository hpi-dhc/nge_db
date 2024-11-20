"""A module containing request/response models for the API."""

import datetime
import re
from pathlib import Path
from typing import Literal, Type, TypeVar

import pydantic
from cachetools import LFUCache
from pydantic import BaseModel, Field
from shelved_cache import PersistentCache

from integration.orm import aact, civic, pubmed
from integration.umls.parser import MetaThesaurusParser
import json

T = TypeVar("T", bound="Evidence")

PHASE_PATTERN = re.compile(r"([Pp]hase\s+([I|i][V|v]|[Ii]{1,3}|[1234]))")


def extract_phases(
    strings_containing_phase: list[str], phase_pattern: re.Pattern = PHASE_PATTERN
) -> list[int]:
    """Extract the highest phase string and phase integer from a list of phase strings."""
    if not strings_containing_phase:
        return []
    for p in strings_containing_phase:
        if not p:
            continue
        phases = [
            (match.group(1), parse_phase_to_int(match.group(2)))
            for match in phase_pattern.finditer(p)
        ]
        if phases:
            return sorted(list(set(p[1] for p in phases)))
    return []


# def extract_highest_phase(
#     strings_containing_phase: list[str], phase_pattern: re.Pattern = PHASE_PATTERN
# ) -> tuple[str, int] | tuple[None, None]:
#     """Extract the highest phase string and phase integer from a list of phase strings."""
#     phases = [
#         (match.group(1), parse_phase_to_int(match.group(2)))
#         for phase_str in strings_containing_phase
#         for match in phase_pattern.finditer(phase_str)
#     ]
#     if phases:
#         return max(phases, key=lambda t: t[1])  # type: ignore
#     return (None, None)


def is_protocol(trial):
    if re.search(r"([pP]rotocol|[dD]esign)", trial.title):
        return True
    publication_types = [p.publication_type for p in trial.publication_types]
    return any(["trial protocol" in t.lower() for t in publication_types])


def is_review(trial):
    publication_types = [p.publication_type for p in trial.publication_types]
    for t in publication_types:
        for term in ["review", "meta-analysis"]:
            if term in t.lower():
                return True
    return False


def parse_phase_to_int(phase_numeral_string: str) -> int | None:
    """Parse the phase information from the string and return it as an integer."""
    roman_numerals = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
    number = int(roman_numerals.get(phase_numeral_string.lower(), phase_numeral_string))
    return number


class ConceptsQuery(BaseModel):
    """A request model for concepts."""

    source: Literal["clinicaltrials", "pubmed"]
    ids: list[int | str]
    kind: Literal["population", "interventions"]


class EvidenceQuery(BaseModel):
    """A request model for populations."""

    sources: list[Literal["civic", "clinicaltrials", "pubmed"]] = Field(
        description="Sources of clinical evidence. If an empty list, will query all.",
        default=[],
    )
    guideline_id: str | None = Field(
        description="Guideline ID to search for. If this is None, all guidelines are searched.",
        title="GGPONC ID",
        default=None,
    )
    cuis_population: list[str] | None = Field(
        description="Additional Population CUIs to search for.",
        title="Population CUIs",
        default=[],
    )
    cuis_intervention: list[str] | None = Field(
        description="Additional Intervention CUIs to search for.",
        title="Intervention CUIs",
        default=[],
    )
    intervention_names: list[str] | None = Field(
        description="Additional Intervention names to search for.",
        title="Intervention Names",
        default=[],
    )
    filter_stns_population: list[str] | None = Field(
        description="UMLS Semantic Type tree numbers for filtering population concepts",
        default=None,
    )
    filter_stns_interventions: list[str] | None = Field(
        description="UMLS Semantic Type tree numbers for filtering intervention concepts",
        default=None,
    )
    ignore_cuis_interventions: list[str] | None = Field(
        description="UMLS CUIs for interventions to ignore",
        default=None,
    )
    filter_stns_interventions_unknown: list[str] | None = Field(
        description="""UMLS Semantic Type tree numbers for filtering intervention concepts
        that are not contained in the CPG(s)""",
        default=None,
    )
    filter_stns_interventions_known: list[str] | None = Field(
        description="""UMLS Semantic Type tree numbers for filtering intervention concepts that
        are contained in the CPG(s).
        This is used to filter out known interventions without effect.""",
        default=None,
    )
    filter_cuis_pediatric_population: list[str] | None = Field(
        description="CUIs that define a evidence with pediatric populations",
        default=None,
    )
    filter_reviews: bool | None = Field(
        description="Filter out results that look like reviews",
        default=True,
    )
    filter_protocols: bool | None = Field(
        description="Filter out results that look like protocols",
        default=True,
    )
    limit : int | None = Field(
        description="Limit the number of results",
        default=None,
    )


class SemanticType(BaseModel):
    """A class that holds semantic type information."""

    tui: str
    tree_number: str
    name: str

    def has_matching_tree_number(self, stns: list[str]) -> bool:
        """Return True if the tree number matches at least one of the given STNs."""
        return self.tree_number.startswith(tuple(stns))


class UmlsConcept(BaseModel):
    """A class that represents CUIs that occur in different CPGs."""

    cui: str
    text: str | None = None
    text_umls: str | None = None
    is_known: bool | None = None
    is_recommended: bool | None = None
    is_hidden_by_filter: bool = False
    matching_cpgs: list[str] = Field(
        description="CPGs in which this UMLS concept occurs.", default=[]
    )
    matching_cpgs_recommended: list[str] = Field(
        description="CPGs in which this UMLS concept occurs inside recommendations.",
        default=[],
    )
    semantic_types: list[SemanticType]

    def __hash__(self):
        """Return the hash of the concept's identifier."""
        return hash(self.cui)

    def __eq__(self, other):
        """Compare two instances of mapped concepts."""
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.cui == other.cui

    def has_matching_semantic_type(self, stns: list[str] | None) -> bool:
        """Return True if the concept matches at least one of the given STNs."""
        if stns is None or len(stns) == 0:
            return True
        return any([st.has_matching_tree_number(stns) for st in self.semantic_types])

    def occurs_in_guideline(
        self, guideline_id: str, in_recommendations: bool = False
    ) -> bool | None:
        """Return True if the concept occurs in the given guideline."""
        if guideline_id is None:
            return None
        if in_recommendations:
            return guideline_id in self.matching_cpgs_recommended
        return guideline_id in self.matching_cpgs


class UmlsConceptParser:
    """A class that parses UMLS concepts and maps them to CPGs."""

    def __init__(
        self,
        umls_parser: MetaThesaurusParser,
        cache_dir: str | Path,
        cui_to_cpg_map_population: dict[str, set[str]],
        cui_to_cpg_map_intervention: dict[str, set[str]],
        cui_to_cpg_map_intervention_recommended: dict[str, set[str]] = {},
    ) -> None:
        """Initialize the UmlsConceptParser."""
        self.umls_parser = umls_parser
        self.cui_to_cpg_map_population = cui_to_cpg_map_population
        self.cui_to_cpg_map_intervention = cui_to_cpg_map_intervention
        self.cui_to_cpg_map_intervention_recommended = (
            cui_to_cpg_map_intervention_recommended
        )
        self.cache_dir = Path(cache_dir)
        self.cache_path = self.cache_dir / "persistent_umls_concepts.cache"
        self._create_cache_dir()
        self.cache = PersistentCache(LFUCache, str(self.cache_path), maxsize=200000)

    def _create_cache_dir(self):
        """Create the cache directory if it does not exist."""
        if not self.cache_dir.exists():
            self.cache_dir.mkdir()

    def _generate_cache_key(self, cui: str, kind: str, guideline_id: str | None) -> str:
        """Generate a unique cache key."""
        if guideline_id is None:
            return f"{cui}-{kind}"
        return f"{cui}-{kind}-{guideline_id}"

    def _parse_concept(
        self,
        cui: str,
        text: str | None,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ) -> UmlsConcept:
        """Parse a UMLS concept and return a UmlsConcept instance."""
        cache_key = self._generate_cache_key(cui, kind, query.guideline_id)

        lookup_table = self._get_lookup_table(kind)
        if cache_key not in lookup_table:
            concept = self._create_new_concept(cui, text, kind, query)
            lookup_table[cache_key] = concept
        return lookup_table[cache_key]

    def _get_lookup_table(self, kind: Literal["intervention", "population"]):
        """Return the lookup table for the given kind."""
        if kind == "intervention":
            return self.cache.setdefault("intervention", {})
        else:
            return self.cache.setdefault("population", {})

    def _create_new_concept(
        self,
        cui: str,
        text: str | None,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ):
        """Create a new UmlsConcept instance."""
        concept = UmlsConcept(
            cui=cui,
            text=text,
            text_umls=self.umls_parser.get_umls_text(cui),
            matching_cpgs=list(self._get_cui_to_cpg_map(kind).get(cui, set())),
            matching_cpgs_recommended=list(
                self._get_cui_to_cpg_map(kind, recommended_only=True).get(cui, set())
            ),
            semantic_types=[
                SemanticType(tui=t["TUI"], tree_number=t["STN"], name=t["STY"])
                for t in self.umls_parser.get_semantic_types(cui)
            ],
        )
        self._set_concept_flags(concept, kind, query)
        return concept

    def _get_cui_to_cpg_map(
        self,
        kind: Literal["intervention", "population"],
        recommended_only: bool = False,
    ):
        """Return the CUI to CPG map for the given kind."""
        cui_to_cpg_map = self.cui_to_cpg_map_population
        if kind == "intervention":
            cui_to_cpg_map = (
                self.cui_to_cpg_map_intervention_recommended
                if recommended_only
                else self.cui_to_cpg_map_intervention
            )
        return cui_to_cpg_map

    def _set_concept_flags(
        self,
        concept: UmlsConcept,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ) -> None:
        self._set_flag_hidden_by_filter(concept, kind, query)
        self._set_flag_known(concept, kind, query)
        self._set_flag_recommended(concept, kind, query)

    def _set_flag_known(
        self,
        concept: UmlsConcept,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ) -> None:
        if kind != "intervention" or query.guideline_id is None:
            return
        concept.is_known = concept.occurs_in_guideline(query.guideline_id)

    def _set_flag_recommended(
        self,
        concept: UmlsConcept,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ) -> None:
        if kind != "intervention" or query.guideline_id is None:
            return
        concept.is_recommended = concept.occurs_in_guideline(
            query.guideline_id, in_recommendations=True
        )

    def _set_flag_hidden_by_filter(
        self,
        concept: UmlsConcept,
        kind: Literal["intervention", "population"],
        query: EvidenceQuery,
    ) -> None:
        if kind == "intervention" and query.filter_stns_interventions:
            concept.is_hidden_by_filter = not concept.has_matching_semantic_type(
                query.filter_stns_interventions
            ) or (concept.cui in query.ignore_cuis_interventions)
        if kind == "population" and query.filter_stns_population:
            concept.is_hidden_by_filter = not concept.has_matching_semantic_type(
                query.filter_stns_population
            )

    def parse_intervention(
        self, cui: str, text: str | None, query: EvidenceQuery
    ) -> UmlsConcept:
        """Parse an intervention UMLS concept and return a UmlsConcept instance."""
        return self._parse_concept(cui, text, "intervention", query)

    def parse_population(
        self, cui: str, text: str | None, query: EvidenceQuery
    ) -> UmlsConcept:
        """Parse a population UMLS concept and return a UmlsConcept instance."""
        return self._parse_concept(cui, text, "population", query)


class Evidence(BaseModel):
    """A response model for evidence retrieved from the database."""

    query: EvidenceQuery

    title: str | None = Field(description="Title", default=None)
    abstract: str | None = Field(description="Abstract", default=None)
    publication_date: datetime.date | None = Field(
        description="Publication date of the document", default=None
    )
    source: Literal["Civic", "ClinicalTrials", "Pubmed"] = Field(description="Source")
    pm_id: int | None = Field(description="Pubmed ID", title="PMID", default=None)
    pmc_id: str | None = Field(
        description="Pubmed Central (PMC) ID", title="PMCID", default=None
    )
    nct_id: str | None = Field(
        description="ClinicalTrials.gov Identifier (NCT ID)",
        title="NCTID",
        default=None,
    )
    referenced_nct_ids: list[str] = Field(description="Referenced NCT IDs", default=[])
    referenced_pm_ids: list[int] = Field(
        description="Referenced Pubmed IDs", default=[]
    )
    phase: str | None = Field(description="Study phase", default=None)
    phase_int: int | None = Field(
        description="Study phase parsed as as integer", default=None
    )
    phases_all: list[int] = Field(description="All potential study phases", default=[])
    sample_size: int | None = Field(description="Sample Size", default=None)
    eligibility: list[str] = Field(description="Eligibility", default=[])
    outcomes: list[str] = Field(description="Outcomes", default=[])

    has_significant_finding: bool | None = Field(
        description="""True if this document has been classified as having a significant finding.
        False if not. None if no abstract or results are available.""",
        default=None,
    )

    concepts_population: list[UmlsConcept] = Field(
        description="Population UMLS concepts mapped to CPGs", default=[]
    )
    concepts_matching_population: list[UmlsConcept] = Field(
        description="Population UMLS which overlap with the query", default=[]
    )
    concepts_intervention: list[UmlsConcept] = Field(
        description="Intervention UMLS concepts mapped to CPGs", default=[]
    )
    citing_guidelines: list[str] = Field(
        description="Guidelines citing this piece of evidence", default=[]
    )

    # source specific fields

    # Pubmed columns
    authors: list[dict[str, str]] = Field(
        description="Authors of the publication", default=[]
    )
    journal: str | None = Field(description="Journal", default=None)
    publication_types: list[str] = Field(
        description="Pubmed publication type tags", default=[]
    )
    is_rct_pt: bool | None = Field(
        description="True if the publication types contain the tag 'Randomized Controlled Trial'",
        default=None,
    )
    is_rct_mt: bool | None = Field(
        description="True if the MeSH terms contain 'Randomized Controlled Trial'",
        default=None,
    )
    is_rct: bool | None = Field(
        description="True if either publication types or MeSH terms contain the RCT tag",
        default=None,
    )
    is_review: bool | None = Field(
        description="True if the publication looks like a review",
        default=None,
    )
    is_protocol: bool | None = Field(
        description="True if the publication looks like a trial protocol'",
        default=None,
    )

    # Civic
    evidence_type: str | None = Field(description="CIViC evidence type", default=None)
    evidence_level: str | None = Field(description="CIViC evidence level", default=None)
    evidence_rating: int | None = Field(
        description="CIViC evidence rating", default=None
    )
    evidence_direction: str | None = Field(
        description="CIViC evidence direction", default=None
    )
    evidence_significance: str | None = Field(
        description="CIViC evidence significance", default=None
    )
    evidence_status: str | None = Field(
        description="CIViC evidence status", default=None
    )

    # ClinicalTrials
    number_of_groups: int | None = Field(
        description="ClinicalTrials number of groups for interventional studies, \
        it is NULL when the study is not an interventional study",
        default=None,
    )
    number_of_arms: int | None = Field(
        description="ClinicalTrials number of arms for interventional studies, \
        it is NULL when the study is not an interventional study",
        default=None,
    )
    study_type: str | None = Field(
        description="ClinicalTrials study type", default=None
    )
    overall_status: str | None = Field(
        description="ClinicalTrials overall status", default=None
    )
    results_available: bool | None = Field(
        description="ClinicalTrials results attached", default=None
    )
    date_last_update: datetime.date | None = Field(
        description="ClinicalTrials results date of last update", default=None
    )
    date_start: datetime.date | None = Field(
        description="ClinicalTrials start date", default=None
    )
    enrollment_type: str | None = Field(
        description="ClinicalTrials enrollment type", default=None
    )
    why_stopped: str | None = Field(
        description="ClinicalTrials reason for stopping", default=None
    )
    referenced_pm_ids_results: list[int] = Field(
        description="Pubmed IDs listed as publications of trial results", default=[]
    )

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_pediatric_population(self) -> bool:
        """Return True if one of the population concepts contains a pediatric CUI."""
        if self.query.filter_cuis_pediatric_population is not None:
            return any(
                [
                    c.cui in self.query.filter_cuis_pediatric_population
                    for c in self.concepts_population
                ]
            )
        return False

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_intervention_filtered(self) -> list[UmlsConcept]:
        """Return a list of intervention concepts that are hidden by the STN filter."""
        return [c for c in self.concepts_intervention if not c.is_hidden_by_filter]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_population_filtered(self) -> list[UmlsConcept]:
        """Return a list of population concepts that are hidden by the STN filter."""
        return [c for c in self.concepts_population if not c.is_hidden_by_filter]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_intervention_known(self) -> list[UmlsConcept]:
        """Return a list of filtered intervention concepts that are contained in the CPG(s)."""
        return [
            c
            for c in self.concepts_intervention_filtered
            if (
                c.has_matching_semantic_type(self.query.filter_stns_interventions_known)
                and c.is_known is True
            )
        ]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_intervention_recommended(self) -> list[UmlsConcept]:
        """Return a list of filtered intervention concepts that are contained in the CPG(s)."""
        return [
            c
            for c in self.concepts_intervention_filtered
            if (
                c.has_matching_semantic_type(self.query.filter_stns_interventions_known)
                and c.is_recommended is True
            )
        ]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_intervention_unknown(self) -> list[UmlsConcept]:
        """Return a list of filtered intervention concepts that are not contained in the CPG(s)."""
        return [
            c
            for c in self.concepts_intervention_filtered
            if (
                c.has_matching_semantic_type(
                    self.query.filter_stns_interventions_unknown
                )
                and c.is_known is False
            )
        ]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def concepts_intervention_not_recommended(self) -> list[UmlsConcept]:
        """Return a list of filtered intervention concepts that are not contained in the CPG(s)."""
        return [
            c
            for c in self.concepts_intervention_filtered
            if (
                c.has_matching_semantic_type(
                    self.query.filter_stns_interventions_unknown
                )
                and c.is_recommended is False
            )
        ]

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_unknown_intervention(self) -> bool:
        """Return True if there is at least one unknown intervention."""
        return len(self.concepts_intervention_unknown) > 0

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_not_recommended_intervention(self) -> bool:
        """Return True if there is at least one unknown intervention."""
        return len(self.concepts_intervention_not_recommended) > 0

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_known_intervention(self) -> bool:
        """Return True if there is at least one known intervention."""
        return len(self.concepts_intervention_known) > 0

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_recommended_intervention(self) -> bool:
        """Return True if there is at least one known intervention."""
        return len(self.concepts_intervention_recommended) > 0

    @pydantic.computed_field()  # type: ignore[misc]
    @property
    def has_known_intervention_not_significant(self) -> bool:
        """Return True if there is at least one known intervention and no significant effect."""
        return (
            len(self.concepts_intervention_known) > 0
            and self.has_significant_finding is False
        )

    @classmethod
    def from_civic_evidence(
        cls: Type[T],
        evidence: civic.Evidence,
        concept_parser: UmlsConceptParser,
        query: EvidenceQuery,
    ) -> T:
        """Parse a civic Source ORM instance into an Evidence response model."""
        concepts_population = set()
        if evidence.disease_cui:
            concepts_population.add(
                concept_parser.parse_population(
                    cui=evidence.disease_cui,
                    text=evidence.disease_display_name,
                    query=query,
                )
            )
        concepts_population.update(
            concept_parser.parse_population(
                cui=phenotype.cui, text=phenotype.name, query=query
            )
            for phenotype in evidence.phenotypes
            if phenotype.cui
        )

        concepts_intervention = {
            concept_parser.parse_intervention(
                cui=therapy.cui, text=therapy.name, query=query
            )
            for therapy in evidence.therapies
            if therapy.cui
        }

        # phase, phase_int = extract_highest_phase(
        #    [evidence.source.title if evidence.source.title else ""]
        #    + [evidence.source.abstract if evidence.source.abstract else ""]
        # )
        phases_all = extract_phases(
            [evidence.source.title if evidence.source.title else ""]
            + [evidence.source.abstract if evidence.source.abstract else ""]
        )

        return cls(
            query=query,
            title=evidence.source.title,
            abstract=evidence.source.abstract,
            publication_date=(
                evidence.source.date_publication.date()
                if evidence.source.date_publication
                else None
            ),
            source="Civic",
            pm_id=evidence.source.pm_id,
            pmc_id=evidence.source.pmc_id,
            referenced_nct_ids=list(
                {
                    trial.nct_id
                    for trial in evidence.source.clinical_trials
                    if trial.nct_id
                }
            ),
            has_significant_finding=evidence.source.flags.has_significant_finding,
            concepts_population=list(concepts_population),
            concepts_intervention=list(concepts_intervention),
            # phase=phase,
            phase_int=max(phases_all) if phases_all else None,
            phases_all=phases_all,
            # civic specific
            evidence_type=evidence.type_,
            evidence_level=evidence.level,
            evidence_rating=evidence.rating,
            evidence_direction=evidence.direction,
            evidence_significance=evidence.significance,
            evidence_status=evidence.status,
        )

    @classmethod
    def from_pubmed_trial(
        cls: Type[T],
        trial: pubmed.Trial,
        concept_parser: UmlsConceptParser,
        query: EvidenceQuery,
    ) -> T:
        """Parse a Pubmed Trial ORM instance into an Evidence response model."""
        concepts_population = set()
        if trial.mesh_terms:
            concepts_population = {
                concept_parser.parse_population(
                    cui=mesh_term.cui,
                    text=mesh_term.mesh_term,
                    query=query,
                )
                for mesh_term in trial.mesh_terms
                if mesh_term.cui
            }

        if trial.umls_population:
            concepts_population.update(
                concept_parser.parse_population(
                    cui=population.cui,
                    text=population.mention,
                    query=query,
                )
                for population in trial.umls_population
                if population.cui
            )

        concepts_intervention = set()
        if trial.umls_interventions:
            concepts_intervention = {
                concept_parser.parse_intervention(
                    cui=intervention.cui,
                    text=intervention.mention,
                    query=query,
                )
                for intervention in trial.umls_interventions
                if intervention.cui
            }

        publication_types: list[str] = []
        mesh_terms: list[str] = []
        is_rct_pt = None
        is_rct_mt = None
        if trial.publication_types:
            publication_types = [p.publication_type for p in trial.publication_types]
            is_rct_pt = any(
                ["randomized controlled trial" in t.lower() for t in publication_types]
            )
        if trial.mesh_terms:
            mesh_terms = [m.mesh_term for m in trial.mesh_terms]
            is_rct_mt = any(
                ["randomized controlled trial" in t.lower() for t in mesh_terms]
            )
        # phase, phase_int = extract_highest_phase(
        #    publication_types
        #    + mesh_terms
        #    + [trial.title if trial.title else ""]
        #    + [trial.abstract if trial.abstract else ""]
        # )

        phases_all = extract_phases(
            [trial.title if trial.title else ""]
            + publication_types
            + mesh_terms
            + [trial.abstract if trial.abstract else ""]
        )

        return cls(
            query=query,
            title=trial.title,
            authors=json.loads(trial.authors),
            journal=trial.journal,
            abstract=trial.abstract,
            publication_date=trial.publication_date,
            source="Pubmed",
            pm_id=trial.pm_id,
            referenced_nct_ids=(
                list(
                    {
                        reference.nct_id
                        for reference in trial.references
                        if reference.nct_id
                    }
                )
                if trial.references
                else []
            ),
            sample_size=trial.num_randomized,
            outcomes=[i.outcome for i in trial.outcomes] if trial.outcomes else [],
            has_significant_finding=trial.flags.has_significant_finding,
            concepts_population=list(concepts_population),
            concepts_intervention=list(concepts_intervention),
            publication_types=publication_types,
            is_rct_pt=is_rct_pt,
            is_rct_mt=is_rct_mt,
            is_review=is_review(trial),
            is_protocol=is_protocol(trial),
            is_rct=(
                is_rct_pt or is_rct_mt
                if (is_rct_mt is not None or is_rct_pt is not None)
                else None
            ),
            # phase=phase,
            phase_int=max(phases_all) if phases_all else None,
            phases_all=phases_all,
        )

    @classmethod
    def from_aact_trial(
        cls: Type[T],
        trial: aact.Trial,
        concept_parser: UmlsConceptParser,
        query: EvidenceQuery,
    ) -> T:
        """Parse a aact Trial ORM instance into an Evidence response model."""
        concepts_population = {
            concept_parser.parse_population(
                cui=population.cui,
                text=population.mesh_term,
                query=query,
            )
            for population in trial.mesh_conditions
            if population.cui
        }
        concepts_intervention = {
            concept_parser.parse_intervention(
                cui=intervention.cui,
                text=intervention.mesh_term,
                query=query,
            )
            for intervention in trial.mesh_interventions
            if intervention.cui
        }

        phase_items = ([trial.phase] if trial.phase else []) + [
            trial.title_official,
            trial.summary,
        ]

        # phase_int = extract_highest_phase(phase_items)[1]
        phases_all = extract_phases(phase_items)

        return cls(
            query=query,
            title=trial.title_brief,
            abstract=trial.summary if trial.summary else trial.description,
            publication_date=trial.date_results_first_posted,
            source="ClinicalTrials",
            nct_id=trial.nct_id,
            referenced_pm_ids=list({r.pm_id for r in trial.references}),
            referenced_pm_ids_results=list(
                {r.pm_id for r in trial.references if r.reference_type == "result"}
            ),
            sample_size=trial.enrollment,
            eligibility=(
                [p.criteria for p in trial.eligibilities if p.criteria]
                if trial.eligibilities
                else []
            ),
            outcomes=(
                [i.title for i in trial.outcomes if i.title] if trial.outcomes else []
            ),
            has_significant_finding=trial.flags.has_significant_finding,
            concepts_population=list(concepts_population),
            concepts_intervention=list(concepts_intervention),
            # clinicaltrials specific
            phase=trial.phase,
            phase_int=max(phases_all) if phases_all else None,
            phases_all=phases_all,
            results_available=(
                any([len(outcome.analyses) > 0 for outcome in trial.outcomes])
                if trial.outcomes
                else False
            ),
            date_last_update=trial.date_last_update,
            date_start=trial.date_start,
            study_type=trial.study_type,
            overall_status=trial.overall_status,
            enrollment_type=trial.enrollment_type,
            why_stopped=trial.why_stopped,
            number_of_groups=trial.number_of_groups,
            number_of_arms=trial.number_of_arms,
        )
