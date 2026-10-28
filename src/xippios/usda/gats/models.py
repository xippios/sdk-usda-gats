"""Pydantic models mirroring upstream's payloads, one ``UpstreamModel`` per object.

Conventions §3 and ``/add-endpoint`` give the rules.

The snapshot types every GATS response as ``object`` and defines no schemas
(``definitions`` is empty in ``docs/upstream/openapi/portal-document.json``). The record
shapes below therefore come from the recorded answers, each named in its model's
docstring; every field is an assumption from that fixture, recorded 2026-10-25 or
2026-10-26. No GATS record carries a personal identifier. Upstream's camelCase names are
snake_cased as they read: ``hS10Code`` is ``hs10_code``, ``hS6Code`` ``hs6_code``,
``isO3Code`` ``iso3_code``, ``censusUOMId1`` ``census_uom_id1``, ``isAgCommodity``
``is_ag_commodity``; upstream's ``endDtate`` is ``end_dtate``, its spelling kept.
Year-month codes (``"202608"``) and the UN Trade years (``"2019"``) stay text: upstream
sends them as digit strings, a year-month without a day, and nothing is combined into a
date here. Quantities and values arrive as JSON
numbers and become ``Decimal`` (ADR-0008); unit-of-measure and customs-district ids stay
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
    "Commodity",
    "Country",
    "CustomsDistrict",
    "CustomsDistrictExport",
    "CustomsDistrictImport",
    "DataReleaseInfo",
    "HS6Commodity",
    "ProductType",
    "Region",
    "UNTradeDataReleaseInfo",
    "UNTradeRecord",
    "UnitOfMeasure",
]


# The docstring below lands in the release-dates MCP tool's input schema
# (``$defs.ProductType.description``), so it speaks to agents and the provenance lives
# here. The members are the codes of ``productType``, the field of the release records
# that tells the two lists apart, so a member equals ``DataReleaseInfo.product_type`` of
# the records it names (ADR-0008: upstream enumerations become ``StrEnum`` with upstream's
# values). Established by the recorded lists, not by the snapshot, which documents no
# record shape: every record of
# ``tests/fixtures/GATSData_GetCensusExportDataReleaseInfo/all.json`` carries ``"X"``,
# every record of ``tests/fixtures/GATSData_GetCensusImportDataReleaseInfo/all.json``
# ``"M"`` (716 each, recorded 2026-10-25). ``X`` selects
# ``GATSData_GetCensusExportDataReleaseInfo`` (``census/data/exports/dataReleaseDates``),
# ``M`` ``GATSData_GetCensusImportDataReleaseInfo``
# (``census/data/imports/dataReleaseDates``). Re-exports have no release-date operation in
# the snapshot, so there is no member for them. The UN Trade release lists carry the same
# two codes: every record of
# ``tests/fixtures/GATSData_GetUNTradeExportDataReleaseInfo/all.json`` ``"X"`` (3,796),
# every record of ``tests/fixtures/GATSData_GetUNTradeImportDataReleaseInfo/all.json``
# ``"M"`` (3,832, recorded 2026-10-26); ``X`` selects
# ``GATSData_GetUNTradeExportDataReleaseInfo``, ``M``
# ``GATSData_GetUNTradeImportDataReleaseInfo``, and the snapshot has no UN re-export
# release list either. Both release-dates tools take the enum, so the class docstring
# names both programs. The enum names the known codes only:
# ``DataReleaseInfo.product_type`` and ``UNTradeDataReleaseInfo.product_type`` stay
# ``str``, so a code upstream adds later parses instead of failing the answer.
class ProductType(StrEnum):
    """Which release-date list: ``X`` the exports list, ``M`` the imports list.

    Upstream's ``productType`` codes, the same for the US Census release lists (one
    record per month) and the UN Trade release lists (one record per reporter and
    year). Re-exports have no release-date list on either side.
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


