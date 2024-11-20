"""A module for parsing the TrialStreamer data into the DB."""

import logging
import re
from pathlib import Path

import pooch
import requests
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tqdm.auto import tqdm

from integration.orm.trialstreamer import Trial, create_metadata
from integration.parsers.trialstreamer import TrialstreamerParser
from integration.sources import Download

logger = logging.getLogger(__name__)


class TrialStreamer(Download):
    """A class to handle parsing the TrialStreamer data."""

    def __init__(
        self,
        url: str,
        batch_size: int | str,
        registry: str,
        lookup_url: str,
        cache_dir: str | Path,
        file_pattern: str,
        engine: Engine,
    ) -> None:
        """Initialize a TrialStreamer data source instance."""
        super().__init__(url, batch_size, registry, cache_dir, lookup_url, engine)
        self.file_pattern = file_pattern
        self._update_registry()

    def _get_filenames_from_zenodo(self) -> list[str]:
        """Parse names of the relevant files from the Zenodo page."""
        logging.info(f"Parsing names of incremental files from {self.lookup_url}")
        response = requests.get(self.lookup_url)
        filenames = sorted(
            set(
                re.findall(
                    self.file_pattern,
                    response.text,
                )
            )
        )
        logging.info(
            f"Found {len(filenames)} files matching the pattern on {self.lookup_url}"
        )
        return filenames

    def _update_registry(self) -> None:
        """Check the Zenodo page for new incremental updates and add them to the registry."""
        current_zenodo_filenames = self._get_filenames_from_zenodo()
        for filename in current_zenodo_filenames:
            if filename not in self.download_manager.registry.keys():
                logger.info(
                    f"New file {filename} found on zenodo, adding it to registry"
                )
                self.download_manager.registry.update({filename: None})

    def download(self) -> None:
        """Download the TrialStreamer data."""
        downloaded_file_paths = []
        for filename in self.download_manager.registry.keys():
            downloaded_file_paths.append(
                self.download_manager.fetch(filename, progressbar=True)
            )
        pooch.make_registry(self.download_manager.path, self.registry)
        self.downloaded_files = sorted(
            [Path(fname) for fname in downloaded_file_paths], reverse=True
        )  # ensure that the newest file is parsed first
        logging.info(f"Download is cached at {Path(self.downloaded_files[0]).parent}")

    def _commit_batch(self, batch: list[Trial]) -> None:
        """Commit a batch of assembled trials to the DB."""
        with Session(self.engine) as session:
            session.add_all(batch)
            session.commit()

    def parse(self, drop_existing: bool = False) -> None:
        """Parse the data and insert it into the DB."""
        create_metadata(self.engine, drop_existing)
        batch = []
        batch_id = 1
        already_seen_pubmed_ids = set()
        for csv_file in tqdm(
            self.downloaded_files, desc="Parsing downloaded .csv files"
        ):
            tp = TrialstreamerParser(csv_file)
            for trial in tp.parse():
                if trial.pm_id not in already_seen_pubmed_ids:
                    batch.append(trial)
                    already_seen_pubmed_ids.add(trial.pm_id)
                if len(batch) == self.batch_size:
                    tqdm.write(f"Writing batch {batch_id} into DB")
                    self._commit_batch(batch)
                    batch_id += 1
                    batch = []
        tqdm.write("Writing final batch into DB")
        self._commit_batch(batch)
