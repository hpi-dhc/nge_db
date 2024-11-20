"""A module for parsing the AACT database."""

import logging
from pathlib import Path
from typing import Tuple

import pooch
import requests
from bs4 import BeautifulSoup
from pooch import Unzip
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tqdm.auto import tqdm

from integration.orm.aact import Trial, create_metadata
from integration.parsers.aact import AACT_REQUIRED_FILES, AactParser
from integration.sources import Download
from integration.umls.normalization import Normalizer

logger = logging.getLogger(__name__)


class Aact(Download):
    """A class to handle parsing the AACT data."""

    def __init__(
        self,
        url: str,
        batch_size: int | str,
        registry: str,
        lookup_url: str,
        cache_dir: str,
        normalizer: Normalizer,
        engine: Engine,
    ) -> None:
        """Initialize a AACT data source instance."""
        super().__init__(url, batch_size, registry, cache_dir, lookup_url, engine)
        self.normalizer = normalizer
        self._update_registry()

    def _remove_annoying_mac_os_files(self) -> None:
        annoying_files = self.download_manager.path.glob(".DS_Store*")
        for f in annoying_files:
            if f.is_dir():
                f.rmdir()
            elif f.is_file():
                f.unlink()

    def download(self) -> None:
        """Download the flat file representation of the AACT database."""
        downloaded_file_paths = self.download_manager.fetch(
                self.newest_dump_name,
                progressbar=True,
                processor=Unzip(members=AACT_REQUIRED_FILES.values()),
            )
        self._remove_annoying_mac_os_files()
        pooch.make_registry(self.download_manager.path, self.registry, recursive=False)
        self.downloaded_files = [Path(fname) for fname in downloaded_file_paths]
        logging.info(f"Download is cached at {Path(downloaded_file_paths[0]).parent}")

    def _get_newest_monthly_dump_name(self) -> Tuple[str, str]:
        """Parse the name of the newest monthly DB dump file."""
        logging.info(f"Parsing filename of newest monthly dump from {self.lookup_url}")
        newest_dump_name = ""
        newest_dump_link = ""
        response = requests.get(self.lookup_url)
        soup = BeautifulSoup(response.text, "html.parser")
        if heading := soup.find(
            "h4", string="Monthly Archive of Static Copies"  # type: ignore
        ):
            if selector := heading.find_next_siblings("select")[0]:
                if options := selector.children:  # type: ignore
                    for option in options:
                        if option.name == "option" and option.has_attr("value"):
                            newest_dump_link = option.get("value")
                            newest_dump_name = option.text.strip()[:19]
                            break
        return newest_dump_name, newest_dump_link

    def _update_registry(self) -> None:
        """Check the AACT page for new incremental updates and add them to the registry."""
        newest_dump_name, newest_dump_link = self._get_newest_monthly_dump_name()
        self.newest_dump_name = newest_dump_name
        if newest_dump_name not in self.download_manager.registry.keys():
            logger.info(f"New file {newest_dump_name} found on AACT, updating registry")
            self.download_manager.urls[newest_dump_name] = newest_dump_link
            self.download_manager.registry = {newest_dump_name: None}

    def _commit_batch(self, batch: list[Trial]) -> None:
        """Commit a batch of assembled trials to the DB."""
        with Session(self.engine) as session:
            session.add_all(batch)
            session.commit()

    def _parse_date(self, dump_name : str):
        date = dump_name.split('_')[0]
        return 'aact_' + date[0:4] + '_' + date[4:6] + '_' + date[6:8]

    def parse(self, drop_existing: bool = False) -> None:
        """Parse the downloaded files into the database."""
        version = self._parse_date(self.newest_dump_name)
        create_metadata(self.engine, drop_existing)
        parser = AactParser(
            self.downloaded_files,
            normalizer=self.normalizer,
        )
        trials = parser.parse()
        batch = []
        batch_id = 1
        for i, trial in tqdm(
            enumerate(trials),
            desc="Parsing trials into the DB",
            total=parser.n_trials,
        ):
            batch.append(trial)
            if (i > 0 and i % self.batch_size == 0) or (i == parser.n_trials - 1):
                tqdm.write(f"Writing batch {batch_id} into DB")
                self._commit_batch(batch)
                batch = []
                batch_id += 1
        self.write_version("clinicaltrials", version)
        