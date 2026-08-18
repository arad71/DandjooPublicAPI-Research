from collections import defaultdict
from typing import List, Dict

from app.helpers.supporting_files import accepted_file_types
from app.models.submission import SurveyMetadata, SupportingFileUsage
from app.models.common_enums import DocumentType
from app.models.supporting_files import SupportingFile


ID_MISMATCH_ERROR = "id_mismatch"
FILE_TYPE_ERROR = "file_type"
RECORD_DATA_ERROR = "record_data"


def validate_file_usage(
    *,
    usage: SupportingFileUsage,
    supporting_file: SupportingFile,
    metadata: SurveyMetadata,
) -> Dict[str, List[str]]:
    """
    Validate a SupportingFileUsage, in relation to the SupprtingFile and survey submission it's for.

    :param usage: The SupportingFileUsage to be validated.
    :param supporting_file: The SupportingFile the usage is for.
    :param metadata: The metadata for the submission the usage is for.
    :return: A dict of errors, will be empty if all validation passes
    """
    errors: Dict[str, List[str]] = defaultdict(list)

    if usage.file_id != supporting_file.id:
        errors[ID_MISMATCH_ERROR].append("File id in usage does not match supporting file")
    if metadata.submission_set_persistent_id != supporting_file.submission_set_persistent_id:
        errors[ID_MISMATCH_ERROR].append("SubmissionSet id in supporting file does not match submission")

    # validate file extension is acceptable for the document type
    file_extension = supporting_file.file_extension
    if file_extension not in accepted_file_types(usage.document_type):
        errors[FILE_TYPE_ERROR].append(f"Invalid file type '{file_extension}' for '{usage.document_type.value}'")

    # if this file being used as RECORD_DATA, validate no other file for the submission is already RECORD DATA
    if usage.document_type == DocumentType.RECORD_DATA:
        if any(
            other_usage.document_type == DocumentType.RECORD_DATA
            for other_usage in (metadata.supporting_files or [])
            if other_usage.usage_id != usage.usage_id
        ):
            errors[RECORD_DATA_ERROR].append("This submission already has a Record Data file")

    return dict(errors)
