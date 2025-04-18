import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column, relationship

from aiochemy import ActiveRecord, PKMixin, UpdateMixin


class ADemoBase(MappedAsDataclass, DeclarativeBase, ActiveRecord):
    pass


class AResident(ADemoBase, PKMixin, UpdateMixin):
    """Resident model."""

    __tablename__ = "resident"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(Text, default=None)

    # Relationship to cities via the association table
    cities: Mapped[list["ACity"]] = relationship(
        "ACity", secondary="resident_city", back_populates="residents", repr=False, init=False
    )
    # Direct relationship to the association object if needed
    city_associations: Mapped[list["AResidentCity"]] = relationship(
        "AResidentCity",
        back_populates="resident",
        cascade="all, delete-orphan",
        repr=False,
        init=False,
        overlaps="cities",  # Specify overlap
    )


class ACity(ADemoBase, PKMixin, UpdateMixin):
    """City model."""

    __tablename__ = "city"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("country.id"), default=None)
    population: Mapped[int | None] = mapped_column(Integer, default=None)

    country: Mapped["ACountry"] = relationship("ACountry", back_populates="cities", init=False, repr=False)

    # Relationship to residents via the association table
    residents: Mapped[list["AResident"]] = relationship(
        "AResident",
        secondary="resident_city",
        back_populates="cities",
        repr=False,
        init=False,
        overlaps="city_associations",  # Specify overlap
    )
    # Direct relationship to the association object if needed
    resident_associations: Mapped[list["AResidentCity"]] = relationship(
        "AResidentCity",
        back_populates="city",
        cascade="all, delete-orphan",
        repr=False,
        init=False,
        overlaps="cities,residents",  # Specify overlap
    )

    __table_args__ = (UniqueConstraint("name", "country_id", name="uq_city_name_country"),)


class ACountry(ADemoBase, PKMixin, UpdateMixin):
    """Country model."""

    __tablename__ = "country"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text, default=None)
    population: Mapped[int | None] = mapped_column(Integer, default=None)

    cities: Mapped[list["ACity"]] = relationship(
        "ACity", back_populates="country", cascade="all, delete-orphan", default_factory=list, repr=False, init=False
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_country_name"),
        UniqueConstraint("code", name="uq_country_code"),
    )


class AResidentCity(ADemoBase, PKMixin, UpdateMixin):
    """Association table between Resident and City."""

    __tablename__ = "resident_city"

    city_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("city.id"), default=None)
    resident_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resident.id"), default=None)
    main_residence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships to parent tables
    city: Mapped["ACity"] = relationship(
        "ACity", back_populates="resident_associations", init=False, repr=False, overlaps="cities,residents"
    )
    resident: Mapped["AResident"] = relationship(
        "AResident", back_populates="city_associations", init=False, repr=False, overlaps="cities,residents"
    )

    __table_args__ = (UniqueConstraint("resident_id", "city_id", name="uq_resident_city"),)
