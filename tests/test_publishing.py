import os
from datetime import datetime
from unittest.mock import ANY

from bson import ObjectId
from starlette import status
from starlette.testclient import TestClient

from app import main
from app.helpers.mongo import get_published_submission_collection, get_published_submission_set_collection

os.environ['API_SYSTEM_KEY'] = 'test_password'

client = TestClient(main.app)


def test_create_published_submission_sets_not_authorised():
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": ""},
        json=[{}],
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_published_submission_sets(get_test_settings):
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024EPP4uda4d000",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Project",
                "purpose": "To be published",
                "comments": "Howdy",
                "submitter": "Someone",
            },
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "last_updated": ANY,
        "persistent_id": "2024EPP4uda4d000",
        "version": 0,
        "metadata": {
            "datatype": "Systematic survey data",
            "name": "A Project",
            "purpose": "To be published",
            "comments": "Howdy",
            "submitter": "Someone",
        },
    }

    submission_dict = (
        get_published_submission_set_collection(get_test_settings())
        .find_one({"persistent_id": "2024EPP4uda4d000"})
    )
    assert submission_dict == {
        '_id': ANY,
        'last_updated': ANY,
        "persistent_id": "2024EPP4uda4d000",
        "version": 0,
        "metadata": {
            "datatype": "Systematic survey data",
            "name": "A Project",
            "purpose": "To be published",
            "comments": "Howdy",
            "submitter": "Someone",
        },
    }
    assert isinstance(submission_dict['_id'], ObjectId)
    assert isinstance(submission_dict['last_updated'], str)
    assert datetime.fromisoformat(submission_dict['last_updated']).tzinfo is not None


def test_delete_published_submission_sets_not_authorised():
    response = client.delete(
        "/published_submission_sets/a1/",
        headers={"x-api-key": ""},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_delete_published_submission_sets_not_found():
    response = client.delete(
        "/published_submission_sets/a1/",
        headers={"x-api-key": "test_password"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"deleted_count": 0}


def test_delete_published_submission_sets(get_test_settings):
    published_submission_set_collection = get_published_submission_set_collection(get_test_settings())
    # Create some submission sets
    for payload in [
        {
            "persistent_id": "2024EPP4uda4d111",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Project 1",
                "purpose": "To be deleted",
                "comments": "Howdy",
                "submitter": "Someone",
            },
        },
        {
            "persistent_id": "2024EPP4uda4d222",
            "version": 1,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Project 2",
                "purpose": "To be kept",
                "comments": "Howdy",
                "submitter": "Someone",
            },
        },
        {
            "persistent_id": "2024EPP4uda4d333",
            "version": 1,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Project 3",
                "purpose": "To be kept",
                "comments": "Howdy",
                "submitter": "Someone",
            },
        },
    ]:
        response = client.post(
            "/published_submission_sets/",
            headers={"x-api-key": "test_password"},
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK
    assert published_submission_set_collection.count_documents({}) == 3

    # delete first one
    response = client.delete(
        "/published_submission_sets/2024EPP4uda4d111/",
        headers={"x-api-key": "test_password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"deleted_count": 1}

    assert published_submission_set_collection.count_documents({}) == 2
    assert published_submission_set_collection.find_one({"persistent_id": "2024EPP4uda4d111"}) is None
    assert published_submission_set_collection.find_one({"persistent_id": "2024EPP4uda4d222"}) is not None
    assert published_submission_set_collection.find_one({"persistent_id": "2024EPP4uda4d333"}) is not None


def test_create_published_submissions_not_authorised():
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": ""},
        json=[{}],
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_published_submissions(get_test_settings):
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024EPP4uda4d75a",
            "version": 0,
            "submission_set_id": "2024EPP4uda4d75b",
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
                        "supporting_file_id": "66276c9b5fa3128d9941ca38",
                        "file_name": "a_file.csv",
                        "file_size": 1_000,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                    },
                    {
                        "supporting_file_id": "66276ce45fa3128d9941ca39",
                        "file_name": "b_file.csv",
                        "file_size": 2_000,
                        "document_types": ["REPORT", "SITE_DATA", "SUPPLEMENTARY_DOCUMENTATION"],
                        "visibility": "PUBLIC",
                        "public_file_location": "https://in.public.blob.store.localhost/a/file",
                        "restricted_file_location": None,
                    },
                ],
            },
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "last_updated": ANY,
        "persistent_id": "2024EPP4uda4d75a",
        "version": 0,
        "submission_set_id": "2024EPP4uda4d75b",
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
                    "supporting_file_id": "66276c9b5fa3128d9941ca38",
                    "file_name": "a_file.csv",
                    "file_size": 1_000,
                    "document_types": ["RECORD_DATA"],
                    "visibility": "RESTRICTED",
                    "public_file_location": None,
                    "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                },
                {
                    "supporting_file_id": "66276ce45fa3128d9941ca39",
                    "file_name": "b_file.csv",
                    "file_size": 2_000,
                    "document_types": ["REPORT", "SITE_DATA", "SUPPLEMENTARY_DOCUMENTATION"],
                    "visibility": "PUBLIC",
                    "public_file_location": "https://in.public.blob.store.localhost/a/file",
                    "restricted_file_location": None,
                },
            ],
        },
    }

    submission_dict = get_published_submission_collection(get_test_settings()).find_one({"persistent_id": "2024EPP4uda4d75a"})
    assert submission_dict == {
        '_id': ANY,
        'last_updated': ANY,
        'persistent_id': '2024EPP4uda4d75a',
        'visibility': "RESTRICTED",
        'submission_set_id': '2024EPP4uda4d75b',
        'version': 0,
        'metadata': {
            'bounding_box_north_west': {'coordinates': [30.0, -40.0], 'type': 'Point'},
            'bounding_box_south_east': {'coordinates': [35.0, -45.0], 'type': 'Point'},
            'datatype': 'Systematic survey data',
            'from_date': '2024-01-01',
            'to_date': '2024-01-30',
            'name': 'A Survey',
            'participants': 'One,Two,Three',
            'rights_holder': 'BBB CORP',
            'submitter': 'AAA CORP',
            'summary': 'This is a survey',
            'tags': ['tag1', 'tag2', 'tag3'],
            'supporting_files': [
                {
                    'document_types': ['RECORD_DATA'],
                    'file_name': 'a_file.csv',
                    'file_size': 1000,
                    'visibility': "RESTRICTED",
                    'public_file_location': None,
                    "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                    'supporting_file_id': ObjectId('66276c9b5fa3128d9941ca38')
                },
                {
                    'document_types': ['REPORT',
                                       'SITE_DATA',
                                       'SUPPLEMENTARY_DOCUMENTATION'],
                    'file_name': 'b_file.csv',
                    'file_size': 2000,
                    'visibility': "PUBLIC",
                    "public_file_location": "https://in.public.blob.store.localhost/a/file",
                    "restricted_file_location": None,
                    'supporting_file_id': ObjectId('66276ce45fa3128d9941ca39'),
                },
            ],
        }
    }
    assert isinstance(submission_dict['_id'], ObjectId)
    assert isinstance(submission_dict['last_updated'], str)
    assert datetime.fromisoformat(submission_dict['last_updated']).tzinfo is not None


