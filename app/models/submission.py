from enum import Enum
from typing import Optional, Union, List, Literal, Dict, Any

from bson.objectid import ObjectId
from pydantic import BaseModel, Field, validator

from app.helpers.py_object import PyObjectId
from app.models.common_enums import DataType, DocumentType
from app.models.geo_json import Point
from app.models.submission_set import SubmissionSet
from app.models.supporting_files import SupportingFile


class DatumEnum(str, Enum):
    GDA94 = 'GDA94'
    WGS84 = 'WGS84'
    GDA2020 = 'GDA2020'
    AGD84 = 'AGD84'
    AGD66 = 'AGD66'
    UNSURE = 'Unsure'
    MULTIPLE = 'Multiple datums'


class SupportingFileUsage(BaseModel):
    """
    Sub-document to represent a supporting file being used by a survey submission.

    A survey can have multiple of these for a particular file,
    when the file is used in different ways by the survey.
    """
    usage_id: PyObjectId  # arbitrary id to identify this usage
    file_id: PyObjectId  # reference to _id in supporting_file collection
    document_type: DocumentType
    private: bool

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class UploadSupportingFileResponse(BaseModel):
    """
    API Response when a new supporting file is uploaded to a survey submission.
    """
    supporting_file: SupportingFile
    usage: SupportingFileUsage

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class SupportingFileUsageResponse(BaseModel):
    """
    API Response when a supporting file usage is updated or created.
    """
    usage: SupportingFileUsage
    sample_data: Optional[Dict[str, Any]]

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class BaseSubmissionMetadata(BaseModel):
    """
    Base model for submission metadata.

    Config:
    - use_enum_values: Set to True to use enum values in serialization

    Fields:
    - submitter: Organisation/Person who submitted the data (optional)
    - datum: Datum type (optional)
    - created_on: Timestamp of creation (optional)

    Methods:
    - new_entry_dict() -> dict: Returns a dictionary suitable for a new entry, excluding specified fields.
    - update_entry_dict() -> dict: Returns a dictionary suitable for an update, excluding specified fields.
    """
    class Config:
        use_enum_values = True
        json_encoders = {
            ObjectId: str,
        }

    # Fields that are set by the user during creation or update
    submitter: Optional[str]
    datum: Optional[DatumEnum]

    # Fields that are never exposed to the user to modify
    created_on: Optional[str]

    @classmethod
    def _new_entry_exclude_fields(cls) -> List[str]:
        """
        Returns fields to exclude for a new entry.

        Should be extended by child classes.

        Returns:
        - List[str]: List of fields to exclude for a new entry.
        """
        return ["created_on"]

    @classmethod
    def _update_entry_exclude_fields(cls) -> List[str]:
        """
        Returns fields to exclude for an update to an existing entry.

        Should be extended by child classes.

        Returns:
        - List[str]: List of fields to exclude for an update.
        """
        return ["created_on"]

    def new_entry_dict(self):
        """
        Returns a dictionary suitable for a new entry, excluding specified fields.

        Returns:
        - dict: Dictionary suitable for a new entry, excluding specified fields.
        """
        exclude_fields = self._new_entry_exclude_fields()
        self_dict = self.dict()
        for e in exclude_fields:
            self_dict.pop(e)
        return self_dict

    def update_entry_dict(self):
        """
        Returns a dictionary suitable for an update to an existing entry, excluding specified fields.

        Returns:
        - dict: Dictionary suitable for an update to an existing entry, excluding specified fields.
        """
        exclude_fields = self._update_entry_exclude_fields()
        self_dict = self.dict(exclude_unset=True)
        for e in exclude_fields:
            if e in self_dict:
                self_dict.pop(e)
        return self_dict


class OccurrenceMetadata(BaseSubmissionMetadata):
    """
    Model for occurrence submission metadata.

    Fields:
    - datatype: Literal[DataType.SPECIES_OCCURRENCE]
    - dataset: The dataset this submission belongs to. Dataset is an informal grouping of Occurrence Submissions.
    - comments: Additional comments provided by the user (optional)
    - sourcefile: Source file of the data (optional)
    """
    datatype: Literal[DataType.SPECIES_OCCURRENCE]

    # Fields that are set by the user during creation or update
    dataset: Optional[str]
    comments: Optional[str]

    # Set via other endpoints
    sourcefile: Optional[str]

    @classmethod
    def _new_entry_exclude_fields(cls) -> List[str]:
        return super()._new_entry_exclude_fields() + ["sourcefile"]

    @classmethod
    def _update_entry_exclude_fields(cls) -> List[str]:
        return super()._update_entry_exclude_fields() + ["sourcefile"]


