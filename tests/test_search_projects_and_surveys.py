from unittest.mock import patch

import pytest
from starlette import status
from starlette.testclient import TestClient

from app import main
from tests.helpers import mock_authentication

client = TestClient(main.app)


@pytest.fixture(scope="module", autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch(
        "app.routers.records.is_authorised",
        mock_authentication.is_authorised,
    ):
        yield


@pytest.fixture(scope="function")
def insert_test_projects(setup_database, test_settings):
    """
    Fixture to insert a standard set of Projects, Surveys and Records to test search against
    """
    # Two Projects
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FVRa8896e260",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Project Alpha",
                "purpose": "For testing",
                "comments": "These are some comments",
                "submitter": "Someone",
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FVRcI8a3bca4",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Project Beta",
                "purpose": "Also for testing",
                "comments": "These are some more comments",
                "submitter": "Someone else",
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK

    # Each Project has two Surveys, one PUBLIC and one RESTRICTED
    # The RESTRICTED Survey for Project Beta has all Conservation listed records.
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FWJBb7f92c37",
            "version": 0,
            "submission_set_id": "2024FVRa8896e260",  # Project Alpha
            "visibility": "PUBLIC",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Survey AAA",
                "summary": "This is a survey",
                "submitter": "AAA CORP",
                "rights_holder": "AAA CORP",
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "participants": "Tester",
                "tags": ["tag1", "tag2", "tag3"],
                "bounding_box_north_west": {
                    "type": "Point",
                    "coordinates": [30.1, -40.1],
                },
                "bounding_box_south_east": {
                    "type": "Point",
                    "coordinates": [35.1, -45.1],
                },
                "supporting_files": [
                    {
                        "supporting_file_id": "664d447bca0651a66120a31c",
                        "file_name": "a_file.csv",
                        "file_size": 1_033,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "PUBLIC",
                        "public_file_location": "https://public.blob.localhost/a/file",
                        "restricted_file_location": None,
                    },
                ],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FWJGga4b5e18",
            "version": 0,
            "submission_set_id": "2024FVRa8896e260",  # Project Alpha
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Survey BBB",
                "summary": "This is a survey",
                "submitter": "BBB CORP",
                "rights_holder": "BBB CORP",
                "from_date": "2024-01-20",
                "to_date": "2024-02-20",
                "participants": "Tester",
                "tags": ["tag1", "tag2", "tag3"],
                "bounding_box_north_west": {
                    "type": "Point",
                    "coordinates": [40.1, -50.1],
                },
                "bounding_box_south_east": {
                    "type": "Point",
                    "coordinates": [45.1, -55.1],
                },
                "supporting_files": [
                    {
                        "supporting_file_id": "664d4575ca0651a66120a31d",
                        "file_name": "b_file.csv",
                        "file_size": 1_077,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://private.blob.localhost/b/file",
                    },
                ],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FWJJJa8157af",
            "version": 0,
            "submission_set_id": "2024FVRcI8a3bca4",  # Project Beta
            "visibility": "PUBLIC",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Survey CCC",
                "summary": "This is a survey",
                "submitter": "CCC CORP",
                "rights_holder": "CCC CORP",
                "from_date": "2024-06-20",
                "to_date": "2024-06-25",
                "participants": "Tester",
                "tags": ["tag1", "tag2", "tag3"],
                "bounding_box_north_west": {
                    "type": "Point",
                    "coordinates": [47.1, -57.1],
                },
                "bounding_box_south_east": {
                    "type": "Point",
                    "coordinates": [48.1, -58.1],
                },
                "supporting_files": [
                    {
                        "supporting_file_id": "664d45e9ca0651a66120a31e",
                        "file_name": "c_file.csv",
                        "file_size": 1_099,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "PUBLIC",
                        "public_file_location": "https://public.blob.localhost/c/file",
                        "restricted_file_location": None,
                    },
                ],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FWJLDc1a1a82",
            "version": 0,
            "submission_set_id": "2024FVRcI8a3bca4",  # Project Beta
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Survey DDD",
                "summary": "This is a survey",
                "submitter": "DDD CORP",
                "rights_holder": "DDD CORP",
                "from_date": "2024-06-01",
                "to_date": "2024-06-30",
                "participants": "Tester",
                "tags": ["tag1", "tag2", "tag3"],
                "bounding_box_north_west": {
                    "type": "Point",
                    "coordinates": [57.1, -37.1],
                },
                "bounding_box_south_east": {
                    "type": "Point",
                    "coordinates": [58.1, -38.1],
                },
                "supporting_files": [
                    {
                        "supporting_file_id": "664d4654ca0651a66120a31f",
                        "file_name": "d_file.csv",
                        "file_size": 1_096,
                        "document_types": ["RECORD_DATA"],
                        "visibility": "RESTRICTED",
                        "public_file_location": None,
                        "restricted_file_location": "https://private.blob.localhost/d/file",
                    },
                ],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK

    # Records for Surveys. Each Survey has one record.
    # Whether that record matches the search determines if the Survey/Project
    # appears in the search results.
    response = client.post(
        "/records/bulk-upload/",
        headers={"x-api-key": "test_password"},
        json=[
            {
                "datatype": "Systematic survey data",
                "submission_set_name": "Project Alpha",
                "submission_id": "2024FWJBb7f92c37",
                "submission_name": "Survey AAA",
                "persistent_id": "2024FWJPA652e9d4",
                "version": 0,
                "accepted_name_usage": "Lepidosperma tenue",
                "scientific_name": "Lepidosperma tenue",
                "kingdom": "Plantae",
                "institution_code": "WA Herbarium",
                "event_date": "2024-01-04T00:00:00+08:00",
                "location": {"type": "Point", "coordinates": [33.5, -42.5]},
                "decimal_longitude": 33.5,
                "decimal_latitude": -42.5,
                "threat_status": None,
            },
            {
                "datatype": "Systematic survey data",
                "submission_set_name": "Project Alpha",
                "submission_id": "2024FWJGga4b5e18",
                "submission_name": "Survey BBB",
                "persistent_id": "2024FWKsA4a5c4b9",
                "version": 0,
                "accepted_name_usage": "Senna symonii",
                "scientific_name": "Senna symonii",
                "kingdom": "Plantae",
                "institution_code": "WA Herbarium",
                "event_date": "2024-02-17T00:00:00+08:00",
                "location": {"type": "Point", "coordinates": [43.5, -52.5]},
                "decimal_longitude": 43.5,
                "decimal_latitude": -52.5,
                "threat_status": None,
            },
            {
                "datatype": "Systematic survey data",
                "submission_set_name": "Project Beta",
                "submission_id": "2024FWJJJa8157af",
                "submission_name": "Survey CCC",
                "persistent_id": "2024FWKtN6c29644",
                "version": 0,
                "accepted_name_usage": "Senna madeupium",
                "scientific_name": "Senna madeupium",
                "kingdom": "Plantae",
                "institution_code": "WA Herbarium",
                "event_date": "2024-06-22T00:00:00+08:00",
                "location": {"type": "Point", "coordinates": [47.5, -57.5]},
                "decimal_longitude": 47.5,
                "decimal_latitude": -57.5,
                "threat_status": None,
            },
            {
                "datatype": "Systematic survey data",
                "submission_set_name": "Project Beta",
                "submission_id": "2024FWJLDc1a1a82",
                "submission_name": "Survey DDD",
                "persistent_id": "2024FWKue3bc4a33",
                "version": 0,
                "accepted_name_usage": "Sarcothalia radula",
                "scientific_name": "Sarcothalia radula",
                "kingdom": "Plantae",
                "institution_code": "WA Herbarium",
                "event_date": "2024-06-28T00:00:00+08:00",
                "location": {"type": "Point", "coordinates": [57.9, -37.9]},
                "decimal_longitude": 57.9,
                "decimal_latitude": -37.9,
                "threat_status": "LC",  # This Survey has all conservation records
            },
        ],
    )
    assert response.status_code == status.HTTP_200_OK


def test_search_projects_matching_all_with_permission(insert_test_projects):
    # Do a search for WA Herbarium. All records have this so all projects/surveys should
    # be returned.
    # User has permission to view sensitive, so RESTRICTED files should be returned,
    # as well as survey with all conservation coded records.
    response = client.get(
        "/records/submission_sets",
        headers={
            "x-email": "sensitive@test.net",
        },
        params={
            "datatype": "Systematic survey data",
            "data_provider": "WA Herbarium",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # All projects returned
    assert response_json["total"] == 2
    assert response_json["count"] == 2
    assert len(response_json["results"]) == 2
    # projects returned in order
    assert response_json["results"][0]["persistent_id"] == "2024FVRa8896e260"
    assert response_json["results"][1]["persistent_id"] == "2024FVRcI8a3bca4"

    # Check project content
    assert response_json["results"][0] == {
        "persistent_id": "2024FVRa8896e260",
        "metadata": {
            "datatype": "Systematic survey data",
            "name": "Project Alpha",
            "submitter": "Someone",
            "purpose": "For testing",
        },
        "from_date": "2024-01-01",
        "to_date": "2024-02-20",
        "total_submissions": 2,
        "set_submissions": [
            {
                "persistent_id": "2024FWJBb7f92c37",
                "submission_set_id": "2024FVRa8896e260",
                "visibility": "PUBLIC",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey AAA",
                    "summary": "This is a survey",
                    "submitter": "AAA CORP",
                    "rights_holder": "AAA CORP",
                    "from_date": "2024-01-01",
                    "to_date": "2024-01-30",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d447bca0651a66120a31c",
                            "file_name": "a_file.csv",
                            "file_size": 1033,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "PUBLIC",
                            "public_file_location": "https://public.blob.localhost/a/file",
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [30.1, -40.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [35.1, -45.1],
                    },
                },
            },
            {
                "persistent_id": "2024FWJGga4b5e18",
                "submission_set_id": "2024FVRa8896e260",
                "visibility": "RESTRICTED",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey BBB",
                    "summary": "This is a survey",
                    "submitter": "BBB CORP",
                    "rights_holder": "BBB CORP",
                    "from_date": "2024-01-20",
                    "to_date": "2024-02-20",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d4575ca0651a66120a31d",
                            "file_name": "b_file.csv",
                            "file_size": 1077,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "RESTRICTED",
                            "public_file_location": None,
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [40.1, -50.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [45.1, -55.1],
                    },
                },
            },
        ],
        "matching_submissions": [
            {
                "persistent_id": "2024FWJBb7f92c37",
                "submission_set_id": "2024FVRa8896e260",
                "visibility": "PUBLIC",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey AAA",
                    "summary": "This is a survey",
                    "submitter": "AAA CORP",
                    "rights_holder": "AAA CORP",
                    "from_date": "2024-01-01",
                    "to_date": "2024-01-30",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d447bca0651a66120a31c",
                            "file_name": "a_file.csv",
                            "file_size": 1033,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "PUBLIC",
                            "public_file_location": "https://public.blob.localhost/a/file",
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [30.1, -40.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [35.1, -45.1],
                    },
                },
            },
            {
                "persistent_id": "2024FWJGga4b5e18",
                "submission_set_id": "2024FVRa8896e260",
                "visibility": "RESTRICTED",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey BBB",
                    "summary": "This is a survey",
                    "submitter": "BBB CORP",
                    "rights_holder": "BBB CORP",
                    "from_date": "2024-01-20",
                    "to_date": "2024-02-20",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d4575ca0651a66120a31d",
                            "file_name": "b_file.csv",
                            "file_size": 1077,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "RESTRICTED",
                            "public_file_location": None,
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [40.1, -50.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [45.1, -55.1],
                    },
                },
            },
        ],
    }

    assert response_json["results"][1] == {
        "persistent_id": "2024FVRcI8a3bca4",
        "metadata": {
            "datatype": "Systematic survey data",
            "name": "Project Beta",
            "submitter": "Someone else",
            "purpose": "Also for testing",
        },
        "from_date": "2024-06-01",
        "to_date": "2024-06-30",
        "total_submissions": 2,
        "set_submissions": [
            {
                "persistent_id": "2024FWJJJa8157af",
                "submission_set_id": "2024FVRcI8a3bca4",
                "visibility": "PUBLIC",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey CCC",
                    "summary": "This is a survey",
                    "submitter": "CCC CORP",
                    "rights_holder": "CCC CORP",
                    "from_date": "2024-06-20",
                    "to_date": "2024-06-25",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d45e9ca0651a66120a31e",
                            "file_name": "c_file.csv",
                            "file_size": 1099,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "PUBLIC",
                            "public_file_location": "https://public.blob.localhost/c/file",
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [47.1, -57.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [48.1, -58.1],
                    },
                },
            },
            {
                "persistent_id": "2024FWJLDc1a1a82",
                "submission_set_id": "2024FVRcI8a3bca4",
                "visibility": "RESTRICTED",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey DDD",
                    "summary": "This is a survey",
                    "submitter": "DDD CORP",
                    "rights_holder": "DDD CORP",
                    "from_date": "2024-06-01",
                    "to_date": "2024-06-30",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d4654ca0651a66120a31f",
                            "file_name": "d_file.csv",
                            "file_size": 1096,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "RESTRICTED",
                            "public_file_location": None,
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [57.1, -37.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [58.1, -38.1],
                    },
                },
            },
        ],
        "matching_submissions": [
            {
                "persistent_id": "2024FWJJJa8157af",
                "submission_set_id": "2024FVRcI8a3bca4",
                "visibility": "PUBLIC",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey CCC",
                    "summary": "This is a survey",
                    "submitter": "CCC CORP",
                    "rights_holder": "CCC CORP",
                    "from_date": "2024-06-20",
                    "to_date": "2024-06-25",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d45e9ca0651a66120a31e",
                            "file_name": "c_file.csv",
                            "file_size": 1099,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "PUBLIC",
                            "public_file_location": "https://public.blob.localhost/c/file",
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [47.1, -57.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [48.1, -58.1],
                    },
                },
            },
            {
                "persistent_id": "2024FWJLDc1a1a82",
                "submission_set_id": "2024FVRcI8a3bca4",
                "visibility": "RESTRICTED",
                "metadata": {
                    "datatype": "Systematic survey data",
                    "name": "Survey DDD",
                    "summary": "This is a survey",
                    "submitter": "DDD CORP",
                    "rights_holder": "DDD CORP",
                    "from_date": "2024-06-01",
                    "to_date": "2024-06-30",
                    "tags": ["tag1", "tag2", "tag3"],
                    "participants": "Tester",
                    "supporting_files": [
                        {
                            "supporting_file_id": "664d4654ca0651a66120a31f",
                            "file_name": "d_file.csv",
                            "file_size": 1096,
                            "document_types": ["RECORD_DATA"],
                            "visibility": "RESTRICTED",
                            "public_file_location": None,
                        }
                    ],
                    "bounding_box_north_west": {
                        "type": "Point",
                        "coordinates": [57.1, -37.1],
                    },
                    "bounding_box_south_east": {
                        "type": "Point",
                        "coordinates": [58.1, -38.1],
                    },
                },
            },
        ],
    }


