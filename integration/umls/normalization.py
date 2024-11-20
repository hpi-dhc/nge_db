"""A module for mapping the different medical identifiers in the data to UMLS CUIs."""

import json
import logging
import pathlib

import pooch

from integration.umls.parser import MetaThesaurusParser

logger = logging.getLogger(__name__)


class Normalizer:
    """A class for mapping different medical identifiers to UMLS CUIs."""

    umls_parser: MetaThesaurusParser
    do_url: str
    mapping_mesh_term_to_cui: dict[str, str]
    mapping_hpo_to_cui: dict[str, str]
    mapping_nci_to_cui: dict[str, str]
    mapping_do_to_cui: dict[str, str]
    cache_dir: pathlib.Path
    cache_file_hpo: str = "hpo.json"
    cache_file_mesh: str = "mesh.json"
    cache_file_nci: str = "nci.json"
    cache_file_do: str = "do.json"

    def __init__(
        self,
        umls_parser: MetaThesaurusParser,
        do_umls_mapping_url: str,
        cache_dir: pathlib.Path | str,
    ) -> None:
        """Return a new Normalizer instance."""
        self.umls_parser = umls_parser
        self.cache_dir = pathlib.Path(cache_dir)
        self.do_umls_mapping_url = do_umls_mapping_url
        self._ensure_cache_dir_exists()
        self._build_mapping_hpo_to_cui()
        self._build_mapping_mesh_term_to_cui()
        self._build_mapping_nci_to_cui()
        self._build_mapping_do_to_cui()

    def _download_do_to_cui_mapping(
        self, downloaded_file_name: str = "do_raw.json"
    ) -> pathlib.Path:
        """Download the disease ontology ID (DOID) to CUI mapping file."""
        logger.info("Downloading the Disease Ontology mapping")
        download_path = pooch.retrieve(
            url=self.do_umls_mapping_url,
            path=self.cache_dir,
            fname=downloaded_file_name,
            known_hash=None,
            progressbar=True,
        )
        return pathlib.Path(download_path)

    def _ensure_cache_dir_exists(self) -> None:
        """Create the cache directory if it does not exist yet."""
        if self.cache_dir.exists():
            logger.info(f"Found existing cache directory at {self.cache_dir}")
        else:
            logger.info(
                f"Cache directory does not exist, creating it at {self.cache_dir}"
            )
            self.cache_dir.mkdir(parents=True)

    def _build_mapping_mesh_term_to_cui(self) -> None:
        """Build a lookup table that maps MeSH terms to UMLS CUIs."""
        cache = self.cache_dir / self.cache_file_mesh
        if cache.exists():
            mapping = json.loads(cache.read_text())
        else:
            subset_df = (
                self.umls_parser.df_mrconso.query("SAB == 'MSH' & TTY != 'QEV'")
                .sort_values("ISPREF")
                .drop_duplicates(subset=["STR", "CUI"], keep="last")
                .drop_duplicates(subset=["STR"], keep="first")
            )
            subset_df["STR"] = subset_df["STR"].str.lower()
            mapping = subset_df.set_index("STR")["CUI"].to_dict()
            cache.write_text(json.dumps(mapping))
        self.mapping_mesh_term_to_cui = mapping

    def _build_mapping_hpo_to_cui(self) -> None:
        """Build a lookup table that maps HPO IDs to UMLS CUIs."""
        cache = self.cache_dir / self.cache_file_hpo
        if cache.exists():
            mapping = json.loads(cache.read_text())
        else:
            subset_df = self.umls_parser.df_mrconso.sort_values(
                ["CODE", "TTY"]
            ).drop_duplicates("CODE", keep="first")[["CODE", "CUI"]]
            mapping = subset_df.set_index("CODE")["CUI"].to_dict()
            cache.write_text(json.dumps(mapping))
        self.mapping_hpo_to_cui = mapping

    def _build_mapping_nci_to_cui(self) -> None:
        """Build a lookup table that maps NCI IDs to UMLS CUIs."""
        cache = self.cache_dir / self.cache_file_nci
        if cache.exists():
            mapping = json.loads(cache.read_text())
        else:
            subset_df = self.umls_parser.df_mrconso.query("SAB == 'NCI' & TTY == 'PT'")[
                ["CODE", "CUI"]
            ].drop_duplicates()
            mapping = subset_df.set_index("CODE")["CUI"].to_dict()
            cache.write_text(json.dumps(mapping))
        self.mapping_nci_to_cui = mapping

    def _build_mapping_do_to_cui(self) -> None:
        cache = self.cache_dir / self.cache_file_do
        if cache.exists():
            mapping = json.loads(cache.read_text())
        else:
            do_umls_mapping_file_download = self._download_do_to_cui_mapping()
            with open(do_umls_mapping_file_download, "r") as f_do:
                data = json.load(f_do)
            mapping = {}
            for graph in data["graphs"]:
                for node in graph["nodes"]:
                    try:
                        found_cui = False
                        if "doid" in node["id"].lower():
                            doid = node["id"].split("DOID_")[-1]
                            xrefs = node["meta"]["xrefs"]
                            for ref in xrefs:
                                if ref["val"].startswith("UMLS_CUI:"):
                                    cui = ref["val"].split(":")[-1]
                                    mapping[doid] = cui
                                    found_cui = True
                                    break
                            # try to map through NCI if no UMLS cui is found
                            if not found_cui:
                                for ref in xrefs:
                                    if ref["val"].startswith("NCI:"):
                                        nci = ref["val"].split(":")[-1]
                                        cui = self.mapping_nci_to_cui[nci]
                                        mapping[doid] = cui
                                        found_cui = True
                                        break
                    except KeyError:
                        continue
            cache.write_text(json.dumps(mapping))
        self.mapping_do_to_cui = mapping

    def mesh_term_to_cui(self, mesh_term: str) -> str | None:
        """Return the CUI that the MeSH term maps to."""
        cui = None
        try:
            cui = self.mapping_mesh_term_to_cui[mesh_term]
        except KeyError:
            logger.debug(
                f"MeSH term {mesh_term} not found in UMLS {self.umls_parser.version}"
            )
        return cui

    def hpo_to_cui(self, hpo_id: str) -> str | None:
        """Return the CUI that the HPO ID maps to."""
        cui = None
        try:
            cui = self.mapping_hpo_to_cui[hpo_id]
        except KeyError:
            logger.debug(
                f"HPO ID {hpo_id} not found in UMLS {self.umls_parser.version}"
            )
        return cui

    def nci_to_cui(self, nci_id: str) -> str | None:
        """Return the CUI that the NCI ID maps to."""
        cui = None
        try:
            cui = self.mapping_nci_to_cui[nci_id]
        except KeyError:
            logger.debug(
                f"NCI ID {nci_id} not found in UMLS {self.umls_parser.version}"
            )
        return cui

    def do_id_to_cui(self, do_id: str) -> str | None:
        """Return the CUI that the Disease Ontology ID maps to."""
        cui = None
        try:
            cui = self.mapping_do_to_cui[do_id]
        except KeyError:
            logger.debug(
                f"Disease Ontology ID {do_id} not found in {self.cache_file_do}"
            )
        return cui
