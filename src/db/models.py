"""SQLAlchemy 2.0 ORM models — Aethelburg ontology v1.0.0."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Schema public ──────────────────────────────────────────────────────


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_name: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(50))
    source_version: Mapped[Optional[str]] = mapped_column(String(50))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    record_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("source_name", "source_version", name="uq_source_version"),)


class GeoPostcodeCentroid(Base):
    __tablename__ = "geo_postcode_centroids"

    postcode: Mapped[str] = mapped_column(String(10), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    admin_district: Mapped[Optional[str]] = mapped_column(String(100))
    admin_county: Mapped[Optional[str]] = mapped_column(String(100))
    admin_ward: Mapped[Optional[str]] = mapped_column(String(100))
    nuts_level1: Mapped[Optional[str]] = mapped_column(String(10))
    country_code: Mapped[Optional[str]] = mapped_column(String(1))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class Company(Base):
    __tablename__ = "companies"

    company_number: Mapped[str] = mapped_column(String(8), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(500))
    # Registered address
    reg_address_care_of: Mapped[Optional[str]] = mapped_column(String(200))
    reg_address_po_box: Mapped[Optional[str]] = mapped_column(String(50))
    reg_address_line1: Mapped[Optional[str]] = mapped_column(String(300))
    reg_address_line2: Mapped[Optional[str]] = mapped_column(String(300))
    reg_address_post_town: Mapped[Optional[str]] = mapped_column(String(100))
    reg_address_county: Mapped[Optional[str]] = mapped_column(String(100))
    reg_address_country: Mapped[Optional[str]] = mapped_column(String(100))
    reg_address_postcode: Mapped[Optional[str]] = mapped_column(String(10))
    # Type and status
    company_category: Mapped[Optional[str]] = mapped_column(String(100))
    company_status: Mapped[Optional[str]] = mapped_column(String(50))
    country_of_origin: Mapped[Optional[str]] = mapped_column(String(100))
    # Dates
    dissolution_date: Mapped[Optional[date]] = mapped_column(Date)
    incorporation_date: Mapped[Optional[date]] = mapped_column(Date)
    # Accounts
    accounts_account_ref_day: Mapped[Optional[int]] = mapped_column(SmallInteger)
    accounts_account_ref_month: Mapped[Optional[int]] = mapped_column(SmallInteger)
    accounts_account_category: Mapped[Optional[str]] = mapped_column(String(50))
    accounts_account_date: Mapped[Optional[date]] = mapped_column(Date)
    accounts_next_due_date: Mapped[Optional[date]] = mapped_column(Date)
    accounts_last_made_up_date: Mapped[Optional[date]] = mapped_column(Date)
    # Returns
    returns_next_due_date: Mapped[Optional[date]] = mapped_column(Date)
    returns_last_made_up_date: Mapped[Optional[date]] = mapped_column(Date)
    # Mortgages
    mortgages_num_charges: Mapped[Optional[int]] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_outstanding: Mapped[Optional[int]] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_part_satisfied: Mapped[Optional[int]] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_satisfied: Mapped[Optional[int]] = mapped_column(SmallInteger, server_default=text("0"))
    # SIC text
    sic_text_1: Mapped[Optional[str]] = mapped_column(String(200))
    sic_text_2: Mapped[Optional[str]] = mapped_column(String(200))
    sic_text_3: Mapped[Optional[str]] = mapped_column(String(200))
    sic_text_4: Mapped[Optional[str]] = mapped_column(String(200))
    # SIC codes
    sic_code_1: Mapped[Optional[str]] = mapped_column(String(10))
    sic_code_2: Mapped[Optional[str]] = mapped_column(String(10))
    sic_code_3: Mapped[Optional[str]] = mapped_column(String(10))
    sic_code_4: Mapped[Optional[str]] = mapped_column(String(10))
    # Limited partnerships
    lp_num_gen_partners: Mapped[Optional[int]] = mapped_column(SmallInteger)
    lp_num_lim_partners: Mapped[Optional[int]] = mapped_column(SmallInteger)
    # URI
    ch_uri: Mapped[Optional[str]] = mapped_column(String(200))
    # Previous names (1-10)
    prev_name_1_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_1: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_2_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_2: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_3_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_3: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_4_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_4: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_5_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_5: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_6_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_6: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_7_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_7: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_8_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_8: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_9_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_9: Mapped[Optional[str]] = mapped_column(String(500))
    prev_name_10_date: Mapped[Optional[date]] = mapped_column(Date)
    prev_name_10: Mapped[Optional[str]] = mapped_column(String(500))
    # Confirmation statement
    conf_stmt_next_due_date: Mapped[Optional[date]] = mapped_column(Date)
    conf_stmt_last_made_up_date: Mapped[Optional[date]] = mapped_column(Date)
    # Aethelburg computed fields
    address_fingerprint: Mapped[Optional[str]] = mapped_column(String(200))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    risk_score: Mapped[Optional[float]] = mapped_column(Float, server_default=text("0.0"))
    ft3_techniques: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(20)))
    officers_fetched_at: Mapped[Optional[datetime]] = mapped_column()
    is_flagged: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    # Provenance
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="company")
    directorships: Mapped[list[Directorship]] = relationship(back_populates="company")
    risk_flags: Mapped[list[RiskFlag]] = relationship(back_populates="company")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    forename: Mapped[Optional[str]] = mapped_column(String(200))
    surname: Mapped[Optional[str]] = mapped_column(String(200))
    title: Mapped[Optional[str]] = mapped_column(String(50))
    nationality: Mapped[Optional[str]] = mapped_column(String(100))
    country_of_residence: Mapped[Optional[str]] = mapped_column(String(100))
    dob_month: Mapped[Optional[int]] = mapped_column(SmallInteger)
    dob_year: Mapped[Optional[int]] = mapped_column(SmallInteger)
    is_pep: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    pep_source: Mapped[Optional[str]] = mapped_column(String(50))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="person")
    directorships: Mapped[list[Directorship]] = relationship(back_populates="person")


class LegalEntity(Base):
    __tablename__ = "legal_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(10))
    company_number_foreign: Mapped[Optional[str]] = mapped_column(String(100))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    is_offshore: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="legal_entity")


class PscOwnership(Base):
    __tablename__ = "psc_ownerships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    person_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id"))
    legal_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_entities.id"))
    nature_of_control: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(100)))
    notified_on: Mapped[Optional[date]] = mapped_column(Date)
    ceased_on: Mapped[Optional[date]] = mapped_column(Date)
    is_ceased: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    is_super_secure: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "(person_id IS NOT NULL AND legal_entity_id IS NULL) OR "
            "(person_id IS NULL AND legal_entity_id IS NOT NULL)",
            name="chk_psc_owner",
        ),
    )

    company: Mapped[Company] = relationship(back_populates="psc_ownerships")
    person: Mapped[Optional[Person]] = relationship(back_populates="psc_ownerships")
    legal_entity: Mapped[Optional[LegalEntity]] = relationship(back_populates="psc_ownerships")


class Directorship(Base):
    __tablename__ = "directorships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    person_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id"))
    officer_role: Mapped[Optional[str]] = mapped_column(String(100))
    appointed_on: Mapped[Optional[date]] = mapped_column(Date)
    resigned_on: Mapped[Optional[date]] = mapped_column(Date)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("true"))
    occupation: Mapped[Optional[str]] = mapped_column(String(200))
    nationality: Mapped[Optional[str]] = mapped_column(String(100))
    country_of_residence: Mapped[Optional[str]] = mapped_column(String(100))
    api_person_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    fetched_via: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    company: Mapped[Company] = relationship(back_populates="directorships")
    person: Mapped[Optional[Person]] = relationship(back_populates="directorships")


class OfficersFetchQueue(Base):
    __tablename__ = "officers_fetch_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    priority: Mapped[Optional[int]] = mapped_column(SmallInteger, server_default=text("5"))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'pending'"))
    enqueued_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    started_at: Mapped[Optional[datetime]] = mapped_column()
    completed_at: Mapped[Optional[datetime]] = mapped_column()
    error_msg: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_number", "status"),)


class StreamingCheckpoint(Base):
    __tablename__ = "streaming_checkpoints"

    stream_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    last_seq_num: Mapped[Optional[int]] = mapped_column(BigInteger)
    last_event_at: Mapped[Optional[datetime]] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Sanction(Base):
    __tablename__ = "sanctions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    aliases: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    topics: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))
    countries: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(10)))
    list_name: Mapped[Optional[str]] = mapped_column(String(100))
    listed_on: Mapped[Optional[date]] = mapped_column(Date)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    opensanctions_id: Mapped[Optional[str]] = mapped_column(String(100))
    raw_properties: Mapped[Optional[dict]] = mapped_column(JSONB)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PepPerson(Base):
    __tablename__ = "pep_persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    country: Mapped[Optional[str]] = mapped_column(String(10))
    party: Mapped[Optional[str]] = mapped_column(String(200))
    legislature: Mapped[Optional[str]] = mapped_column(String(200))
    mandate_start: Mapped[Optional[date]] = mapped_column(Date)
    mandate_end: Mapped[Optional[date]] = mapped_column(Date)
    is_current: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"))
    pep_source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class NameVariant(Base):
    __tablename__ = "name_variants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    entity_type: Mapped[str] = mapped_column(String(30))
    variant_text: Mapped[str] = mapped_column(String(500))
    fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    ftm_id: Mapped[Optional[str]] = mapped_column(String(64))
    variant_type: Mapped[Optional[str]] = mapped_column(String(30))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))

    __table_args__ = (UniqueConstraint("entity_id", "entity_type", "fingerprint"),)


class IcijEntity(Base):
    __tablename__ = "icij_entities"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    original_name: Mapped[Optional[str]] = mapped_column(String(500))
    former_name: Mapped[Optional[str]] = mapped_column(String(500))
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(200))
    jurisdiction_description: Mapped[Optional[str]] = mapped_column(String(200))
    company_type: Mapped[Optional[str]] = mapped_column(String(200))
    address: Mapped[Optional[str]] = mapped_column(Text)
    internal_id: Mapped[Optional[str]] = mapped_column(String(100))
    incorporation_date: Mapped[Optional[date]] = mapped_column(Date)
    inactivation_date: Mapped[Optional[date]] = mapped_column(Date)
    struck_off_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(String(100))
    source_id_list: Mapped[Optional[str]] = mapped_column(String(200))
    valid_until: Mapped[Optional[str]] = mapped_column(String(100))
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijOfficer(Base):
    __tablename__ = "icij_officers"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(500))
    name_fingerprint: Mapped[Optional[str]] = mapped_column(String(500))
    icij_id: Mapped[Optional[str]] = mapped_column(String(100))
    valid_until: Mapped[Optional[str]] = mapped_column(String(100))
    country_codes: Mapped[Optional[str]] = mapped_column(String(200))
    countries: Mapped[Optional[str]] = mapped_column(String(500))
    source_id_list: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijRelationship(Base):
    __tablename__ = "icij_relationships"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    node_id_start: Mapped[str] = mapped_column(String(50))
    node_id_end: Mapped[str] = mapped_column(String(50))
    rel_type: Mapped[Optional[str]] = mapped_column(String(100))
    link: Mapped[Optional[str]] = mapped_column(String(200))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    source_id_list: Mapped[Optional[str]] = mapped_column(String(200))
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    ft3_technique: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10))
    score_contribution: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    evidence: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    source_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    __table_args__ = (UniqueConstraint("company_number", "ft3_technique"),)

    company: Mapped[Company] = relationship(back_populates="risk_flags")


class EntityEvent(Base):
    __tablename__ = "entity_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(100))
    old_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    source: Mapped[Optional[str]] = mapped_column(String(50))


# ── Schema casework ────────────────────────────────────────────────────


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'open'"))
    priority: Mapped[Optional[str]] = mapped_column(String(10), server_default=text("'medium'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    closed_at: Mapped[Optional[datetime]] = mapped_column()

    entities: Mapped[list[InvestigationEntity]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    snapshots: Mapped[list[VisualSnapshot]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    events: Mapped[list[InvestigationEvent]] = relationship(back_populates="investigation", cascade="all, delete-orphan")


class InvestigationEntity(Base):
    __tablename__ = "investigation_entities"
    __table_args__ = (
        UniqueConstraint("investigation_id", "entity_type", "entity_id"),
        {"schema": "casework"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(100))
    added_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    investigation: Mapped[Investigation] = relationship(back_populates="entities")


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    entity_type: Mapped[Optional[str]] = mapped_column(String(30))
    entity_id: Mapped[Optional[str]] = mapped_column(String(100))
    annotation_text: Mapped[str] = mapped_column(Text)
    annotation_type: Mapped[Optional[str]] = mapped_column(String(30), server_default=text("'note'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="annotations")


class ManualLink(Base):
    __tablename__ = "manual_links"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="SET NULL"))
    from_entity_type: Mapped[str] = mapped_column(String(30))
    from_entity_id: Mapped[str] = mapped_column(String(100))
    to_entity_type: Mapped[str] = mapped_column(String(30))
    to_entity_id: Mapped[str] = mapped_column(String(100))
    link_type: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[Optional[float]] = mapped_column(Float, server_default=text("1.0"))
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class VisualSnapshot(Base):
    __tablename__ = "visual_snapshots"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    title: Mapped[Optional[str]] = mapped_column(String(300))
    snapshot_png_b64: Mapped[Optional[str]] = mapped_column(Text)
    graph_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="snapshots")


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    query_type: Mapped[str] = mapped_column(String(30))
    query_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class InvestigationEvent(Base):
    __tablename__ = "investigation_events"
    __table_args__ = {"schema": "casework"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="events")


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    generated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    generation_params: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))
