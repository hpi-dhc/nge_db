"""A module for parsing the annotated Pubmed data into the DB."""

import logging
import os
from pathlib import Path

import pooch
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy import delete
from tqdm.auto import tqdm

from integration.orm.pubmed import Trial, create_metadata
from integration.parsers.pubmed import PubmedParser
from integration.sources import Download
from integration.umls.normalization import Normalizer

logger = logging.getLogger(__name__)

class Pubmed(Download):
    """A class to handle parsing the annotated Pubmed data."""

    def __init__(
        self,
        url: str,
        batch_size: int | str,
        registry: str,
        cache_dir: str | Path,
        engine: Engine,
        normalizer: Normalizer,
        local_dir: str | Path = None,
        update_batch_size: int | str = None,
    ) -> None:
        """Initialize a Pubmed data source instance."""
        if update_batch_size:
            batch_size = update_batch_size
        super().__init__(
            url=url,
            batch_size=batch_size,
            registry=registry,
            cache_dir=cache_dir,
            lookup_url="",
            engine=engine,
        )
        self.normalizer = normalizer
        self.local_dir = local_dir

    def download(self) -> None:
        """Download the Pubmed data."""
        if self.local_dir is not None:
            downloaded_file_paths = [Path(f) for f in Path(self.local_dir).glob('*.parquet')]
        else:
            downloaded_file_paths = []
            download_auth = pooch.HTTPDownloader(
                auth=(os.getenv("NEXTCLOUD_USER"), os.getenv("NEXTCLOUD_PW"))
            )
            for filename in self.download_manager.registry.keys():
                downloaded_file_paths.append(
                    self.download_manager.fetch(
                        filename, progressbar=True, downloader=download_auth
                    )
                )
            pooch.make_registry(self.download_manager.path, self.registry)
        self.downloaded_files = sorted(
            [Path(fname) for fname in downloaded_file_paths]
        )
        logging.info(f"Download is cached at {Path(self.downloaded_files[0]).parent}")

    def _commit_batch(self, batch: list[Trial]) -> None:
        """Commit a batch of assembled trials to the DB."""
        with Session(self.engine) as session:
            batch_pmids = [trial.pm_id for trial in batch]
            result = session.connection().execute(delete(Trial).where(Trial.pm_id.in_(batch_pmids)))
            n_deleted = result.rowcount
            if n_deleted > 0:
                logger.info(f"Updating {n_deleted} existing trials with same PMIDs.")
            session.add_all(batch)
            session.commit()

    def parse(self, drop_existing: bool = False) -> None:
        """Parse the data and insert it into the DB."""        
        create_metadata(self.engine, drop_existing)
        batch = []
        batch_id = 1
        tp = PubmedParser(self.downloaded_files, normalizer=self.normalizer)
        for trial in tp.parse():
            batch.append(trial)                
            if len(batch) == self.batch_size:
                tqdm.write(f"Writing batch {batch_id} into DB")
                self._commit_batch(batch)
                batch_id += 1
                batch = []
        tqdm.write("Writing final batch into DB")
        self._commit_batch(batch)
        self.write_version("pubmed", Path(self.downloaded_files[-1]).stem)
