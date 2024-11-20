"""A module for running the entire data aggregation logic."""

import logging
import sys

from integration.config import load_config
from integration.db import get_engine
from integration.erd import create_erd
from integration.flagging import SignificanceFlagger
from integration.sources.aact import Aact
from integration.sources.civic import Civic
from integration.sources.ggponc import Ggponc
from integration.sources.pubmed import Pubmed
from integration.sources.ggponc_literature import GgponcLiterature
from integration.umls.normalization import Normalizer
from integration.umls.parser import MetaThesaurusParser
from integration.umls.relationship_mapping import RelationshipMapper
import argparse
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
)

logger = logging.getLogger(__name__)

VALID_SOURCES = [
    "ggponc",
    "civic",
    "pubmed",
    "pubmed_update",
    "aact",
    "literature",
    "flags",
]


def main() -> None:
    """Run the complete data integration logic."""

    parser = argparse.ArgumentParser(
        description="Run the complete data integration logic."
    )
    parser.add_argument(
        "sources",
        metavar="source",
        type=str,
        nargs="+",
        help=f"Valid sources are {VALID_SOURCES} or 'all' to download all sources.",
    )
    parser.add_argument("--file", type=str, help="Update file path")

    args = parser.parse_args()
    sources = args.sources
    file = args.file
    if sources == ["all"]:
        sources = VALID_SOURCES
    for s in sources:
        if not s in VALID_SOURCES:
            logger.error(f"Invalid source: {s}, valid sources are {VALID_SOURCES}")
            sys.exit(1)
    logger.info(f"Loading sources {sources}")

    cfg = load_config("config.ini")
    engine = get_engine(cfg["DB"]["url"])

    umls_parser = MetaThesaurusParser(**cfg["MetaThesaurusParser"])
    norm = Normalizer(umls_parser=umls_parser, **cfg["Normalizer"])
    relationship_mapper = RelationshipMapper(
        umls_parser=umls_parser, **cfg["RelationshipMapper"]
    )

    if "ggponc" in sources:
        gg = Ggponc(
            **cfg["GGPONC"], relationship_mapper=relationship_mapper, engine=engine
        )
        gg.download()
        gg.parse(drop_existing=True)

    if "civic" in sources:
        cv = Civic(normalizer=norm, engine=engine)
        cv.download()
        cv.parse(drop_existing=True)

    if "pubmed" in sources:
        pm = Pubmed(**cfg["Pubmed"], normalizer=norm, engine=engine)
        pm.download()
        pm.parse(drop_existing=True)

    if "pubmed_update" in sources:
        pm = Pubmed(**cfg["Pubmed"], normalizer=norm, engine=engine)
        assert file is not None, "Please provide a file path for the update"
        pm.downloaded_files = [Path(file)]
        pm.parse(drop_existing=False)

    if "aact" in sources:
        ct = Aact(**cfg["AACT"], normalizer=norm, engine=engine)
        ct.download()
        ct.parse(drop_existing=True)

    if "literature" in sources:
        lit = GgponcLiterature(**cfg["GGPONC"], engine=engine)
        lit.parse(drop_existing=True)

    # set significance flags
    if "flags" in sources:
        flagger = SignificanceFlagger(**cfg["SignificanceFlagger"], engine=engine)
        flagger.flag_aact()
        flagger.flag_civic()
        flagger.flag_pubmed()

    # create the Entity-Relation Diagram
    # create_erd("erd.png", engine=engine)


if __name__ == "__main__":
    main()