class Region(UpstreamModel):
    """One record of ``GATSData_GetRegions`` (``GET /api/gats/regions``).

    Shape from ``tests/fixtures/GATSData_GetRegions/all.json`` (15 records, every one with
    both fields, no code twice, ``"R05"`` to ``"R99"`` in order). Upstream: "Use it to
    associate Region Name with Country records obtained by querying Country end point";
    every ``Country.region_code`` recorded is one of the 15.

    Attributes:
        region_code: ``regionCode``, e.g. ``"R40"``; the ``regionCode`` of
            ``GATSData_GetCountries``.
        region_name: ``regionName``, e.g. ``"East Asia"``.
    """

    region_code: str = Field(validation_alias="regionCode")
    region_name: str = Field(validation_alias="regionName")


class Commodity(UpstreamModel):
    """One record of ``GATSData_GetCommodities`` (``GET /api/gats/commodities``).

    Shape from ``tests/fixtures/GATSData_GetCommodities/all.json``, recorded 2026-10-26:
    24,936 records, 7,592,916 bytes of JSON (8,383,278 as a fixture file), every one with
    all eleven fields.
    Upstream: "Commodity record contains HS10 Code and Census and FAS Unit Of Measure
    IDS". A record names a code, the month it starts, a product type, a short name, a
    description, an agricultural flag and four unit-of-measure ids; it carries no FAS
    product group and no other grouping. A code is not unique: 20,702 distinct codes in
    24,397 distinct code and product type pairs, and a pair repeats with a later
    ``startDate`` (``"0207410000"`` under ``"M"`` is chicken cuts from ``"198901"`` and
    ducks from ``"201201"``); code, product type and start month are unique together. In
    code order.

    Attributes:
        hs10_code: ``hS10Code``, ten characters as upstream sends them, e.g.
            ``"0103910000"``; the 4,548 records of product types ``"T"`` and ``"B"``
            carry seven digits and three spaces (``"0011010   "``), kept as sent.
        start_date: ``startDate``, a year and month as six digits, e.g. ``"198901"``.
        end_dtate: ``endDtate``, upstream's spelling; ``null`` in every recorded record,
            typed as text or ``None`` by assumption.
        product_type: ``productType``, ``"X"`` (5,919 records), ``"M"`` (14,469), ``"T"``
            (2,704) or ``"B"`` (1,844); the snapshot does not say what they stand for.
            Every HS10 code of the recorded export and re-export answers is listed under
            ``"X"``, every one of the recorded import answers under ``"M"``. Text, like
            ``DataReleaseInfo.product_type``.
        commodity_name: ``commodityName``, at most 16 characters as recorded, e.g.
            ``"SWINE,<50KG EACH"``.
        commodity_description: ``commodityDescription``, e.g. ``"SWINE, LIVE, NESOI,
            WEIGHING LESS THAN 50 KG EACH  (NO)"``; ``None`` where upstream sends
            ``null`` (every ``"T"`` and ``"B"`` record and seven others).
        is_ag_commodity: ``isAgCommodity``, ``True`` in 13,870 records, ``False`` in
            11,066.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``78``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``78``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``78``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``78``.
    """

    hs10_code: str = Field(validation_alias="hS10Code")
    start_date: str = Field(validation_alias="startDate")
    end_dtate: str | None = Field(validation_alias="endDtate")
    product_type: str = Field(validation_alias="productType")
    commodity_name: str = Field(validation_alias="commodityName")
    commodity_description: str | None = Field(validation_alias="commodityDescription")
    is_ag_commodity: bool = Field(validation_alias="isAgCommodity")
    census_uom_id1: int = Field(validation_alias="censusUOMId1")
    census_uom_id2: int = Field(validation_alias="censusUOMId2")
    fas_converted_uom_id: int = Field(validation_alias="fasConvertedUOMId")
    fas_non_converted_uom_id: int = Field(validation_alias="fasNonConvertedUOMId")


