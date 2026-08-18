from typing import Tuple, List

from app.helpers.mongo import get_published_submission_collection
from app.models.published_submissions import PublishedSubmissionInternal
from app.models.published_submission_sets import PublishedSubmissionSetInternal
from app.settings import Settings


def get_submission_metadata_file(
    *,
    settings: Settings,
    submission: PublishedSubmissionInternal,
    submission_set: PublishedSubmissionSetInternal,
) -> Tuple[str, str]:
    """
     Get the content of the Submission metadata file download.

    :return: (file_name, file_content) tuple
    """
    published_submission_collection = get_published_submission_collection(settings)

    # Derive the Submission Set date range from all Submission in it.
    cursor = published_submission_collection.aggregate([
        # Part 1: Get the matching Submissions for the Submission Set
        {"$match": {"submission_set_id": submission_set.persistent_id}},
        # Part 3: Compute derived fields from $all_submission array.
        {"$group": {
            "_id": None,
            "from_date": {"$min": "$metadata.from_date"},
            "to_date": {"$max": "$metadata.to_date"},
        }},
    ])
    with cursor:
        result = next(cursor, {})
    submission_set_from_date = result.get("from_date") or ""
    submission_set_to_date = result.get("to_date") or ""

    # Construct content of the file download
    file_lines: List[str] = [
        f"Project and Survey Metadata for {submission.metadata.name} ({submission.persistent_id})",
        "",
        "Project Metadata",
        f"Project name (abis:project): {submission_set.metadata.name}",
        f"Project date range start: {submission_set_from_date}",
        f"Project date range end: {submission_set_to_date}",
        f"Project purpose (abis:purpose): {_single_line(submission_set.metadata.purpose or '')}",
        f"Project reference (dwc:parentEventID): {submission_set.persistent_id}",
        "",
        "Survey Metadata",
        f"Survey name (tern:survey): {submission.metadata.name}",
        f"Survey date range start (tern:survey; prov:startedAtTime): {submission.metadata.from_date}",
        f"Survey date range end (tern:survey; prov:endedAtTime): {submission.metadata.to_date}",
        f"Survey summary (dwc:eventRemarks): {_single_line(submission.metadata.summary or '')}",
        f"Survey participants (dcterms:contributor): {submission.metadata.participants}",
        f"Survey ID (dwc:eventID): {submission.persistent_id}",
        "",
    ]
    file_content = "\n".join(file_lines)
    file_name = f"Project and Survey Metadata for {submission.metadata.name} ({submission.persistent_id}).txt"

    return file_name, file_content


def _single_line(text: str) -> str:
    return " ".join(text.split())
