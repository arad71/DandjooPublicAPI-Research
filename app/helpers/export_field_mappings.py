import dataclasses
import functools
from typing import Any, Callable, Dict, List, Optional, Sequence, Collection, Tuple, \
    Literal

from app.helpers.mongo import get_published_submission_collection, \
    get_published_submission_set_collection
from app.models.common_enums import DataType
from app.models.records import Record, EXPORT_EXCLUDED_FIELDS
from app.models.published_submissions import PublishedSubmissionInternal, \
    PublishedSubmissionVisibility
from app.models.published_submission_sets import PublishedSubmissionSetInternal
from app.settings import Settings


@dataclasses.dataclass(frozen=True)
class ExportMapping:
    """
    Represents a column/field in a Record export.

    Options specify the header for the column, and how to get the value for each row.
    """
    header: str  # Header for the column

    # Option 1: Define the Record attribute to export in this column
    attribute: Optional[str] = None
    # Option 2: Define a function to receive the Record and return the export value
    function: Optional[Callable[[Record], Any]] = None

    # Optional function to transform the value before export
    transform: Optional[Callable[[Any], Any]] = None
    # Optionally restrict this mapping to Records of certain data types
    datatypes: Optional[Collection[DataType]] = None

    def get_value(self, record: Record) -> Any:
        """Get the value to export, given a record."""
        # Check datatype
        if self.datatypes is not None:
            if record.logical_datatype not in self.datatypes:
                return None

        # Get export value
        if self.attribute is not None:
            export_value = getattr(record, self.attribute)
        elif self.function is not None:
            export_value = self.function(record)
        else:
            export_value = None

        # Transform
        if self.transform is not None:
            export_value = self.transform(export_value)

        return export_value


# # # CSV export # # #