class HS6Commodity(UpstreamModel):
    """One record of ``GATSData_GetHS6Commodities`` (``GET /api/gats/HS6Commodities``).

    Shape from ``tests/fixtures/GATSData_GetHS6Commodities/all.json``: 2,909 records,
    661,146 bytes of JSON, every one with all seven fields and none ``null``, one per HS6
    code, no code twice, in code order. Upstream: "a list of Commodities classified at a
    broader level of classification, at the HS6 Level, as opposed to HS10 Level. Use this
    to correlate the Import, Export and Re-export data records obtained by querying UN
    Trade Data." A record names the code, a name, a description and four unit-of-measure
    ids: no product type, start month or agricultural flag, no grouping field. The first
    six digits of every HS10 code in the recorded Census answers are a listed code.

    Attributes:
        hs6_code: ``hS6Code``, six digits as text, e.g. ``"010110"``.
        commodity_name: ``commodityName``, e.g. ``"Purebred Breeding Animal"``.
        commodity_description: ``commodityDescription``, e.g.
            ``"Purebred Breeding Animal"``; equal to the name in 1,376 records.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``78``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``78``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``78``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``78``.
    """

    hs6_code: str = Field(validation_alias="hS6Code")
    commodity_name: str = Field(validation_alias="commodityName")
    commodity_description: str = Field(validation_alias="commodityDescription")
    census_uom_id1: int = Field(validation_alias="censusUOMId1")
    census_uom_id2: int = Field(validation_alias="censusUOMId2")
    fas_converted_uom_id: int = Field(validation_alias="fasConvertedUOMId")
    fas_non_converted_uom_id: int = Field(validation_alias="fasNonConvertedUOMId")


class UnitOfMeasure(UpstreamModel):
    """One record of ``GATSData_GetUnitsOfMeasure`` (``GET /api/gats/unitsOfMeasure``).

    Shape from ``tests/fixtures/GATSData_GetUnitsOfMeasure/all.json``: 108 records, every
    one with all four fields, ids ``0`` to ``107`` in order without a gap. Upstream: "Use
    this to match against Units Of Measure IDs in the Import and Export records to get
    the name of the Unit of Measure"; every unit-of-measure id in the recorded data and
    commodity answers is listed. An id is unique, a code is not: ``"CRT"``
    (``"Crates"``) is id ``33`` and id ``105``.

    Attributes:
        unit_of_measure_id: ``unitOfMeasureId``, e.g. ``47``; the id the
            ``census_uom_id1`` and other unit fields hold.
        unit_of_measure_code: ``unitOfMeasureCode``, e.g. ``"KG"``.
        unit_of_measure_name: ``unitOfMeasureName``, e.g. ``"Kilograms"``.
        unit_of_measure_description: ``unitOfMeasureDescription``, e.g.
            ``"Kilograms"``; equal to the name in every recorded record.
    """

    unit_of_measure_id: int = Field(validation_alias="unitOfMeasureId")
    unit_of_measure_code: str = Field(validation_alias="unitOfMeasureCode")
    unit_of_measure_name: str = Field(validation_alias="unitOfMeasureName")
    unit_of_measure_description: str = Field(validation_alias="unitOfMeasureDescription")


