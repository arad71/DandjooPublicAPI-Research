from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from typing import Union, List, Optional, Tuple, FrozenSet

from bson import ObjectId
from pydantic import BaseModel, Field, root_validator, validator
from pydantic.fields import ModelField

from app.models.common_enums import DataType
from app.settings import Settings

EXPORT_EXCLUDED_FIELDS: FrozenSet[str] = frozenset([
    'location',
    'infraspecific_epithet',
    'recorded_by',
    'identified_by',
    'occurrence_id',
    'material_sample_id',
    'submission_id',
    'version',
    'last_updated',
    'obfuscated_location'
])

# valid formats for location coordinates
Point = List[float]
PointList = List[List[float]]
Polygon = List[List[List[float]]]


class Location(BaseModel):
    type: str
    coordinates: Union[Point, PointList, Polygon]


class ObfuscatedLocation(BaseModel):
    location: Location
    bounding_box: Location
    scale: float
    date_obfuscated: str
    latitude: float
    longitude: float


class BaseRecord(BaseModel):
    """
    This class contains non-darwin core terms common to public and .
    """
    # location field is created in __init__ method from darwin core decimal_latitude/decimal_longitude fields
    location: Optional[Location]
    obfuscated_location: Optional[ObfuscatedLocation]

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }

    def __init__(self, **data):
        super().__init__(**data)
        if self.location is None:
            self.location = Location(type='Point', coordinates=[self.decimal_longitude, self.decimal_latitude])


