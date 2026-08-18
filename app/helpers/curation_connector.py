import json
import os
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bson import ObjectId
from starlette import status

from app.helpers.mongo import get_supporting_file_collection, get_submission_set_collection
from app.models.submission import Submission, SurveyMetadata, OccurrenceMetadata, VegetationMetadata
from app.settings import Settings


def send_submission_to_curation(submission: Submission, settings: Settings) -> str:
    supporting_files = get_supporting_file_collection(settings)
    submission_sets = get_submission_set_collection(settings)

    # if dandjoo_curation_api_url not specified in settings, do nothing
    if settings.dandjoo_curation_api_url is None:
        return submission.persistent_id

    files: List[Tuple[str, Tuple[str, bytes]]] = []

    if isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)):
        # If Occurrence data - get "sourcefile" - the file Curation will extract records from
        sourcefile_file_path = submission.metadata.sourcefile
        if not sourcefile_file_path:
            raise ValueError("Submission has no sourcefile")
        _add_file_for_post(sourcefile_file_path, "source_file", files, settings)
    elif isinstance(submission.metadata, SurveyMetadata):
        # If Survey data - send all supporting files. Curation will extract records from the appropriate one.
        supporting_file_ids = sorted(set(
            supporting_file.file_id for supporting_file in (submission.metadata.supporting_files or [])
        ))
        for file_id in supporting_file_ids:
            file_metadata = supporting_files.find_one({"_id": file_id})
            _add_file_for_post(file_metadata["internal_file_name"], "supporting_files", files, settings)

    # get submission dict JSON payload, only of fields to send to Curation
    submission_dict = submission.dict(include={"submitter_id", "metadata", "mappings", "persistent_id"})
    # Update supporting files entries
    if isinstance(submission.metadata, SurveyMetadata) and submission_dict['metadata'].get('supporting_files'):
        for supporting_file_dict in submission_dict['metadata']['supporting_files']:
            file_id = supporting_file_dict.pop("file_id")
            supporting_file_dict.pop("usage_id")
            supporting_file_dict['supporting_file_id'] = str(file_id)
            # Add fields from metadata in supporting_files collection
            file_metadata = supporting_files.find_one({"_id": ObjectId(file_id)})
            supporting_file_dict['file_name'] = file_metadata['file_name']
            supporting_file_dict['file_size'] = file_metadata['file_size']
            # when POSTING, file_location refers to the file name given to the file in the POST.
            supporting_file_dict['file_location'] = os.path.basename(file_metadata['internal_file_name'])
    # Populate submission set info
    if isinstance(submission.metadata, SurveyMetadata) and submission.metadata.submission_set_persistent_id:
        submission_set = submission_sets.find_one({"persistent_id": submission.metadata.submission_set_persistent_id})
        submission_dict["submission_set"] = {
            "persistent_id": submission_set['persistent_id'],
            "submitter_id": submission_set.get('submitter_id'),
            "metadata": {
                "name": submission_set.get("name"),
                "submitter": submission_set.get("submitter"),
                "comments": submission_set.get("comments"),
                **submission_set['metadata'],
            }
        }

    response = requests.post(urljoin(settings.dandjoo_curation_api_url, 'submissions/'),
                             data={'submission_json': json.dumps(submission_dict)}, files=files)

    if response.status_code != status.HTTP_201_CREATED:
        response.raise_for_status()

    curation_submission_id = response.json()
    assert isinstance(curation_submission_id, str)
    return curation_submission_id


def _add_file_for_post(
    internal_file_name: str,
    form_field: str,
    files: List[Tuple[str, Tuple[str, bytes]]],
    settings: Settings,
) -> None:
    """
    Adds a file to the list of files to be POSTed.

    :param internal_file_name: Name/path of file relative to settings.temp_file_storage_path
    :param form_field: Name of form field file will be posted as.
    :param files: List to add the file to.
    :param settings:
    """
    file_name_to_send = os.path.basename(internal_file_name)
    with open(os.path.join(settings.temp_file_storage_path, internal_file_name), 'rb') as file_obj:
        files.append((form_field, (file_name_to_send, file_obj.read())))