class CustomsDistrict(UpstreamModel):
    """One record of ``GATSData_GetCustomsDistricts`` (``GET /api/gats/customsDistricts``).

    Shape from ``tests/fixtures/GATSData_GetCustomsDistricts/all.json``: 53 records, every
    one with all four fields, ids from ``0`` to ``99`` in order, with gaps. Upstream: "US
    Customs Districts, the point of Entry and Exit for the Commodity Imports and
    Exports." A record names an id, a name and the district's region, one of five; no
    code besides the id, no port. Id ``0`` is ``"Z UNKNOW CDIST CODES"``; ids ``60``,
    ``70``, ``80`` and ``99`` are ``"VESSELS-POWER/AFLOAT"``, ``"SHIPMENTS UNDER $251"``,
    ``"MAIL SHIPMENTS"`` and ``"MILITARY SHIPMENTS"``.

    Attributes:
        customs_district_id: ``customsDistrictId``, e.g. ``10``; the id the
            customs-district data records carry.
        customs_district_name: ``customsDistrictName``, e.g. ``"NEW YORK, N.Y."``.
        customs_district_region_code: ``customsDistrictRegionCode``, ``"EC"``, ``"GL"``,
            ``"GP"``, ``"WC"`` or ``"OP"``.
        customs_district_region_name: ``customsDistrictRegionName``, e.g.
            ``"EAST COAST DISTRICTS"``; one name per region code.
    """

    customs_district_id: int = Field(validation_alias="customsDistrictId")
    customs_district_name: str = Field(validation_alias="customsDistrictName")
    customs_district_region_code: str = Field(validation_alias="customsDistrictRegionCode")
    customs_district_region_name: str = Field(validation_alias="customsDistrictRegionName")


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
    partner. The UN Trade lists answer another record, one per reporter and year
    (``UNTradeDataReleaseInfo``).

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
    which unit is not documented. ``GATSData_GetCensusReExports``
    (``censusReExports/partnerCode/...``) answers the same record, the same ten fields in
    the same order (``tests/fixtures/GATSData_GetCensusReExports/IC_2026_8.json``, 12
    records for Iceland, August 2026).

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
    Like every field of every record here, the five come from the fixture, since the
    snapshot documents no record field; they are kept as upstream sends them and nothing
    is derived from them.

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


class CustomsDistrictExport(UpstreamModel):
    """One record of the customs-district exports and re-exports.

    ``GATSData_GetCustomsDistrictsExports`` (``customsDistrictExports/partnerCode/...``)
    and ``GATSData_GetCustomsDistrictsReExports``
    (``customsDistrictReExports/partnerCode/...``) answer the same record. Shape from
    ``tests/fixtures/GATSData_GetCustomsDistrictsExports/IC_2026_8.json`` (107 records,
    Iceland, August 2026), ``.../CH_2026_8.json`` (1,697 records, China) and
    ``tests/fixtures/GATSData_GetCustomsDistrictsReExports/IC_2026_8.json`` (13 records):
    every record with all eleven fields, ``customsDistrictId`` first, then the ten fields
    of ``CensusExport`` in its order. One record per district and HS10 code, no pair
    twice; the district is named by its id alone, an id of ``GATSData_GetCustomsDistricts``.
    As recorded for China and for Iceland's re-exports, the records of one HS10 code add
    up, over the districts, to that code's record in ``GATSData_GetCensusExports`` or
    ``GATSData_GetCensusReExports`` (value and both quantities, the same unit ids).

    Attributes:
        customs_district_id: ``customsDistrictId``, e.g. ``1`` (``"PORTLAND,MAINE"``).
        date: ``date``, the year and month as six digits, e.g. ``"202608"``.
        country_code: ``countryCode``, the partner, e.g. ``"IC"``.
        hs10_code: ``hS10Code``, ten digits as text, e.g. ``"0713202000"``.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``47``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``47``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``70``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``70``.
        quantity1: ``quantity1``, e.g. ``Decimal("1162.0")``.
        quantity2: ``quantity2``, e.g. ``Decimal("0.0")``.
        value: ``value``, e.g. ``Decimal("6905.0")``; the snapshot names no currency.
    """

    customs_district_id: int = Field(validation_alias="customsDistrictId")
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


