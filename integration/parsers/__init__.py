"""A module containing parsers for reading the different data sources' files into ORM objects."""

from abc import ABC, abstractmethod
from typing import Iterable

from integration.orm import aact, civic, ggponc, pubmed, trialstreamer


class Parser(ABC):
    """An abstract base class for parsing data into ORM objects."""

    @abstractmethod
    def parse(
        self,
    ) -> Iterable[
        aact.Trial
        | trialstreamer.Trial
        | civic.Assertion
        | ggponc.Guideline
        | pubmed.Trial
    ]:
        """Return a list of parsed ORM objects."""
        pass
