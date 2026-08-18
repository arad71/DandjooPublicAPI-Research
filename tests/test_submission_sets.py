from unittest.mock import patch, ANY

import pytest
from starlette import status
from fastapi.testclient import TestClient

from app import main
from app.helpers.dandjoo_id import DandjooId
from app.helpers.mongo import get_submission_set_collection, get_submission_collection
from app.helpers.py_object import PyObjectId
from app.models.common_enums import DataType, DocumentType
from app.models.submission import Submission, SurveyMetadata, SupportingFileUsage
from tests.helpers import mock_authentication
from tests.helpers.factories import supporting_file_factory, submission_set_factory


client = TestClient(main.app)


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.routers.submission_set.is_authorised', mock_authentication.is_authorised) as _fixture:
        yield _fixture


def test_list_submission_sets(test_settings):
    submission_sets_collection = get_submission_set_collection(test_settings)
    submission_sets_collection.drop()  # clear collection so list result is not flaky

    submission_set_1 = submission_set_factory(test_settings, name="Submission Set Foo", comments="Foo foo")
    submission_set_2 = submission_set_factory(test_settings, name="Submission Set Bar", comments="Bar bar")

    response = client.get(f"/submission_sets",
                          headers={'x-email': 'submitter@test.net'})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "_id": str(submission_set_1.id),
            "persistent_id": submission_set_1.persistent_id,
            'name': 'Submission Set Foo',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "Foo foo",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
        {
            "_id": str(submission_set_2.id),
            "persistent_id": submission_set_2.persistent_id,
            'name': 'Submission Set Bar',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "Bar bar",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        }
    ]


def test_list_submission_sets_with_filter(test_settings):
    submission_set_1 = submission_set_factory(test_settings, name="Submission Set One")
    submission_set_2 = submission_set_factory(test_settings, name="Submission Set One and a half")
    # will be filtered due to name
    submission_set_factory(test_settings, name="Submission Set Two")
    # will be filtered due to datatype
    submission_set_factory(test_settings, name="Submission Set One and a quarter", metadata={"datatype": DataType.SPECIES_OCCURRENCE})

    response = client.get(f"/submission_sets",
                          headers={'x-email': 'submitter@test.net'},
                          params={"name": "One", "datatype": "Systematic survey data"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "_id": str(submission_set_1.id),
            "persistent_id": submission_set_1.persistent_id,
            'name': 'Submission Set One',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "These are comments for a test submission set",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
        {
            "_id": str(submission_set_2.id),
            "persistent_id": submission_set_2.persistent_id,
            'name': 'Submission Set One and a half',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "These are comments for a test submission set",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
    ]

    # test filter by persistent_id
    response_2 = client.get(f"/submission_sets",
                          headers={'x-email': 'submitter@test.net'},
                          params={"persistent_id": submission_set_1.persistent_id})
    assert response_2.status_code == status.HTTP_200_OK
    assert response_2.json() == [
        {
            "_id": str(submission_set_1.id),
            "persistent_id": submission_set_1.persistent_id,
            'name': 'Submission Set One',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "These are comments for a test submission set",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
    ]


def test_list_submission_sets_archived_filter(test_settings):
    submission_set_1 = submission_set_factory(
        test_settings, name="Submission Set One", archived_in_curation=None,
    )
    submission_set_2 = submission_set_factory(
        test_settings, name="Submission Set Two", archived_in_curation=False,
    )
    # will be excluded by filter
    submission_set_factory(
        test_settings, name="Submission Set Three", archived_in_curation=True,
    )

    response = client.get(
        f"/submission_sets",
        headers={'x-email': 'submitter@test.net'},
        params={"exclude_archived": "true"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "_id": str(submission_set_1.id),
            "persistent_id": submission_set_1.persistent_id,
            'name': 'Submission Set One',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': None,
            'comments': "These are comments for a test submission set",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
        {
            "_id": str(submission_set_2.id),
            "persistent_id": submission_set_2.persistent_id,
            'name': 'Submission Set Two',
            'submitter_id': "test-submitter-id",
            "sent_to_curation": None,
            'archived_in_curation': False,
            'comments': "These are comments for a test submission set",
            "submitter": "Department of Testing",
            "metadata": {
                "datatype": "Systematic survey data",
                "purpose": "for testing",
            },
        },
    ]


def test_get_submission_set(test_settings):
    submission_set_1 = submission_set_factory(test_settings, name="Submission Set Foo", comments="Foo foo")

    response = client.get(f"/submission_set/{submission_set_1.id}",
                          headers={'x-email': 'submitter@test.net'})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "_id": str(submission_set_1.id),
        "persistent_id": submission_set_1.persistent_id,
        'name': 'Submission Set Foo',
        'submitter_id': "test-submitter-id",
        "sent_to_curation": None,
        'archived_in_curation': None,
        'comments': "Foo foo",
        "submitter": "Department of Testing",
        "metadata": {
            "datatype": "Systematic survey data",
            "purpose": "for testing",
        },
    }


def test_get_files_for_submission_set(test_settings):
    submission_set = submission_set_factory(test_settings)
    supporting_file_1 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    supporting_file_2 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)

    response = client.get(f"/submission_set/{submission_set.id}/supporting-files",
                          headers={'x-email': 'submitter@test.net'})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            '_id': str(supporting_file_1.id),
            'file_name': 'some_file.csv',
            'file_size': 43,
            'internal_file_name': supporting_file_1.internal_file_name,
            'submission_set_persistent_id': submission_set.persistent_id,
            'uploaded_at': '2023-01-01T00:00:00Z',
        },
        {
            '_id': str(supporting_file_2.id),
            'file_name': 'some_file.csv',
            'file_size': 43,
            'internal_file_name': supporting_file_2.internal_file_name,
            'submission_set_persistent_id': submission_set.persistent_id,
            'uploaded_at': '2023-01-01T00:00:00Z',
        },
    ]


