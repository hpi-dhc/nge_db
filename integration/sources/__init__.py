"""A module for keeping track of the different data sources."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pooch
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from datetime import datetime
from integration.orm.versions import Version

logger = logging.getLogger(__name__)


class Source(ABC):
    """An abstract base class for different data sources."""

    engine: Engine

    def __init__(self, engine: Engine):
        """Create a new Source instance."""
        self.engine = engine

    @abstractmethod
    def parse(self, drop_existing: bool = False) -> None:
        """Parse the data and insert it into the DB."""
        pass

    def write_version(self, source : str, version : str, import_date : datetime = datetime.now()):
        """Write the version information to the DB."""
        with Session(self.engine) as session:
            version = Version(source=source, version=version, import_date=import_date)
            session.merge(version)
            session.commit()


class Download(Source):
    """An abstract base class for data sources involving a download."""

    url: str
    batch_size: int
    registry: str
    downloaded_files: list[Path] = []
    download_manager: pooch.Pooch
    cache_dir: Path
    lookup_url: str

    def __init__(
        self,
        url: str,
        batch_size: int | str,
        registry: str,
        cache_dir: str | Path,
        lookup_url: str,
        engine: Engine,
    ) -> None:
        """Create a new Download instance."""
        super().__init__(engine=engine)
        self.url = url
        self.batch_size = int(batch_size)
        self.registry = registry
        self.cache_dir = Path(cache_dir)
        self.lookup_url = lookup_url
        self.download_manager = pooch.create(
            path=self.cache_dir,
            base_url=self.url,
        )
        self.download_manager.load_registry(self.registry)

    @abstractmethod
    def download(self) -> None:
        """Download the data."""
        pass
