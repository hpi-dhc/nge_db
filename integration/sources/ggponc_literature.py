""" A module for parsing the GGPONC literature index into the DB. """

import logging

from integration.parsers.ggponc_literature import GgponcLiteratureParser
from integration.sources import Source
from sqlalchemy import select
from sqlalchemy.orm import Session
from integration.citation_utils import retrieve_all_identifiers, get_title_to_id_mapping_pubmed, get_title_to_id_mapping_clinicaltrials
from integration.orm.ggponc_literature import create_metadata
from pathlib import Path
from tqdm.auto import tqdm
import pandas as pd
import os

logger = logging.getLogger(__name__)

class GgponcLiterature(Source):

    def __init__(
        self,
        engine,
        local_dir,
        doi_pm_id_cache,
        cn_pm_id_cache,
        title_nct_id_cache,
        title_pm_id_cache,
        **kwargs,
    ):
        """Create a new GgponcLiterature instance."""
        self.local_dir = Path(local_dir)
        self.doi_pm_id_cache = Path(doi_pm_id_cache)
        self.cn_pm_id_cache = Path(cn_pm_id_cache)
        self.title_nct_id_cache = Path(title_nct_id_cache)
        self.title_pm_id_cache = Path(title_pm_id_cache)
        super().__init__(engine)

    def parse(self, drop_existing: bool = False) -> None:

        lit_index = self.local_dir / "xml" / "literature_index.tsv"

        if not lit_index.exists():
            raise ValueError(
                f"Literature index file {lit_index} does not exist. Did you already download GGPONC + PubMed?"
            )

        df_ggponc_translations = pd.read_csv(
            self.local_dir / "guideline_translations.csv"
        ).rename(columns={"id": "guideline_id"})

        df_ggponc_literature = pd.read_csv(
            lit_index, sep="\t"
        ).rename(columns={"title": "german_name"})

        df_ggponc = df_ggponc_literature.merge(df_ggponc_translations, on="german_name")

        if not self.local_dir.name.startswith('v2.0'):
            # Fix column name inconsistencies across versions: TODO what happened?
            ids = df_ggponc.id.copy()
            df_ggponc['id'] = df_ggponc['ref_id']
            df_ggponc['ref_id'] = ids
        
        df_ggponc["title"] = df_ggponc["id"].str.extract("<i>(.+)<\/i>")

        df_ggponc.dropna(subset=['title'], axis=0, inplace=True)

        df_ggponc["pm_id"] = (
            df_ggponc["id"]
            .str.extract(r"https://pubmed.ncbi.nlm.nih.gov/(\d{8})")
            .astype("Int64")
        )

        # Retrieving IDs
        df_ggponc["nct_id"] = pd.NA
        df_ggponc["doi"] = pd.NA
        df_ggponc["cn_id"] = pd.NA

        with Session(self.engine) as session:
            df_pm = get_title_to_id_mapping_pubmed(session)
            df_ct = get_title_to_id_mapping_clinicaltrials(session)


        tqdm.pandas(desc="Retrieving available identifiers")

        df_ggponc = df_ggponc.progress_apply(  # type: ignore
            lambda row: retrieve_all_identifiers(
                row=row,
                entrez_email=os.environ.get("PUBMED_USER"),
                entrez_api_key=os.environ.get("PUBMED_API_KEY"),
                doi_pm_id_cache=self.doi_pm_id_cache,
                cn_pm_id_cache=self.cn_pm_id_cache,
                title_nct_id_cache=self.title_nct_id_cache,
                title_pm_id_cache=self.title_pm_id_cache,
                df_pm=df_pm,
                df_ct=df_ct,
            ),
            axis=1,
        )
        df_ggponc = df_ggponc.astype(
            {col: "Int64" for col in df_ggponc.columns if "pm_id" in col.lower()}
        )

        df_ggponc.to_csv(f"output/_literature_index_{self.local_dir.name}.csv")

        create_metadata(self.engine, drop_existing)
        parser = GgponcLiteratureParser(df_ggponc)
        refs = parser.parse()
        logger.info("Inserting references into the DB")
        with Session(self.engine) as session:
            session.add_all(refs)
            session.commit()
        logger.info("Done.")
