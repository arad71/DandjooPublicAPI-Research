import os
import datetime
import shutil
from typing import List, Union, Optional

from bson.objectid import ObjectId
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Body
from fastapi.responses import Response, JSONResponse
from pymongo import ReturnDocument
from starlette import status

from app.dependencies import get_settings
from app.helpers.curation_connector import send_submission_to_curation
from app.helpers.dandjoo_id import DandjooId
from app.helpers.mongo import get_supporting_file_collection, get_submission_collection, \
    get_submission_set_collection
from app.helpers.supporting_files import validate_and_get_sample_record_data, uniquify
from app.models.submission import (Metadata, Submission, SpreadsheetMappings, Mappings, SubmissionSet,
                                   NewSubmissionMetadata, SurveyMetadata,
                                   SupportingFileUsage, OccurrenceMetadata,
                                   UploadSupportingFileResponse, SupportingFileUsageResponse,
                                   SubmissionCompleteResponse, VegetationMetadata)
from app.models.common_enums import DataType, DocumentType
from app.models.supporting_files import SupportingFile
from app.helpers.authorisation import is_authorised, Permission, get_user_id
from app.helpers.py_object import PyObjectId
from app.settings import Settings
from app.validators.data_validator import DataValidator
from app.validators.file_validators import CSVFileValidator, ExcelFileValidator, ShapeFileValidator, FileValidator
from app.validators.metadata_validators import validate_file_usage
from app.readers.file_readers import CSVFileReader, ExcelFileReader, ShapeFileReader

router = APIRouter()


@router.post("/submission", status_code=status.HTTP_201_CREATED)
def create_new_submission(
    request: Request,
    metadata: NewSubmissionMetadata,
    settings: Settings = Depends(get_settings),
) -> NewSubmissionMetadata:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_sets = get_submission_set_collection(settings)

    if not metadata.accept_terms_and_conditions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Must contain accept_terms_and_conditions flag set as true')

    submitter_id = get_user_id(request, settings)
    if submitter_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Unable to obtain user id')

    # Create a new submission metadata object that only contains information in fields that are valid for user input
    submission_metadata = Metadata(__root__=metadata.submission.__root__.new_entry_dict())
    submission_metadata.__root__.created_on = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()

    submission_set_dict = None
    if isinstance(submission_metadata.__root__, SurveyMetadata):
        # For surveys, get or create the Project (Submission Set)
        if not submission_metadata.__root__.submission_set_persistent_id:
            # The submission does not specify an existing submission_set, so we need to make one
            if not metadata.submission_set:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='No submission set details for existing or new submission set provided')
            # Create a new submission_set metadata object that only contains information in fields that are valid for user input
            new_submission_set = SubmissionSet(**metadata.submission_set.new_entry_dict())
            new_submission_set.submitter_id = submitter_id
            if new_submission_set.metadata.datatype != submission_metadata.__root__.datatype:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='Datatype for new submission_set and new submission must match')

            new_submission_set_id = submission_sets.insert_one(new_submission_set.dict(exclude_unset=True)).inserted_id
            submission_metadata.__root__.submission_set_persistent_id = new_submission_set.persistent_id
            submission_set_dict = submission_sets.find_one({"_id": new_submission_set_id})
        else:
            # submission_set_persistent_id was included in the submission, validate the id and use that submission set
            submission_set_dict = submission_sets.find_one(
                {'persistent_id': submission_metadata.__root__.submission_set_persistent_id}
            )
            if not submission_set_dict:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='Invalid submission_set_persistent_id')
            if submission_set_dict['metadata']['datatype'] != submission_metadata.__root__.datatype.value:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail='Datatype for new submission must match existing submission_set')

    # Add the new submission (occurrence submission or survey submission) to the submissions collection
    submission_entry = Submission(
        persistent_id=DandjooId.new_id(),
        metadata=submission_metadata.__root__.dict(),
        submitter_id=submitter_id,
    )
    submission_insert_result = submissions.insert_one(submission_entry.dict())
    submission_id = str(submission_insert_result.inserted_id)

    new_submission = NewSubmissionMetadata(accept_terms_and_conditions=True,
                                           submission=submission_metadata,
                                           submission_set=submission_set_dict,
                                           new_submission_id=submission_id)

    return new_submission


