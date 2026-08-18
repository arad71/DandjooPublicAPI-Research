import enum
from datetime import datetime, timezone
from typing import Optional, Literal, List

from bson import ObjectId
from pydantic import BaseModel, Field, root_validator

from app.helpers.py_object import PyObjectId
from app.models.common_enums import DataType, DocumentType
from app.models.geo_json import Point


_ISO_DATE_REGEX = r"(?a)^\d\d\d\d-\d\d-\d\d$"


class PublishedSubmissionVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"  # publicly viewable
    RESTRICTED = "RESTRICTED"  # only viewable to users with permission


class SupportingFileVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"  # publicly downloadable
    RESTRICTED = "RESTRICTED"  # only downloadable by users with permission


# # # DataBase / Curation API interfaces # # #

class PublishedSupportingFileInternal(BaseModel):
    supporting_file_id: PyObjectId  # original _id of the supporting file

    file_name: str = Field(min_length=1)  # original name of file
    file_size: int = Field(ge=0)
    document_types: List[DocumentType] = Field(min_items=1)

    # If the file is restricted/public, and either a public url or private url.
    visibility: SupportingFileVisibility
    public_file_location: Optional[str] = Field(min_length=1)
    restricted_file_location: Optional[str] = Field(min_length=1)

    @root_validator()
    def validate_visibility_and_locations(cls, values):
        """
        Validate that only one of public_file_location and restricted_file_location
        is set depending on the visibility flag.
        """
        required_fields = {
            "visibility", "public_file_location", "restricted_file_location"
        }
        if required_fields.issubset(values.keys()):
            if values["visibility"] == SupportingFileVisibility.RESTRICTED:
                if (
                    values["public_file_location"] is None
                    and values["restricted_file_location"] is not None
                ):
                    pass  # data is valid for RESTRICTED
                else:
                    raise ValueError(
                        "RESTRICTED files must have only restricted_file_location, "
                        "and not public_file_location."
                    )
            elif values['visibility'] == SupportingFileVisibility.PUBLIC:
                if (
                    values["public_file_location"] is not None
                    and values["restricted_file_location"] is None
                ):
                    pass  # data is valid for PUBLIC
                else:
                    raise ValueError(
                        "PUBLIC files must have only public_file_location, "
                        "and not restricted_file_location."
                    )
            else:
                raise ValueError(
                    f"Unexpected visibility flag value: {values['visibility']}"
                )
        return values


class PublishedSurveyMetadataInternal(BaseModel):
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]

    name: str
    summary: Optional[str]
    submitter: Optional[str]
    rights_holder: Optional[str]
    from_date: str = Field(regex=_ISO_DATE_REGEX)
    to_date: str = Field(regex=_ISO_DATE_REGEX)
    participants: Optional[str]
    tags: List[str]
    bounding_box_north_west: Point
    bounding_box_south_east: Point
    supporting_files: List[PublishedSupportingFileInternal]


class PublishedSubmissionInternal(BaseModel):
    """
    Class to represent a Published Submission in the DB, and in the API that Curation uses.
    """
    persistent_id: str = Field(min_length=1)  # persistent id from the source submission (not the _id)
    version: int = Field(ge=0)
    last_updated: Optional[str] = Field(default=None)

    # persistent id from the parent submission set
    submission_set_id: str = Field(min_length=1)

    # If the submission is restricted from being viewed, or public.
    visibility: PublishedSubmissionVisibility

    # datatype in metadata defines which type of submission this is.
    metadata: PublishedSurveyMetadataInternal

    class Config:
        json_encoders = {
            ObjectId: str,
        }

    def prepare_save(self):
        self.last_updated = datetime.now(timezone.utc).isoformat()


# # # Public API interfaces # # #

class PublishedSupportingFile(BaseModel):
    """
    A Published supporting file in the public API
    """
    supporting_file_id: PyObjectId

    file_name: str = Field(min_length=1)  # original name of file
    file_size: int = Field(ge=0)
    document_types: List[DocumentType] = Field(min_items=1)

    visibility: SupportingFileVisibility
    public_file_location: Optional[str] = Field(min_length=1)
    # "restricted_file_location" field not included in public API


class PublishedSurveyMetadata(BaseModel):
    """"
    Published Survey Metadata in the public API
    """
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]

    name: str
    summary: Optional[str]
    submitter: Optional[str]
    rights_holder: Optional[str]
    from_date: str = Field(regex=_ISO_DATE_REGEX)
    to_date: str = Field(regex=_ISO_DATE_REGEX)
    tags: List[str]
    participants: Optional[str]
    # supporting_files and bounding box should not be shown to a public user
    # when the survey visibility is set to RESTRICTED
    supporting_files: Optional[List[PublishedSupportingFile]]
    bounding_box_north_west: Optional[Point]
    bounding_box_south_east: Optional[Point]


class PublishedSubmission(BaseModel):
    """
    A Published Submission in the public API
    """
    persistent_id: str = Field(min_length=1)
    submission_set_id: str = Field(min_length=1)
    visibility: PublishedSubmissionVisibility
    metadata: PublishedSurveyMetadata

    def redact_for_public_user(self):
        """
        Redact information from this Submission that a public user doesn't have
        permission to see.
        """
        # If submission is RESTRICTED, don't return these fields to a public user.
        if self.visibility == PublishedSubmissionVisibility.RESTRICTED:
            self.metadata.supporting_files = None
            self.metadata.bounding_box_north_west = None
            self.metadata.bounding_box_south_east = None

        # If there is a supporting files list, only show the ones that are PUBLIC
        if self.metadata.supporting_files:
            self.metadata.supporting_files = [
                file for file in self.metadata.supporting_files
                if file.visibility == SupportingFileVisibility.PUBLIC
            ]