def test_get_single_file_for_submission_set(test_settings):
    submission_set = submission_set_factory(test_settings)
    supporting_file_1 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)  # supporting_file_2 is not returned

    response = client.get(f"/submission_set/{submission_set.id}/supporting-file/{supporting_file_1.id}",
                          headers={'x-email': 'submitter@test.net'})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        '_id': str(supporting_file_1.id),
        'file_name': 'some_file.csv',
        'file_size': 43,
        'internal_file_name': supporting_file_1.internal_file_name,
        'submission_set_persistent_id': submission_set.persistent_id,
        'uploaded_at': '2023-01-01T00:00:00Z',
    }


def test_list_submissions_in_set(test_settings):
    submissions_collection = get_submission_collection(test_settings)

    # Create Submission Set
    submission_set = submission_set_factory(
        test_settings,
        metadata={"datatype": DataType.SYSTEMATIC_SURVEY},
    )

    # Create Submissions in Set
    file_id_1 = PyObjectId()
    file_id_2 = PyObjectId()
    file_id_3 = PyObjectId()  # shared file
    submission_1 = Submission(
        persistent_id=DandjooId.new_id(),
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
            name="Test Survey One",
            supporting_files=[
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_id_1,
                    document_type=DocumentType.RECORD_DATA,
                    private=False,
                ),
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_id_3,
                    document_type=DocumentType.REPORT,
                    private=True,
                ),
            ],
        ),
        submitter_id="some_test_submitter",
        sent_to_curation=True,
    )
    submission_1_id = submissions_collection.insert_one(submission_1.dict(exclude_unset=True)).inserted_id
    submission_2 = Submission(
        persistent_id=DandjooId.new_id(),
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
            name="Test Survey Two",
            supporting_files=[
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_id_2,
                    document_type=DocumentType.RECORD_DATA,
                    private=False,
                ),
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_id_3,
                    document_type=DocumentType.SITE_DATA,
                    private=True,
                ),
            ],
        ),
        submitter_id="some_test_submitter",
    )
    submission_2_id = submissions_collection.insert_one(submission_2.dict(exclude_unset=True)).inserted_id

    # Create submission not in Set (won't be returned)
    submission_3 = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
        ),
        submitter_id="some_test_submitter",
    )
    submissions_collection.insert_one(submission_3.dict(exclude_unset=True))

    response = client.get(f"/submission_set/{submission_set.id}/submissions",
                          headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            '_id': str(submission_2_id),
            'persistent_id': submission_2.persistent_id,
            'submitter_id': 'some_test_submitter',
            "sent_to_curation": None,
            'unmappable': None,
            'mappings': None,
            'metadata': {
                'bounding_box_north_west': None,
                'bounding_box_south_east': None,
                'created_on': None,
                'datatype': 'Systematic survey data',
                'datum': None,
                'from_date': None,
                'has_threatened_species': None,
                'participants': None,
                'submission_set_persistent_id': submission_set.persistent_id,
                'submitter': None,
                'name': "Test Survey Two",
                'summary': None,
                'tags': None,
                'to_date': None,
                'supporting_files': [
                    {
                        'document_type': 'RECORD_DATA',
                        'file_id': str(file_id_2),
                        'private': False,
                        'usage_id': ANY,
                    },
                    {
                        'document_type': 'SITE_DATA',
                        'file_id': str(file_id_3),
                        'private': True,
                        'usage_id': ANY,
                    },
                ],
            },
        },
        {
            '_id': str(submission_1_id),
            'persistent_id': submission_1.persistent_id,
            'submitter_id': 'some_test_submitter',
            "sent_to_curation": True,
            'unmappable': None,
            'mappings': None,
            'metadata': {
                'bounding_box_north_west': None,
                'bounding_box_south_east': None,
                'created_on': None,
                'datatype': 'Systematic survey data',
                'datum': None,
                'from_date': None,
                'has_threatened_species': None,
                'participants': None,
                'submission_set_persistent_id': submission_set.persistent_id,
                'submitter': None,
                'name': "Test Survey One",
                'summary': None,
                'tags': None,
                'to_date': None,
                'supporting_files': [
                    {
                        'document_type': 'RECORD_DATA',
                        'file_id': str(file_id_1),
                        'private': False,
                        'usage_id': ANY
                    },
                    {
                        'document_type': 'REPORT',
                        'file_id': str(file_id_3),
                        'private': True,
                        'usage_id': ANY,
                    },
                ],
            },
        },
    ]


