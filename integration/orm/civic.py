"""A module for modeling the CivicDB data for the DB."""

import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from integration.orm.base import Base


class Assertion(Base):
    """ORM class that represents CivicDB."""

    __tablename__ = "cv_assertion"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("cv_evidence.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(512))
    assertion_type: Mapped[str] = mapped_column(String(512))
    assertion_direction: Mapped[str] = mapped_column(String(512))
    molecular_profile_id: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text())
    summary: Mapped[str] = mapped_column(Text())
    variant_origin: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(512))
    significance: Mapped[str] = mapped_column(String(512))
    nccn_guideline_version: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    nccn_guideline_name: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    fda_regulatory_approval: Mapped[Optional[bool]]
    fda_companion_test: Mapped[Optional[bool]]
    amp_level: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="assertions")


class Therapy(Base):
    """ORM class that represents a Civic therapy."""

    __tablename__ = "cv_therapy"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("cv_evidence.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(512))
    nci_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    therapy_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)

    evidence: Mapped["Evidence"] = relationship("Evidence", back_populates="therapies")


class Phenotype(Base):
    """ORM class that represents a phenotype."""

    __tablename__ = "cv_phenotype"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("cv_evidence.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(512))
    hpo_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(512))
    cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)

    evidence: Mapped["Evidence"] = relationship(back_populates="phenotypes")


class Evidence(Base):
    """ORM class that represents Civic evidence."""

    __tablename__ = "cv_evidence"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text())
    direction: Mapped[str] = mapped_column(String(512))
    level: Mapped[str] = mapped_column(String(512))
    type_: Mapped[str] = mapped_column(String(512))
    rating: Mapped[Optional[int]]
    significance: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(512))
    disease_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    disease_display_name: Mapped[Optional[str]] = mapped_column(
        String(512), nullable=True
    )
    disease_do_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    disease_do_id_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    disease_cui: Mapped[Optional[str]] = mapped_column(String(8), index=True)
    molecular_profile_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # evidence can have one source, but source could be tied to other evidence items
    source_id: Mapped[int] = mapped_column(ForeignKey("cv_source.id"), index=True)
    source: Mapped["Source"] = relationship()

    assertions: Mapped[list["Assertion"]] = relationship(back_populates="evidence")
    therapies: Mapped[list["Therapy"]] = relationship(back_populates="evidence")
    phenotypes: Mapped[list["Phenotype"]] = relationship(back_populates="evidence")
    


class Source(Base):
    """ORM class that represents a Civic source."""

    __tablename__ = "cv_source"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(512))
    title: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    citation: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    citation_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    asco_abstract_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    author_string: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    date_publication: Mapped[Optional[datetime.datetime]]
    pmc_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pm_id: Mapped[Optional[int]]
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    clinical_trials: Mapped[list["ClinicalTrial"]] = relationship(
        back_populates="source"
    )

    flags: Mapped["integration.orm.civic.Flags"] = relationship(  # noqa: F821
        back_populates="source"
    )

    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="source")


class ClinicalTrial(Base):
    """ORM class that represents a Civic ClinicalTrials.gov reference."""

    __tablename__ = "cv_clinical_trial"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("cv_source.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(512))
    nct_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(512))

    source: Mapped[list["Source"]] = relationship(back_populates="clinical_trials")


class Flags(Base):
    """ORM class that represents boolean flags."""

    __tablename__ = "cv_flags"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("cv_source.id"), nullable=False, index=True
    )

    has_significant_finding: Mapped[Optional[bool]] = mapped_column(default=None)

    source: Mapped["integration.orm.civic.Source"] = relationship(  # noqa: F821
        back_populates="flags"
    )


def create_metadata(engine: Engine, drop_existing: bool = False) -> None:
    """Create the schema defined by the classes in this module."""
    if drop_existing:
        Base.metadata.drop_all(
            engine,
            tables=[
                Assertion.__table__,
                Therapy.__table__,
                Phenotype.__table__,
                Evidence.__table__,
                Source.__table__,
                ClinicalTrial.__table__,
                Flags.__table__,
            ],
        )
    Base.metadata.create_all(engine)
