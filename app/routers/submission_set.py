import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi_key_auth import AuthorizerDependency
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from starlette import status

from app.dependencies import get_settings
from app.helpers.mongo import get_supporting_file_collection, get_submission_set_collection, \
    get_submission_collection
from app.helpers.py_object import PyObjectId
from app.models.common_enums import DataType
from app.models.submission import Submission
from app.models.submission_set import SubmissionSet, SubmissionSetCurationUpdate, SurveySubmissionSetMetadata
from app.helpers.authorisation import is_authorised, Permission
from app.models.supporting_files import SupportingFile
from app.settings import Settings


router = APIRouter()

authorizer = AuthorizerDependency(key_pattern="API_SYSTEM_KEY")


@router.get("/submission_sets", status_code=status.HTTP_200_OK, response_model=List[SubmissionSet])
def list_submission_sets(
    request: Request,
    name: Optional[str] = Query(default=None, min_length=1),
    datatype: Optional[DataType] = Query(default=None),
    persistent_id: Optional[str] = Query(default=None, min_length=1),
    exclude_archived: Optional[bool] = Query(default=None),
    limit: int = Query(default=50, gt=0),
    settings: Settings = Depends(get_settings),
):
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submission_sets = get_submission_set_collection(settings)

    query = {}
    if name is not None:
        query["name"] = {"$regex": re.escape(name), "$options": 'i'}
    if datatype is not None:
        query["metadata.datatype"] = {"$eq": datatype.value}
    if persistent_id is not None:
        query["persistent_id"] = {"$eq": persistent_id}
    if exclude_archived:
        query["archived_in_curation"] = {"$ne": True}

    found_submission_sets = list(submission_sets.find(filter=query, limit=limit, sort=[("_id", ASCENDING)]))
    return found_submission_sets


@router.get("/submission_set/{submission_set_id}", status_code=status.HTTP_200_OK, response_model=SubmissionSet)
def get_submission_set(
    request: Request,
    submission_set_id: PyObjectId,
    settings: Settings = Depends(get_settings),
) -> SubmissionSet:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submission_sets = get_submission_set_collection(settings)

    submission_set_dict = submission_sets.find_one({'_id': submission_set_id})

    # check if submission_set exists
    if not bool(submission_set_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='submission_set not found')

    submission_set = SubmissionSet(**submission_set_dict)

    return submission_set


@router.get("/submission_set/{submission_set_id}/supporting-files",
            status_code=status.HTTP_200_OK, response_model=List[SupportingFile])
def get_supporting_files_for_submission_set(
    request: Request,
    submission_set_id: PyObjectId,
    settings: Settings = Depends(get_settings),
):
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submission_sets = get_submission_set_collection(settings)
    submission_set_dict = submission_sets.find_one({'_id': submission_set_id})

    # check if submission_set exists
    if not bool(submission_set_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='submission_set not found')

    supporting_files = get_supporting_file_collection(settings)
    submission_set_files = list(supporting_files.find(
        filter={"submission_set_persistent_id": submission_set_dict['persistent_id']}, sort=[("_id", ASCENDING)]
    ))
    return submission_set_files


@router.get("/submission_set/{submission_set_id}/supporting-file/{file_id}",
            status_code=status.HTTP_200_OK, response_model=SupportingFile)
def get_supporting_file(
    request: Request,
    submission_set_id: PyObjectId,
    file_id: PyObjectId,
    settings: Settings = Depends(get_settings),
):
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submission_sets = get_submission_set_collection(settings)
    submission_set_dict = submission_sets.find_one({'_id': submission_set_id})

    # check if submission_set exists
    if not bool(submission_set_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='submission_set not found')

    supporting_files = get_supporting_file_collection(settings)
    supporting_file_dict = supporting_files.find_one(
        {"_id": file_id, "submission_set_persistent_id": submission_set_dict['persistent_id']},
    )

    # check if file exists
    if not bool(supporting_file_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='File not found')

    return supporting_file_dict


@router.get("/submission_set/{submission_set_id}/submissions",
            status_code=status.HTTP_200_OK, response_model=List[Submission])
def get_submissions_for_submission_set(
    request: Request,
    submission_set_id: PyObjectId,
    settings: Settings = Depends(get_settings),
) -> List[Submission]:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submission_sets = get_submission_set_collection(settings)
    submission_set_dict = submission_sets.find_one({'_id': submission_set_id})

    # check if submission_set exists and has persistent_id
    if not submission_set_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='submission_set not found')
    if not submission_set_dict.get("persistent_id"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="submission_set has no persistent_id")

    submissions = get_submission_collection(settings)
    submissions_in_set = list(submissions.find(
        filter={"metadata.submission_set_persistent_id": submission_set_dict['persistent_id']},
        sort=[("_id", DESCENDING)],
    ))
    return submissions_in_set


@router.patch(
    "/submission_set/{submission_set_persistent_id}/curation_update",
    status_code=status.HTTP_200_OK,
    response_model=SubmissionSet,
    dependencies=[Depends(authorizer)],
)
def update_submission_set_from_curation(
    submission_set_persistent_id: str,
    update: SubmissionSetCurationUpdate,
    settings: Settings = Depends(get_settings),
) -> SubmissionSet:
    """
    This endpoint is used by Curation when a curator updates a submission set there,
    and the update needs to be synced back to Submission so that future submissions using the submission set
    can see the updated details.
    """
    submission_sets = get_submission_set_collection(settings)
    submission_set_dict = submission_sets.find_one({'persistent_id': submission_set_persistent_id})

    # check if submission_set exists
    if not bool(submission_set_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='submission_set not found')

    submission_set = SubmissionSet(**submission_set_dict)

    set_operation = {}
    if update.name is not None:
        set_operation['name'] = update.name
    if update.submitter is not None:
        set_operation['submitter'] = update.submitter
    if update.comments is not None:
        set_operation['comments'] = update.comments
    if update.purpose is not None and isinstance(submission_set.metadata, SurveySubmissionSetMetadata):
        set_operation['metadata.purpose'] = update.purpose
    if update.archived is not None:
        set_operation['archived_in_curation'] = update.archived

    updated_submission_set_dict = submission_sets.find_one_and_update(
        {'_id': submission_set.id},
        {'$set': set_operation},
        return_document=ReturnDocument.AFTER,
    )
    return SubmissionSet(**updated_submission_set_dict)
