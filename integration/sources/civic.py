"""A module for parsing the CIViC data into the DB."""

import logging

from civicpy import civic
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from integration.orm.civic import create_metadata
from integration.parsers.civic import CivicParser
from integration.sources import Source
from integration.umls.normalization import Normalizer

logger = logging.getLogger(__name__)


class Civic(Source):
    """A class to handle parsing the CivicDB data."""

    def __init__(self, normalizer: Normalizer, engine: Engine) -> None:
        """Create a new Civic instance."""
        super().__init__(engine)
        self.normalizer = normalizer
        self.fetched_evidence: list[civic.Evidence] = []

    def download(self) -> None:
        """Retrieve evidence from the Civic API."""
        logger.info("Downloading assertions from Civic API")
        evidence = civic.get_all_evidence(allow_cached=False)
        self.fetched_evidence = [a for a in evidence if isinstance(a, civic.Evidence)]
        logger.info("Done.")

    def parse(self, drop_existing: bool = False) -> None:
        """Parse the Civic DB data into the DB."""
        if not self.fetched_evidence:
            raise ValueError(
                "No evidence to parse. Did you forget to download?"
                "Call `download` before `parse`."
            )
        create_metadata(self.engine, drop_existing)
        cp = CivicParser(self.fetched_evidence, self.normalizer)
        evidence = cp.parse()
        logger.info("Inserting evidence into the DB")
        with Session(self.engine) as session:
            session.add_all(evidence)
            session.commit()
        self.write_version("civic", "nightly")
        logger.info("Done.")
