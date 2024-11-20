"""A module for parsing the GGPONC corpus."""

import yaml
import logging
import os
from pathlib import Path

import pooch
from pooch import Unzip
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tqdm.auto import tqdm

from integration.orm import ggponc
from integration.orm.ggponc import create_metadata
from integration.parsers.ggponc import GgponcParser
from integration.sources import Download
from integration.umls.relationship_mapping import RelationshipMapper

logger = logging.getLogger(__name__)


def _load_ggponc_topic_to_cui_mapping(
    topic_yaml_path: str | Path,
) -> dict[str, list[str]]:
    """Return a mapping of GGPONC topic to CUIs."""
    topic_yaml_path = Path(topic_yaml_path)
    if not topic_yaml_path.exists():
        raise ValueError(f"Mapping file {topic_yaml_path} does not exist.")
    with open(topic_yaml_path, "r") as fh:
        topic_map = yaml.safe_load(fh)
        for topic, config in topic_map.items():
            if "scope" in config:
                topic_map[topic] = {"incl" : config["scope"]["incl"], "excl" : config["scope"].get("excl", [])}
        return topic_map

def parse_max_mapping_depth(max_depth: str | int | None) -> int | None:
    """Parse the max mapping depth from the config string."""
    if max_depth is None or max_depth == "None" or max_depth == "":
        return None
    else:
        return int(max_depth)


