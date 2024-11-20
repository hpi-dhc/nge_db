"""A module for parsing TrialStreamer .csv files to ORM objects."""

import ast
import csv
from pathlib import Path
from typing import Any, Iterator

from tqdm.auto import tqdm

from integration.orm.trialstreamer import (
    Flags,
    Intervention,
    MeshIntervention,
    MeshOutcome,
    MeshPopulation,
    Outcome,
    Population,
    Trial,
)
from integration.parsers import Parser, utils

INCREASED_FIELD_LIMIT = 10000000
csv.field_size_limit(INCREASED_FIELD_LIMIT)


class TrialstreamerParser(Parser):
    """A class for handling the parsing of the TrialStreamer .csv files into Trial objects."""

    def __init__(self, csv_file: str | Path) -> None:
        """Create a new TrialParser instance."""
        self.csv_file = Path(csv_file)

    @staticmethod
    def _get_single_field_list(row: dict[str, Any], field_name: str) -> list[str]:
        """Parse the string representations of a list."""
        return ast.literal_eval(row.get(field_name, "[]"))

    @staticmethod
    def _get_list_of_dicts(
        row: dict[str, Any], field_name: str
    ) -> list[dict[str, str]]:
        """Parse the string representation of a list of dictionaries."""
        return ast.literal_eval(row.get(field_name, "[]"))

    @property
    def n_lines(self) -> int:
        """Return the number of lines in the csv file."""
        with open(self.csv_file, newline="") as f:
            return sum(1 for _ in csv.reader(f))

    def parse(self) -> Iterator[Trial]:
        """Parse the rows in the .csv file into Trial objects."""
        with open(self.csv_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in tqdm(
                reader, desc=f"Parsing {self.csv_file.name}", total=self.n_lines
            ):
                yield Trial(
                    pm_id=int(row["pmid"]),
                    title=row.get("ti"),
                    abstract=row.get("ab"),
                    year=row.get("year"),
                    punchline=row.get("punchline_text"),
                    num_randomized=utils.str_to_num(
                        row.get("num_randomized"), cast_to="int"
                    ),
                    low_rsg_bias=row.get("low_rsg_bias") == "True",
                    low_ac_bias=row.get("low_ac_bias") == "True",
                    low_bpp_bias=row.get("low_bpp_bias") == "True",
                    prob_low_rob=utils.str_to_num(
                        row.get("prob_low_rob"), cast_to="float"
                    ),
                    journal=row.get("journal"),
                    populations=[
                        Population(population=t)
                        for t in self._get_single_field_list(row, "population")
                    ],
                    interventions=[
                        Intervention(intervention=t)
                        for t in self._get_single_field_list(row, "interventions")
                    ],
                    outcomes=[
                        Outcome(outcome=t)
                        for t in self._get_single_field_list(row, "outcomes")
                    ],
                    mesh_populations=[
                        MeshPopulation(cui=d["cui"], cui_term=d.get("cui_str", None))
                        for d in self._get_list_of_dicts(row, "population_mesh")
                        if isinstance(d, dict)
                    ],
                    mesh_interventions=[
                        MeshIntervention(cui=d["cui"], cui_term=d.get("cui_str", None))
                        for d in self._get_list_of_dicts(row, "interventions_mesh")
                        if isinstance(d, dict)
                    ],
                    mesh_outcomes=[
                        MeshOutcome(cui=d["cui"], cui_term=d.get("cui_str", None))
                        for d in self._get_list_of_dicts(row, "outcomes_mesh")
                        if isinstance(d, dict)
                    ],
                    flags=Flags(),
                )
