"""Module for assigning effect significance flags to evidence."""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, Select, select, update
from sqlalchemy.orm import MappedClassProtocol, Session, contains_eager
from tqdm.auto import tqdm

from integration.orm import aact, civic, pubmed

logger = logging.getLogger(__name__)


class SignificanceFlagger:
    """Flag trials with significant findings."""

    def __init__(
        self,
        id_to_prediction_mapping_file: str,
        mark_split_decisions_as_significant: str | bool,
        p_value_threshold: str | float,
        engine: Engine,
        batch_size: int | str,
    ):
        """Initialize the flagger."""
        self.id_to_prediction_mapping_file = Path(id_to_prediction_mapping_file)
        self.mark_split_decisions_as_significant = bool(
            mark_split_decisions_as_significant
        )
        self.p_value_threshold = float(p_value_threshold)
        self.id_to_prediction_map = self._load_id_to_prediction_mapping_from_parquet()
        self.engine = engine
        self.batch_size = int(batch_size)

    def _load_id_to_prediction_mapping_from_parquet(self) -> dict[int, bool]:
        """Load the mapping from PubMed IDs to classifier predictions."""
        logger.info("Loading ID to prediction mapping...")
        df = pd.read_parquet(self.id_to_prediction_mapping_file)
        if "pm_id" not in df.columns:
            raise ValueError("pm_id column not found in mapping file.")
        if self.mark_split_decisions_as_significant:
            df["has_significant_effect"] = df["prob_significant effect"] >= 0.5
        return df.set_index("pm_id")["has_significant_effect"].to_dict()

    def _flag_items(
        self,
        query_items_to_flag: Select,
        table_name: str,
        flags_table: MappedClassProtocol,
        flag_override: bool | None = None,
    ):
        """Flag items with significant findings."""
        logger.info(f"Fetching items to flag for {table_name}...")
        with Session(self.engine) as session:
            items_to_flag = session.scalars(query_items_to_flag).unique().all()

        updates = [
            {
                "id": item.flags.id,
                "has_significant_finding": flag_override
                if flag_override is not None
                else self.id_to_prediction_map.get(item.pm_id),
            }
            for item in items_to_flag
        ]

        logger.info("Setting effect significance flag...")
        with Session(self.engine) as session:
            session.execute(update(flags_table), updates)  # type: ignore
            session.commit()
        logger.info("Done.")

    def flag_aact(self):
        """Flag Clinicaltrials evidence with significant findings."""
        query_significant_outcomes = (
            select(aact.Outcome.id)
            .join(aact.OutcomeAnalyses)
            .where(
                aact.OutcomeAnalyses.p_value.isnot(None),
                aact.OutcomeAnalyses.p_value < self.p_value_threshold,
            )
            .distinct()
        )

        query_trials_significant = (
            select(aact.Trial)
            .join(aact.Flags)
            .join(aact.Outcome)
            .where(aact.Outcome.id.in_(query_significant_outcomes))
            .distinct()
            .options(contains_eager(aact.Trial.flags))
        )

        query_trials_not_significant = (
            select(aact.Trial)
            .join(aact.Flags)
            .join(aact.Outcome)
            .where(aact.Outcome.id.notin_(query_significant_outcomes))
            .distinct()
            .options(contains_eager(aact.Trial.flags))
        )
        self._flag_items(
            query_trials_significant,
            "Clinicaltrials (significant)",
            aact.Flags,
            flag_override=True,
        )
        self._flag_items(
            query_trials_not_significant,
            "Clinicaltrials (not significant)",
            aact.Flags,
            flag_override=False,
        )

    def flag_pubmed(self):
        """Flag Pubmed evidence with significant findings."""
        ids = list(self.id_to_prediction_map.keys())
        for i in tqdm(range(0, len(ids), self.batch_size)):
            chunk = ids[i : i + self.batch_size]
            items_to_flag = (
                select(pubmed.Trial)
                .join(pubmed.Flags)
                .where(pubmed.Trial.pm_id.in_(chunk))
                .options(contains_eager(pubmed.Trial.flags))
            )
            self._flag_items(items_to_flag, "Pubmed", pubmed.Flags)

    def flag_civic(self):
        """Flag CIViC evidence with significant findings."""
        ids = list(self.id_to_prediction_map.keys())
        for i in tqdm(range(0, len(ids), self.batch_size)):
            chunk = ids[i : i + self.batch_size]
            items_to_flag = (
                select(civic.Source)
                .join(civic.Flags)
                .where(civic.Source.pm_id.in_(chunk))
                .options(contains_eager(civic.Source.flags))
            )
            self._flag_items(items_to_flag, "Civic", civic.Flags)