class CustomsDistrictImport(UpstreamModel):
    """One record of ``GATSData_GetCustomsDistrictsImports``.

    Path ``customsDistrictImports/partnerCode/...``. Shape from
    ``tests/fixtures/GATSData_GetCustomsDistrictsImports/IC_2026_8.json``: 123 records for
    Iceland (``"IC"``), August 2026, every record with all sixteen fields,
    ``customsDistrictId`` first, then the fifteen fields of ``CensusImport`` in its order.
    One record per district and HS10 code, no pair twice, 21 districts and 74 codes; the
    district is named by its id alone, an id of ``GATSData_GetCustomsDistricts``.

    Attributes:
        customs_district_id: ``customsDistrictId``, e.g. ``1`` (``"PORTLAND,MAINE"``).
        consumption_quantity1: ``consumptionQuantity1``, e.g. ``Decimal("571053.0")``.
        consumption_quantity2: ``consumptionQuantity2``, e.g. ``Decimal("0.0")``.
        consumption_value: ``consumptionValue``, e.g. ``Decimal("4814084.0")``.
        consumption_cif_value: ``consumptionCIFValue``, e.g. ``Decimal("4985562.0")``.
        cif_value: ``cifValue``, e.g. ``Decimal("171478.0")``.
        date: ``date``, the year and month as six digits, e.g. ``"202608"``.
        country_code: ``countryCode``, the partner, e.g. ``"IC"``.
        hs10_code: ``hS10Code``, ten digits as text, e.g. ``"0302140003"``.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id, e.g. ``47``; ``0`` occurs.
        census_uom_id2: ``censusUOMId2``, e.g. ``47``.
        fas_converted_uom_id: ``fasConvertedUOMId``, e.g. ``70``.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``70``.
        quantity1: ``quantity1``, e.g. ``Decimal("571053.0")``.
        quantity2: ``quantity2``, e.g. ``Decimal("0.0")``.
        value: ``value``, e.g. ``Decimal("4814084.0")``; the snapshot names no currency.
    """

    customs_district_id: int = Field(validation_alias="customsDistrictId")
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


class UNTradeDataReleaseInfo(UpstreamModel):
    """One record of the UN Trade release-date lists.

    ``GATSData_GetUNTradeExportDataReleaseInfo``
    (``GET /api/gats/UNTrade/data/exports/dataReleaseDates``) and
    ``GATSData_GetUNTradeImportDataReleaseInfo``
    (``GET /api/gats/UNTrade/data/imports/dataReleaseDates``) answer the same record. Shape
    from ``tests/fixtures/GATSData_GetUNTradeExportDataReleaseInfo/all.json`` (3,796
    records, 206 reporters) and
    ``tests/fixtures/GATSData_GetUNTradeImportDataReleaseInfo/all.json`` (3,832 records,
    207 reporters), recorded 2026-10-26: every record with all four fields, none ``null``,
    one per reporter and statistical year, no pair twice, years ``"1989"`` to ``"2019"``,
    newest year first and reporters in code order within a year. It differs from the
    Census ``DataReleaseInfo`` in its first field, ``statisticalYear`` for
    ``statisticalYearMonth``, and in being per reporter. Every ``reporterCode`` is a code
    of ``GATSData_GetCountries``; eleven are codes the countries list marks discontinued,
    and nine of those are listed for years after their ``discontinuedOn`` (``"NO"``,
    Norway, ``"198712"``, listed to ``"2018"``), their same-name successors (``"N3"``)
    never. The newest ``releaseTimeStamp`` is ``2021-01-18T01:25:58`` in the exports list
    and ``2021-01-18T01:27:44`` in the imports list.

    Attributes:
        statistical_year: ``statisticalYear``, the year as four digits, e.g. ``"2019"``;
            the same form as ``UNTradeRecord.year``.
        product_type: ``productType``, ``"X"`` in every exports record and ``"M"`` in
            every imports record, the codes ``ProductType`` names; text, so that an
            unknown code does not fail the answer.
        reporter_code: ``reporterCode``, a GATS country code, e.g. ``"IC"`` (Iceland).
        release_time_stamp: ``releaseTimeStamp``, e.g. ``2020-06-03T05:50:46``: a date
            and a time to the second without a time zone, kept naive as upstream sends it.
    """

    statistical_year: str = Field(validation_alias="statisticalYear")
    product_type: str = Field(validation_alias="productType")
    reporter_code: str = Field(validation_alias="reporterCode")
    release_time_stamp: datetime = Field(validation_alias="releaseTimeStamp")