def test_search_projects_matching_all_without_permission(insert_test_projects):
    # Do a search for WA Herbarium. All records have this so all projects/surveys should
    # be returned, including survey with all conservation listed records.
    # User does not have permission to view sensitive files, they won't be returned.
    # Also, bounding box is not returned to public user.
    response = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "data_provider": "WA Herbarium",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # All projects returned
    assert response_json["total"] == 2
    assert response_json["count"] == 2
    assert len(response_json["results"]) == 2
    # projects returned in order
    assert response_json["results"][0]["persistent_id"] == "2024FVRa8896e260"
    assert response_json["results"][1]["persistent_id"] == "2024FVRcI8a3bca4"
    # Files/bounding box for RESTRICTED surveys are not returned, PUBLIC they are
    project_0_submissions = response_json["results"][0]["matching_submissions"]
    assert len(project_0_submissions) == 2
    # Project Alpha public survey
    assert project_0_submissions[0]["persistent_id"] == "2024FWJBb7f92c37"
    assert project_0_submissions[0]["visibility"] == "PUBLIC"
    assert project_0_submissions[0]["metadata"]["supporting_files"] == [
        {
            "document_types": ["RECORD_DATA"],
            "file_name": "a_file.csv",
            "file_size": 1033,
            "public_file_location": "https://public.blob.localhost/a/file",
            "supporting_file_id": "664d447bca0651a66120a31c",
            "visibility": "PUBLIC",
        },
    ]
    assert project_0_submissions[0]["metadata"]["bounding_box_north_west"] == {
        "type": "Point",
        "coordinates": [30.1, -40.1],
    }
    assert project_0_submissions[0]["metadata"]["bounding_box_south_east"] == {
        "type": "Point",
        "coordinates": [35.1, -45.1],
    }
    # Project Alpha restricted survey
    assert project_0_submissions[1]["persistent_id"] == "2024FWJGga4b5e18"
    assert project_0_submissions[1]["visibility"] == "RESTRICTED"
    assert project_0_submissions[1]["metadata"]["supporting_files"] is None
    assert project_0_submissions[1]["metadata"]["bounding_box_north_west"] is None
    assert project_0_submissions[1]["metadata"]["bounding_box_south_east"] is None

    project_1_submissions = response_json["results"][1]["matching_submissions"]
    assert len(project_1_submissions) == 2
    # Project Beta public survey
    assert project_1_submissions[0]["persistent_id"] == "2024FWJJJa8157af"
    assert project_1_submissions[0]["visibility"] == "PUBLIC"
    assert project_1_submissions[0]["metadata"]["supporting_files"] == [
        {
            "document_types": ["RECORD_DATA"],
            "file_name": "c_file.csv",
            "file_size": 1099,
            "public_file_location": "https://public.blob.localhost/c/file",
            "supporting_file_id": "664d45e9ca0651a66120a31e",
            "visibility": "PUBLIC",
        },
    ]
    assert project_1_submissions[0]["metadata"]["bounding_box_north_west"] == {
        "type": "Point",
        "coordinates": [47.1, -57.1],
    }
    assert project_1_submissions[0]["metadata"]["bounding_box_south_east"] == {
        "type": "Point",
        "coordinates": [48.1, -58.1],
    }
    # Project Beta restricted survey,
    # shown even though it has all conservation listed records.
    assert project_1_submissions[1]["persistent_id"] == "2024FWJLDc1a1a82"
    assert project_1_submissions[1]["visibility"] == "RESTRICTED"
    assert project_1_submissions[1]["metadata"]["supporting_files"] is None
    assert project_1_submissions[1]["metadata"]["bounding_box_north_west"] is None
    assert project_1_submissions[1]["metadata"]["bounding_box_south_east"] is None


