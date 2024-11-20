"""A module that contains parsing logic for the UMLS metathesaurus."""

import functools
import logging
import zipfile
from pathlib import Path
from typing import Any, Literal

import cachetools
import pandas as pd
import umls_downloader

from integration.config import parse_config_list

COLNAMES: dict[str, dict[str, Any]] = {
    "MRCONSO.RRF": {
        "names_dtypes": {
            "CUI": str,
            "LAT": str,
            "TS": str,
            "LUI": str,
            "STT": str,
            "SUI": str,
            "ISPREF": "category",
            "AUI": str,
            "SAUI": str,
            "SCUI": str,
            "SDUI": str,
            "SAB": "category",
            "TTY": str,
            "CODE": str,
            "STR": str,
            "SRL": str,
            "SUPPRESS": "category",
            "CVF": str,
        },
        "required_cols": [
            "CUI",
            "LAT",
            "STT",
            "ISPREF",
            "SAB",
            "TTY",
            "CODE",
            "STR",
            "SUPPRESS",
        ],
    },
    "MRREL.RRF": {
        "names_dtypes": {
            "CUI1": str,
            "AUI1": str,
            "STYPE1": str,
            "REL": "category",
            "CUI2": str,
            "AUI2": str,
            "STYPE2": "category",
            "RELA": "category",
            "RUI": str,
            "SRUI": str,
            "SAB": "category",
            "SL": str,
            "RG": str,
            "DIR": "category",
            "SUPPRESS": "category",
            "CVF": str,
        },
        "required_cols": ["CUI1", "REL", "CUI2", "SAB", "SUPPRESS"],
    },
    "MRSTY.RRF": {
        "names_dtypes": {
            "CUI": str,
            "TUI": str,
            "STN": str,
            "STY": str,
            "ATUI": str,
            "CVF": str,
        },
        "required_cols": ["CUI", "TUI", "STN", "STY"],
    },
}

logger = logging.getLogger(__name__)

class MetaThesaurusParser:
    """A class for downloading and parsing the UMLS metathesaurus."""

    sab_for_text_lookup: list[str]

    def __init__(
        self,
        version: str,
        cache_dir: str | Path,
        sab_for_text_lookup: str | list[str],
    ):
        """Return a new parser instance."""
        self.version: str = version
        self.path_download: Path = self.download()
        self.path_base: Path = Path(cache_dir)
        self.path_mrconso: Path = self.path_base / f"{self.version}/META/MRCONSO.RRF"
        self.path_mrsty: Path = self.path_base / f"{self.version}/META/MRSTY.RRF"
        self.path_mrrel: Path = self.path_base / f"{self.version}/META/MRREL.RRF"
        self.sab_for_text_lookup = parse_config_list(sab_for_text_lookup)

    def download(self) -> Path:
        """Download the UMLS metathesaurus."""
        return umls_downloader.download_umls_full(version=self.version)

    def _file_name_to_path(
        self, file_name: Literal["MRCONSO.RRF", "MRREL.RRF", "MRSTY.RRF"]
    ) -> Path:
        """Return the cached path belonging of file_name."""
        return self.path_base / f"{self.version}/META/{file_name}"

    def _extract_file_from_downloaded_zip(
        self, file_name: Literal["MRCONSO.RRF", "MRREL.RRF", "MRSTY.RRF"]
    ) -> None:
        """Extract a file from the UMLS metathesaurus zip file."""
        file_path = self._file_name_to_path(file_name)
        if not file_path.exists():
            with zipfile.ZipFile(self.path_download) as umls_zip:
                logger.info(f"Extracting {file_path.name} from UMLS metathesaurus zip")
                path_of_file_within_zip = Path(*file_path.parts[-3:])
                umls_zip.extract(str(path_of_file_within_zip), self.path_base)
                logger.info("Done.")

    def _parse_file(
        self, file_name: Literal["MRCONSO.RRF", "MRREL.RRF", "MRSTY.RRF"]
    ) -> pd.DataFrame:
        """Parse a file of the UMLS metathesaurus."""
        file_path = self.path_base / f"{self.version}/META/{file_name}"
        file_path_parquet = file_path.parent / f"{file_name}.parquet"
        if file_path_parquet.exists():
            logger.info(f"Parsing {file_path_parquet}, this could take a while...")
            df = pd.read_parquet(file_path_parquet)
        else:
            if not file_path.exists():
                self._extract_file_from_downloaded_zip(file_name)
            logger.info(f"Parsing {file_name}, this could take a while...")
            df = pd.read_csv(
                file_path,
                sep="|",
                names=COLNAMES[file_name]["names_dtypes"].keys(),
                dtype=COLNAMES[file_name]["names_dtypes"],
                usecols=COLNAMES[file_name]["required_cols"],
                encoding="utf-8",
                index_col=False,
            )
            logger.info(f"Saving a copy to {file_path_parquet.name} for faster access")
            df.to_parquet(file_path_parquet, index=False)
        return df

    @functools.cached_property
    def df_mrrel(self) -> pd.DataFrame:
        """Parse MRREL.RRF into a dataframe."""
        return self._parse_file("MRREL.RRF")

    @functools.cached_property
    def df_mrconso(self) -> pd.DataFrame:
        """Parse MRCONSO.RRF into a dataframe."""
        return self._parse_file("MRCONSO.RRF")

    @functools.cached_property
    def df_mrsty(self) -> pd.DataFrame:
        """Parse MRSTY.RRF into a dataframe."""
        return self._parse_file("MRSTY.RRF")

    @functools.cached_property
    def df_mrsty_indexed(self) -> pd.DataFrame:
        """Return a dataframe of MRSTY.RRF indexed by CUI."""
        return self.df_mrsty.set_index("CUI").sort_index()

    @functools.cached_property
    def cui_to_text_mapping(self) -> dict[str, str]:
        """Return a mapping from CUI to preferred term (where available)."""
        df = self.df_mrconso
        df["SAB"] = pd.Categorical(df["SAB"], self.sab_for_text_lookup, ordered=True)
        df['_pref_tty'] = (df.TTY == 'PT')
        df = df.query("LAT == 'ENG' & SAB in @self.sab_for_text_lookup")
        df = df.sort_values(["_pref_tty", "SAB", "ISPREF"], ascending=False)
        df = df.drop_duplicates(subset="CUI", keep="first")
        return df.set_index("CUI")["STR"].to_dict()

    def get_umls_text(self, cui: str) -> str | None:
        """Return the preferred UMLS term associated with the CUI."""
        return self.cui_to_text_mapping.get(cui)

    @cachetools.cached(cachetools.LFUCache(maxsize=200000))
    def get_semantic_types(self, cui: str) -> list[dict[str, str]]:
        """Return a list of semantic types from MRSTY.RRF attached to the CUI."""
        try:
            semantic_types = self.df_mrsty_indexed.loc[[cui]].to_dict("records")  # type: ignore
        except KeyError:
            semantic_types = []
        return semantic_types  # type: ignore
