from typing import Optional, Union, Literal

from bson.objectid import ObjectId
from pydantic import BaseModel, Field

from app.helpers.dandjoo_id import DandjooId
from app.helpers.py_object import PyObjectId
from app.models.common_enums import DataType


class BaseSubmissionSetMetadata(BaseModel):
    """SubmissionSet Metadata shared by all datatypes"""
    datatype: DataType


class OccurrenceSubmissionSetMetadata(BaseSubmissionSetMetadata):
    datatype: Literal[DataType.SPECIES_OCCURRENCE]


class SurveySubmissionSetMetadata(BaseSubmissionSetMetadata):
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]
    purpose: Optional[str]


class SubmissionSet(BaseModel):
    """
    A SubmissionSet is a collection of Submissions

    All Submissions must be the same datatype (Occurrence / Systematic Survey Data) as the SubmissionSet itself.
    A SubmissionSet can be referred to as a "Project" for Systematic Survey submissions.
    """
    id: Optional[PyObjectId] = Field(alias='_id')
    persistent_id: Optional[str]  # DandjooId
    submitter_id: Optional[Union[str, int]]  # The id of the user who first submitted for this SubmissionSet

    sent_to_curation: Optional[bool]
    archived_in_curation: Optional[bool]

    name: Optional[str]  # e.g. Project name
    submitter: Optional[str]  # The organisation name that uses this SubmissionSet
    comments: Optional[str]  # Comments provided by the user

    # metadata defines which datatype this SubmissionSet is, and holds datatype-specific information.
    metadata: Union[OccurrenceSubmissionSetMetadata, SurveySubmissionSetMetadata] = Field(discriminator="datatype")

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str
        }

    def new_entry_dict(self):
        """
        Returns a dictionary suitable for a new entry, excluding specified fields.

        Returns:
        - dict: Dictionary suitable for a new entry, excluding specified fields.
        """
        exclude_fields = ["_id", "persistent_id", "submitter_id"]
        self_dict = self.dict(by_alias=True)
        for e in exclude_fields:
            self_dict.pop(e)
        self_dict["persistent_id"] = DandjooId.new_id()
        return self_dict


class SubmissionSetCurationUpdate(BaseModel):
    """
    Defines the API for Curation to update a submission set.

    Fields omitted or set to None will not be updated.
    """
    name: Optional[str]
    submitter: Optional[str]
    comments: Optional[str]
    # metadata fields
    purpose: Optional[str]
    # flags
    archived: Optional[bool]
