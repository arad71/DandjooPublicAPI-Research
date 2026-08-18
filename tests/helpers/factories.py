import os.path
from os import path
from typing import Optional

from app.helpers.dandjoo_id import DandjooId
from app.helpers.mongo import get_submission_set_collection, get_supporting_file_collection
from app.helpers.py_object import PyObjectId
from app.helpers.supporting_files import uniquify
from app.models.common_enums import DataType
from app.models.submission_set import SubmissionSet
from app.models.supporting_files import SupportingFile
from app.settings import Settings


def submission_set_factory(settings: Settings, **kwargs) -> SubmissionSet:
    submission_sets = get_submission_set_collection(settings=settings)
    metadata = {
        "datatype": DataType.SYSTEMATIC_SURVEY,
        "purpose": "for testing",
        **kwargs.pop("metadata", {}),
    }
    values = {
        "persistent_id": DandjooId.new_id(),
        "submitter_id": "test-submitter-id",
        "name": "Test Submission Set",
        "submitter": "Department of Testing",
        "comments": "These are comments for a test submission set",
        "metadata": metadata,
        **kwargs,
    }
    submission_set = SubmissionSet(**values)
    submission_set_id = submission_sets.insert_one(submission_set.dict()).inserted_id
    return SubmissionSet(**submission_sets.find_one({"_id": submission_set_id}))


def supporting_file_factory(
    settings: Settings,
    _id: Optional[PyObjectId] = None,
    submission_set_persistent_id: Optional[str] = None,
    # specify existing test file relative to "test-data" dir
    test_file: Optional[str] = None,
    # OR specify file name and content manually
    file_name: Optional[str] = None,
    file_content: Optional[bytes] = None,
) -> SupportingFile:
    if not submission_set_persistent_id:
        submission_set_persistent_id = submission_set_factory(settings=settings).persistent_id

    if test_file is not None:
        file_name = os.path.basename(test_file)
        with open(path.join(path.dirname(path.dirname(__file__)), "test-data", test_file), mode="rb") as f:
            file_content = f.read()
    elif file_name is not None and file_content is not None:
        pass
    else:
        file_name = "some_file.csv"
        file_content = b"name,lat,long,date\ntest,-40,123,2024-02-02\n"

    internal_file_name = uniquify(settings, os.path.join(submission_set_persistent_id, file_name))
    file_path = path.join(settings.temp_file_storage_path, internal_file_name)
    os.makedirs(path.dirname(file_path), exist_ok=True)
    with open(file_path, mode='wb') as f_to_write:
        f_to_write.write(file_content)

    supporting_file = SupportingFile(
        _id=_id or PyObjectId(),
        submission_set_persistent_id=submission_set_persistent_id,
        file_name=file_name,
        internal_file_name=internal_file_name,
        uploaded_at="2023-01-01T00:00:00Z",
        file_size=len(file_content),
    )
    supporting_files = get_supporting_file_collection(settings=settings)
    supporting_files.insert_one(supporting_file.dict(by_alias=True))
    return supporting_file
