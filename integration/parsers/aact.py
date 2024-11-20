"""A module for parsing DB dumps from AACT."""

from collections import OrderedDict
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from integration.orm.aact import (
    Condition,
    Eligibility,
    Flags,
    Intervention,
    MeshCondition,
    MeshIntervention,
    Outcome,
    OutcomeAnalyses,
    Reference,
    Trial,
)
from integration.parsers import Parser, utils
from integration.umls.normalization import Normalizer

AACT_REQUIRED_FILES = {
    "studies": "studies.txt",
    "summaries": "brief_summaries.txt",
    "descriptions": "detailed_descriptions.txt",
    "eligibilities": "eligibilities.txt",
    "conditions": "conditions.txt",
    "interventions": "interventions.txt",
    "outcomes": "outcomes.txt",
    "outcome_analyses": "outcome_analyses.txt",
    "mesh_conditions": "browse_conditions.txt",
    "mesh_interventions": "browse_interventions.txt",
    "references": "study_references.txt",
}

AACT_REQUIRED_STUDY_COLS = [
    "nct_id",
    "brief_title",
    "official_title",
    "study_type",
    "acronym",
    "overall_status",
    "why_stopped",
    "enrollment",
    "enrollment_type",
    "phase",
    "number_of_groups",
    "number_of_arms",
    "start_date",
    "start_date_type",
    "completion_date",
    "completion_date_type",
    "last_update_posted_date",
    "last_update_posted_date_type",
    "results_first_posted_date",
    "results_first_posted_date_type",
]

aact_orm_type = (
    Reference
    | Eligibility
    | Intervention
    | Outcome
    | OutcomeAnalyses
    | Condition
    | MeshCondition
    | MeshIntervention
)

aact_lookup_dict_type = dict[
    str, dict[str, list[aact_orm_type] | dict[int, list[aact_orm_type]]]
]


