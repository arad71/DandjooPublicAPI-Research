from os import path

from bson import ObjectId
from pydantic import BaseModel, Field

from app.helpers.py_object import PyObjectId


class SupportingFile(BaseModel):
    """
    SupportingFile represents a file that has been uploaded to a submission in a SubmissionSet,
    That can then be re-used for other submissions in the same SubmissionSet.
    i.e. this file can be references by multiple submissions in the SubmissionSet it belongs to.
    """
    id: PyObjectId = Field(alias='_id')
    file_name: str  # original name of uploaded file
    internal_file_name: str  # path and name of file relative to `settings.temp_file_storage_path`
    uploaded_at: str
    file_size: int

    submission_set_persistent_id: str  # reference to persistent_id in submission_sets collection

    class Config:
        json_encoders = {
            ObjectId: str,
        }

    @property
    def file_extension(self) -> str:
        """
        Return the file extension, not including '.', e.g. "csv" or "PDF"
        Will return empty string if file_name has no extension, e.g. "some_binary" or ".config"
        """
        return path.splitext(self.file_name)[1][1:]