def test_search_projects_pagination(insert_test_projects):
    # Do a search for WA Herbarium to return all projects across two pages
    response_1 = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "data_provider": "WA Herbarium",
            "offset": 0,
            "limit": 1,
        },
    )
    assert response_1.status_code == status.HTTP_200_OK
    response_json_1 = response_1.json()
    # 1 project returned
    assert response_json_1["total"] == 2
    assert response_json_1["count"] == 1
    assert len(response_json_1["results"]) == 1
    assert response_json_1["results"][0]["persistent_id"] == "2024FVRa8896e260"

    response_2 = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "data_provider": "WA Herbarium",
            "offset": 1,
            "limit": 1,
        },
    )
    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()
    # second project returned in 2nd page
    assert response_json_2["total"] == 2
    assert response_json_2["count"] == 1
    assert len(response_json_2["results"]) == 1
    assert response_json_2["results"][0]["persistent_id"] == "2024FVRcI8a3bca4"


def test_search_projects_matching_one_project(insert_test_projects):
    # Do a search by date to only matches records from Project Alpha,
    # So only that project will be returned
    response = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "date_from": "2024-01-01",
            "date_to": "2024-02-29",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # Project Beta returned
    assert response_json["total"] == 1
    assert response_json["count"] == 1
    assert len(response_json["results"]) == 1
    assert response_json["results"][0]["persistent_id"] == "2024FVRa8896e260"
    assert response_json["results"][0]["metadata"]["name"] == "Project Alpha"
    assert response_json["results"][0]["total_submissions"] == 2
    # Note search matches records in both surveys, so both are returned here
    assert len(response_json["results"][0]["matching_submissions"]) == 2
    assert (
        response_json["results"][0]["matching_submissions"][0]["persistent_id"]
        == "2024FWJBb7f92c37"
    )
    assert (
        response_json["results"][0]["matching_submissions"][1]["persistent_id"]
        == "2024FWJGga4b5e18"
    )


