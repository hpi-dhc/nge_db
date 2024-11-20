"""A module for modeling the GGPONC data for the DB."""

import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from integration.orm.base import Base


class Guideline(Base):
    """ORM class that represents a clinical practice guideline (CPG)."""

    __tablename__ = "gg_guideline"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ggponc_id: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(512))
    name_en: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    text_blocks: Mapped[
        list["integration.orm.ggponc.TextBlock"]  # noqa: F821
    ] = relationship(back_populates="guideline")
    populations: Mapped[
        list["integration.orm.ggponc.Population"]  # noqa: F821
    ] = relationship(back_populates="guideline")


class TextBlock(Base):
    """ORM class that represents a CPG recommendation."""

    __tablename__ = "gg_text_block"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guideline_id: Mapped[int] = mapped_column(
        ForeignKey("gg_guideline.id"), nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(512))
    number: Mapped[Optional[str]] = mapped_column(String(512))
    sections: Mapped[str] = mapped_column(String(512))
    recommendation: Mapped[bool]
    recommendation_creation_date: Mapped[Optional[datetime.date]]
    recommendation_grade: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    edit_state: Mapped[Optional[Optional[str]]] = mapped_column(
        String(512), nullable=True
    )
    type_of_recommendation: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    strength_of_consensus: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    entities: Mapped[
        list["integration.orm.ggponc.Entity"]  # noqa: F821
    ] = relationship(back_populates="text_block")

    guideline: Mapped["integration.orm.ggponc.Guideline"] = relationship(  # noqa: F821
        back_populates="text_blocks"
    )


class Entity(Base):
    """ORM class that represents an Entity found in the CPG."""

    __tablename__ = "gg_entity"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text_block_id: Mapped[int] = mapped_column(
        ForeignKey("gg_text_block.id"), nullable=False, index=True
    )

    text: Mapped[str] = mapped_column(String(512))
    type_: Mapped[str] = mapped_column(String(512))
    start: Mapped[int]
    end: Mapped[int]
    cui: Mapped[str] = mapped_column(String(8), index=True)
    tuis: Mapped[str] = mapped_column(String(512))
    canonical: Mapped[str] = mapped_column(String(512))
    confidence: Mapped[float]

    text_block: Mapped["integration.orm.ggponc.TextBlock"] = relationship(  # noqa: F821
        back_populates="entities"
    )

    super_concepts: Mapped[
        list["integration.orm.ggponc.SuperConcept"]  # noqa: F821
    ] = relationship(back_populates="entity")


class SuperConcept(Base):
    """ORM class that represents a broader intervention concept."""

    __tablename__ = "gg_super_concept"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("gg_entity.id"), index=True)

    text: Mapped[str] = mapped_column(String(512))
    cui: Mapped[str] = mapped_column(String(8), index=True)

    entity: Mapped["integration.orm.ggponc.Entity"] = relationship(  # noqa: F821
        back_populates="super_concepts"
    )


class Population(Base):
    """ORM class that represents a population."""

    __tablename__ = "gg_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guideline_id: Mapped[int] = mapped_column(ForeignKey("gg_guideline.id"), index=True)

    cui: Mapped[str] = mapped_column(String(8), index=True)
    text: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sub_populations: Mapped[
        list["integration.orm.ggponc.SubPopulation"]  # noqa: F821
    ] = relationship(back_populates="population")

    guideline: Mapped["integration.orm.ggponc.Guideline"] = relationship(  # noqa: F821
        back_populates="populations"
    )


class SubPopulation(Base):
    """ORM class that represents a narrower population."""

    __tablename__ = "gg_sub_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    population_id: Mapped[int] = mapped_column(
        ForeignKey("gg_population.id"), index=True
    )

    text: Mapped[str] = mapped_column(String(512))
    cui: Mapped[str] = mapped_column(String(8), index=True)

    population: Mapped[
        "integration.orm.ggponc.Population"  # noqa: F821
    ] = relationship(back_populates="sub_populations")


def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                Guideline.__table__,
                TextBlock.__table__,
                Entity.__table__,
                SuperConcept.__table__,
                Population.__table__,
                SubPopulation.__table__,
            ],
        )
    Base.metadata.create_all(engine)