@router.delete("/submission/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(request: Request, submission_id: str, settings: Settings = Depends(get_settings)) -> Response:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # delete source file if it exists
    if isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)) and submission.metadata.sourcefile:
        file_path = os.path.join(settings.temp_file_storage_path, submission.metadata.sourcefile)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass

    submissions.delete_one({'_id': ObjectId(submission_id)})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/submission/{submission_id}/metadata", status_code=status.HTTP_200_OK)
def partially_update_metadata(request: Request, submission_id: str, metadata: Metadata,
                                    settings: Settings = Depends(get_settings)) -> Metadata:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    if submission.metadata is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission metadata does not exist')
    if submission.metadata.datatype != metadata.__root__.datatype:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission datatype must not be changed")

    # get dictionary of just the items being patched and apply those changes
    update_metadata_dict = metadata.__root__.update_entry_dict()
    updated_metadata = submission.metadata.copy(update=update_metadata_dict)
    updated_submission_dict = submissions.find_one_and_update({'_id': ObjectId(submission_id)},
                                                              {'$set': {'metadata': updated_metadata.dict()}},
                                                              return_document=ReturnDocument.AFTER)

    return Metadata(__root__=updated_submission_dict['metadata'])


@router.post("/submission/{submission_id}/source-file", status_code=status.HTTP_201_CREATED)
def upload_source(request: Request, submission_id: str, source_file: UploadFile = File(...),
                        settings: Settings = Depends(get_settings)) -> Response:
    """
    Used to upload a source file to a submission
    """
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # check submission can receive sourcefile
    if not isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission does not support sourcefile')

    # if submission already has a source file, delete it in favor of new one
    if submission.metadata.sourcefile:
        old_file_path = os.path.join(settings.temp_file_storage_path, submission.metadata.sourcefile)
        try:
            os.remove(old_file_path)
        except FileNotFoundError:
            pass

    if submission.metadata.datatype == DataType.VEGETATION_ASSOCIATION:
        geometry_types = ['POLYGON', 'POLYGONZ']
    else:
        geometry_types = ['POINT', 'POINTZ']

    file_path = os.path.join(settings.temp_file_storage_path, source_file.filename)

    with open(file_path, "wb") as saved_file:
        shutil.copyfileobj(source_file.file, saved_file)

    if source_file.filename.endswith('.csv'):
        validator = CSVFileValidator(file_path)
        reader = CSVFileReader(file_path)
    elif source_file.filename.endswith('.xlsx') or source_file.filename.endswith('.xlsm'):
        validator = ExcelFileValidator(file_path)
        reader = ExcelFileReader(file_path)
    elif source_file.filename.endswith('.zip'):
        validator = ShapeFileValidator(file_path, geometry_types)
        reader = ShapeFileReader(file_path)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid content type')

    validator.validate()

    if not validator.is_valid:
        try:
            os.remove(file_path)
        except OSError:
            pass

        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=validator.errors)

    updated_metadata = submission.metadata.copy(update={'sourcefile': source_file.filename})

    submissions.find_one_and_update({'_id': ObjectId(submission_id)},
                                    {'$set': {
                                        'metadata': updated_metadata.dict()
                                    }})

    return reader.get_data_sample()


@router.delete("/submission/{submission_id}/source-file", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(request: Request, submission_id: str, settings: Settings = Depends(get_settings)) -> Response:
    """
    Used to delete a source file from a submission
    """
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # check this submission has a sourcefile
    if not isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)) or not submission.metadata.sourcefile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='No source file associated with this submission')

    file_path = os.path.join(settings.temp_file_storage_path, submission.metadata.sourcefile)

    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass

    updated_metadata = submission.metadata.copy(update={'sourcefile': None})

    submissions.find_one_and_update({'_id': ObjectId(submission_id)},
                                    {'$set': {
                                        'metadata': updated_metadata.dict()
                                    }})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/submission/{submission_id}/supporting-file", response_model=UploadSupportingFileResponse)