class Record(BaseRecord):
    """
    This class has all Darwin core terms that are stored in the backend, but not seen on the public interface when
    searching - they only appear in the exported csv / shapefiles. This can be loaded via DwC aliases.
    """
    # mandatory fields
    persistent_id: str  # persistent id from the source record (not the _id)
    submission_id: str
    version: int
    last_updated: Optional[str] = None
    # datatype defines which type of submission this record came from.
    # If record has no datatype, it should be considered to be SPECIES_OCCURRENCE.
    datatype: Optional[DataType] = None

    decimal_latitude: float = Field(alias='dwc:decimalLatitude')
    decimal_longitude: float = Field(alias='dwc:decimalLongitude')
    event_date: str = Field(alias='dwc:eventDate')
    scientific_name: str = Field(alias='dwc:scientificName')
    accepted_name_usage: str = Field(alias='dwc:acceptedNameUsage')
    institution_code: str = Field(alias='dwc:institutionCode')

    # Fields that are mandatory for SPECIES_OCCURRENCE records
    dcterms_title: Optional[str] = Field(alias="dcterms:title", default=None)

    # Fields that are mandatory for SYSTEMATIC_SURVEY records
    # Needs to be on record for searching by Survey Name
    submission_name: Optional[str] = Field(alias="tern:survey", default=None)
    # Needs to be on record for searching by Project Name
    submission_set_name: Optional[str] = Field(alias="abis:project", default=None)

    # optional fields
    infraspecific_epithet: Optional[str] = Field(alias='dwc:infraspecificEpithet')
    individual_count: Optional[Union[int, str]] = Field(alias='dwc:individualCount')
    rights_holder: Optional[str] = Field(alias='dwc:RightsHolder')
    sampling_protocol: Optional[str] = Field(alias='dwc:samplingProtocol')
    threat_status: Optional[str] = Field(alias='dwc:threatStatus')
    basis_of_record: Optional[str] = Field(alias='dwc:basisOfRecord')
    verbatim_identification: Optional[str] = Field(alias='dwc:verbatimIdentification')
    date_identified: Optional[str] = Field(alias='dwc:dateIdentified')
    recorded_by: Optional[str] = Field(alias='dwc:recordedBy')
    identified_by: Optional[str] = Field(alias='dwc:identifiedBy')
    identification_qualifier: Optional[str] = Field(alias='dwc:identificationQualifier')
    identification_remarks: Optional[str] = Field(alias='dwc:identificationRemarks')
    scientific_name_authorship: Optional[str] = Field(alias='dwc:scientificNameAuthorship')
    taxon_rank: Optional[str] = Field(alias='dwc:taxonRank')
    organism_remarks: Optional[str] = Field(alias='dwc:organismRemarks')
    occurrence_status: Optional[str] = Field(alias='dwc:occurrenceStatus')
    preparations: Optional[str] = Field(alias='dwc:preparations')
    associated_sequences: Optional[str] = Field(alias='dwc:associatedSequences')
    life_stage: Optional[str] = Field(alias='dwc:lifeStage')
    reproductive_condition: Optional[str] = Field(alias='dwc:reproductiveCondition')
    establishment_means: Optional[str] = Field(alias='dwc:establishmentMeans')
    geographic_uncertainty: Optional[float] = Field(alias='dwc:coordinateUncertaintyInMeters')
    locality: Optional[str] = Field(alias='dwc:locality')
    habitat: Optional[str] = Field(alias='dwc:habitat')
    occurrence_id: Optional[str] = Field(alias='dwc:occurrenceID')
    material_sample_id: Optional[str] = Field(alias='dwc:materialSampleID')
    vernacular_name: Optional[List[str]] = Field(alias='vernacular_name')
    informal_groups: Optional[List[str]] = Field(alias='informalGroup')
    kingdom: Optional[str] = Field(alias='dwc:kingdom')
    phylum: Optional[str] = Field(alias='dwc:phylum')
    class_: Optional[str] = Field(alias='dwc:class')
    order: Optional[str] = Field(alias='dwc:order')
    family: Optional[str] = Field(alias='dwc:family')
    taxonomic_status: Optional[str] = Field(alias='dwc:taxonomicStatus')
    nomos_id: Optional[int] = Field(alias='NomosID', default=None)
    restricted: Optional[bool] = False

    @root_validator(pre=True)
    def normalise_legacy_nomos_id_alias(cls, values):
        if isinstance(values, dict) and 'NomosID' not in values and 'nomosID' in values:
            values['NomosID'] = values['nomosID']
        return values

    def mongo_dict(self):
        record = self.dict()
        if 'nomos_id' in record:
            record['NomosID'] = record.pop('nomos_id')
        return record

    def __init__(self, **data):
        super().__init__(**data)

        if 'last_updated' not in data:
            self.last_updated = datetime.now().isoformat()

    @validator("dcterms_title", always=True)
    # @field_validator("dcterms_title", always=True)
    def check_species_occurrence_mandatory_fields_not_none(cls, v, values, field: ModelField):
        if "datatype" in values and values['datatype'] in [None, DataType.SPECIES_OCCURRENCE]:
            if v is None:
                raise ValueError(f"Species occurrence Record must have {field.alias}")
        return v

    @validator("submission_name", "submission_set_name", always=True)
    # @field_validator("submission_name", "submission_set_name", always=True)
    def check_systematic_survey_mandatory_fields_not_none(cls, v, values, field: ModelField):
        if "datatype" in values and values['datatype'] == DataType.SYSTEMATIC_SURVEY:
            if v is None:
                raise ValueError(f"Systematic survey Record must have {field.alias}")
        return v

    @property
    def logical_datatype(self) -> DataType:
        if self.datatype is not None:
            return self.datatype
        else:
            # Records with no datatype are considered SPECIES_OCCURRENCE
            return DataType.SPECIES_OCCURRENCE

    @classmethod
    def create_obfuscated_location(cls, lng: float, lat: float, settings: Settings) -> ObfuscatedLocation:
        """
        Create an obfuscated location object based on the provided longitude and latitude coordinates.

        Args:
            lng (float): Decimal longitude of the specific location.
            lat (float): Decimal latitude of the specific location.
            settings (Settings): Environment settings

        Returns:
            ObfuscatedLocation: An obfuscated location object representing the specific location. The object
            may contain modified or obscured coordinates based on the provided settings.
        """
        loc, b_box = cls.create_generalised_location(lng, lat, settings)
        [sw_lng, sw_lat] = loc.coordinates
        return ObfuscatedLocation(location=loc,
                                  bounding_box=b_box,
                                  scale=float(settings.obfuscation_grid_size),
                                  date_obfuscated=datetime.now().isoformat(),
                                  latitude=sw_lat,
                                  longitude=sw_lng)

    @staticmethod
    def create_generalised_location(lng: float, lat: float, settings: Settings) -> Tuple[Location, Location]:
        """
        Calculate the generalised point location and bounding box polygon for a specific location.

        Args:
            lng (float): Decimal longitude of the specific location.
            lat (float): Decimal latitude of the specific location.
            settings (Settings): Object containing the settings for calculating the generalised location.

        Returns:
            Location(Point): The generalised location representing the southwest corner of the bounding box for the
            specific location.
            Location(Polygon): The bounding box used for location searches of the specific location.
        """
        coordinates = [lng, lat]
        grid_size = settings.obfuscation_grid_size

        # Create the generalised location point
        for index, number in enumerate(coordinates):
            decimal_number = Decimal(str(number))
            # Find the southwest corner,
            # This means 'rounding down' to the nearest grid size,
            # but numbers should always lose value, i.e.
            # negative numbers should get more negative, positive numbers should get less positive
            # This means a floor operation, rather than a 'round down'
            coordinates[index] = float(decimal_number.quantize(
                Decimal(str(grid_size)),
                rounding=ROUND_FLOOR))
        point = Location(type="Point", coordinates=coordinates)

        # Create the generalised location bounding box
        [sw_lng, sw_lat] = point.coordinates
        # Lat long pairs as a 'ring', i.e. first point repeated as last point.
        b_box = Location(
            type='Polygon',
            coordinates=[[
                [sw_lng, sw_lat],
                [sw_lng + grid_size, sw_lat],
                [sw_lng + grid_size, sw_lat + grid_size],
                [sw_lng, sw_lat + grid_size],
                [sw_lng, sw_lat]
            ]])
        return point, b_box


class PublicRecord(BaseRecord):
    """
    This class represents the "public" version of records that will be used by the front end, which has a cut-down list
    of terms aliased to what they're stored as in the database.

    Note however that other Record fields from the database, not present here,
    are accessible to front end users via CSV and shapefile export.
    """
    id: str = Field(alias='persistent_id')
    datatype: DataType

    # Species occurrence
    dataset: Optional[str] = Field(alias='dcterms_title', default=None)

    # Systematic Survey
    submission_name: Optional[str] = Field(default=None)
    submission_set_name: Optional[str] = Field(default=None)

    date: str = Field(alias='event_date')
    recorded_species: str = Field(alias='scientific_name')
    kingdom: Optional[str] = Field(alias='kingdom')
    species: str = Field(alias='accepted_name_usage')
    data_provider: str = Field(alias='institution_code')
    conservation_status: Optional[str] = Field(alias='threat_status')
    taxonomic_status: Optional[str] = Field(alias='taxonomic_status', default=None)
    nomos_id: Optional[int] = Field(default=None)

    def __init__(self, **data):
        # For API responses, allways return a datatype, default to SPECIES_OCCURRENCE when it is missing or null.
        if "datatype" not in data or data["datatype"] is None:
            data["datatype"] = DataType.SPECIES_OCCURRENCE
        super().__init__(**data)
