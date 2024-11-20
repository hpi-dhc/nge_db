"""A module for modeling the TrialStreamer data for the DB."""

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from integration.orm.base import Base


class Trial(Base):
    """ORM class that represents a trial."""

    __tablename__ = "ts_trial"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pm_id: Mapped[int]
    title: Mapped[str] = mapped_column(Text())
    abstract: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    year: Mapped[int]
    punchline: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    num_randomized: Mapped[Optional[int]]
    low_rsg_bias: Mapped[Optional[bool]]
    low_ac_bias: Mapped[Optional[bool]]
    low_bpp_bias: Mapped[Optional[bool]]
    prob_low_rob: Mapped[Optional[float]]
    journal: Mapped[str] = mapped_column(String(512))

    populations: Mapped[
        Optional[list["integration.orm.trialstreamer.Population"]]  # noqa: F821
    ] = relationship(back_populates="trial")
    interventions: Mapped[
        Optional[list["integration.orm.trialstreamer.Intervention"]]  # noqa: F821
    ] = relationship(back_populates="trial")
    outcomes: Mapped[
        Optional[list["integration.orm.trialstreamer.Outcome"]]  # noqa: F821
    ] = relationship(back_populates="trial")
    mesh_populations: Mapped[
        Optional[list["integration.orm.trialstreamer.MeshPopulation"]]  # noqa: F821
    ] = relationship(back_populates="trial")
    mesh_interventions: Mapped[
        Optional[list["integration.orm.trialstreamer.MeshIntervention"]]  # noqa: F821
    ] = relationship(back_populates="trial")
    mesh_outcomes: Mapped[
        Optional[list["integration.orm.trialstreamer.MeshOutcome"]]  # noqa: F821
    ] = relationship(back_populates="trial")

    flags: Mapped["integration.orm.trialstreamer.Flags"] = relationship(  # noqa: F821
        back_populates="trial"
    )


class Population(Base):
    """ORM class representing study populations."""

    __tablename__ = "ts_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    population: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="populations"
    )


class Intervention(Base):
    """ORM class representing an intervention."""

    __tablename__ = "ts_intervention"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    intervention: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="interventions"
    )


class Outcome(Base):
    """ORM class representing an outcome."""

    __tablename__ = "ts_outcome"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    outcome: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="outcomes"
    )


class MeshPopulation(Base):
    """ORM class representing MeSH-coded population information."""

    __tablename__ = "ts_mesh_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[str] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_populations"
    )


class MeshIntervention(Base):
    """ORM class representing MeSH-coded intervention information."""

    __tablename__ = "ts_mesh_intervention"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[str] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_interventions"
    )


class MeshOutcome(Base):
    """ORM class representing MeSH-coded outcome information."""

    __tablename__ = "ts_mesh_outcome"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ts_trial.id"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[str] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_outcomes"
    )


class Flags(Base):
    """ORM class that represents boolean flags."""

    __tablename__ = "ts_flags"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("ts_trial.id"), index=True)

    has_significant_finding: Mapped[Optional[bool]] = mapped_column(default=None)

    trial: Mapped["integration.orm.trialstreamer.Trial"] = relationship(  # noqa: F821
        back_populates="flags"
    )


def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                Trial.__table__,
                Population.__table__,
                Intervention.__table__,
                Outcome.__table__,
                MeshPopulation.__table__,
                MeshIntervention.__table__,
                MeshOutcome.__table__,
                Flags.__table__,
            ],
        )
    Base.metadata.create_all(engine)
