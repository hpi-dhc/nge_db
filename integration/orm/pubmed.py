"""A module for modeling the Pubmed data for the DB."""

import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, Integer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from integration.orm.base import Base


class Trial(Base):
    """ORM class that represents a trial."""

    __tablename__ = "pm_trial"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pm_id: Mapped[int] = mapped_column(Integer(), index=True)
    status: Mapped[str] = mapped_column(String(512))
    indexing_method: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(Text())
    authors: Mapped[str] = mapped_column(Text())
    abstract: Mapped[Optional[str]] = mapped_column(Text())
    abstract_formatted: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    publication_date: Mapped[Optional[datetime.date]]
    num_randomized: Mapped[Optional[int]]
    journal: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ftp_fn: Mapped[str] = mapped_column(String(512))

    publication_types: Mapped[
        Optional[list["integration.orm.pubmed.PublicationType"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    references: Mapped[
        Optional[list["integration.orm.pubmed.Reference"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    dois: Mapped[Optional[list["integration.orm.pubmed.Doi"]]] = (  # noqa: F821
        relationship(
            back_populates="trial",
            cascade="all, delete, delete-orphan",
            passive_deletes=True,
        )
    )
    populations: Mapped[
        Optional[list["integration.orm.pubmed.Population"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    interventions: Mapped[
        Optional[list["integration.orm.pubmed.Intervention"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    outcomes: Mapped[Optional[list["integration.orm.pubmed.Outcome"]]] = (  # noqa: F821
        relationship(
            back_populates="trial",
            cascade="all, delete, delete-orphan",
            passive_deletes=True,
        )
    )
    mesh_terms: Mapped[
        Optional[list["integration.orm.pubmed.MeshTerm"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    umls_population: Mapped[
        Optional[list["integration.orm.pubmed.UmlsPopulation"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    umls_interventions: Mapped[
        Optional[list["integration.orm.pubmed.UmlsIntervention"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    umls_outcomes: Mapped[
        Optional[list["integration.orm.pubmed.UmlsOutcome"]]  # noqa: F821
    ] = relationship(
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )
    flags: Mapped["integration.orm.pubmed.Flags"] = relationship(  # noqa: F821
        back_populates="trial",
        cascade="all, delete, delete-orphan",
        passive_deletes=True,
    )


class Population(Base):
    """ORM class representing study populations."""

    __tablename__ = "pm_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    population: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="populations"
    )


class Intervention(Base):
    """ORM class representing an intervention."""

    __tablename__ = "pm_intervention"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    intervention: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="interventions"
    )


class Outcome(Base):
    """ORM class representing an outcome."""

    __tablename__ = "pm_outcome"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    outcome: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="outcomes"
    )


class Doi(Base):
    """ORM class representing a DOI."""

    __tablename__ = "pm_doi"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    doi: Mapped[str] = mapped_column(String(512))

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="dois"
    )


class PublicationType(Base):
    """ORM class representing a DOI."""

    __tablename__ = "pm_publication_type"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    publication_type: Mapped[str] = mapped_column(String(512))

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="publication_types"
    )


class Reference(Base):
    """ORM class representing a DOI."""

    __tablename__ = "pm_reference"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    nct_id: Mapped[str] = mapped_column(String(15))

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="references"
    )


class MeshTerm(Base):
    """ORM class representing MeSH-coded population information."""

    __tablename__ = "pm_mesh_term"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    mesh_term: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_terms"
    )


class UmlsPopulation(Base):
    """ORM class representing UMLS-coded population information."""

    __tablename__ = "pm_umls_population"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    mention: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="umls_population"
    )


class UmlsIntervention(Base):
    """ORM class representing UMLS-coded intervention information."""

    __tablename__ = "pm_umls_intervention"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    mention: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="umls_interventions"
    )


class UmlsOutcome(Base):
    """ORM class representing UMLS-coded outcome information."""

    __tablename__ = "pm_umls_outcome"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), nullable=False, index=True
    )

    cui: Mapped[str] = mapped_column(String(8), index=True)
    cui_term: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    mention: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="umls_outcomes"
    )


class Flags(Base):
    """ORM class that represents boolean flags."""

    __tablename__ = "pm_flags"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("pm_trial.id", ondelete="CASCADE"), index=True
    )

    has_significant_finding: Mapped[Optional[bool]] = mapped_column(default=None)

    trial: Mapped["integration.orm.pubmed.Trial"] = relationship(  # noqa: F821
        back_populates="flags"
    )


def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                Trial.__table__,
                Doi.__table__,
                PublicationType.__table__,
                Reference.__table__,
                Population.__table__,
                Intervention.__table__,
                Outcome.__table__,
                MeshTerm.__table__,
                UmlsPopulation.__table__,
                UmlsIntervention.__table__,
                UmlsOutcome.__table__,
                Flags.__table__,
            ],
        )
    Base.metadata.create_all(engine)
