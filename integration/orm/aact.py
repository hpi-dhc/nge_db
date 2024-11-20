"""A module for modeling the ClinicalTrials data for the DB."""

import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from integration.orm.base import Base


class Trial(Base):
    """ORM class that represents a trial."""

    __tablename__ = "ct_trial"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # info
    nct_id: Mapped[str] = mapped_column(String(15))
    title_brief: Mapped[str] = mapped_column(Text())
    title_official: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    study_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    acronym: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    overall_status: Mapped[str] = mapped_column(String(512))
    why_stopped: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    phase: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    number_of_groups: Mapped[Optional[int]]
    number_of_arms: Mapped[Optional[int]]
    # enrollment
    enrollment: Mapped[Optional[int]]
    enrollment_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    # dates
    date_start: Mapped[Optional[datetime.date]]
    date_start_type: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    date_completion: Mapped[Optional[datetime.date]]
    date_completion_type: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    date_last_update: Mapped[Optional[datetime.date]]
    date_last_update_type: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    date_results_first_posted: Mapped[Optional[datetime.date]]
    date_results_first_posted_type: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    # relations
    references: Mapped[
        list["integration.orm.aact.Reference"]  # noqa: F821
    ] = relationship(back_populates="trial")
    eligibilities: Mapped[
        list["integration.orm.aact.Eligibility"]  # noqa: F821
    ] = relationship(back_populates="trial")
    conditions: Mapped[
        list["integration.orm.aact.Condition"]  # noqa: F821
    ] = relationship(back_populates="trial")
    interventions: Mapped[
        list["integration.orm.aact.Intervention"]  # noqa: F821
    ] = relationship(back_populates="trial")
    outcomes: Mapped[list["integration.orm.aact.Outcome"]] = relationship(  # noqa: F821
        back_populates="trial"
    )
    mesh_conditions: Mapped[
        list["integration.orm.aact.MeshCondition"]  # noqa: F821
    ] = relationship(back_populates="trial")
    mesh_interventions: Mapped[
        list["integration.orm.aact.MeshIntervention"]  # noqa: F821
    ] = relationship(back_populates="trial")

    flags: Mapped["integration.orm.aact.Flags"] = relationship(  # noqa: F821
        back_populates="trial"
    )


class Reference(Base):
    """ORM class that represents references to Pubmed."""

    __tablename__ = "ct_references"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    pm_id: Mapped[int]
    reference_type: Mapped[str] = mapped_column(String(512))

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="references"
    )


class MeshCondition(Base):
    """ORM class that represents entries from the browse_conditions table."""

    __tablename__ = "ct_mesh_conditions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    mesh_term: Mapped[str] = mapped_column(Text())
    mesh_type: Mapped[str] = mapped_column(String(512))
    cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_conditions"
    )


class MeshIntervention(Base):
    """ORM class that represents entries from the browse_interventions table."""

    __tablename__ = "ct_mesh_interventions"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    mesh_term: Mapped[str] = mapped_column(Text())
    mesh_type: Mapped[str] = mapped_column(String(512))
    cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="mesh_interventions"
    )


class Eligibility(Base):
    """ORM class that represents eligibilities."""

    __tablename__ = "ct_eligibilities"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    gender: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    minimum_age: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    maximum_age: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    healthy_volunteers: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    population: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    criteria: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="eligibilities"
    )


class Condition(Base):
    """ORM class that represents conditions."""

    __tablename__ = "ct_condition"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    condition: Mapped[str] = mapped_column(Text())

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="conditions"
    )


class Intervention(Base):
    """ORM class that represents an intervention."""

    __tablename__ = "ct_intervention"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    intervention_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="interventions"
    )


class Outcome(Base):
    """ORM class that represents primary outcomes."""

    __tablename__ = "ct_outcome"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    outcome_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    time_frame: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    population: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    analyses: Mapped[
        Optional[list["integration.orm.aact.OutcomeAnalyses"]]  # noqa: F821
    ] = relationship(back_populates="outcome")

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="outcomes"
    )


class OutcomeAnalyses(Base):
    """ORM class that represents outcome analyses."""

    __tablename__ = "ct_outcome_analyses"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    outcome_id: Mapped[int] = mapped_column(
        ForeignKey("ct_outcome.id"), nullable=False, index=True
    )

    param_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    param_value: Mapped[Optional[float]]
    p_value: Mapped[Optional[float]]
    p_value_modifier: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ci_n_sides: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ci_percent: Mapped[Optional[float]]
    ci_lower_limit: Mapped[Optional[float]]
    ci_upper_limit: Mapped[Optional[float]]
    method: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    outcome: Mapped[list["integration.orm.aact.Outcome"]] = relationship(  # noqa: F821
        back_populates="analyses"
    )


class Flags(Base):
    """ORM class that represents boolean flags."""

    __tablename__ = "ct_flags"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("ct_trial.id"), nullable=False, index=True
    )

    has_significant_finding: Mapped[Optional[bool]] = mapped_column(default=None)

    trial: Mapped["integration.orm.aact.Trial"] = relationship(  # noqa: F821
        back_populates="flags"
    )


def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                Trial.__table__,
                Reference.__table__,
                MeshCondition.__table__,
                MeshIntervention.__table__,
                Eligibility.__table__,
                Condition.__table__,
                Intervention.__table__,
                Outcome.__table__,
                OutcomeAnalyses.__table__,
                Flags.__table__,
            ],
        )
    Base.metadata.create_all(engine)
