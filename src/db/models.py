"""SQLAlchemy 2.0 ORM models — Aethelburg ontology v1.1.0 (FollowTheMoney v3.x compatible)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

try:
    from geoalchemy2 import Geometry
except ImportError:
    def Geometry(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]  # noqa: N802 - stands in for geoalchemy2.Geometry
        return None

try:
    from sqlalchemy import (
        BigInteger,
        Boolean,
        CheckConstraint,
        Computed,
        Date,
        Float,
        ForeignKey,
        Integer,
        SmallInteger,
        String,
        Text,
        UniqueConstraint,
        text,
    )
    from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False
    Mapped = Optional  # type: ignore[misc,assignment]

    class DeclarativeBase:  # type: ignore[no-redef]
        metadata = None

    def _noop(*args: Any, **kwargs: Any) -> Any:
        return None

    BigInteger = Boolean = CheckConstraint = Computed = Date = Float = ForeignKey = _noop  # type: ignore[assignment]
    Integer = SmallInteger = String = Text = UniqueConstraint = text = ARRAY = JSONB = UUID = _noop  # type: ignore[assignment]
    mapped_column = relationship = _noop  # type: ignore[assignment]


class Base(DeclarativeBase):
    pass


# ── Core FollowTheMoney Entity Table (ADR-007 & Ontology Layer 1) ──────


class FtmEntity(Base):
    """Canonical FollowTheMoney entity storage (nodes & edge entities)."""

    __tablename__ = "ftm_entities"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    schema: Mapped[str] = mapped_column(String(64), nullable=False)
    caption: Mapped[str] = mapped_column(String(500), nullable=False)
    is_edge: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    source_prop: Mapped[str | None] = mapped_column(String(64))
    target_prop: Mapped[str | None] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(128))
    target_id: Mapped[str | None] = mapped_column(String(128))
    properties: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    datasets: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    referents: Mapped[list[str] | None] = mapped_column(ARRAY(String(128)))
    first_seen: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen: Mapped[datetime] = mapped_column(server_default=text("now()"))
    provenance_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


# ── Schema public ──────────────────────────────────────────────────────


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_name: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(50))
    source_version: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    record_count: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("source_name", "source_version", name="uq_source_version"),)


class GeoPostcodeCentroid(Base):
    __tablename__ = "geo_postcode_centroids"

    postcode: Mapped[str] = mapped_column(String(10), primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    geom = mapped_column(
        Geometry("POINT", srid=4326),
        Computed("ST_SetSRID(ST_MakePoint(lon, lat), 4326)", persisted=True),
        nullable=True,
    )
    admin_district: Mapped[str | None] = mapped_column(String(100))
    admin_county: Mapped[str | None] = mapped_column(String(100))
    admin_ward: Mapped[str | None] = mapped_column(String(100))
    nuts_level1: Mapped[str | None] = mapped_column(String(10))
    country_code: Mapped[str | None] = mapped_column(String(1))
    lsoa11: Mapped[str | None] = mapped_column(String(15))
    msoa11: Mapped[str | None] = mapped_column(String(15))
    laua: Mapped[str | None] = mapped_column(String(15))
    ward: Mapped[str | None] = mapped_column(String(15))
    ctry: Mapped[str | None] = mapped_column(String(1))
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class Address(Base):
    """Registered and operational addresses (FtM: Address)."""

    __tablename__ = "addresses"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # FtM ID
    address_fingerprint: Mapped[str] = mapped_column(String(200), unique=True)
    full_address: Mapped[str] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(100))
    county: Mapped[str | None] = mapped_column(String(100))
    postcode: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    geocoding_source: Mapped[str | None] = mapped_column(String(30))
    company_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class Company(Base):
    __tablename__ = "companies"

    company_number: Mapped[str] = mapped_column(String(8), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(500))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Company'"))
    # Registered address
    reg_address_care_of: Mapped[str | None] = mapped_column(String(200))
    reg_address_po_box: Mapped[str | None] = mapped_column(String(50))
    reg_address_line1: Mapped[str | None] = mapped_column(String(300))
    reg_address_line2: Mapped[str | None] = mapped_column(String(300))
    reg_address_post_town: Mapped[str | None] = mapped_column(String(100))
    reg_address_county: Mapped[str | None] = mapped_column(String(100))
    reg_address_country: Mapped[str | None] = mapped_column(String(100))
    reg_address_postcode: Mapped[str | None] = mapped_column(String(10))
    # Type and status
    company_category: Mapped[str | None] = mapped_column(String(100))
    company_status: Mapped[str | None] = mapped_column(String(50))
    country_of_origin: Mapped[str | None] = mapped_column(String(100))
    # Dates
    dissolution_date: Mapped[date | None] = mapped_column(Date)
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    # Accounts
    accounts_account_ref_day: Mapped[int | None] = mapped_column(SmallInteger)
    accounts_account_ref_month: Mapped[int | None] = mapped_column(SmallInteger)
    accounts_account_category: Mapped[str | None] = mapped_column(String(50))
    accounts_account_date: Mapped[date | None] = mapped_column(Date)
    accounts_next_due_date: Mapped[date | None] = mapped_column(Date)
    accounts_last_made_up_date: Mapped[date | None] = mapped_column(Date)
    # Returns
    returns_next_due_date: Mapped[date | None] = mapped_column(Date)
    returns_last_made_up_date: Mapped[date | None] = mapped_column(Date)
    # Mortgages
    mortgages_num_charges: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_outstanding: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_part_satisfied: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    mortgages_num_satisfied: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    # SIC text
    sic_text_1: Mapped[str | None] = mapped_column(String(200))
    sic_text_2: Mapped[str | None] = mapped_column(String(200))
    sic_text_3: Mapped[str | None] = mapped_column(String(200))
    sic_text_4: Mapped[str | None] = mapped_column(String(200))
    # SIC codes
    sic_code_1: Mapped[str | None] = mapped_column(String(10))
    sic_code_2: Mapped[str | None] = mapped_column(String(10))
    sic_code_3: Mapped[str | None] = mapped_column(String(10))
    sic_code_4: Mapped[str | None] = mapped_column(String(10))
    # Limited partnerships
    lp_num_gen_partners: Mapped[int | None] = mapped_column(SmallInteger)
    lp_num_lim_partners: Mapped[int | None] = mapped_column(SmallInteger)
    # URI
    ch_uri: Mapped[str | None] = mapped_column(String(200))
    # Previous names (1-10)
    prev_name_1_date: Mapped[date | None] = mapped_column(Date)
    prev_name_1: Mapped[str | None] = mapped_column(String(500))
    prev_name_2_date: Mapped[date | None] = mapped_column(Date)
    prev_name_2: Mapped[str | None] = mapped_column(String(500))
    prev_name_3_date: Mapped[date | None] = mapped_column(Date)
    prev_name_3: Mapped[str | None] = mapped_column(String(500))
    prev_name_4_date: Mapped[date | None] = mapped_column(Date)
    prev_name_4: Mapped[str | None] = mapped_column(String(500))
    prev_name_5_date: Mapped[date | None] = mapped_column(Date)
    prev_name_5: Mapped[str | None] = mapped_column(String(500))
    prev_name_6_date: Mapped[date | None] = mapped_column(Date)
    prev_name_6: Mapped[str | None] = mapped_column(String(500))
    prev_name_7_date: Mapped[date | None] = mapped_column(Date)
    prev_name_7: Mapped[str | None] = mapped_column(String(500))
    prev_name_8_date: Mapped[date | None] = mapped_column(Date)
    prev_name_8: Mapped[str | None] = mapped_column(String(500))
    prev_name_9_date: Mapped[date | None] = mapped_column(Date)
    prev_name_9: Mapped[str | None] = mapped_column(String(500))
    prev_name_10_date: Mapped[date | None] = mapped_column(Date)
    prev_name_10: Mapped[str | None] = mapped_column(String(500))
    # Confirmation statement
    conf_stmt_next_due_date: Mapped[date | None] = mapped_column(Date)
    conf_stmt_last_made_up_date: Mapped[date | None] = mapped_column(Date)
    # Aethelburg computed fields
    address_fingerprint: Mapped[str | None] = mapped_column(String(200))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    risk_score: Mapped[float | None] = mapped_column(Float, server_default=text("0.0"))
    ft3_techniques: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)))
    officers_fetched_at: Mapped[datetime | None] = mapped_column()
    is_flagged: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    # Provenance
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="company")
    directorships: Mapped[list[Directorship]] = relationship(back_populates="company")
    risk_flags: Mapped[list[RiskFlag]] = relationship(back_populates="company")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Person'"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    forename: Mapped[str | None] = mapped_column(String(200))
    surname: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(50))
    nationality: Mapped[str | None] = mapped_column(String(100))
    country_of_residence: Mapped[str | None] = mapped_column(String(100))
    dob_month: Mapped[int | None] = mapped_column(SmallInteger)
    dob_year: Mapped[int | None] = mapped_column(SmallInteger)
    is_pep: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    pep_source: Mapped[str | None] = mapped_column(String(50))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="person")
    directorships: Mapped[list[Directorship]] = relationship(back_populates="person")


class LegalEntity(Base):
    __tablename__ = "legal_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'LegalEntity'"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    jurisdiction: Mapped[str | None] = mapped_column(String(50))
    company_number_foreign: Mapped[str | None] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(80))
    is_offshore: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    psc_ownerships: Mapped[list[PscOwnership]] = relationship(back_populates="legal_entity")


class PscOwnership(Base):
    __tablename__ = "psc_ownerships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Ownership'"))
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id"))
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_entities.id"))
    psc_kind: Mapped[str | None] = mapped_column(String(80))
    nature_of_control: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    notified_on: Mapped[date | None] = mapped_column(Date)
    ceased_on: Mapped[date | None] = mapped_column(Date)
    is_ceased: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    is_super_secure: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    is_sanctioned: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "(person_id IS NOT NULL AND legal_entity_id IS NULL) OR "
            "(person_id IS NULL AND legal_entity_id IS NOT NULL) OR "
            "(is_super_secure = true AND person_id IS NULL AND legal_entity_id IS NULL)",
            name="chk_psc_owner",
        ),
    )

    company: Mapped[Company] = relationship(back_populates="psc_ownerships")
    person: Mapped[Person | None] = relationship(back_populates="psc_ownerships")
    legal_entity: Mapped[LegalEntity | None] = relationship(back_populates="psc_ownerships")


class Directorship(Base):
    __tablename__ = "directorships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Directorship'"))
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("persons.id"))
    officer_role: Mapped[str | None] = mapped_column(String(100))
    appointed_on: Mapped[date | None] = mapped_column(Date)
    resigned_on: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    occupation: Mapped[str | None] = mapped_column(String(200))
    nationality: Mapped[str | None] = mapped_column(String(100))
    country_of_residence: Mapped[str | None] = mapped_column(String(100))
    api_person_id: Mapped[str | None] = mapped_column(String(100))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    fetched_via: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    company: Mapped[Company] = relationship(back_populates="directorships")
    person: Mapped[Person | None] = relationship(back_populates="directorships")


class OfficersFetchQueue(Base):
    __tablename__ = "officers_fetch_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    priority: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("5"))
    status: Mapped[str | None] = mapped_column(String(20), server_default=text("'pending'"))
    enqueued_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column()
    error_msg: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("company_number", "status"),)


class StreamingCheckpoint(Base):
    __tablename__ = "streaming_checkpoints"

    stream_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_event_id: Mapped[str | None] = mapped_column(String(100))
    last_seq_num: Mapped[int | None] = mapped_column(BigInteger)
    last_event_at: Mapped[datetime | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Sanction(Base):
    __tablename__ = "sanctions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Sanction'"))
    unique_id: Mapped[str | None] = mapped_column(String(50))
    ofsi_group_id: Mapped[str | None] = mapped_column(String(50))
    un_reference_number: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    registration_numbers: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    regime_name: Mapped[str | None] = mapped_column(String(300))
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    countries: Mapped[list[str] | None] = mapped_column(ARRAY(String(10)))
    list_name: Mapped[str | None] = mapped_column(String(100))
    listed_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(50))
    opensanctions_id: Mapped[str | None] = mapped_column(String(100))
    raw_properties: Mapped[dict | None] = mapped_column(JSONB)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class PepPerson(Base):
    __tablename__ = "pep_persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Person'"))
    name: Mapped[str] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(10))
    party: Mapped[str | None] = mapped_column(String(200))
    legislature: Mapped[str | None] = mapped_column(String(200))
    mandate_start: Mapped[date | None] = mapped_column(Date)
    mandate_end: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    pep_source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class NameVariant(Base):
    __tablename__ = "name_variants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(128))  # Supports company_number, UUID, ICIJ node_id, or ftm_id
    entity_type: Mapped[str] = mapped_column(String(30))
    variant_text: Mapped[str] = mapped_column(String(500))
    fingerprint: Mapped[str | None] = mapped_column(String(500))
    phonetic_key: Mapped[str | None] = mapped_column(String(200))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    variant_type: Mapped[str | None] = mapped_column(String(30))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))

    __table_args__ = (UniqueConstraint("entity_id", "entity_type", "fingerprint"),)


class IcijEntity(Base):
    __tablename__ = "icij_entities"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Company'"))
    name: Mapped[str | None] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    original_name: Mapped[str | None] = mapped_column(String(500))
    former_name: Mapped[str | None] = mapped_column(String(500))
    jurisdiction: Mapped[str | None] = mapped_column(String(200))
    jurisdiction_description: Mapped[str | None] = mapped_column(String(200))
    company_type: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    internal_id: Mapped[str | None] = mapped_column(String(100))
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    inactivation_date: Mapped[date | None] = mapped_column(Date)
    struck_off_date: Mapped[date | None] = mapped_column(Date)
    dorm_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(100))
    service_provider: Mapped[str | None] = mapped_column(String(200))
    ibc_ruc: Mapped[str | None] = mapped_column(String(100))
    country_codes: Mapped[str | None] = mapped_column(String(200))
    countries: Mapped[str | None] = mapped_column(String(500))
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    valid_until: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijOfficer(Base):
    __tablename__ = "icij_officers"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Person'"))
    name: Mapped[str | None] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    icij_id: Mapped[str | None] = mapped_column(String(100))
    valid_until: Mapped[str | None] = mapped_column(String(100))
    country_codes: Mapped[str | None] = mapped_column(String(200))
    countries: Mapped[str | None] = mapped_column(String(500))
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijIntermediary(Base):
    __tablename__ = "icij_intermediaries"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'LegalEntity'"))
    name: Mapped[str | None] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str | None] = mapped_column(String(100))
    internal_id: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    countries: Mapped[str | None] = mapped_column(String(500))
    country_codes: Mapped[str | None] = mapped_column(String(200))
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    valid_until: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijAddress(Base):
    __tablename__ = "icij_addresses"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'Address'"))
    address: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(String(500))
    address_fingerprint: Mapped[str | None] = mapped_column(String(200))
    countries: Mapped[str | None] = mapped_column(String(500))
    country_codes: Mapped[str | None] = mapped_column(String(200))
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    valid_until: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijOther(Base):
    __tablename__ = "icij_others"

    node_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'LegalEntity'"))
    name: Mapped[str | None] = mapped_column(String(500))
    name_fingerprint: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(200))
    incorporation_date: Mapped[date | None] = mapped_column(Date)
    struck_off_date: Mapped[date | None] = mapped_column(Date)
    closed_date: Mapped[date | None] = mapped_column(Date)
    jurisdiction: Mapped[str | None] = mapped_column(String(200))
    jurisdiction_description: Mapped[str | None] = mapped_column(String(200))
    countries: Mapped[str | None] = mapped_column(String(500))
    country_codes: Mapped[str | None] = mapped_column(String(200))
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    valid_until: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class IcijRelationship(Base):
    __tablename__ = "icij_relationships"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str | None] = mapped_column(String(64))
    node_id_start: Mapped[str] = mapped_column(String(50))
    node_id_end: Mapped[str] = mapped_column(String(50))
    rel_type: Mapped[str | None] = mapped_column(String(100))
    link: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_id_list: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("data_sources.id"))


class RiskFlag(Base):
    __tablename__ = "risk_flags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_number: Mapped[str] = mapped_column(String(8), ForeignKey("companies.company_number"))
    ft3_technique: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10))
    score_contribution: Mapped[float] = mapped_column(Float, server_default=text("0.0"))
    grade: Mapped[str | None] = mapped_column(String(4))  # UNODC 4x4 e.g. 'A1', 'B2', 'C3'
    evidence: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'"))
    source_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    __table_args__ = (UniqueConstraint("company_number", "ft3_technique"),)

    company: Mapped[Company] = relationship(back_populates="risk_flags")


class EntityEvent(Base):
    __tablename__ = "entity_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(128))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    source: Mapped[str | None] = mapped_column(String(50))


# ── Schema casework ────────────────────────────────────────────────────


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), server_default=text("'open'"))
    priority: Mapped[str | None] = mapped_column(String(10), server_default=text("'medium'"))
    classification: Mapped[str] = mapped_column(String(30), server_default=text("'TLP:AMBER'"))
    investigator: Mapped[str | None] = mapped_column(String(200), server_default=text("'Analyst'"))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column()

    entities: Mapped[list[InvestigationEntity]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    annotations: Mapped[list[Annotation]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    manual_links: Mapped[list[ManualLink]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    snapshots: Mapped[list[VisualSnapshot]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    saved_queries: Mapped[list[SavedQuery]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    events: Mapped[list[InvestigationEvent]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    reports: Mapped[list[GeneratedReport]] = relationship(back_populates="investigation", cascade="all, delete-orphan")


class InvestigationEntity(Base):
    __tablename__ = "investigation_entities"
    __table_args__ = (
        UniqueConstraint("investigation_id", "entity_type", "entity_id"),
        {"schema": "casework"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(128))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(500))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    risk_score: Mapped[float | None] = mapped_column(Float)
    flags: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)))
    investigator_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    added_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    notes: Mapped[str | None] = mapped_column(Text)

    investigation: Mapped[Investigation] = relationship(back_populates="entities")


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    entity_type: Mapped[str | None] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    annotation_text: Mapped[str] = mapped_column(Text)
    annotation_type: Mapped[str | None] = mapped_column(String(30), server_default=text("'note'"))  # note | hypothesis | finding | caveat | source
    grade: Mapped[str | None] = mapped_column(String(4))  # UNODC 4x4 e.g. 'A1', 'B2'
    is_pinned: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="annotations")


class ManualLink(Base):
    __tablename__ = "manual_links"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    ftm_id: Mapped[str | None] = mapped_column(String(128))
    ftm_schema: Mapped[str] = mapped_column(String(64), server_default=text("'UnknownLink'"))
    from_entity_type: Mapped[str] = mapped_column(String(30))
    from_entity_id: Mapped[str] = mapped_column(String(128))
    to_entity_type: Mapped[str] = mapped_column(String(30))
    to_entity_id: Mapped[str] = mapped_column(String(128))
    link_type: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float, server_default=text("0.7"))
    confidence_level: Mapped[str] = mapped_column(String(20), server_default=text("'moderate'"))  # high | moderate | low
    grade: Mapped[str | None] = mapped_column(String(4), server_default=text("'B2'"))  # UNODC 4x4 code
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation | None] = relationship(back_populates="manual_links")


class VisualSnapshot(Base):
    __tablename__ = "visual_snapshots"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    snapshot_type: Mapped[str] = mapped_column(String(30), server_default=text("'network_graph'"))
    title: Mapped[str | None] = mapped_column(String(300))
    snapshot_png_b64: Mapped[str | None] = mapped_column(Text)
    viewport_state: Mapped[dict | None] = mapped_column(JSONB)
    graph_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="snapshots")


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300))
    query_type: Mapped[str] = mapped_column(String(30))
    query_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation | None] = relationship(back_populates="saved_queries")


class InvestigationEvent(Base):
    __tablename__ = "investigation_events"
    __table_args__ = {"schema": "casework"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    investigation: Mapped[Investigation] = relationship(back_populates="events")


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    __table_args__ = {"schema": "casework"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("casework.investigations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    generated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    generation_params: Mapped[dict | None] = mapped_column(JSONB, server_default=text("'{}'"))

    investigation: Mapped[Investigation | None] = relationship(back_populates="reports")
