from integration.orm.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text
from sqlalchemy.engine import Engine

class GgponcLiteratureReference(Base):

    __tablename__ = "gg_literature"
    id: Mapped[int] = mapped_column(primary_key=True)

    citation: Mapped[str] = mapped_column(Text(), nullable=True)
    ref_id: Mapped[int] = mapped_column(nullable=False)
    guideline_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(Text())
    pm_id: Mapped[int] = mapped_column(nullable=True)

def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                GgponcLiteratureReference.__table__,
            ],
        )
    Base.metadata.create_all(engine)