def upload_submission_supporting_file(
    request: Request,
    submission_id: PyObjectId,
    supporting_file: UploadFile = File(),
    settings: Settings = Depends(get_settings),
) -> UploadSupportingFileResponse:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_dict = submissions.find_one({'_id': submission_id})

    # check if submission exists
    if not submission_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # check if submission is a survey
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no survey metadata')

    # Check submission has submission_set to associate new file with
    submission_set_persistent_id = submission.metadata.submission_set_persistent_id
    if not submission_set_persistent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no submission_set')

    # Generate file id, and unique internal file name.
    file_id = PyObjectId()
    internal_file_name = uniquify(
        settings,
        os.path.join("submission-sets", submission_set_persistent_id, supporting_file.filename),
    )
    # Save uploaded file
    file_path = os.path.join(settings.temp_file_storage_path, internal_file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, mode="wb") as file_to_write:
        shutil.copyfileobj(supporting_file.file, file_to_write)

    # get uploaded file size
    file_size = os.stat(file_path).st_size

    # Create document for new file and usage
    supporting_file_document = SupportingFile(
        _id=file_id,
        file_name=supporting_file.filename,
        internal_file_name=internal_file_name,
        uploaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        file_size=file_size,
        submission_set_persistent_id=submission_set_persistent_id,
    )
    supporting_file_usage = SupportingFileUsage(
        usage_id=PyObjectId(),
        file_id=file_id,
        # Uploaded files default to these options.
        document_type=DocumentType.SUPPLEMENTARY_DOCUMENTATION,
        private=False,
    )

    # at this point don't know if the file is going to be record data or not, just perform basic validation
    validator = FileValidator(file_path)
    validator.validate()
    # also validate the usage of the new file
    usage_errors = validate_file_usage(
        usage=supporting_file_usage,
        supporting_file=supporting_file_document,
        metadata=submission.metadata,
    )
    if not validator.is_valid or usage_errors:
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={**validator.errors, **usage_errors})

    # insert new document in supporting_files_collection
    supporting_files = get_supporting_file_collection(settings)
    inserted_id = supporting_files.insert_one(supporting_file_document.dict(by_alias=True)).inserted_id
    assert inserted_id == file_id

    # Update submission metadata with new file
    submissions.update_one(
        {"_id": submission_id},
        # can't use $push because supporting_files might be NULL
        [
            {
                "$set": {
                    "metadata.supporting_files": {
                        "$ifNull": [
                            {"$concatArrays": ["$metadata.supporting_files", [supporting_file_usage.dict()]]},
                            [supporting_file_usage.dict()],
                        ],
                    },
                },
            },
        ],
    )
    return UploadSupportingFileResponse(
        supporting_file=supporting_file_document,
        usage=supporting_file_usage,
    )


@router.post("/submission/{submission_id}/supporting-file-usage", response_model=SupportingFileUsageResponse)
def create_submission_supporting_file_usage(
    request: Request,
    submission_id: PyObjectId,
    file_id: PyObjectId = Body(embed=True),
    document_type: DocumentType = Body(embed=True),
    private: bool = Body(embed=True),
    settings: Settings = Depends(get_settings),
) -> SupportingFileUsageResponse:
    """
    Add a usage of an existing supporting file to an existing submission.
    """
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_dict = submissions.find_one({"_id": submission_id})

    # check if submission and file exists
    if not submission_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission and/or file usage not found")

    submission = Submission(**submission_dict)

    # check if submission is a survey
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no survey metadata')

    # check supporting file exists
    supporting_files = get_supporting_file_collection(settings)
    supporting_file_dict = supporting_files.find_one({"_id": file_id})
    if not supporting_file_dict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not find file matching file_id")
    supporting_file = SupportingFile(**supporting_file_dict)

    # create new usage in memory
    new_usage = SupportingFileUsage(
        usage_id=PyObjectId(),
        file_id=supporting_file.id,
        document_type=document_type,
        private=private,
    )
    # validate new usage
    errors = validate_file_usage(
        usage=new_usage,
        supporting_file=supporting_file,
        metadata=submission.metadata,
    )
    # if there are no other errors and the file is being used as RECORD_DATA,
    # validate file content and get sample data.
    if not errors and new_usage.document_type == DocumentType.RECORD_DATA:
        record_errors, sample_data = validate_and_get_sample_record_data(
            supporting_file=supporting_file, settings=settings
        )
        if record_errors:
            errors.update(record_errors)
    else:
        sample_data = None

    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)

    # Update submission metadata with new usage
    submissions.update_one(
        {"_id": submission_id},
        # can't use $push because supporting_files might be NULL
        [
            {
                "$set": {
                    "metadata.supporting_files": {
                        "$ifNull": [
                            {"$concatArrays": ["$metadata.supporting_files", [new_usage.dict()]]},
                            [new_usage.dict()],
                        ],
                    },
                },
            },
        ],
    )
    return SupportingFileUsageResponse(usage=new_usage, sample_data=sample_data)


