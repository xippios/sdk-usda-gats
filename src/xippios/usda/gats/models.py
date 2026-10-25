"""Pydantic models mirroring USDA FAS Global Agricultural Trade System payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. Where upstream spells a field differently,
``Field(validation_alias=...)`` accepts that spelling on input; never ``alias=``, which the
adapters would serialise, handing agents the upstream spelling. Within-source hygiene only:
dates become ``datetime.date``, numbers become numbers, upstream enumerations become
``StrEnum``, and an enumeration of integer ids ``IntEnum``. No cross-source normalisation
(ADR-0003): an upstream concept stays an upstream concept.

These read models stay faithful, documented personal identifiers included (``ssn``,
``iban`` and their like). The projections tasks return leave those out, a write task does
not echo one in ``meta.request``, and fixtures never carry their values (ADR-0017).

The snapshot types every GATS response as ``object`` and defines no schemas
(``definitions`` is empty in ``docs/upstream/openapi/portal-document.json``). The record
shapes below therefore come from the recorded answers, each named in its model's
docstring; every field is an assumption from that fixture, recorded 2026-10-25. No GATS
record carries a personal identifier. Upstream's camelCase names are snake_cased as they
read: ``hS10Code`` is ``hs10_code``, ``isO3Code`` is ``iso3_code``, ``censusUOMId1`` is
``census_uom_id1``. Year-month codes (``"202608"``) stay text: upstream sends them as
digit strings without a day, and nothing is combined into a date here. Quantities and
values arrive as JSON numbers and become ``Decimal`` (ADR-0008); unit-of-measure ids stay
plain ``int``.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field
from xippios.core import UpstreamModel

__all__ = [
    "CensusExport",
    "CensusImport",
    "Country",
    "DataReleaseInfo",
    "ProductType",
]


class ProductType(StrEnum):
    """Upstream's code for a Census release-date list: ``X`` exports, ``M`` imports.

    The members are the codes of ``productType``, the field of the release records that
    tells the two lists apart, so a member equals ``DataReleaseInfo.product_type`` of the
    records it names (ADR-0008: upstream enumerations become ``StrEnum`` with upstream's
    values). Established by the recorded lists, not by the snapshot, which documents no
    record shape: every record of
    ``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json`` carries ``"X"``,
    every record of ``tests/fixtures/GATSData_GetCensusImportDataReleaseInfo/all.json``
    ``"M"`` (716 each, recorded 2026-10-25). ``X`` selects
    ``GATSData_GetCensusExportDataReleaseInfo``
    (``census/data/exports/dataReleaseDates``), ``M``
    ``GATSData_GetCensusImportDataReleaseInfo`` (``census/data/imports/dataReleaseDates``).
    Re-exports have no release-date operation in the snapshot, so there is no member for
    them. The UN Trade release lists are not recorded; whether they carry the same codes
    is not established.

    The enum names the known codes only: ``DataReleaseInfo.product_type`` stays ``str``,
    so a code upstream adds later parses instead of failing the answer.
    """

    X = "X"
    M = "M"


class Country(UpstreamModel):
    """One record of ``GATSData_GetCountries`` (``GET /api/gats/countries``).

    Shape from ``tests/fixtures/GATSData_GetCountries/all.json`` (322 records, every one
    with all eight fields; 26 with a ``discontinuedOn``, 79 without a GENC code, 66 whose
    ``countryParentCode`` differs from their own code).

    Attributes:
        country_code: ``countryCode``, two characters, letters or digits, e.g. ``"CH"``
            (China), ``"01"`` (``"Caribbean,nes"``); the partner code of the Census data
            operations.
        region_code: ``regionCode``, e.g. ``"R40"``; the snapshot points to
            ``GATSData_GetRegions`` for its name.
        country_parent_code: ``countryParentCode``, a ``countryCode``, e.g. ``"CH"`` for
            China itself, ``"AS"`` for Heard Island and McDonald Islands (``"HM"``).
        country_name: ``countryName``, e.g. ``"China"``.
        description: ``description``; ``null`` in every recorded record, typed as text
            or ``None`` by assumption.
        iso3_code: ``isO3Code``, three characters, e.g. ``"CHN"``; also set for
            aggregates (``"X21"`` for ``"Caribbean,nes"``).
        discontinued_on: ``discontinuedOn``, a year and month as six digits, e.g.
            ``"198712"``; ``None`` where upstream sends ``null`` (the code is current).
        genc_code: ``gencCode``, three letters, e.g. ``"CHN"``; ``None`` where upstream
            sends ``null``.
    """

    country_code: str = Field(validation_alias="countryCode")
    region_code: str = Field(validation_alias="regionCode")
    country_parent_code: str = Field(validation_alias="countryParentCode")
    country_name: str = Field(validation_alias="countryName")
    description: str | None = Field(validation_alias="description")
    iso3_code: str = Field(validation_alias="isO3Code")
    discontinued_on: str | None = Field(validation_alias="discontinuedOn")
    genc_code: str | None = Field(validation_alias="gencCode")


class DataReleaseInfo(UpstreamModel):
    """One record of the Census release-date lists.

    ``GATSData_GetCensusExportDataReleaseInfo``
    (``GET /api/gats/census/data/exports/dataReleaseDates``) and
    ``GATSData_GetCensusImportDataReleaseInfo``
    (``GET /api/gats/census/data/imports/dataReleaseDates``) answer the same record. Shape
    from ``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json`` and
    ``tests/fixtures/GATSData_GetCensusImportDataReleaseInfo/all.json``: 716 records each,
    one per statistical month from ``"196701"`` to ``"202608"``, newest first, no month
    twice, ``reporterCode`` ``"US"`` in every record. A record is per month, not per
    partner. The UN Trade lists are not recorded and may differ.

    Attributes:
        statistical_year_month: ``statisticalYearMonth``, a year and month as six digits,
            e.g. ``"202608"``; the same form as ``CensusExport.date``.
        product_type: ``productType``, ``"X"`` in every exports record and ``"M"`` in
            every imports record, the codes ``ProductType`` names; text, so that an
            unknown code does not fail the answer.
        reporter_code: ``reporterCode``, e.g. ``"US"``.
        release_time_stamp: ``releaseTimeStamp``, e.g. ``2026-10-06T08:00:00``: a date
            and a time without a time zone, kept naive as upstream sends it.
    """

    statistical_year_month: str = Field(validation_alias="statisticalYearMonth")
    product_type: str = Field(validation_alias="productType")
    reporter_code: str = Field(validation_alias="reporterCode")
    release_time_stamp: datetime = Field(validation_alias="releaseTimeStamp")


class CensusExport(UpstreamModel):
    """One record of ``GATSData_GetCensusExports`` (``censusExports/partnerCode/...``).

    Shape from ``tests/fixtures/GATSData_GetCensusExports/CH_2026_8.json``: 777 records for
    China (``"CH"``), August 2026, one per HS10 code, no code twice, every record with all
    ten fields. The record names its partner, month and HS10 code and four
    unit-of-measure ids; it names no customs district and no FAS product group. The
    snapshot points to ``GATSData_GetUnitsOfMeasure`` for the units; which quantity is in
    which unit is not documented.

    Attributes:
        date: ``date``, the year and month as six digits, e.g. ``"202608"``.
        country_code: ``countryCode``, the partner, e.g. ``"CH"``.
        hs10_code: ``hS10Code``, ten digits as text, e.g. ``"0103910000"``.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``78``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``78``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``78``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``78``.
        quantity1: ``quantity1``, e.g. ``Decimal("394.0")``.
        quantity2: ``quantity2``, e.g. ``Decimal("0.0")``.
        value: ``value``, e.g. ``Decimal("20672.0")``; the snapshot names no currency.
    """

    date: str = Field(validation_alias="date")
    country_code: str = Field(validation_alias="countryCode")
    hs10_code: str = Field(validation_alias="hS10Code")
    census_uom_id1: int = Field(validation_alias="censusUOMId1")
    census_uom_id2: int = Field(validation_alias="censusUOMId2")
    fas_converted_uom_id: int = Field(validation_alias="fasConvertedUOMId")
    fas_non_converted_uom_id: int = Field(validation_alias="fasNonConvertedUOMId")
    quantity1: Decimal = Field(validation_alias="quantity1")
    quantity2: Decimal = Field(validation_alias="quantity2")
    value: Decimal = Field(validation_alias="value")


class CensusImport(UpstreamModel):
    """One record of ``GATSData_GetCensusImport`` (``censusImports/partnerCode/...``).

    Shape from ``tests/fixtures/GATSData_GetCensusImport/CH_2026_8.json``: 3,294 records for
    China (``"CH"``), August 2026, one per HS10 code, no code twice, every record with all
    fifteen fields. It carries every field of ``CensusExport`` and five more, sent first:
    ``consumptionQuantity1``, ``consumptionQuantity2``, ``consumptionValue``,
    ``consumptionCIFValue`` and ``cifValue``. No customs district, no FAS product group.
    The snapshot documents none of the five; they are kept as upstream sends them and
    nothing is derived from them.

    Attributes:
        consumption_quantity1: ``consumptionQuantity1``, e.g. ``Decimal("9640.0")``.
        consumption_quantity2: ``consumptionQuantity2``, e.g. ``Decimal("0.0")``.
        consumption_value: ``consumptionValue``, e.g. ``Decimal("1111254.0")``.
        consumption_cif_value: ``consumptionCIFValue``, e.g. ``Decimal("1166564.0")``.
        cif_value: ``cifValue``, e.g. ``Decimal("55310.0")``.
        date: ``date``, the year and month as six digits, e.g. ``"202608"``.
        country_code: ``countryCode``, the partner, e.g. ``"CH"``.
        hs10_code: ``hS10Code``, ten digits as text, e.g. ``"0106199195"``.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``78``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``78``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``78``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``78``.
        quantity1: ``quantity1``, e.g. ``Decimal("9640.0")``.
        quantity2: ``quantity2``, e.g. ``Decimal("0.0")``.
        value: ``value``, e.g. ``Decimal("1111254.0")``; the snapshot names no currency.
    """

    consumption_quantity1: Decimal = Field(validation_alias="consumptionQuantity1")
    consumption_quantity2: Decimal = Field(validation_alias="consumptionQuantity2")
    consumption_value: Decimal = Field(validation_alias="consumptionValue")
    consumption_cif_value: Decimal = Field(validation_alias="consumptionCIFValue")
    cif_value: Decimal = Field(validation_alias="cifValue")
    date: str = Field(validation_alias="date")
    country_code: str = Field(validation_alias="countryCode")
    hs10_code: str = Field(validation_alias="hS10Code")
    census_uom_id1: int = Field(validation_alias="censusUOMId1")
    census_uom_id2: int = Field(validation_alias="censusUOMId2")
    fas_converted_uom_id: int = Field(validation_alias="fasConvertedUOMId")
    fas_non_converted_uom_id: int = Field(validation_alias="fasNonConvertedUOMId")
    quantity1: Decimal = Field(validation_alias="quantity1")
    quantity2: Decimal = Field(validation_alias="quantity2")
    value: Decimal = Field(validation_alias="value")
