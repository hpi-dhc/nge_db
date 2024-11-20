"""A module for parsing annotated Pubmed parquet files to ORM objects."""

import json
import re
from pathlib import Path
from typing import Iterator

import pandas as pd
from tqdm.auto import tqdm

from integration.orm.pubmed import (
    Doi,
    Flags,
    Intervention,
    MeshTerm,
    Outcome,
    Population,
    PublicationType,
    Reference,
    Trial,
    UmlsIntervention,
    UmlsOutcome,
    UmlsPopulation,
)
from integration.parsers import Parser, utils
from integration.umls.normalization import Normalizer


class PubmedParser(Parser):
    """A class for handling the parsing of the annotated Pubmed parquet files into Trial objects."""

    def __init__(self, parquet_files: list[Path], normalizer: Normalizer) -> None:
        """Create a new PubmedParser instance."""
        self.parquet_files: list[Path] = [
            Path(parquet_file) for parquet_file in parquet_files
        ]
        self.normalizer: Normalizer = normalizer

    def parse(self) -> Iterator[Trial]:
        """Parse the rows in the .csv file into Trial objects."""
        nct_regex = re.compile(r"(NCT\d{8})")
        for parquet_file in tqdm(self.parquet_files, "Parsing parquet files"):
            df = pd.read_parquet(parquet_file).drop_duplicates(subset='pmid', keep='last')
            month_mapping = {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            }

            df["publication_date"] = pd.to_datetime(
                df["year"]
                + "/"
                + df["month"]
                .apply(lambda m: month_mapping[m] if len(m) == 3 else m)
                .astype(str)
            )
            for row in tqdm(
                df.itertuples(), desc=f"Parsing {parquet_file}", total=len(df)
            ):
                num_randomized = utils.str_to_num(row.num_randomized, cast_to="int")
                if num_randomized is not None:
                    num_randomized = (
                        num_randomized
                        if num_randomized
                        <= 1000000000  # unlikely to see sample size of > than one billion
                        else None
                    )
                authors = []
                if row.authors is not None and type(row.authors) != float:
                    for a in row.authors:
                        authors.append({
                            'LastName' : a['LastName'],
                            'ForeName' : a['ForeName'],
                            'Initials' : a['Initials'],
                        })

                yield Trial(
                    pm_id=int(row.pmid),
                    status=row.status,
                    indexing_method=row.indexing_method,
                    title=row.title,
                    authors=json.dumps(authors[0:100]),
                    abstract=row.abstract_plaintext,
                    abstract_formatted=json.dumps(list(row.abstract)),
                    publication_date=row.publication_date,
                    num_randomized=num_randomized,
                    journal=row.journal,
                    ftp_fn=row.ftp_fn,
                    publication_types=[
                        PublicationType(publication_type=p_type) for p_type in row.ptyp
                    ],
                    references=[
                        Reference(nct_id=nct_id)
                        for nct_id in row.registry_ids
                        if nct_regex.fullmatch(nct_id)
                    ],
                    dois=[Doi(doi=doi) for doi in row.dois],
                    populations=[Population(population=t) for t in row.population],
                    interventions=[
                        Intervention(intervention=t) for t in row.interventions
                    ],
                    outcomes=[Outcome(outcome=t) for t in row.outcomes],
                    mesh_terms=[
                        MeshTerm(
                            mesh_term=mesh_term,
                            cui=self.normalizer.mesh_term_to_cui(mesh_term.lower()),
                        )
                        for mesh_term in row.mesh
                    ],
                    umls_population=[
                        UmlsPopulation(
                            cui=d["cui"],
                            cui_term=d.get("cui_str"),
                            mention=d.get("mention"),
                        )
                        for d in row.population_umls
                        if isinstance(d, dict)
                    ],
                    umls_interventions=[
                        UmlsIntervention(
                            cui=d["cui"],
                            cui_term=d.get("cui_str"),
                            mention=d.get("mention"),
                        )
                        for d in row.interventions_umls
                        if isinstance(d, dict)
                    ],
                    umls_outcomes=[
                        UmlsOutcome(
                            cui=d["cui"],
                            cui_term=d.get("cui_str"),
                            mention=d.get("mention"),
                        )
                        for d in row.outcomes_umls
                        if isinstance(d, dict)
                    ],
                    flags=Flags(),
                )