@router.get("/submission/{submission_id}/supporting-file-usages", response_model=List[SupportingFileUsage])
def get_submission_supporting_file_usages(
    request: Request,
    submission_id: PyObjectId,
    settings: Settings = Depends(get_settings),
) -> List[SupportingFileUsage]:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_dict = submissions.find_one({'_id': submission_id})

    # check if submission exists
    if not submission_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # check if submission is a survey
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no survey metadata')

    return submission.metadata.supporting_files or []


@router.patch("/submission/{submission_id}/supporting-file-usage/{usage_id}", response_model=SupportingFileUsageResponse)
def update_submission_supporting_file_usage(
    request: Request,
    submission_id: PyObjectId,
    usage_id: PyObjectId,
    document_type: DocumentType = Body(embed=True),
    private: bool = Body(embed=True),
    settings: Settings = Depends(get_settings),
) -> SupportingFileUsageResponse:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_dict = submissions.find_one(
        {"_id": submission_id, "metadata.supporting_files.usage_id": usage_id}
    )

    # check if submission and usage exists
    if not submission_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission and/or file usage not found")

    submission = Submission(**submission_dict)

    # check if submission is a survey
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no survey metadata')

    usage = next(u for u in (submission.metadata.supporting_files or []) if u.usage_id == usage_id)

    # get supporting file document
    supporting_files = get_supporting_file_collection(settings)
    supporting_file_dict = supporting_files.find_one({"_id": usage.file_id})
    if not supporting_file_dict:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not find file for usage")
    supporting_file = SupportingFile(**supporting_file_dict)

    # update usage in-memory
    usage.private = private
    usage.document_type = document_type
    # validate updated usage
    errors = validate_file_usage(
        usage=usage,
        supporting_file=supporting_file,
        metadata=submission.metadata,
    )
    # if there are no other errors and the file is being used as RECORD_DATA,
    # validate file content and get sample data.
    if not errors and usage.document_type == DocumentType.RECORD_DATA:
        record_errors, sample_data = validate_and_get_sample_record_data(
            supporting_file=supporting_file, settings=settings
        )
        if record_errors:
            errors.update(record_errors)
    else:
        sample_data = None

    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)

    updated_submission = submissions.find_one_and_update(
        {"_id": submission_id, "metadata.supporting_files.usage_id": usage_id},
        {"$set": {
            "metadata.supporting_files.$": usage.dict(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    updated_submission = Submission(**updated_submission)
    updated_usage = next(u for u in (updated_submission.metadata.supporting_files or []) if u.usage_id == usage_id)
    return SupportingFileUsageResponse(usage=updated_usage, sample_data=sample_data)


@router.delete("/submission/{submission_id}/supporting-file-usage/{usage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission_supporting_file_usage(
    request: Request,
    submission_id: PyObjectId,
    usage_id: PyObjectId,
    settings: Settings = Depends(get_settings),
) -> Response:
    """
    Delete the supporting file usage,
    and if there are no remaining usages of the supporting file, delete the supporting file.
    """
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_dict = submissions.find_one(
        {"_id": submission_id, "metadata.supporting_files.usage_id": usage_id}
    )

    # check if submission exists
    if not submission_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission and/or usage not found")

    submission = Submission(**submission_dict)

    # check if submission is a survey
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Submission has no survey metadata')

    usage_to_delete = next(
        usage
        for usage in submission.metadata.supporting_files
        if usage.usage_id == usage_id
    )

    # delete usage from mongo
    submissions.update_one(
        {"_id": submission_id},
        {"$pull": {"metadata.supporting_files": {"usage_id": usage_id}}},
    )

    # If there are no submissions using this supporting file, i.e. there are no usages of it left, delete it entirely.
    submissions_using_file = submissions.count_documents({"metadata.supporting_files.file_id": usage_to_delete.file_id})
    if submissions_using_file == 0:
        supporting_files = get_supporting_file_collection(settings)
        supporting_file_to_delete = SupportingFile(**supporting_files.find_one({"_id": usage_to_delete.file_id}))
        # Delete actual file.
        file_to_delete = os.path.join(settings.temp_file_storage_path, supporting_file_to_delete.internal_file_name)
        try:
            os.remove(file_to_delete)
        except FileNotFoundError:
            pass
        # Delete supporting file entry from Mongo.
        supporting_files.delete_one({"_id": supporting_file_to_delete.id})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/submission/{submission_id}/mappings", status_code=status.HTTP_201_CREATED)
def create_mappings(request: Request, submission_id: str, mappings: Union[SpreadsheetMappings, Mappings],
                    settings: Settings = Depends(get_settings)) -> Union[SpreadsheetMappings, Mappings]:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    supporting_files = get_supporting_file_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    submission = Submission(**submission_dict)

    if submission.metadata is None:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Submission has no associated metadata")

    # Get the file name of the record file, depending on what type of submission it is
    record_data_file_name: Optional[str] = None
    if isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)):
        record_data_file_name = submission.metadata.sourcefile
    elif isinstance(submission.metadata, SurveyMetadata):
        record_data_file_id = next(
            (
                usage.file_id for usage in (submission.metadata.supporting_files or [])
                if usage.document_type == DocumentType.RECORD_DATA
            ),
            None,
        )
        if record_data_file_id:
            supporting_file_dict = supporting_files.find_one({"_id": record_data_file_id})
            if not supporting_file_dict:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="Could not find file for usage")
            record_data_file_name = supporting_file_dict['file_name']

    if not record_data_file_name:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Submission has no sourcefile or record data")

    updated_submission_dict = submissions.find_one_and_update({'_id': ObjectId(submission_id)},
                                                              {'$set': {'mappings': mappings.dict()}},
                                                              return_document=ReturnDocument.AFTER)

    if record_data_file_name.endswith('.zip'):
        return Mappings(**updated_submission_dict['mappings'])
    else:
        return SpreadsheetMappings(**updated_submission_dict['mappings'])


@router.delete("/submission/{submission_id}/mappings", status_code=status.HTTP_204_NO_CONTENT)
def delete_mappings(request: Request, submission_id: str, settings: Settings = Depends(get_settings)) -> Response:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")


    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Submission not found')

    submission = Submission(**submission_dict)

    # check if mappings have been specified
    if submission.mappings is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='No mappings associated with this submission')

    submissions.find_one_and_update({'_id': ObjectId(submission_id)},
                                    {'$set': {
                                        'mappings': None
                                    }})

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/submission/{submission_id}/validate", status_code=status.HTTP_200_OK)
def validate_records_and_mappings(request: Request, submission_id: str, format: str = 'json',
             settings: Settings = Depends(get_settings)) -> Response:
    """
    Validate that the source file / record data file contains valid Records when read according to the current mappings.
    """
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    supporting_files = get_supporting_file_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    submission = Submission(**submission_dict)

    if submission.metadata is None:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Submission has no associated metadata")

    if submission.mappings is None:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Submission has no mappings set")

    # Depending on what type of submission it is, get the file path of the record file.
    record_data_file_path: Optional[str] = None
    if isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)):
        if submission.metadata.sourcefile:
            record_data_file_path = os.path.join(settings.temp_file_storage_path, submission.metadata.sourcefile)
    elif isinstance(submission.metadata, SurveyMetadata):
        record_data_file_id = next(
            (
                usage.file_id for usage in (submission.metadata.supporting_files or [])
                if usage.document_type == DocumentType.RECORD_DATA
            ),
            None,
        )
        if record_data_file_id:
            supporting_file_dict = supporting_files.find_one({"_id": record_data_file_id})
            if not supporting_file_dict:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="Could not find file for usage")
            supporting_file = SupportingFile(**supporting_file_dict)
            record_data_file_path = os.path.join(settings.temp_file_storage_path, supporting_file.internal_file_name)

    if not record_data_file_path:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY,
                            detail="Submission has no sourcefile or record data")

    if record_data_file_path.endswith('.csv'):
        reader = CSVFileReader(record_data_file_path)
    elif record_data_file_path.endswith('.zip'):
        reader = ShapeFileReader(record_data_file_path)
    else:
        reader = ExcelFileReader(record_data_file_path)

    is_spreadsheet = not record_data_file_path.endswith('zip')

    data_validator = DataValidator(submission.mappings, reader.records, is_spreadsheet)

    errors = data_validator.validate()

    if format == 'file':
        response_body = '\n'.join(errors)
        response = Response(response_body, media_type='text/plain')
        response.headers['Content-Disposition'] = 'attachment; filename="submission errors.txt"'

        return response

    return errors


