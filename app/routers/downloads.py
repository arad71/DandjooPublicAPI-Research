import os
import os.path
import tempfile
import zipfile
from typing import Iterator, IO

from fastapi import APIRouter, Depends, Request, HTTPException, Response
from fastapi.responses import StreamingResponse
from starlette import status

from app.dependencies import get_settings
from app.helpers.authorisation import is_authorised, Permission
from app.helpers.azure_blobs import check_blob_store_available, get_blob_downloader
from app.helpers.mongo import get_published_submission_collection, \
    get_published_submission_set_collection
from app.helpers.py_object import PyObjectId
from app.helpers.submission_exports import get_submission_metadata_file
from app.models.published_submission_sets import PublishedSubmissionSetInternal
from app.models.published_submissions import PublishedSubmissionInternal, \
    SupportingFileVisibility, PublishedSubmissionVisibility
from app.settings import Settings

router = APIRouter()


@router.get(
    "/published_submissions/{published_submission_id}/supporting_files/{supporting_file_id}/",
    status_code=status.HTTP_200_OK,
)
def download_restricted_supporting_file(
    request: Request,
    published_submission_id: str,
    supporting_file_id: PyObjectId,
    settings: Settings = Depends(get_settings),
):
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    if not has_sensitive_permission:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    published_submission_collection = get_published_submission_collection(settings)
    raw_submission = published_submission_collection.find_one(
        {"persistent_id": published_submission_id},
    )
    if raw_submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published submission not found",
        )

    submission = PublishedSubmissionInternal(**raw_submission)
    supporting_file = next(
        (
            file for file in submission.metadata.supporting_files
            if file.supporting_file_id == supporting_file_id
        ),
        None,
    )
    if supporting_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supporting file not found",
        )
    if supporting_file.visibility != SupportingFileVisibility.RESTRICTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supporting file is not restricted",
        )

    if not check_blob_store_available(settings):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Blob store not configured",
        )

    try:
        file_downloader = get_blob_downloader(
            settings=settings,
            blob_url=supporting_file.restricted_file_location,
            use_credentials=True,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting blob downloader: {e}",
        )

    return StreamingResponse(
        file_downloader.chunks(),
        headers={
            "Content-Disposition": f'attachment; filename="{supporting_file.file_name}"',
            # Fastapi does not automatically determine the content-length for
            # StreamingResponse, so set it here.
            # This lets the browser tell the user the progress of the file download.
            "Content-Length": str(file_downloader.size),
        },
    )


@router.get(
    "/published_submissions/{published_submission_id}/metadata-download/",
    status_code=status.HTTP_200_OK,
)
def download_submission_metadata_file(
    request: Request,
    published_submission_id: str,
    settings: Settings = Depends(get_settings),
):
    published_submission_collection = get_published_submission_collection(settings)
    published_submission_set_collection = get_published_submission_set_collection(settings)

    raw_submission = published_submission_collection.find_one(
        {"persistent_id": published_submission_id},
    )
    if raw_submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published submission not found",
        )
    submission = PublishedSubmissionInternal(**raw_submission)

    # Forbid download if Submission is restricted and User does not have permission.
    if submission.visibility == PublishedSubmissionVisibility.RESTRICTED:
        if not is_authorised(Permission.SENSITIVE, request, settings):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    raw_submission_set = published_submission_set_collection.find_one(
        {"persistent_id": submission.submission_set_id},
    )
    if raw_submission_set is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No Submission Set found for Submission",
        )
    submission_set = PublishedSubmissionSetInternal(**raw_submission_set)

    file_name, file_content = get_submission_metadata_file(
        settings=settings,
        submission=submission,
        submission_set=submission_set,
    )

    return Response(
        file_content,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.get(
    "/published_submissions/{published_submission_id}/bundle-download/",
    status_code=status.HTTP_200_OK,
)
def download_submission_bundle_file(
    request: Request,
    published_submission_id: str,
    settings: Settings = Depends(get_settings),
):
    published_submission_collection = get_published_submission_collection(settings)
    published_submission_set_collection = get_published_submission_set_collection(settings)

    raw_submission = published_submission_collection.find_one(
        {"persistent_id": published_submission_id},
    )
    if raw_submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published submission not found",
        )
    submission = PublishedSubmissionInternal(**raw_submission)

    # Forbid download if Submission is restricted and User does not have permission.
    if submission.visibility == PublishedSubmissionVisibility.RESTRICTED:
        if not is_authorised(Permission.SENSITIVE, request, settings):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    raw_submission_set = published_submission_set_collection.find_one(
        {"persistent_id": submission.submission_set_id},
    )
    if raw_submission_set is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No Submission Set found for Submission",
        )
    submission_set = PublishedSubmissionSetInternal(**raw_submission_set)

    # Setup zipfile as a temporary file on disk
    temp_zip_file = tempfile.TemporaryFile(mode="w+b", suffix="_dandjoo_temp_zip")
    zip_file_writer = zipfile.ZipFile(temp_zip_file, mode="w")

    # Write metadata file to zip archive
    metadata_name, metadata_content = get_submission_metadata_file(
        settings=settings,
        submission=submission,
        submission_set=submission_set,
    )
    zip_file_writer.writestr(metadata_name, metadata_content)

    # Write supporting files
    blob_store_available = check_blob_store_available(settings)
    for supporting_file in submission.metadata.supporting_files:
        # Check blob_url is there
        if supporting_file.visibility == SupportingFileVisibility.RESTRICTED:
            blob_url = supporting_file.restricted_file_location
            use_credentials = True
        elif supporting_file.visibility == SupportingFileVisibility.PUBLIC:
            blob_url = supporting_file.public_file_location
            use_credentials = False
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unknown file visibility: {supporting_file.visibility!r}",
            )
        if not blob_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Supporting file did not have a blob url",
            )

        # If blob store unavailable, or this file wasn't actually uploaded, skip it.
        if (
            blob_url == "placeholder_location_string"
            or (not blob_store_available)
        ):
            continue

        # Determine filename to use in zip
        file_name_in_zip = supporting_file.file_name
        i = 0
        while file_name_in_zip in zip_file_writer.namelist():
            i += 1
            base, ext = os.path.splitext(supporting_file.file_name)
            file_name_in_zip = f"{base}({i}){ext}"

        # Create local temp copy of file
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix="_dandjoo_temp_blob_copy",
        ) as temp_copy:
            blob_downloader = get_blob_downloader(
                settings=settings,
                blob_url=blob_url,
                use_credentials=use_credentials,
            )
            blob_downloader.readinto(temp_copy)
            temp_copy.flush()

            # Write supporting file to zip
            zip_file_writer.write(
                filename=temp_copy.name, arcname=file_name_in_zip
            )

    # Finalize writing zip file
    zip_file_writer.close()
    temp_zip_file.flush()
    temp_zip_file.seek(0)

    file_size = os.stat(temp_zip_file.fileno()).st_size
    file_name = f"Bundle for {submission.metadata.name} ({submission.persistent_id}).zip"
    return StreamingResponse(
        _stream_file_then_close(file_obj=temp_zip_file),
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(file_size),
        },
    )


def _stream_file_then_close(
    *,
    file_obj: IO[bytes],
    chunk_size: int = 1024 * 1024,
) -> Iterator[bytes]:
    """
    Return an iterator that yields chunks of file_obj, then closes it when finished.

    This is designed to be passed to a fastapi StreamingResponse.
    """
    while True:
        chunk = file_obj.read(chunk_size)
        if chunk:
            yield chunk
        else:
            break
    file_obj.close()
