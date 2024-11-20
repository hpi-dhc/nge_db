"""Module for parsing GGPONC literature index"""

from integration.parsers import Parser
from integration.orm.ggponc_literature import GgponcLiteratureReference

class GgponcLiteratureParser(Parser):

    def __init__(self, literature_index_df):
        self.literature_index_df = literature_index_df

    def parse(self) -> list[GgponcLiteratureReference]:
        """Parse the rows in the .csv file into GgponcLiteratureReference objects."""
        return [
            GgponcLiteratureReference(
                citation=row["id"],
                ref_id=row["ref_id"],
                guideline_id=row["guideline_id"],
                pm_id=row["pm_id"] if type(row["pm_id"]) == int else None,
                title=row["title"]                
            )
            for _, row in self.literature_index_df.iterrows()
        ]