def test_delete_published_submission_not_authorised():
    response = client.delete(
        "/published_submissions/aaa/",
        headers={"x-api-key": ""},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_delete_published_submission_not_found():
    response = client.delete(
        "/published_submissions/aaa/",
        headers={"x-api-key": "test_password"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"deleted_count": 0}


def test_delete_published_submission(get_test_settings):
    published_submission_collection = get_published_submission_collection(get_test_settings())
    # Create some submissions
    for payload in [
        {
            "persistent_id": "2024EPP4uda4d777",
            "version": 0,
            "submission_set_id": "2024EPP4uda4d75b",
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Survey 1",
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
                        "supporting_file_id": "66276c9b5fa3128d9941ca34",
                        "file_name": "a_file.csv",
                        "file_size": 1_000,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                    },
                ],
            },
        },
        {
            "persistent_id": "2024EPP4uda4d888",
            "version": 0,
            "submission_set_id": "2024EPP4uda4d75b",
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "A Survey 2",
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
                        "supporting_file_id": "66276c9b5fa3128d9941ca87",
                        "file_name": "a_file.csv",
                        "file_size": 1_000,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://in.private.blob.store.localhost/a/file",
                    },
                ],
            },
        },
    ]:
        response = client.post(
            "/published_submissions/",
            headers={"x-api-key": "test_password"},
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK
    assert published_submission_collection.count_documents({}) == 2

    # delete first one
    response = client.delete(
        "/published_submissions/2024EPP4uda4d777/",
        headers={"x-api-key": "test_password"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"deleted_count": 1}

    assert published_submission_collection.count_documents({}) == 1
    assert published_submission_collection.find_one({"persistent_id": "2024EPP4uda4d777"}) is None
    assert published_submission_collection.find_one({"persistent_id": "2024EPP4uda4d888"}) is not None