def get_record_csv_mapping(
    *,
    settings: Settings,
    has_sensitive_permission: bool,
) -> List[ExportMapping]:
    """
    Get the list of ExportMappings to use for Record export CSV.
    """
    get_submission_cached, get_submission_set_cached = get_cached_lookups(settings)

    field_mapping: List[ExportMapping] = [
        ExportMapping('Record_ID', 'persistent_id'),
        ExportMapping("Data type (dwc:eventType)", attribute="logical_datatype"),
        ExportMapping('Latitude (dwc:decimalLatitude)', 'decimal_latitude'),
        ExportMapping('Longitude (dwc:decimalLongitude)', 'decimal_longitude'),
        ExportMapping('Date (dwc:eventDate)', 'event_date'),
        ExportMapping('Recorded name (dwc:scientificName)', 'scientific_name'),
        ExportMapping('Accepted name (dwc:acceptedNameUsage)', 'accepted_name_usage'),
        ExportMapping('Data provider (dwc:institutionCode)', 'institution_code'),
        ExportMapping('Nomos ID', 'nomos_id'),
        ExportMapping(
            'Dataset (dcterms:title)',
            datatypes=(DataType.SPECIES_OCCURRENCE,),
            attribute='dcterms_title',
        ),
        ExportMapping(
            "Project name (abis:project)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_name,
        ),
        ExportMapping(
            "Project ID (dwc:parentEventID)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_id,
        ),
        ExportMapping(
            "Survey name (tern:survey)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_name,
        ),
        ExportMapping(
            "Survey ID (dwc:eventID)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_id,
        ),
        ExportMapping(
            "Survey participants (dcterms:contributor)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_participants,
        ),
        ExportMapping(
            "Survey date range start (tern:survey; prov:startedAtTime)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_from_date,
        ),
        ExportMapping(
            "Survey date range end (tern:survey; prov:endedAtTime)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_to_date,
        ),
        ExportMapping(
            "Bounding box (dwc:footprintWKT)",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=functools.partial(
                get_submission_bounding_box,
                has_sensitive_permission=has_sensitive_permission,
                export_format="WKT",
            ),
        ),
        ExportMapping('Count (dwc:individualCount)', 'individual_count'),
        ExportMapping('Rights holder (dcterms:rightsHolder)', 'rights_holder'),
        ExportMapping('Method/protocol (dwc:samplingProtocol)', 'sampling_protocol'),
        ExportMapping('Conservation code (threatStatus)', 'threat_status'),
        ExportMapping('Identification basis (dwc:basisOfRecord)', 'basis_of_record'),
        ExportMapping('Field identification (dwc:verbatimIdentification)', 'verbatim_identification'),
        ExportMapping('Date identified (dwc:dateIdentified)', 'date_identified'),
        ExportMapping('Identification ambiguity (dwc:identificationQualifier)', 'identification_qualifier'),
        ExportMapping('Identification notes (dwc:identificationRemarks)', 'identification_remarks'),
        ExportMapping('Scientific name publisher (dwc:scientificNameAuthorship)', 'scientific_name_authorship'),
        ExportMapping('Taxon rank (dwc:taxonRank)', 'taxon_rank'),
        ExportMapping('Organism remarks (dwc:organismRemarks)', 'organism_remarks'),
        ExportMapping('Presence/Absence (dwc:occurrenceStatus)', 'occurrence_status'),
        ExportMapping('Preparations (dwc:preparations)', 'preparations'),
        ExportMapping('Genomic sequence information (dwc:associatedSequences)', 'associated_sequences'),
        ExportMapping('Life stage (dwc:lifeStage)', 'life_stage'),
        ExportMapping('Reproductive condition (dwc:reproductiveCondition)', 'reproductive_condition'),
        ExportMapping('Native/introduced/feral (dwc:establishmentMeans)', 'establishment_means'),
        ExportMapping('Geographic uncertainty (dwc:coordinateUncertaintyInMeters)', 'geographic_uncertainty'),
        ExportMapping('Area/locality (dwc:locality)', 'locality'),
        ExportMapping('Habitat (dwc:habitat)', 'habitat'),
        ExportMapping('Vernacular name (dwc:vernacularName)', 'vernacular_name', transform=convert_lists_for_csv_export),
        ExportMapping('Informal groups', 'informal_groups', transform=convert_lists_for_csv_export),
        ExportMapping('Kingdom (dwc:kingdom)', 'kingdom'),
        ExportMapping('Phylum (dwc:phylum)', 'phylum'),
        ExportMapping('Class (dwc:class)', 'class_'),
        ExportMapping('Order (dwc:order)', 'order'),
        ExportMapping('Family (dwc:family)', 'family'),
        ExportMapping('Taxonomic Status (dwc:taxonomicStatus)', 'taxonomic_status'),
    ]

    if any(mapping.attribute in EXPORT_EXCLUDED_FIELDS for mapping in field_mapping):
        raise Exception("CSV mapping includes fields that must not be exported")

    return field_mapping


def get_record_csv_row(record: Record, field_mapping: Sequence[ExportMapping]) -> List[Any]:
    """
    Get a Row for the Record export csv.
    """
    csv_row = [
        mapping.get_value(record)
        for mapping in field_mapping
    ]
    return csv_row


def convert_lists_for_csv_export(value: Optional[List[str]]) -> Optional[str]:
    """
    Converts specific fields containing lists into a formatted string for CSV export.
    Removes semicolons, trims white spaces, and joins list elements into a single string
    separated by semicolons.

    :param value: The value from the record to convert.
    :return: The formatted string for the CSV export.
    """
    if value is None:
        return None

    temp_list = [entry.replace(";", "").strip() for entry in value]
    return '; '.join(temp_list)


# # # geojson export # # #


