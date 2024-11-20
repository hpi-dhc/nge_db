"""Module for parsing clinical practice guidelines from GGPONC."""

from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from integration.orm.ggponc import Entity, Guideline, TextBlock
from integration.parsers import Parser


def parse_guideline(files_df: pd.DataFrame, min_confidence: float) -> Guideline:
    """Parse a slice of the CPG dataframe to a Guideline ORM object."""
    first_row = files_df.head(1).iloc[0]
    return Guideline(
        ggponc_id=first_row.name[0],  # type: ignore
        name=first_row["name"],
        name_en=first_row.get("english_name", None),
        text_blocks=files_df.groupby(level=1)
        .apply(
            lambda entities_df: parse_text_block(
                entities_df, min_confidence=min_confidence  # type: ignore
            )
        )
        .to_list(),
    )


def parse_text_block(entities_df: pd.DataFrame, min_confidence: float) -> TextBlock:
    """Parse a slice of the CPG dataframe to a TextBlock ORM object."""
    first_row = entities_df.head(1).iloc[0]
    entities = entities_df.apply(parse_entity, axis=1).to_list()  # type: ignore
    entities = [e for e in entities if e.text and e.canonical and e.confidence and e.confidence >= min_confidence]
    return TextBlock(
        filename=first_row.name[1],  # type: ignore
        number=first_row["number"],
        sections=first_row["sections"],
        recommendation=first_row["recommendation"],
        recommendation_creation_date=first_row["recommendation_creation_date"],
        recommendation_grade=first_row["recommendation_grade"],
        edit_state=first_row["edit_state"],
        type_of_recommendation=first_row["type_of_recommendation"],
        strength_of_consensus=first_row["strength_of_consensus"],
        entities=entities,
    )


def parse_entity(annotation: pd.Series) -> Entity:
    """Parse an annotation row into an Entity ORM object."""
    return Entity(
        text=annotation["text"],
        type_=annotation["type"],
        start=annotation["start"],
        end=annotation["end"],
        cui=annotation["cui"],
        tuis=annotation["tuis"],
        canonical=annotation["canonical"],
        confidence=annotation["confidence"],
    )


class GgponcParser(Parser):
    """A class for handling the parsing of the GGPONC files into Guideline objects."""

    def __init__(
        self,
        guidelines_xml: str | Path,
        entities_tsv: str | Path,
        translations_csv: str | Path,
        metadata_tsv: str | Path,
        min_entity_confidence: float,
    ) -> None:
        """Create a new GuidelineParser instance."""
        self.guidelines_xml = Path(guidelines_xml)
        self.entities_tsv = Path(entities_tsv)
        self.translations_csv = Path(translations_csv)
        self.metadata_tsv = Path(metadata_tsv)
        self.min_entity_confidence = min_entity_confidence

        self.entities: pd.DataFrame = self._parse_entities()
        self.translations: pd.DataFrame = self._parse_translations()
        self.metadata: pd.DataFrame = self._parse_metadata()
        self.annotations: pd.DataFrame = self._merge_annotations_data()

    def _parse_entities(self) -> pd.DataFrame:
        """Parse the TSV file containing the entity annotations."""
        return pd.read_csv(self.entities_tsv, sep="\t")

    def _parse_translations(self) -> pd.DataFrame:
        """Parse the CSV file containing the guideline name translations."""
        return pd.read_csv(self.translations_csv)

    def _parse_metadata(self) -> pd.DataFrame:
        """Parse the TSV file containing GGPONC metadata."""
        df = pd.read_csv(
            self.metadata_tsv, sep="\t", parse_dates=["recommendation_creation_date"]
        )
        df["id"] = df["file"].str[3:-5]
        return df

    def _merge_annotations_data(self) -> pd.DataFrame:
        """Combine the different dataframes into a single annotations dataframe."""
        df = (
            self.metadata.merge(self.translations, on="id", how="left")
            .drop(columns="german_name")
            .merge(self.entities, left_on="file", right_on="document")
            .drop(
                columns=[
                    "document",
                    "vote",
                    "linker",
                    "level_of_evidences",
                    "expert_opinion",
                    "guideline_id",
                ]
            )
        ).set_index(["id", "file"])
        df = df.replace([np.nan, pd.NaT], None)
        df["number"] = df["number"].astype(str).replace("None", None)
        return df

    def parse(self) -> list[Guideline]:
        """Parse the CPGs contained in the files into ORM objects."""
        tqdm.pandas(desc="Parsing CPGs")
        return (
            self.annotations.groupby(level=0)  # type: ignore
            .progress_apply(
                lambda files_df: parse_guideline(
                    files_df, min_confidence=self.min_entity_confidence
                )
            )
            .to_list()
        )