def test_search_projects_matching_one_project_and_subset_of_surveys(
    insert_test_projects,
):
    # Do a search by species to only match records from Project Alpha,
    # and only 1 only the Surveys in that project.
    response = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "species": "Lepidosperma tenue",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # Project Alpha returned
    assert response_json["total"] == 1
    assert response_json["count"] == 1
    assert len(response_json["results"]) == 1
    assert response_json["results"][0]["persistent_id"] == "2024FVRa8896e260"
    assert response_json["results"][0]["metadata"]["name"] == "Project Alpha"
    # 2 surveys total
    assert response_json["results"][0]["total_submissions"] == 2
    # date range is derived from ALL 2 surveys in the project
    assert response_json["results"][0]["from_date"] == "2024-01-01"
    assert response_json["results"][0]["to_date"] == "2024-02-20"
    # only matching surveys are returned here
    assert len(response_json["results"][0]["matching_submissions"]) == 1
    assert (
        response_json["results"][0]["matching_submissions"][0]["persistent_id"]
        == "2024FWJBb7f92c37"
    )


def test_search_projects_matching_two_projects_and_subset_of_surveys(
    insert_test_projects,
):
    # Do a search by species to match records from both Projects,
    # but only 1 Survey in each project.
    response = client.get(
        "/records/submission_sets",
        params={
            "datatype": "Systematic survey data",
            "species": ["Senna madeupium", "Senna symonii"]  # matches both "Senna madeupium" and "Senna symonii"
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # both projects returned
    assert response_json["total"] == 2
    assert response_json["count"] == 2
    assert len(response_json["results"]) == 2
    assert response_json["results"][0]["persistent_id"] == "2024FVRa8896e260"
    assert response_json["results"][0]["metadata"]["name"] == "Project Alpha"
    assert response_json["results"][1]["persistent_id"] == "2024FVRcI8a3bca4"
    assert response_json["results"][1]["metadata"]["name"] == "Project Beta"

    # Project Alpha
    # 2 surveys total
    assert response_json["results"][0]["total_submissions"] == 2
    # date range is derived from ALL 2 surveys in the project
    assert response_json["results"][0]["from_date"] == "2024-01-01"
    assert response_json["results"][0]["to_date"] == "2024-02-20"
    # only matching surveys are returned here
    assert len(response_json["results"][0]["matching_submissions"]) == 1
    assert (
        response_json["results"][0]["matching_submissions"][0]["persistent_id"]
        == "2024FWJGga4b5e18"
    )

    # Project Beta
    # 2 surveys total
    assert response_json["results"][1]["total_submissions"] == 2
    # date range is derived from ALL 2 surveys in the project
    assert response_json["results"][1]["from_date"] == "2024-06-01"
    assert response_json["results"][1]["to_date"] == "2024-06-30"
    # only matching surveys are returned here
    assert len(response_json["results"][1]["matching_submissions"]) == 1
    assert (
        response_json["results"][1]["matching_submissions"][0]["persistent_id"]
        == "2024FWJJJa8157af"
    )


def test_search_only_matches_conservation_records_and_project_still_shown(
    insert_test_projects,
):
    # Do a search that only matches conservation listed records,
    # to test that the Project/Survey(s) for those records are still shown.
    # In this case it is Project Beta and Survey DDD
    response = client.get(
        "/records/submission_sets",
        # No email header - public user
        params={
            "datatype": "Systematic survey data",
            "species": "Sarcothalia radula",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # Project Beta returned
    assert response_json["total"] == 1
    assert response_json["count"] == 1
    assert len(response_json["results"]) == 1
    assert response_json["results"][0]["persistent_id"] == "2024FVRcI8a3bca4"
    assert response_json["results"][0]["metadata"]["name"] == "Project Beta"
    # 2 surveys total
    assert response_json["results"][0]["total_submissions"] == 2
    # only matching Survey DDD is returned
    assert len(response_json["results"][0]["matching_submissions"]) == 1
    assert (
        response_json["results"][0]["matching_submissions"][0]["persistent_id"]
        == "2024FWJLDc1a1a82"
    )