def test_update_submission_set_from_curation_not_authorized(test_settings):
    submission_set = submission_set_factory(test_settings)

    response = client.patch(
        f"/submission_set/{submission_set.persistent_id}/curation_update",
        json={"name": "new name"},
        headers={"x-api-key": "wrong"},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    submission_set = get_submission_set_collection(test_settings).find_one({"_id": submission_set.id})
    assert submission_set['name'] == "Test Submission Set"  # not updated


def test_update_submission_set_from_curation(test_settings):
    submission_set = submission_set_factory(test_settings)

    response = client.patch(
        f"/submission_set/{submission_set.persistent_id}/curation_update",
        headers={"x-api-key": "test_password"},
        json={
            "name": "new name",
            "submitter": "new submitter",
            "comments": "new comments",
            "purpose": "new purpose",
        },
    )
    assert response.status_code == status.HTTP_200_OK

    submission_set_updated = get_submission_set_collection(test_settings).find_one({"_id": submission_set.id})
    assert submission_set_updated['name'] == "new name"
    assert submission_set_updated['submitter'] == "new submitter"
    assert submission_set_updated['comments'] == "new comments"
    assert submission_set_updated['metadata']['purpose'] == 'new purpose'


@pytest.mark.parametrize(
    "archived",
    [
        pytest.param(True, id="Archived=True"),
        pytest.param(False, id="Archived=False"),
    ],
)
def test_update_submission_set_archived_flag_from_curation(test_settings, archived):
    submission_set = submission_set_factory(test_settings)

    response = client.patch(
        f"/submission_set/{submission_set.persistent_id}/curation_update",
        headers={"x-api-key": "test_password"},
        json={
            "archived": archived,
        },
    )
    assert response.status_code == status.HTTP_200_OK

    submission_set_updated = get_submission_set_collection(test_settings).find_one({"_id": submission_set.id})
    assert submission_set_updated['archived_in_curation'] == archived