def get_record_geojson_mapping(
    *,
    settings: Settings,
    has_sensitive_permission: bool,
) -> List[ExportMapping]:
    """
    Get the list of ExportMappings to use for Record export to geojson.
    """
    get_submission_cached, get_submission_set_cached = get_cached_lookups(settings)

    # For geojson, the "header" is actually used as a JSON object key
    field_mapping: List[ExportMapping] = [
        ExportMapping("id", "persistent_id"),
        ExportMapping("datatype", attribute="logical_datatype"),
        ExportMapping("date", "event_date"),
        ExportMapping("recorded_species", "scientific_name"),
        ExportMapping("kingdom", "kingdom"),
        ExportMapping("species", "accepted_name_usage"),
        ExportMapping("nomos_id", "nomos_id"),
        ExportMapping(
            "dataset",
            datatypes=(DataType.SPECIES_OCCURRENCE,),
            attribute="dcterms_title",
        ),
        ExportMapping("data_provider", "institution_code"),
        ExportMapping("conservation_status", "threat_status"),
        ExportMapping(
            "project_name",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_name,
        ),
        ExportMapping(
            "project_id",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_id,
        ),
        ExportMapping(
            "survey_name",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_name,
        ),
        ExportMapping(
            "survey_id",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_id,
        ),
        ExportMapping(
            "survey_participants",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_participants,
        ),
        ExportMapping(
            "survey_date_range_start",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_from_date,
        ),
        ExportMapping(
            "survey_date_range_end",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_to_date,
        ),
        ExportMapping(
            "survey_bounding_box",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=functools.partial(
                get_submission_bounding_box,
                has_sensitive_permission=has_sensitive_permission,
                export_format="GEOJSON",
            ),
        ),
    ]

    if any(mapping.attribute in EXPORT_EXCLUDED_FIELDS for mapping in field_mapping):
        raise Exception("geojson mapping includes fields that must not be exported")

    return field_mapping


def get_properties_for_geojson_feature(record: Record, field_mapping: Sequence[ExportMapping]) -> Dict[str, Optional[str]]:
    """
    Get a dictionary of the properties to include for each feature of a geojson export.
    """
    # For geojson, the "header" is actually used as a JSON object key
    properties = {
        mapping.header: mapping.get_value(record)
        for mapping in field_mapping
    }
    return properties


# # # Shapefile export # # #

@dataclasses.dataclass(frozen=True)
class ShapefileExportMapping(ExportMapping):
    """
    Mapping with extra options and checks for shapefile export.
    """
    shapefile_field_size: int = 50

    def __post_init__(self):
        # Check options do not exceed shapefile limits
        if len(self.header) > 10:
            raise ValueError(
                f"Shapefile header must be 10 chars or less: '{self.header}'"
            )
        if self.shapefile_field_size < 1 or self.shapefile_field_size > 254:
            raise ValueError(
                f"Invalid shapefile_field_size: {self.shapefile_field_size}"
            )


