import io
import zipfile
from typing import IO, Iterator
from unittest.mock import patch, call

import pytest
from bson import ObjectId
from starlette import status
from starlette.testclient import TestClient

from app import main
from app.helpers.dandjoo_id import DandjooId
from tests.helpers import mock_authentication


client = TestClient(main.app)


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch(
        'app.routers.downloads.is_authorised',
        mock_authentication.is_authorised,
    ):
        yield


@pytest.fixture(scope='function')
def insert_restricted_test_submission():
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024GMP3Zcae75b8",
            "version": 0,
            "submission_set_id": "2024GMP3i487f118",
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Survey",
                "summary": "This is a survey",
                "submitter": "AAA CORP",
                "rights_holder": "BBB CORP",
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "participants": "One,Two,Three",
                "tags": ["tag1", "tag2", "tag3"],
                "bounding_box_north_west": {"type": "Point", "coordinates": [30, -40]},
                "bounding_box_south_east": {"type": "Point", "coordinates": [35, -45]},
                "supporting_files": [
                    {
                        "supporting_file_id": "66695492a00f3810f741c1be",
                        "file_name": "a_file.csv",
                        "file_size": 1_000,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                    },
                    {
                        "supporting_file_id": "66695493a00f3810f741c1bf",
                        "file_name": "b_file.csv",
                        "file_size": 2_000,
                        "document_types": ["SITE_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/b/file",
                    },
                    {
                        "supporting_file_id": "66695493a00f3810f741c100",
                        # same name as previous, but different file
                        "file_name": "b_file.csv",
                        "file_size": 2_077,
                        "document_types": ["SUPPLEMENTARY_DOCUMENTATION"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/b/file2",
                    },
                ],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.fixture(scope='function')
def insert_test_submission_set():
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024GMP3i487f118",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Project",
                "purpose": "For testing\nA second line...  ",
                "comments": "These are some comments",
                "submitter": "The Submitter",
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK


class MockFileDownloader:
    """
    This class is a minimal imitation of azure.storage.blob.StorageStreamDownloader

    To use as the return value for mocked functions in tests.
    """
    def __init__(self, content: bytes):
        self.size = len(content)
        self._content = content

    def readall(self) -> bytes:
        return self._content

    def chunks(self) -> Iterator[bytes]:
        return iter([self._content[i:i+2] for i in range(0, len(self._content), 2)])

    def readinto(self, stream: IO[bytes]) -> int:
        for chunk in self.chunks():
            stream.write(chunk)
        return self.size


def test_download_restricted_file_as_public_user():
    response = client.get(
        f"/published_submissions/{DandjooId.new_id()}/supporting_files/{ObjectId()}/",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_download_restricted_file_submission_not_found():
    response = client.get(
        f"/published_submissions/{DandjooId.new_id()}/supporting_files/{ObjectId()}/",
        headers={
            "X-email": "sensitive@test.net",
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Published submission not found'}


def test_download_restricted_file_supporting_file_not_found(
    insert_restricted_test_submission,
):
    response = client.get(
        f"/published_submissions/2024GMP3Zcae75b8/supporting_files/{ObjectId()}/",
        headers={
            "X-email": "sensitive@test.net",
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Supporting file not found'}


def test_download_restricted_file_success(
    insert_restricted_test_submission,
    test_settings,
):
    mock_downloader = MockFileDownloader(b"This is a file!")

    with  \
        patch(
            "app.routers.downloads.check_blob_store_available",
            return_value=True,
        ) as mock_check_blob_store_available, \
        patch(
            "app.routers.downloads.get_blob_downloader",
            return_value=mock_downloader,
        ) as mock_get_blob_downloader \
    :
        response = client.get(
            f"/published_submissions/2024GMP3Zcae75b8/supporting_files/66695492a00f3810f741c1be/",
            headers={
                "X-email": "sensitive@test.net",
            },
        )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="a_file.csv"'
    )
    assert int(response.headers["Content-Length"]) == len(b"This is a file!")
    assert response.content == b"This is a file!"

    mock_check_blob_store_available.assert_called_once_with(test_settings)
    mock_get_blob_downloader.assert_called_once_with(
        settings=test_settings,
        blob_url="https://in.private.blob.store.localhost/a/file",
        use_credentials=True,
    )


def test_download_metadata_submission_not_found():
    response = client.get(
        f"/published_submissions/{DandjooId.new_id()}/metadata-download/",
        headers={
            "X-email": "sensitive@test.net",
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Published submission not found'}


def test_download_restricted_metadata_as_public_user(
    insert_restricted_test_submission,
):
    response = client.get(
        "/published_submissions/2024GMP3Zcae75b8/metadata-download/",
        # No email header
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_download_metadata_success(
    insert_restricted_test_submission,
    insert_test_submission_set,
):
    response = client.get(
        "/published_submissions/2024GMP3Zcae75b8/metadata-download/",
        headers={
            "X-email": "sensitive@test.net",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="Project and Survey Metadata for A Survey (2024GMP3Zcae75b8).txt"'
    )
    assert response.content == (
        b'Project and Survey Metadata for A Survey (2024GMP3Zcae75b8)\n'
        b'\n'
        b'Project Metadata\n'
        b'Project name (abis:project): A Project\n'
        b'Project date range start: 2024-01-01\n'
        b'Project date range end: 2024-01-30\n'
        b'Project purpose (abis:purpose): For testing A second line...\n'
        b'Project reference (dwc:parentEventID): 2024GMP3i487f118\n'
        b'\n'
        b'Survey Metadata\n'
        b'Survey name (tern:survey): A Survey\n'
        b'Survey date range start (tern:survey; prov:startedAtTime): 2024-01-01\n'
        b'Survey date range end (tern:survey; prov:endedAtTime): 2024-01-30\n'
        b'Survey summary (dwc:eventRemarks): This is a survey\n'
        b'Survey participants (dcterms:contributor): One,Two,Three\n'
        b'Survey ID (dwc:eventID): 2024GMP3Zcae75b8\n'
    )


def test_download_zip_bundle_submission_not_found():
    response = client.get(
        f"/published_submissions/{DandjooId.new_id()}/bundle-download/",
        headers={
            "X-email": "sensitive@test.net",
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Published submission not found'}


def test_download_restricted_zip_bundle_as_public_user(
    insert_restricted_test_submission,
):
    response = client.get(
        "/published_submissions/2024GMP3Zcae75b8/bundle-download/",
        # No email header
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_download_zip_bundle_success(
    insert_restricted_test_submission,
    insert_test_submission_set,
    test_settings,
):
    mock_downloaders = [
        MockFileDownloader(b"File one"),
        MockFileDownloader(b"File two"),
        MockFileDownloader(b"File three"),
    ]

    with \
        patch(
            "app.routers.downloads.check_blob_store_available",
            return_value=True,
        ) as mock_check_blob_store_available, \
        patch(
            "app.routers.downloads.get_blob_downloader",
            side_effect=mock_downloaders,
        ) as mock_get_blob_downloader \
    :
        response = client.get(
            "/published_submissions/2024GMP3Zcae75b8/bundle-download/",
            headers={
                "X-email": "sensitive@test.net",
            },
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="Bundle for A Survey (2024GMP3Zcae75b8).zip"'
    )
    # testing that this header is present and matches size of response.
    assert int(response.headers["Content-Length"]) == len(response.content)

    mock_check_blob_store_available.assert_called_once_with(test_settings)
    mock_get_blob_downloader.assert_has_calls([
        call(settings=test_settings, blob_url="https://in.private.blob.store.localhost/a/file", use_credentials=True),
        call(settings=test_settings, blob_url="https://in.private.blob.store.localhost/b/file", use_credentials=True),
        call(settings=test_settings, blob_url="https://in.private.blob.store.localhost/b/file2", use_credentials=True),
    ])

    zip_file_reader = zipfile.ZipFile(io.BytesIO(response.content), mode="r")
    assert sorted(zip_file_reader.namelist()) == [
        'Project and Survey Metadata for A Survey (2024GMP3Zcae75b8).txt',
        'a_file.csv',
        'b_file(1).csv',
        'b_file.csv',
    ]
    with zip_file_reader.open('Project and Survey Metadata for A Survey (2024GMP3Zcae75b8).txt') as f:
        assert f.read().startswith(b'Project and Survey Metadata for A Survey')
    with zip_file_reader.open('a_file.csv',) as f:
        assert f.read() == b"File one"
    with zip_file_reader.open('b_file.csv',) as f:
        assert f.read() == b"File two"
    with zip_file_reader.open('b_file(1).csv',) as f:
        assert f.read() == b"File three"
    zip_file_reader.close()
