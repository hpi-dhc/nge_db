"""A module for mapping narrow CUIs for broader ones."""

import functools
import logging
from typing import Literal

import cachetools
import pandas as pd

from integration.config import parse_config_list
from integration.umls.parser import MetaThesaurusParser

logger = logging.getLogger(__name__)


class RelationshipMapper:
    """A class responsible for mapping broad CUIs to their attached narrow concepts recursively."""

    umls_parser: MetaThesaurusParser
    relations_for_broad2narrow: list[str]
    relations_for_narrow2broad: list[str]
    sab_for_broad2narrow: list[str]
    sab_for_narrow2broad: list[str]
    stns_for_narrow2broad: list[str]

    def __init__(
        self,
        umls_parser: MetaThesaurusParser,
        relations_for_broad2narrow: str | list[str],
        relations_for_narrow2broad: str | list[str],
        sab_for_broad2narrow: str | list[str],
        sab_for_narrow2broad: str | list[str],
        stns_for_narrow2broad: str | list[str] = [],
    ) -> None:
        """Return a new instance of the mapper."""
        self.umls_parser = umls_parser
        self.relations_for_broad2narrow = parse_config_list(relations_for_broad2narrow)
        self.relations_for_narrow2broad = parse_config_list(relations_for_narrow2broad)
        self.sab_for_broad2narrow = parse_config_list(sab_for_broad2narrow)
        self.sab_for_narrow2broad = parse_config_list(sab_for_narrow2broad)
        self.stns_for_narrow2broad = parse_config_list(stns_for_narrow2broad)

    @functools.cached_property
    def df_mrrel_filtered_indexed(self) -> pd.DataFrame:
        """Return MRREL.RRF dataframe filtered by accepted sources."""
        accepted_relations = (  # noqa: F841
            self.relations_for_broad2narrow + self.relations_for_narrow2broad
        )
        return (
            self.umls_parser.df_mrrel.query(
                "SUPPRESS == 'N' & REL in @accepted_relations "
            )[["CUI1", "REL", "CUI2", "SAB"]]
            .astype(str)
            .set_index("CUI1")
            .sort_index()
        )

    @functools.cached_property
    def df_mrrel_for_broad2narrow(self) -> pd.DataFrame:
        """Return filtered MRREL.RRF dataframe for broad->narrow relationship mapping."""
        return self.df_mrrel_filtered_indexed.query(
            "REL in @self.relations_for_broad2narrow"
            " & SAB in @self.sab_for_broad2narrow"
        ).drop(columns=["REL", "SAB"])

    @functools.cached_property
    def df_mrrel_for_narrow2broad(self) -> pd.DataFrame:
        """Return filtered MRREL.RRF dataframe for narrow->broad relationship mapping."""
        df = self.df_mrrel_filtered_indexed.query(
            "REL in @self.relations_for_narrow2broad"
            " & SAB in @self.sab_for_narrow2broad"
        ).drop(columns=["REL", "SAB"])
        if self.stns_for_narrow2broad is not None:
            cuis_with_accepted_stns = self.umls_parser.df_mrsty[  # noqa: F841
                self.umls_parser.df_mrsty["STN"].str.startswith(
                    tuple(self.stns_for_narrow2broad)
                )
            ]["CUI"].unique()
            df.query(
                "index in @cuis_with_accepted_stns & CUI2 in @cuis_with_accepted_stns",
                inplace=True,
            )
        return df

    @cachetools.cached(cachetools.LFUCache(maxsize=1000000))
    def _get_related_concepts_with_names(
        self,
        starting_cui: str,
        direction: Literal["broad2narrow", "narrow2broad"],
        max_depth: int | None = None,
        include_cuis_without_text: bool = False,
        stop_cuis: tuple[str] | None = (),
    ) -> dict[str, str | None]:
        """Return a dictionary containing the related concepts and their names."""
        related_cuis = self.get_related_concepts(
            starting_cui=starting_cui,
            direction=direction,
            max_depth=max_depth,
            stop_cuis=stop_cuis,
        )
        related_concepts = {}
        for cui in related_cuis:
            text = self.umls_parser.get_umls_text(cui)
            if include_cuis_without_text or text is not None:
                related_concepts[cui] = text

        return related_concepts

    @cachetools.cached(cachetools.LFUCache(maxsize=1000000))
    def get_related_concepts(
        self,
        starting_cui: str,
        direction: Literal["broad2narrow", "narrow2broad"],
        max_depth: int | None = None,
        stop_cuis: tuple[str] | None = (),
    ) -> list[str]:
        """Return all CUIs attached to starting_cui in either narrower or broader direction."""
        related_cuis: set[str] = set()
        new_cuis: set[str] = set([starting_cui])
        stop_cuis : set[str]= set(stop_cuis)
        depth = 0

        if direction == "broad2narrow":
            mrrel_df = self.df_mrrel_for_broad2narrow
        elif direction == "narrow2broad":
            mrrel_df = self.df_mrrel_for_narrow2broad
        else:
            raise NotImplementedError(f"Direction {direction} is not implemented!")

        while len(new_cuis) > 0:
            referenced_cuis = set(
                mrrel_df.loc[mrrel_df.index.intersection(list(new_cuis))]["CUI2"]
            )
            new_cuis = referenced_cuis - related_cuis - stop_cuis

            # Add the new narrow concepts to the set
            related_cuis.update(new_cuis)

            depth += 1

            if max_depth is not None and depth == max_depth:
                break

        return list(related_cuis)

    def _get_related_concepts_metrics(
        self,
        starting_cui: str,
        direction: Literal["broad2narrow", "narrow2broad"],
        max_depth: int | None = None,
    ) -> tuple[list[str], list[dict[str, int]]]:
        """Return all attached CUIs in either narrower or broader direction along with metrics."""
        related_cuis: set[str] = set()
        new_cuis: set[str] = set([starting_cui])
        depth = 0
        metrics: list[dict[str, int]] = [{}]

        if direction == "broad2narrow":
            mrrel_df = self.df_mrrel_for_broad2narrow
        elif direction == "narrow2broad":
            mrrel_df = self.df_mrrel_for_narrow2broad
        else:
            raise NotImplementedError(f"Direction {direction} is not implemented!")

        while len(new_cuis) > 0:
            referenced_cuis = set(
                mrrel_df.loc[mrrel_df.index.intersection(list(new_cuis))]["CUI2"]
            )
            new_cuis = referenced_cuis - related_cuis

            # Add the new narrow concepts to the set
            related_cuis.update(new_cuis)

            metrics.append(
                {
                    "n_referenced_cuis": len(referenced_cuis),
                    "n_new_cuis": len(new_cuis),
                    "n_related_cuis": len(related_cuis),
                }
            )

            depth += 1

            if max_depth is not None and depth == max_depth:
                break

        return list(related_cuis), metrics