def get_record_shapefile_mapping(
    *,
    settings: Settings,
    has_sensitive_permission: bool,
) -> List[ShapefileExportMapping]:
    """
    Get the list of mappings of header titles to attribute names for shapefile export.

    Use the "header" of each mapping to populate export headers,
    and use the list of mappings with the `get_record_shapefile_row` function below
    to generate a list of attribute values for each Record to export.

    :return: The list of export mappings.
    """
    get_submission_cached, get_submission_set_cached = get_cached_lookups(settings)

    field_mapping: List[ShapefileExportMapping] = [
        ShapefileExportMapping('Record_ID', attribute='persistent_id'),
        ShapefileExportMapping("Data_type", attribute="logical_datatype"),
        ShapefileExportMapping('Latitude', attribute='decimal_latitude'),
        ShapefileExportMapping('Longitude', attribute='decimal_longitude'),
        ShapefileExportMapping('Date', attribute='event_date'),
        ShapefileExportMapping('Kingdom', attribute='kingdom'),
        ShapefileExportMapping('Rcrdd_name', attribute='scientific_name'),
        ShapefileExportMapping('Acptd_name', attribute='accepted_name_usage'),
        ShapefileExportMapping('Data_prvdr', attribute='institution_code'),
        ShapefileExportMapping('Nomos_ID', attribute='nomos_id'),
        ShapefileExportMapping(
            'Dataset',
            datatypes=(DataType.SPECIES_OCCURRENCE,),
            attribute='dcterms_title',
        ),
        ShapefileExportMapping(
            "Prjct_name",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_name,
        ),
        ShapefileExportMapping(
            "Prjct_ID",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_set_cached,
            transform=get_submission_set_id,
        ),
        ShapefileExportMapping(
            "Srvy_name",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_name,
        ),
        ShapefileExportMapping(
            "Srvy_ID",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_id,
        ),
        ShapefileExportMapping(
            "Srvy_prtcp",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_participants,
        ),
        ShapefileExportMapping(
            "Srvy_start",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_from_date,
        ),
        ShapefileExportMapping(
            "Srvy_end",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            transform=get_submission_to_date,
        ),
        ShapefileExportMapping(
            "Srvy_bbox",
            datatypes=(DataType.SYSTEMATIC_SURVEY,),
            function=get_submission_cached,
            shapefile_field_size=125,
            transform=functools.partial(
                get_submission_bounding_box,
                has_sensitive_permission=has_sensitive_permission,
                export_format="WKT",
                # limit WKT to the same size as the shapefile field.
                wkt_length_limit=125,
            ),
        ),
        ShapefileExportMapping('Count', attribute='individual_count'),
        ShapefileExportMapping('Rghts_hldr', attribute='rights_holder'),
        ShapefileExportMapping('Method', attribute='sampling_protocol'),
        ShapefileExportMapping('Csvtn_code', attribute='threat_status'),
        ShapefileExportMapping('ID_basis', attribute='basis_of_record'),
        ShapefileExportMapping('Field_ID', attribute='verbatim_identification'),
        ShapefileExportMapping('Date_IDed', attribute='date_identified'),
        ShapefileExportMapping('ID_ambgty', attribute='identification_qualifier'),
        ShapefileExportMapping('ID_notes', attribute='identification_remarks'),
        ShapefileExportMapping('Name_pblsh', attribute='scientific_name_authorship'),
        ShapefileExportMapping('Taxon_rank', attribute='taxon_rank'),
        ShapefileExportMapping('Orgnsm_rem', attribute='organism_remarks'),
        ShapefileExportMapping('Pres_Abs', attribute='occurrence_status'),
        ShapefileExportMapping('Preprtn', attribute='preparations'),
        ShapefileExportMapping('Genome_seq', attribute='associated_sequences'),
        ShapefileExportMapping('Life_stage', attribute='life_stage'),
        ShapefileExportMapping('Repr_Condt', attribute='reproductive_condition'),
        ShapefileExportMapping('Native_fer', attribute='establishment_means'),
        ShapefileExportMapping('Geo_uncert', attribute='geographic_uncertainty'),
        ShapefileExportMapping('Area_local', attribute='locality'),
        ShapefileExportMapping('Habitat', attribute='habitat'),
    ]

    if any(mapping.attribute in EXPORT_EXCLUDED_FIELDS for mapping in field_mapping):
        raise Exception("Shapefile mapping includes fields that must not be exported")

    return field_mapping


def get_record_shapefile_row(record: Record, field_mapping: Sequence[ShapefileExportMapping]) -> List[Any]:
    """
    Generate a list of attribute values for shapefile export based on the given mapping.

    :param record: The Record to export.
    :param field_mapping: A list of ExportMappings as returned by get_record_shapefile_mapping().
    :return: The list of values to write as an attribute record in the shapefile.
    """
    shapefile_row = [
        mapping.get_value(record)
        for mapping in field_mapping
    ]
    return shapefile_row


# # # Common exporter transform functions # # #

def get_submission_set_id(submission_set: Optional[PublishedSubmissionSetInternal]) -> Optional[str]:
    return submission_set.persistent_id if submission_set is not None else None


def get_submission_set_name(submission_set: Optional[PublishedSubmissionSetInternal]) -> Optional[str]:
    return submission_set.metadata.name if submission_set is not None else None


def get_submission_id(submission: Optional[PublishedSubmissionInternal]) -> Optional[str]:
    return submission.persistent_id if submission is not None else None


def get_submission_name(submission: Optional[PublishedSubmissionInternal]) -> Optional[str]:
    return submission.metadata.name if submission is not None else None


def get_submission_from_date(submission: Optional[PublishedSubmissionInternal]) -> Optional[str]:
    return submission.metadata.from_date if submission is not None else None


def get_submission_to_date(submission: Optional[PublishedSubmissionInternal]) -> Optional[str]:
    return submission.metadata.to_date if submission is not None else None


def get_submission_participants(submission: Optional[PublishedSubmissionInternal]) -> Optional[str]:
    return submission.metadata.participants if submission is not None else None