class SurveyMetadata(BaseSubmissionMetadata):
    """
    Model for survey metadata.

    Fields:
    - datatype: Literal[DataType.SYSTEMATIC_SURVEY]
    - submission_set_persistent_id: The Project this Survey belongs to.
    - name: Name of the survey (optional)
    - summary: Free test description/summary of the survey (optional)
    - from_date/to_date: Date(s) of the survey (optional)
    - participants: Participants in the survey (optional)
    - has_threatened_species: Indicates if the survey includes threatened species (optional)
    - List of tags that have been applied to this survey. (optional)
    - bounding_box_north_west/south_east: Corners of the bounding box containing the Survey.
    - supporting_files: List of supporting files (optional)
    """
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]

    # Fields that are only set by the user during creation
    submission_set_persistent_id: Optional[str]  # reference to persistent_id in submission_sets collection

    # Fields that are set during creation or update
    name: Optional[str]
    summary: Optional[str]
    from_date: Optional[str]
    to_date: Optional[str]
    participants: Optional[str]
    has_threatened_species: Optional[bool]
    tags: Optional[List[str]]
    bounding_box_north_west: Optional[Point]
    bounding_box_south_east: Optional[Point]

    # Set via other endpoints
    supporting_files: Optional[List[SupportingFileUsage]]

    @classmethod
    def _new_entry_exclude_fields(cls) -> List[str]:
        return super()._new_entry_exclude_fields() + ["supporting_files"]

    @classmethod
    def _update_entry_exclude_fields(cls) -> List[str]:
        return super()._update_entry_exclude_fields() + ["supporting_files", "submission_set_persistent_id"]

    @validator("bounding_box_north_west", "bounding_box_south_east")
    # @field_validator("bounding_box_north_west", "bounding_box_south_east")
    def round_bounding_box_coordinates(cls, point: Optional[Point]) -> Optional[Point]:
        """
        Round bounding box coordinates to 5 decimal places.
        """
        if point is not None:
            point.coordinates = (
                round(point.coordinates[0], 5),
                round(point.coordinates[1], 5),
            )
        return point


class VegetationMetadata(BaseSubmissionMetadata):
    """
    Model for Vegetation Association submission metadata.

    Fields:
    - datatype: Literal[DataType.VEGETATION_ASSOCIATION]
    - dataset: The dataset this submission belongs to.
    - comments: Additional comments provided by the user (optional)
    - sourcefile: Source file of the data (optional)
    """
    datatype: Literal[DataType.VEGETATION_ASSOCIATION]

    # Fields that are set by the user during creation or update
    dataset: Optional[str]
    comments: Optional[str]

    # Set via other endpoints
    sourcefile: Optional[str]

    @classmethod
    def _new_entry_exclude_fields(cls) -> List[str]:
        return super()._new_entry_exclude_fields() + ["sourcefile"]

    @classmethod
    def _update_entry_exclude_fields(cls) -> List[str]:
        return super()._update_entry_exclude_fields() + ["sourcefile"]


class Metadata(BaseModel):
    """
    Union model for occurrence and survey metadata.

    This class is implemented to allow fastapi to accept any valid format of metadata json from the
    frontend, and use the 'datatype' field discriminator to create the appropriate child class object.

    Fields:
    - __root__: Union[OccurrenceMetadata, SurveyMetadata, VegetationMetadata] with discriminator 'datatype'.
    """
    __root__: Union[OccurrenceMetadata, SurveyMetadata, VegetationMetadata] = Field(discriminator='datatype')

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class NewSubmissionMetadata(BaseModel):
    """
    Request and Response Model for creating a new Submission.

    Fields:
    - accept_terms_and_conditions: Must be true to indicate User has accepted terms and conditions.
    - submission: Metadata object (either OccurrenceMetadata or SurveyMetadata or VegetationMetadata)
        Request: Used to create the new Submission.
        Response: Used to return details of the new Submission.
    - submission_set: SubmissionSet object
        Request: Used to create a new Submission Set,
            only when "submission" does not contain an ID for an existing Submission Set to use.
        Response: Used to return details of the new/specified Submission Set.
    - new_submission_id:
        Request: Not used.
        Response: ID of the new submission.
    """
    accept_terms_and_conditions: bool
    submission: Optional[Metadata]
    submission_set: Optional[SubmissionSet]
    new_submission_id: Optional[str]

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class Mappings(BaseModel):
    class SpeciesMappings(BaseModel):
        field_scientific_name: str

    class SpeciesGenusMappings(BaseModel):
        genus: str
        species: str

    taxon: Union[SpeciesMappings, SpeciesGenusMappings]
    date_observed_collected: str
    sub_species: Optional[str]
    count: Optional[str]
    method_protocol: Optional[str]
    identification_basis: Optional[str]
    field_identification: Optional[str]
    date_identified: Optional[str]
    collector: Optional[str]
    identified_by: Optional[str]
    identification_ambiguity: Optional[str]
    identification_notes: Optional[str]
    scientific_name_publisher: Optional[str]
    taxonomic_rank: Optional[str]
    organism_remarks: Optional[str]
    presence_absence: Optional[str]
    preparations: Optional[str]
    genomic_sequence_information: Optional[str]
    life_stage: Optional[str]
    reproductive_state: Optional[str]
    native_introduced_feral: Optional[str]
    geographic_uncertainty: Optional[str]
    area_locality_of_occurrence: Optional[str]
    habitat: Optional[str]


class SpreadsheetMappings(Mappings):
    class GeographicLocationMappings(BaseModel):
        latitude: str
        longitude: str

    class GeometricLocationMappings(BaseModel):
        easting: str
        northing: str
        zone: str

    location: Union[GeographicLocationMappings, GeometricLocationMappings]


class Submission(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id')
    submitter_id: Optional[Union[str, int]]
    metadata: Optional[Union[OccurrenceMetadata, SurveyMetadata, VegetationMetadata]] = Field(discriminator='datatype')
    mappings: Optional[Union[SpreadsheetMappings, Mappings]]
    persistent_id: Optional[str]

    # A Submission can be considered "submitted" if either of these flags are set to True
    unmappable: Optional[bool]
    sent_to_curation: Optional[bool]

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }


class SubmissionCompleteResponse(BaseModel):
    """
    API Response when a submission is finished, either by sending to Curation or being marked as unmappable.
    """
    submission_id: str
    persistent_id: str
    sent_to_curation: bool
    unmappable: bool
