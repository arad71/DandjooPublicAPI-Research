from datetime import datetime, timezone
from typing import Optional, Literal, List

from pydantic import BaseModel, Field

from app.models.common_enums import DataType
from app.models.published_submissions import PublishedSubmission


# # # DataBase / Curation API interfaces # # #

class PublishedProjectMetadataInternal(BaseModel):
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]

    name: str
    comments: Optional[str]
    submitter: Optional[str]
    purpose: Optional[str]


class PublishedSubmissionSetInternal(BaseModel):
    """
    Class to represent a Published Submission Set in the DB,
    and in the API that Curation uses.
    """
    persistent_id: str = Field(min_length=1)
    version: int = Field(ge=0)
    last_updated: Optional[str] = Field(default=None)

    # datatype in metadata defines which type of submission set this is.
    metadata: PublishedProjectMetadataInternal

    def prepare_save(self):
        self.last_updated = datetime.now(timezone.utc).isoformat()


# # # Public API interfaces # # #

class PublishedProjectMetadata(BaseModel):
    """
    Published Project Metadata in the public API
    """
    datatype: Literal[DataType.SYSTEMATIC_SURVEY]
    name: str
    submitter: Optional[str]
    purpose: Optional[str]


class PublishedSubmissionSet(BaseModel):
    """
    A Published Submission Set in the public API
    """
    persistent_id: str = Field(min_length=1)
    metadata: PublishedProjectMetadata

    # Derived fields
    from_date: Optional[str] = Field(
        default=None,
        description="Earliest from_date for all submissions in this set.",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="Latest to_date for all submissions in this set.",
    )
    total_submissions: Optional[int] = Field(
        default=None,
        description="Total number of submissions in this set.",
    )
    set_submissions: Optional[List[PublishedSubmission]] = Field(
        default=None,
        description=(
            "Unfiltered list of submissions in this set. "
            "Not Limited to only those submissions with records in the search results."
        ),
    )
    matching_submissions: Optional[List[PublishedSubmission]] = Field(
        default=None,
        description=(
            "Filtered list of submissions in this set. "
            "Limited to only those submissions with records in the search results."
        ),
    )

    def redact_for_public_user(self):
        """
        Redact information from this Submission Set that a public user doesn't have
        permission to see.
        """
        if self.matching_submissions:
            for submission in self.matching_submissions:
                submission.redact_for_public_user()
