from fastapi import APIRouter, BackgroundTasks, Depends, Path
from fastapi_key_auth import AuthorizerDependency
from pydantic import BaseModel
from pymongo import ReturnDocument
from starlette import status

from app.dependencies import get_settings
from app.helpers.lookup import on_published_submission_invalidation, on_published_submission_set_invalidation
from app.helpers.mongo import get_published_submission_collection, get_published_submission_set_collection
from app.models.published_submissions import PublishedSubmissionInternal
from app.models.published_submission_sets import PublishedSubmissionSetInternal
from app.settings import Settings

router = APIRouter()

authorizer = AuthorizerDependency(key_pattern="API_SYSTEM_KEY")


class DeleteResponse(BaseModel):
    deleted_count: int


@router.post(
    "/published_submission_sets/",
    dependencies=[Depends(authorizer)],
    status_code=status.HTTP_200_OK,
    response_model=PublishedSubmissionSetInternal,
)
def create_or_update_published_submission_set(
    background_tasks: BackgroundTasks,
    published_submission_set: PublishedSubmissionSetInternal,
    settings: Settings = Depends(get_settings),
) -> PublishedSubmissionSetInternal:
    published_submission_set_collection = get_published_submission_set_collection(settings)

    published_submission_set.prepare_save()
    update_result = published_submission_set_collection.find_one_and_update(
        {'persistent_id': published_submission_set.persistent_id},
        {'$set': published_submission_set.dict()},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    background_tasks.add_task(on_published_submission_set_invalidation, settings)
    return PublishedSubmissionSetInternal(**update_result)


@router.delete(
    "/published_submission_sets/{submission_set_id}/",
    dependencies=[Depends(authorizer)],
    status_code=status.HTTP_200_OK,
    response_model=DeleteResponse,
)
def delete_published_submission_set(
    background_tasks: BackgroundTasks,
    submission_set_id: str = Path(min_length=1),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    published_submission_set_collection = get_published_submission_set_collection(settings)
    result = published_submission_set_collection.delete_one(
        {'persistent_id': submission_set_id},
    )
    background_tasks.add_task(on_published_submission_set_invalidation, settings)
    return DeleteResponse(deleted_count=result.deleted_count)


@router.post(
    "/published_submissions/",
    dependencies=[Depends(authorizer)],
    status_code=status.HTTP_200_OK,
    response_model=PublishedSubmissionInternal,
)
def create_or_update_published_submission(
    background_tasks: BackgroundTasks,
    published_submission: PublishedSubmissionInternal,
    settings: Settings = Depends(get_settings),
) -> PublishedSubmissionInternal:
    published_submission_collection = get_published_submission_collection(settings)

    published_submission.prepare_save()
    update_result = published_submission_collection.find_one_and_update(
        {'persistent_id': published_submission.persistent_id},
        {'$set': published_submission.dict()},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    background_tasks.add_task(on_published_submission_invalidation, settings)
    return PublishedSubmissionInternal(**update_result)


@router.delete(
    "/published_submissions/{submission_id}/",
    dependencies=[Depends(authorizer)],
    status_code=status.HTTP_200_OK,
    response_model=DeleteResponse,
)
def delete_published_submission(
    background_tasks: BackgroundTasks,
    submission_id: str = Path(min_length=1),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    published_submission_collection = get_published_submission_collection(settings)
    result = published_submission_collection.delete_one(
        {"persistent_id": submission_id},
    )
    background_tasks.add_task(on_published_submission_invalidation, settings)
    return DeleteResponse(deleted_count=result.deleted_count)