class AactParser(Parser):
    """A class for parsing the AACT dump into Trial objects."""

    def __init__(
        self,
        downloaded_files: list[Path],
        normalizer: Normalizer,
        required_files: dict[str, str] = AACT_REQUIRED_FILES,
        required_cols: list[str] = AACT_REQUIRED_STUDY_COLS,
    ) -> None:
        """Create a new TrialParser instance."""
        self.normalizer = normalizer
        self.required_files = self._map_required_files_to_paths(
            required_files, downloaded_files
        )
        self.required_cols = required_cols
        self.data: dict[str, pd.DataFrame] = {}
        self._read_data_from_files()

    @staticmethod
    def _map_required_files_to_paths(
        required_files: dict[str, str], downloaded_files: list[Path]
    ) -> dict[str, Path]:
        """Map the required files to their actual download paths."""
        mapped_files = {}
        for key, file_name in required_files.items():
            if file_path := list(
                filter(lambda p: file_name == p.name, downloaded_files)
            )[0]:
                mapped_files[key] = Path(file_path)
            else:
                raise FileNotFoundError()
        return mapped_files

    @staticmethod
    def _txt_to_df(txt_file: Path, **kwargs) -> pd.DataFrame:
        """Parse an AACT txt file to a pandas DataFrame."""
        return pd.read_csv(txt_file, sep="|", low_memory=False, **kwargs)

    def _merge_studies_summaries_descriptions(self) -> None:
        """Merge summaries and descriptions into the studies table."""
        df = self.data["studies"].merge(self.data["summaries"], on="nct_id", how="left")
        self.data["studies"] = df.merge(
            self.data["descriptions"], on="nct_id", how="left"
        )
        self.data.pop("summaries")
        self.data.pop("descriptions")

    def _cast_to_none(self) -> None:
        """Ensure all missing values are identified by None."""
        for name, df in self.data.items():
            self.data[name] = df.replace([np.nan, pd.NaT, ""], None)

    def _read_data_from_files(self) -> None:
        """Parse the required files to pandas DataFrames."""
        for name, path in tqdm(
            self.required_files.items(), desc="Parsing data to memory..."
        ):
            tqdm.write(f"Parsing {name} from {path.name}")
            if name == "studies":
                self.data[name] = self._txt_to_df(
                    path,
                    parse_dates=[
                        "start_date",
                        "completion_date",
                        "last_update_posted_date",
                        "results_first_posted_date",
                    ],
                    usecols=self.required_cols,
                )
            elif name == "references":
                # drop references without PubmedID
                self.data[name] = self._txt_to_df(path).dropna(subset="pmid")
            elif name == "summaries":
                self.data[name] = self._txt_to_df(
                    path, usecols=["nct_id", "description"]
                ).rename(columns={"description": "summary"})
            elif name == "descriptions":
                self.data[name] = self._txt_to_df(
                    path, usecols=["nct_id", "description"]
                )
            else:
                self.data[name] = self._txt_to_df(path)
        self._merge_studies_summaries_descriptions()
        self._cast_to_none()

    @staticmethod
    def _get_orm_objects(df: pd.DataFrame, parser: Callable) -> list[aact_orm_type]:
        """Return either an empty list or parse the dataframe into a list of Objects."""
        objects = []
        if not df.empty:
            objects = df.apply(parser, axis=1).to_list()
        return objects

    def _build_subtable_lookup_dict(self) -> None:
        """Build lookup tables (key: nct_id) for the subtables."""
        self.lookup_dict: aact_lookup_dict_type = {}
        subtable_to_parser_mapping = OrderedDict(
            [
                ("references", self._parse_references),
                ("eligibilities", self._parse_eligibilities),
                ("conditions", self._parse_condition),
                ("interventions", self._parse_intervention),
                ("mesh_conditions", self._parse_mesh_conditions),
                ("mesh_interventions", self._parse_mesh_interventions),
                ("outcome_analyses", self._parse_outcome_analyses),
                (
                    "outcomes",
                    self._parse_outcome,
                ),  # outcomes must be parsed after outcome_analyses
            ]
        )
        for subtable, parser in subtable_to_parser_mapping.items():
            self.lookup_dict[subtable] = {}
            for nct_id, group in tqdm(
                self.data[subtable].groupby("nct_id"),
                desc=f"Parsing {subtable} to ORM objects",
            ):
                nct_id = str(nct_id)
                if subtable == "outcome_analyses":
                    self.lookup_dict[subtable][nct_id] = {}
                    for outcome_id, group in group.groupby("outcome_id"):
                        self.lookup_dict[subtable][nct_id][  # type: ignore
                            outcome_id
                        ] = self._get_orm_objects(group, parser)
                else:
                    self.lookup_dict[subtable][nct_id] = self._get_orm_objects(
                        group, parser
                    )

    def _row_to_trial(self, row: pd.Series) -> Trial:
        """Parse row content into a Trial."""
        nct_id = row["nct_id"]
        return Trial(
            nct_id=nct_id,
            title_brief=row["brief_title"],
            title_official=row["official_title"],
            study_type=row["study_type"],
            acronym=row["acronym"],
            summary=row["summary"],
            description=row["description"],
            overall_status=row["overall_status"],
            why_stopped=row["why_stopped"],
            phase=row["phase"],
            number_of_groups=utils.str_to_num(row["number_of_groups"], "int"),
            number_of_arms=utils.str_to_num(row["number_of_arms"], "int"),
            enrollment=row["enrollment"],
            enrollment_type=row["enrollment_type"],
            # dates
            date_start=row["start_date"],
            date_start_type=row["start_date_type"],
            date_completion=row["completion_date"],
            date_completion_type=row["completion_date_type"],
            date_last_update=row["last_update_posted_date"],
            date_last_update_type=row["last_update_posted_date_type"],
            date_results_first_posted=row["results_first_posted_date"],
            date_results_first_posted_type=row["results_first_posted_date_type"],
            # relations
            references=self.lookup_dict["references"].get(nct_id, []),
            eligibilities=self.lookup_dict["eligibilities"].get(nct_id, []),
            conditions=self.lookup_dict["conditions"].get(nct_id, []),
            interventions=self.lookup_dict["interventions"].get(nct_id, []),
            mesh_conditions=self.lookup_dict["mesh_conditions"].get(nct_id, []),
            mesh_interventions=self.lookup_dict["mesh_interventions"].get(nct_id, []),
            outcomes=self.lookup_dict["outcomes"].get(nct_id, []),
            flags=Flags(),
        )

    @staticmethod
    def _parse_references(row: pd.Series) -> Reference | None:
        """Parse row contents into References."""
        return Reference(pm_id=row["pmid"], reference_type=row["reference_type"])

    @staticmethod
    def _parse_eligibilities(row: pd.Series) -> Eligibility:
        """Parse row contents into Eligibilities."""
        return Eligibility(
            gender=row["gender"],
            minimum_age=row["minimum_age"],
            maximum_age=row["maximum_age"],
            healthy_volunteers=row["healthy_volunteers"],
            population=row["population"],
            criteria=row["criteria"],
        )

    @staticmethod
    def _parse_condition(row: pd.Series) -> Condition:
        """Parse row content into a Condition."""
        return Condition(condition=row["name"])

    @staticmethod
    def _parse_intervention(row: pd.Series) -> Intervention:
        """Parse row contents into an Intervention."""
        return Intervention(
            intervention_type=row["intervention_type"],
            name=row["name"],
            description=row["description"],
        )

    def _parse_mesh_conditions(self, row: pd.Series) -> MeshCondition:
        """Parse row contents into a MeshCondition."""
        mesh_term = row["downcase_mesh_term"]
        return MeshCondition(
            mesh_term=mesh_term,
            mesh_type=row["mesh_type"],
            cui=self.normalizer.mesh_term_to_cui(mesh_term),
        )

    def _parse_mesh_interventions(self, row: pd.Series) -> MeshIntervention:
        """Parse row contents into a MeshCondition."""
        mesh_term = row["downcase_mesh_term"]
        return MeshIntervention(
            mesh_term=mesh_term,
            mesh_type=row["mesh_type"],
            cui=self.normalizer.mesh_term_to_cui(mesh_term),
        )

    def _parse_outcome(self, row: pd.Series) -> Outcome:
        """Parse row contents into an Outcome."""
        nct_id = row["nct_id"]
        outcome_id = row["id"]
        return Outcome(
            outcome_type=row["outcome_type"],
            title=row["title"],
            description=row["description"],
            time_frame=row["time_frame"],
            population=row["population"],
            analyses=self.lookup_dict["outcome_analyses"]
            .get(nct_id, {})
            .get(outcome_id, []),  # type: ignore
        )

    @staticmethod
    def _parse_outcome_analyses(row: pd.Series) -> OutcomeAnalyses:
        """Parse row contents into OutcomeAnalyses."""
        return OutcomeAnalyses(
            param_type=row["param_type"],
            param_value=utils.str_to_num(row["param_value"], "float"),
            p_value=utils.str_to_num(row["p_value"], "float"),
            p_value_modifier=row["p_value_modifier"],
            ci_n_sides=row["ci_n_sides"],
            ci_percent=utils.str_to_num(row["ci_percent"], "float"),
            ci_lower_limit=utils.str_to_num(row["ci_lower_limit"], "float"),
            ci_upper_limit=utils.str_to_num(row["ci_upper_limit"], "float"),
            method=row["method"],
        )

    @property
    def n_trials(self) -> int:
        """Return the number of trials found."""
        if self.data.get("studies") is not None:
            return len(self.data["studies"])
        return 0

    def parse(self) -> Iterator[Trial]:
        """Parse the Trials into ORM objects."""
        self._build_subtable_lookup_dict()
        for _, row in self.data["studies"].iterrows():
            yield self._row_to_trial(row)