class UNTradeRecord(UpstreamModel):
    """One record of the UN Trade exports, imports and re-exports.

    ``GATSData_GetUNTradeExports``, ``GATSData_GetUNTradeImports`` and
    ``GATSData_GetUNTradeReExports`` (``UNTrade{Exports|Imports|ReExports}/reporterCode/
    {reporterCode}/year/{year}``) answer the same record, the same eleven fields in the
    same order, every record with all of them and none ``null``. Shape from
    ``tests/fixtures/GATSData_GetUNTradeExports/IC_2019.json`` (3,980 records, Iceland,
    2019), ``tests/fixtures/GATSData_GetUNTradeImports/TP_2019.json`` (2,377 records, Sao
    Tome and Principe) and ``tests/fixtures/GATSData_GetUNTradeReExports/MC_2019.json``
    (421 records, Macau), recorded 2026-10-26. The snapshot: "a list of records of
    Commodity Export data as reported by UN COMTrade for a given year. UN COMTrade reports
    data on a yearly basis at a HS6 Code Level." A record names its year, reporter,
    partner and HS6 code and four unit-of-measure ids; one record per partner and HS6
    code, no pair twice, in partner and then HS6 code order. The codes are GATS's own,
    nothing here is UN Comtrade's: every reporter and partner code recorded is a code of
    ``GATSData_GetCountries``, among them codes the countries list marks discontinued
    long before the year (``"NO"``, Norway, ``"198712"``) and never their same-name
    successors, and every HS6 code is a code of ``GATSData_GetHS6Commodities``, which
    reaches beyond HS chapters 01 to 24 (``"611011"``, ``"Sweaters & Simil. Articles,
    Knit/crochet Of Wool"``, in Iceland's exports). Which quantity is in which unit is not
    documented; in every recorded record both Census unit ids are ``0`` (``"NONE"``) and
    ``fasConvertedUOMId`` is ``47`` (``"KG"``).

    Attributes:
        year: ``year``, the year as four digits, e.g. ``"2019"``.
        reporter_country_code: ``reporterCountryCode``, the reporter, e.g. ``"IC"``.
        partner_country_code: ``partnerCountryCode``, the partner, e.g. ``"15"``
            (``"Areas, not elsewhere specified"``), ``"US"``.
        hs6_code: ``hS6Code``, six digits as text, e.g. ``"070700"``.
        census_uom_id1: ``censusUOMId1``, a unit-of-measure id; ``0`` in every recorded
            record.
        census_uom_id2: ``censusUOMId2``; ``0`` in every recorded record.
        fas_converted_uom_id: ``fasConvertedUOMId``; ``47`` in every recorded record.
        fas_non_converted_uom_id: ``fasNonConvertedUOMId``, e.g. ``47``, ``78``, ``95``.
        quantity1: ``quantity1``, e.g. ``Decimal("29051.0")``; fractions occur
            (``Decimal("582.3")``).
        quantity2: ``quantity2``, e.g. ``Decimal("29051.0")``.
        value: ``value``, e.g. ``Decimal("73524.0")``; the snapshot names no currency.
    """

    year: str = Field(validation_alias="year")
    reporter_country_code: str = Field(validation_alias="reporterCountryCode")
    partner_country_code: str = Field(validation_alias="partnerCountryCode")
    hs6_code: str = Field(validation_alias="hS6Code")
    census_uom_id1: int = Field(validation_alias="censusUOMId1")
    census_uom_id2: int = Field(validation_alias="censusUOMId2")
    fas_converted_uom_id: int = Field(validation_alias="fasConvertedUOMId")
    fas_non_converted_uom_id: int = Field(validation_alias="fasNonConvertedUOMId")
    quantity1: Decimal = Field(validation_alias="quantity1")
    quantity2: Decimal = Field(validation_alias="quantity2")
    value: Decimal = Field(validation_alias="value")