def get_submission_bounding_box(
    submission: Optional[PublishedSubmissionInternal],
    *,
    has_sensitive_permission: bool,
    export_format: Literal["WKT", "GEOJSON"],
    wkt_length_limit: Optional[int] = None,
) -> Optional[object]:
    if submission is None:
        return None

    # Don't show bounding box if survey is restricted and the user doesn't have permission
    if (
        submission.visibility == PublishedSubmissionVisibility.RESTRICTED
        and not has_sensitive_permission
    ):
        return None

    west, north = submission.metadata.bounding_box_north_west.coordinates
    east, south = submission.metadata.bounding_box_south_east.coordinates

    # For both export formats, the coordinates of the Polygon's exterior must be
    # defined in a counter-clockwise direction.

    if export_format == "WKT":
        # return Bound box in WKT (Well-Known Text) representation
        # See https://dwc.tdwg.org/terms/#dwc:footprintWKT
        
        west_str, north_str = str(west), str(north)
        east_str, south_str = str(east), str(south) 
        # Limit string representation of each coordinate to ensure the entire WKT string 
        # does not exceed the wkt_length_limit, if required.
        if wkt_length_limit is not None:
            # minus 25 for over chars in final string,
            # divide by 10 for the 10 places coords appear in final string.
            coord_limit = (wkt_length_limit - 25) // 10
            west_str, north_str = west_str[0:coord_limit], north_str[0:coord_limit]
            east_str, south_str = east_str[0:coord_limit], south_str[0:coord_limit]
        
        return (
            f"POLYGON (("
            f"{west_str} {north_str}, "
            f"{west_str} {south_str}, "
            f"{east_str} {south_str}, "
            f"{east_str} {north_str}, "
            f"{west_str} {north_str}"
            f"))"
        )

    elif export_format == "GEOJSON":
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, north],
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                ],
            ],
        }
    else:
        raise ValueError(f"Unknown bounding box export_format: '{export_format}'")


# # # Common functions to set up cached Submission and Submission Set lookups # # #


def get_cached_lookups(settings: Settings) -> (
    Tuple[
        Callable[[Record], Optional[PublishedSubmissionInternal]],
        Callable[[Record], Optional[PublishedSubmissionSetInternal]],
    ]
):
    """
    Get cached functions to get Submissions and Submission Sets for Records.

    The lifetime of the cache is tied to the lifetime of these functions,
    which is typically a single export.
    """
    submission_cache: Dict[str, Optional[PublishedSubmissionInternal]] = {}
    submission_set_cache: Dict[str, Optional[PublishedSubmissionSetInternal]] = {}
    get_submission_cached = functools.partial(
        _get_submission,
        settings=settings,
        cache=submission_cache,
    )
    get_submission_set_cached = functools.partial(
        _get_submission_set,
        settings=settings,
        cache=submission_set_cache,
        get_submission_cached=get_submission_cached,
    )

    return get_submission_cached, get_submission_set_cached


def _get_submission(
    record: Record,
    *,
    settings: Settings,
    cache: Dict[str, Optional[PublishedSubmissionInternal]],
) -> Optional[PublishedSubmissionInternal]:
    """
    Get the Submission for a record, by checking the cache and falling back to DB.
    """
    submission_id = record.submission_id
    if not submission_id:
        return None

    if submission_id not in cache:
        collection = get_published_submission_collection(settings)
        row = collection.find_one({'persistent_id': submission_id})
        submission = PublishedSubmissionInternal(**row) if row is not None else None
        cache[submission_id] = submission

    return cache[submission_id]


def _get_submission_set(
    record: Record,
    *,
    settings: Settings,
    cache: Dict[str, Optional[PublishedSubmissionInternal]],
    get_submission_cached: Callable[[Record], Optional[PublishedSubmissionInternal]],
) -> Optional[PublishedSubmissionInternal]:
    """
    Get the Submission Set for a record, by checking the cache and falling back to DB.
    """
    submission = get_submission_cached(record)
    if submission is None:
        return None

    submission_set_id = submission.submission_set_id
    if not submission_set_id:
        return None

    if submission_set_id not in cache:
        collection = get_published_submission_set_collection(settings)
        row = collection.find_one({'persistent_id': submission_set_id})
        submission_set = PublishedSubmissionSetInternal(**row) if row is not None else None
        cache[submission_set_id] = submission_set

    return cache[submission_set_id]
