"""Module for parsing assertions from CivicDB."""

import datetime
import re
from collections import namedtuple

from civicpy import civic
from tqdm.auto import tqdm

import integration.orm.civic as orm
from integration.parsers import Parser
from integration.umls.normalization import Normalizer

civic_trial_like = namedtuple(
    "civic_trial_like", ["name", "nctId", "url"]
)  # stand-in for ClinicalTrials type


def get_pm_id_from_source_url(source_url: str) -> int | None:
    """Extract the Pubmed ID from the source url of a Civic Source."""
    pm_id = None
    matches = re.search(
        pattern=r"www.ncbi.nlm.nih.gov/pubmed/(\d{7,8})", string=source_url
    )
    if matches:
        try:
            match = matches.group(1)
            try:
                pm_id = int(match)
            except ValueError:
                pass
        except IndexError:
            pass
    return pm_id


def parse_publication_date(date_str: str) -> datetime.datetime | None:
    """Parse the publication date from a civic Source object to Python datetime."""
    parsed_date = None
    if date_str:
        if "-" not in date_str:
            parsed_date = datetime.datetime.strptime(date_str, r"%Y")
        else:
            try:
                parsed_date = datetime.datetime.strptime(date_str, r"%Y-%m-%d")
            except ValueError:
                parsed_date = datetime.datetime.strptime(date_str, r"%Y-%m")
            finally:
                pass
    return parsed_date


def parse_clinical_trial(trial: civic_trial_like) -> orm.ClinicalTrial:
    """Parse a civic ClinicalTrial object to its ORM representation."""
    return orm.ClinicalTrial(name=trial.name, nct_id=trial.nctId, url=trial.url)


def parse_source(source: civic.Source) -> orm.Source:
    """Parse a civic Source object to its ORM representation."""
    return orm.Source(
        id=source.id,
        name=source.name,
        title=source.title,
        abstract=source.abstract,
        citation=source.citation,
        citation_id=source.citation_id,
        source_type=source.source_type,
        asco_abstract_id=source.asco_abstract_id,
        author_string=source.author_string,
        journal=source.full_journal_title,
        date_publication=parse_publication_date(source.publication_date),
        pmc_id=source.pmc_id,
        pm_id=get_pm_id_from_source_url(source.source_url),
        source_url=source.source_url,
        clinical_trials=[parse_clinical_trial(t) for t in source.clinical_trials],
        flags=orm.Flags(),
    )

NUM_RETRIES = 10
def _get_assertions(evidence: civic.Evidence):
    """ For some reason, this works not always at the first attempt """
    for i in range(0, NUM_RETRIES):
        try:
            return evidence.assertions
        except AttributeError as ex:
            pass
    return []

def parse_evidence(
    evidence: civic.Evidence,
    normalizer: Normalizer,
    parsed_sources: dict[int, orm.Source],
) -> orm.Evidence:
    """Parse a civic Evidence object to its ORM representation."""
    has_attached_disease = isinstance(evidence.disease, civic.Disease)
    if evidence.source.id in parsed_sources.keys():
        source = parsed_sources[evidence.source.id]
    else:
        source = parse_source(evidence.source)
        parsed_sources[evidence.source.id] = source
    return orm.Evidence(
        description=evidence.description,
        name=evidence.name,
        direction=evidence.evidence_direction,
        level=evidence.evidence_level,
        type_=evidence.evidence_type,
        rating=evidence.rating,
        significance=evidence.significance,
        status=evidence.status,
        disease_name=evidence.disease.name if has_attached_disease else None,
        disease_display_name=evidence.disease.display_name
        if has_attached_disease
        else None,
        disease_do_id=int(evidence.disease.doid)
        if has_attached_disease and evidence.disease.doid
        else None,
        disease_do_id_url=evidence.disease.disease_url
        if has_attached_disease
        else None,
        disease_cui=normalizer.do_id_to_cui(evidence.disease.doid)
        if has_attached_disease
        else None,
        source=source,
        molecular_profile_id=int(evidence.molecular_profile_id),
        phenotypes=[parse_phenotype(p, normalizer) for p in evidence.phenotypes],
        therapies=[parse_therapy(t, normalizer) for t in evidence.therapies],
        assertions=[parse_assertion(a) for a in _get_assertions(evidence)],
    )


def parse_therapy(therapy: civic.Therapy, normalizer: Normalizer) -> orm.Therapy:
    """Parse a civic Therapy object to its ORM representation."""
    return orm.Therapy(
        name=therapy.name,
        nci_id=therapy.ncit_id,
        therapy_url=therapy.therapy_url,
        cui=normalizer.nci_to_cui(therapy.ncit_id) if therapy.ncit_id else None,
    )


def parse_phenotype(
    phenotype: civic.Phenotype, normalizer: Normalizer
) -> orm.Phenotype:
    """Parse a civic Phenotype object to its ORM representation."""
    return orm.Phenotype(
        name=phenotype.name,
        hpo_id=phenotype.hpo_id,
        url=phenotype.url,
        cui=normalizer.hpo_to_cui(phenotype.hpo_id),
    )


def parse_assertion(assertion: civic.Assertion) -> orm.Assertion:
    """Parse a civic Assertion object to its ORM representation."""
    return orm.Assertion(
        name=assertion.name,
        assertion_type=assertion.assertion_type,
        assertion_direction=assertion.assertion_direction,
        molecular_profile_id=int(assertion.molecular_profile_id),
        description=assertion.description,
        summary=assertion.summary,
        status=assertion.status,
        variant_origin=assertion.variant_origin,
        significance=assertion.significance,
        nccn_guideline_version=assertion.nccn_guideline_version,
        nccn_guideline_name=assertion.nccn_guideline.get("name")
        if isinstance(assertion.nccn_guideline, dict)
        else None,
        fda_regulatory_approval=assertion.fda_regulatory_approval,
        fda_companion_test=assertion.fda_companion_test,
        amp_level=assertion.amp_level,
    )


class CivicParser(Parser):
    """A class for parsing Civic API data as ORM objects."""

    def __init__(self, evidence: list[civic.Evidence], normalizer: Normalizer) -> None:
        """Create a new EvidenceParser instance."""
        self.evidence: list[civic.Evidence] = evidence
        self.normalizer: Normalizer = normalizer

    def parse(self) -> list[orm.Evidence]:
        """Parse civic API assertions to ORM ones."""
        parsed_sources: dict[int, orm.Source] = {}
        return [
            parse_evidence(e, normalizer=self.normalizer, parsed_sources=parsed_sources)
            for e in tqdm(self.evidence, desc="Parsing evidence")
        ]