@router.post("/submission/{submission_id}/submit",
             status_code=status.HTTP_200_OK,
             response_model=SubmissionCompleteResponse)
def submit(request: Request, submission_id: str, settings: Settings = Depends(get_settings)) -> SubmissionCompleteResponse:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)
    submission_sets = get_submission_set_collection(settings)

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    submission = Submission(**submission_dict)
    if submission.metadata is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission has no metadata")

    try:
        curation_submission_id = send_submission_to_curation(submission, settings)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Error forwarding to curation: {str(e)}')

    # Updated sent_to_curation flag
    updates = {"sent_to_curation": True}
    # update persistent_id if Curation has returned a different id to what submission already has.
    if curation_submission_id and curation_submission_id != submission.persistent_id:
        updates['persistent_id'] = curation_submission_id
    submissions.find_one_and_update({'_id': ObjectId(submission_id)}, update={"$set": updates})

    # update sent_to_curation flag on Submission Set, if not already set to True.
    if isinstance(submission.metadata, SurveyMetadata) and submission.metadata.submission_set_persistent_id:
        submission_sets.find_one_and_update(
            filter={
                'persistent_id': submission.metadata.submission_set_persistent_id,
                "sent_to_curation": {"$ne": True},
            },
            update={"$set": {"sent_to_curation": True}},
        )

    # delete temp files after submission:
    # delete source file if it exists
    if isinstance(submission.metadata, (OccurrenceMetadata, VegetationMetadata)) and submission.metadata.sourcefile:
        try:
            os.remove(os.path.join(settings.temp_file_storage_path, submission.metadata.sourcefile))
        except FileNotFoundError:
            pass

    return SubmissionCompleteResponse(
        submission_id=submission_id,
        persistent_id=curation_submission_id,
        sent_to_curation=True,
        unmappable=False,
    )


@router.post("/submission/{submission_id}/mark-unmappable",
             status_code=status.HTTP_200_OK,
             response_model=SubmissionCompleteResponse)
def mark_unmappable(
    request: Request,
    submission_id: PyObjectId,
    settings: Settings = Depends(get_settings),
) -> SubmissionCompleteResponse:
    if not is_authorised(Permission.SUBMIT, request, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    submissions = get_submission_collection(settings)

    submission_dict = submissions.find_one({'_id': submission_id})

    # check if submission exists
    if not bool(submission_dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    submission = Submission(**submission_dict)
    if not isinstance(submission.metadata, SurveyMetadata):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission is not a Survey")

    if not submission.persistent_id:
        # Generate a "persistent ID" if this submission doesn't already have one.
        submission.persistent_id = DandjooId.new_id()

    submissions.find_one_and_update(
        {'_id': submission_id},
        {'$set': {
            "unmappable": True,
            'persistent_id': submission.persistent_id,
        }},
    )
    return SubmissionCompleteResponse(
        submission_id=str(submission_id),
        persistent_id=submission.persistent_id,
        sent_to_curation=False,
        unmappable=True,
    )