class Ggponc(Download):
    """A class to handle the parsing of the CPG data from GGPONC."""

    ggponc_dir: Path
    relationship_mapper: RelationshipMapper
    topic_yaml_path: Path
    max_mapping_depth_populations: int | None
    max_mapping_depth_interventions: int | None

    def __init__(
        self,
        url: str,
        batch_size: int | str,
        registry: str,
        cache_dir: str | Path,
        engine: Engine,
        relationship_mapper: RelationshipMapper,
        min_entity_confidence: float | str,
        topic_yaml_path: str | Path,
        max_mapping_depth_populations: int | str | None,
        max_mapping_depth_interventions: int | str | None,
        local_dir: str | Path = None,
        **kwargs,
    ) -> None:
        """Create a new Civic instance."""
        super().__init__(
            url=url,
            batch_size=batch_size,
            registry=registry,
            cache_dir=cache_dir,
            lookup_url="",
            engine=engine,
        )
        self.relationship_mapper = relationship_mapper
        self.min_entity_confidence = float(min_entity_confidence)
        self.topic_yaml_path = Path(topic_yaml_path)
        self.max_mapping_depth_populations = parse_max_mapping_depth(
            max_mapping_depth_populations
        )
        self.max_mapping_depth_interventions = parse_max_mapping_depth(
            max_mapping_depth_interventions
        )
        self.local_dir = local_dir

    def download(self) -> None:
        """Download the GGPONC data."""
        if self.local_dir is not None:
            self.ggponc_dir = Path(self.local_dir)
            self.downloaded_files = [Path(f) for f in Path(self.ggponc_dir).glob('*')]
        else:
            download_auth = pooch.HTTPDownloader(
                auth=(os.getenv("NEXTCLOUD_USER"), os.getenv("NEXTCLOUD_PW"))
            )
            if len(self.download_manager.registry.keys()) == 1:
                filename = list(self.download_manager.registry.keys())[0]
                unzipped_files = self.download_manager.fetch(
                    filename,
                    progressbar=True,
                    downloader=download_auth,
                    processor=Unzip(),
                )
                self.downloaded_files = [Path(f) for f in unzipped_files]
                self.ggponc_dir = self.cache_dir / self.downloaded_files[0].parent
                pooch.make_registry(
                    self.download_manager.path, self.registry, recursive=False
                )
                logging.info(f"Download is cached at {self.ggponc_dir}")
            else:
                raise ValueError(
                    "The GGPONC data source should contains the newest file to download."
                    "Please adjust the registry (registries/ggponc.txt) accordingly."
                )

    def _map_ggponc_guidelines_to_populations(
        self,
        session: Session,
        max_depth: int | None,
    ) -> None:
        """Map GGPONC guidelines to population and sub-populations."""
        query = select(ggponc.Guideline).distinct()
        topic_to_cui_map = _load_ggponc_topic_to_cui_mapping(
            self.topic_yaml_path
        )
        guidelines = session.scalars(query).all()
        for guideline in tqdm(
            guidelines,
            desc="Mapping GGPONC guideline topics to populations and sub-populations",
        ):
            population_cuis = topic_to_cui_map.get(guideline.ggponc_id, {})
            population_cuis_incl = population_cuis.get("incl", [])            
            population_cuis_excl = population_cuis.get("excl", [])
            logger.info(f"{guideline.ggponc_id} - Incl: {population_cuis_incl} - Excl: {population_cuis_excl}")
            for cui in population_cuis_incl:
                population = ggponc.Population(
                    cui=cui,
                    text=self.relationship_mapper.umls_parser.get_umls_text(cui),
                    sub_populations=[],
                )
                child_populations = (
                    self.relationship_mapper._get_related_concepts_with_names(
                        cui, direction="broad2narrow", max_depth=max_depth, stop_cuis=tuple(population_cuis_excl)
                    )
                )
                population.sub_populations = [
                    ggponc.SubPopulation(cui=sub_pop_cui, text=text)
                    for sub_pop_cui, text in child_populations.items() if not sub_pop_cui in population_cuis_excl
                ]
                guideline.populations.append(population)
        session.commit()

    def _map_ggponc_entities_to_super_concepts(
        self,
        session: Session,
        max_depth: int | None = None,
    ) -> None:
        """Map GGPONC entities to broader concepts."""
        mappable_cuis = set(self.relationship_mapper.df_mrrel_for_narrow2broad.index)
        query = select(ggponc.Entity)
        entities = session.scalars(query).all()

        for i, entity in enumerate(
            tqdm(entities, desc="Mapping GGPONC entities to super-concepts")
        ):
            if entity.cui in mappable_cuis:
                broader_concepts = (
                    self.relationship_mapper._get_related_concepts_with_names(
                        entity.cui, direction="narrow2broad", max_depth=max_depth
                    )
                )
                entity.super_concepts = [
                    ggponc.SuperConcept(cui=cui, text=text)
                    for cui, text in broader_concepts.items()
                ]
                if i > 0 and i % self.batch_size == 0:
                    session.commit()
        session.commit()

    def map_topics_to_sub_populations(self) -> None:
        """Map the GGPONC topics to sub-populations."""
        logger.info("Mapping CPG topics to sub-populations")
        with Session(self.engine) as session:
            self._map_ggponc_guidelines_to_populations(
                session,
                max_depth=self.max_mapping_depth_populations,
            )
        logger.info("Done.")

    def map_interventions_to_super_concepts(self) -> None:
        """Map the GGPONC (intervention) entities to super concepts."""
        logger.info("Mapping CPG interventions to super concepts")
        with Session(self.engine) as session:
            self._map_ggponc_entities_to_super_concepts(
                session, max_depth=self.max_mapping_depth_interventions
            )
        logger.info("Done.")

    def _commit_batch(self, batch: list[ggponc.Guideline]) -> None:
        """Commit a batch of assembled trials to the DB."""
        with Session(self.engine) as session:
            session.add_all(batch)
            session.commit()

    def parse(self, drop_existing: bool = False) -> None:
        """Parse the GGPONC CPGs into the database."""
        create_metadata(self.engine, drop_existing)
        batch = []
        batch_id = 1
        if self.ggponc_dir is None:
            raise ValueError(
                "No data to parse. Did you forget to download?"
                "Call `download` before `parse`."
            )
        gp = GgponcParser(
            guidelines_xml=self.ggponc_dir / "xml" / "cpg-corpus-cms.xml",
            entities_tsv=self.ggponc_dir / "predictions" / "silver_standard_entities_linked_xmen.tsv",
            translations_csv=self.ggponc_dir / "guideline_translations.csv",
            metadata_tsv=self.ggponc_dir / "plain_text" / "metadata_index.tsv",
            min_entity_confidence=self.min_entity_confidence,
        )
        logger.info("Parsing CPGs from GGPONC")
        for guideline in gp.parse():
            batch.append(guideline)
            if len(batch) == self.batch_size:
                tqdm.write(f"Writing batch {batch_id} into DB")
                self._commit_batch(batch)
                batch_id += 1
                batch = []
        tqdm.write("Writing final batch into DB")
        self._commit_batch(batch)

        # map GGPONC populations and interventions
        self.map_topics_to_sub_populations()
        self.map_interventions_to_super_concepts()
        self.write_version("ggponc", self.ggponc_dir.name)