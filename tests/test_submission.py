import json
import os.path
from unittest.mock import patch, ANY

import pymongo
import pytest
import responses
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette import status

from app import main
from app.helpers.dandjoo_id import DandjooId
from app.helpers.mongo import get_submission_collection, get_supporting_file_collection, get_submission_set_collection
from app.helpers.py_object import PyObjectId
from app.models.geo_json import Point
from app.models.submission import (Submission, SurveyMetadata, SupportingFileUsage, Mappings, OccurrenceMetadata, DatumEnum, SpreadsheetMappings)
from app.models.common_enums import DataType, DocumentType
from tests.helpers import mock_authentication
from app.models.submission import Metadata, NewSubmissionMetadata
from app.models.submission_set import SubmissionSet
from tests.helpers.factories import supporting_file_factory, submission_set_factory


TEST_FILE_DIRECTORY = os.path.join('test-data', 'submission')
TEST_CSV_FILE = 'test.csv'
TEST_CSV_FILE_UNSUPPORTED_ENCODING = 'test-unsupported-encoding.csv'
TEST_CSV_FILE_MISSING_HEADER = 'test-missing-header.csv'
TEST_CSV_FILE_INVALID_HEADER = 'test-invalid-header.csv'
TEST_CSV_FILE_MISSING_DATA = 'test-missing-data.csv'
TEST_CSV_FILE_INVALID_DATA = 'test-invalid-data.csv'
TEST_EXCEL_FILE = 'test.xlsx'
TEST_CORRUPT_EXCEL_FILE = 'test-corrupt.xlsx'
TEST_EXCEL_FILE_MISSING_HEADER = 'test-missing-header.xlsx'
TEST_EXCEL_FILE_INVALID_HEADER = 'test-invalid-header.xlsx'
TEST_EXCEL_FILE_MISSING_DATA = 'test-missing-data.xlsx'
TEST_EXCEL_FILE_INVALID_DATA = 'test-invalid-data.xlsx'
TEST_POLYGONS_SHAPEFILE = 'test-polygons.zip'
TEST_POINTS_SHAPEFILE = 'test-points.zip'
TEST_POINTS_SHAPEFILE_MISSING_DATA = 'test-points-missing-data.zip'
TEST_POINTS_SHAPEFILE_INVALID_DATA = 'test-points-invalid-data.zip'
TEST_SHAPEFILE_MISSING_SHP = 'test-missing-shp.zip'
TEST_SHAPEFILE_MISSING_DBF = 'test-inadequate-dbf.zip'
TEST_CORRUPT_ZIP_FILE = 'test-corrupt.zip'
TEST_INVALID_FILE_TYPES = 'test-invalid-file-types.zip'

client = TestClient(main.app)


def get_metadata(datatype: DataType):
    meta = {
        "datatype": datatype,
        "submitter": "tester",
        "datum": "GDA94",
        # species occurrence fields
        "dataset": "test-dataset",
        "comments": "test comments",
        "sourcefile": "testfile.csv",
        # systematic survey fields
        "name": "TestSurveyName",
        "summary": "TestSurveySummary",
        "from_date": "2020-01-01",
        "to_date": "2020-12-31",
        "participants": "Aaa,Bbb,Ccc",
        "has_threatened_species": True,
        "tags": ["Lake", "Fauna"],
        "bounding_box_north_west": {"type": "Point", "coordinates": [116.11223344, -50]},
        "bounding_box_south_east": {"type": "Point", "coordinates": [118, -55.11227988]},
    }
    return Metadata(__root__=meta)


def get_submission_set(datatype: DataType):
    submission_set = {
        "comments": "testing",
        "name": "test submission set",
        "metadata": {
            "datatype": datatype,
            "purpose": "this is for unit tests",
        },
    }
    return SubmissionSet(**submission_set)


def get_new_submission(datatype: DataType = DataType.SPECIES_OCCURRENCE):
    if datatype == DataType.SYSTEMATIC_SURVEY:
        submission_set = get_submission_set(datatype).dict()
    else:
        submission_set = None
    submission = get_metadata(datatype)
    submission = NewSubmissionMetadata(
        submission=submission,
        submission_set=submission_set,
        accept_terms_and_conditions=True,
    )

    return submission


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.routers.submission.is_authorised', mock_authentication.is_authorised) as _fixture:
        yield _fixture


@pytest.fixture(scope='module', autouse=True)
def get_user_id_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.routers.submission.get_user_id', mock_authentication.get_user_id) as _fixture:
        yield _fixture


def test_create_species_occurrence_submission(test_settings):
    submissions = get_submission_collection(test_settings)

    # confirm the new submission process has created parent submission_set and child submission metadata items
    new_submission = get_new_submission(datatype=DataType.SPECIES_OCCURRENCE)
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)
    assert response.status_code == status.HTTP_201_CREATED
    # check API response
    json_response = response.json()
    assert json_response == {
        'new_submission_id': ANY,
        'submission_set': None,
        'submission': {
            'created_on': ANY,
            'datatype': 'Species occurrence data',
            'datum': "GDA94",
            'sourcefile': None,
            'submitter': 'tester',
            "dataset": "test-dataset",
            "comments": "test comments",
        },
        "accept_terms_and_conditions": True,
    }
    assert ObjectId.is_valid(json_response['new_submission_id'])
    # check submission correctly created in DB
    submission_id = ObjectId(json_response['new_submission_id'])
    new_submission_dict = submissions.find_one({"_id": submission_id})
    assert new_submission_dict == {
        '_id': submission_id,
        'persistent_id': ANY,
        "sent_to_curation": None,
        "unmappable": None,
        'id': None,
        'mappings': None,
        'metadata': {
            'created_on': json_response['submission']['created_on'],
            'datatype': 'Species occurrence data',
            'datum': "GDA94",
            'sourcefile': None,
            'submitter': 'tester',
            "dataset": "test-dataset",
            "comments": "test comments",
        },
        'submitter_id': 1,
    }
    assert DandjooId.is_valid(new_submission_dict['persistent_id'])


def test_create_systematic_survey_data_submission(test_settings):
    submission_sets = get_submission_set_collection(test_settings)
    submissions = get_submission_collection(test_settings)

    # confirm the new submission process has created parent submission_set and child submission metadata items
    new_submission = get_new_submission(datatype=DataType.SYSTEMATIC_SURVEY)
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)
    assert response.status_code == status.HTTP_201_CREATED
    # check API response
    json_response = response.json()
    assert json_response == {
        'new_submission_id': ANY,
        'submission_set': {
            '_id': ANY,
            "persistent_id": ANY,
            'comments': 'testing',
            'metadata': {
                'datatype': 'Systematic survey data',
                'purpose': 'this is for unit tests',
            },
            'name': "test submission set",
            'submitter_id': 1,
            'submitter': None,
            'sent_to_curation': None,
            'archived_in_curation': None,
        },
        'submission': {
            'submission_set_persistent_id': ANY,
            'submitter': 'tester',
            'created_on': ANY,
            'datum': "GDA94",
            'datatype': 'Systematic survey data',
            'name': 'TestSurveyName',
            'summary': 'TestSurveySummary',
            'from_date': "2020-01-01",
            'to_date': "2020-12-31",
            'has_threatened_species': True,
            'participants': "Aaa,Bbb,Ccc",
            "tags": ["Lake", "Fauna"],
            "bounding_box_north_west": {"type": "Point", "coordinates": [116.11223, -50.0]},
            "bounding_box_south_east": {"type": "Point", "coordinates": [118.0, -55.11228]},
            'supporting_files': None,
        },
        "accept_terms_and_conditions": True,
    }
    assert ObjectId.is_valid(json_response['new_submission_id'])
    assert ObjectId.is_valid(json_response['submission_set']['_id'])
    assert json_response['submission_set']['persistent_id'] == json_response['submission']['submission_set_persistent_id']

    # check submission (Survey) and submission_set (Project) created in DB
    submission_set_id = ObjectId(json_response['submission_set']['_id'])
    new_submission_set_dict = submission_sets.find_one({"_id": submission_set_id})
    assert new_submission_set_dict == {
        '_id': submission_set_id,
        "persistent_id": json_response['submission_set']["persistent_id"],
        'comments': 'testing',
        'metadata': {
            'datatype': 'Systematic survey data',
            'purpose': 'this is for unit tests',
        },
        'name': "test submission set",
        'submitter_id': 1,
        'submitter': None,
        "sent_to_curation": None,
        'archived_in_curation': None,
    }
    submission_id = ObjectId(json_response['new_submission_id'])
    new_submission_dict = submissions.find_one({"_id": submission_id})
    assert new_submission_dict == {
        '_id': submission_id,
        'persistent_id': ANY,
        "sent_to_curation": None,
        "unmappable": None,
        'id': None,
        'mappings': None,
        'metadata': {
            'submission_set_persistent_id': new_submission_set_dict['persistent_id'],
            'submitter': 'tester',
            'created_on': json_response['submission']['created_on'],
            'datum': "GDA94",
            'datatype': 'Systematic survey data',
            'name': 'TestSurveyName',
            'summary': 'TestSurveySummary',
            'from_date': "2020-01-01",
            'to_date': "2020-12-31",
            'has_threatened_species': True,
            'participants': "Aaa,Bbb,Ccc",
            "tags": ["Lake", "Fauna"],
            "bounding_box_north_west": {"type": "Point", "coordinates": [116.11223, -50.0]},
            "bounding_box_south_east": {"type": "Point", "coordinates": [118.0, -55.11228]},
            'supporting_files': None,
        },
        'submitter_id': 1,
    }
    assert DandjooId.is_valid(new_submission_dict['persistent_id'])

    # confirm new submission can be added to the existing submission set (Project) previously created
    new_submission.submission.__root__.submission_set_persistent_id = new_submission_set_dict['persistent_id']
    new_submission.submission.__root__.name = "Second Survey"
    data2 = new_submission.dict()
    response2 = client.post('/submission',
                            headers={'accept': 'application/json',
                                     'Content-Type': 'application/json',
                                     'x-email': 'submitter@test.net'},
                            json=data2)

    assert response2.status_code == status.HTTP_201_CREATED
    # check API response
    json_response2 = response2.json()
    assert json_response2 == {
        'new_submission_id': ANY,
        'submission_set': {
            '_id': str(submission_set_id),
            "persistent_id": new_submission_set_dict["persistent_id"],
            'comments': 'testing',
            'metadata': {
                'datatype': 'Systematic survey data',
                'purpose': 'this is for unit tests',
            },
            'name': "test submission set",
            'submitter_id': 1,
            'submitter': None,
            'sent_to_curation': None,
            'archived_in_curation': None,
        },
        'submission': {
            'datatype': 'Systematic survey data',
            'created_on': ANY,
            'datum': "GDA94",
            'submission_set_persistent_id': new_submission_set_dict["persistent_id"],
            'submitter': 'tester',
            'name': 'Second Survey',
            'summary': 'TestSurveySummary',
            'from_date': "2020-01-01",
            'to_date': "2020-12-31",
            'has_threatened_species': True,
            'participants': "Aaa,Bbb,Ccc",
            "tags": ["Lake", "Fauna"],
            "bounding_box_north_west": {"type": "Point", "coordinates": [116.11223, -50.0]},
            "bounding_box_south_east": {"type": "Point", "coordinates": [118.0, -55.11228]},
            'supporting_files': None,
        },
        "accept_terms_and_conditions": True,
    }
    assert ObjectId.is_valid(json_response2['new_submission_id'])
    # check submission created in DB
    submission2_id = ObjectId(json_response2['new_submission_id'])
    new_submission2_dict = submissions.find_one({"_id": submission2_id})
    assert new_submission2_dict == {
        '_id': submission2_id,
        'persistent_id': ANY,
        "sent_to_curation": None,
        "unmappable": None,
        'id': None,
        'mappings': None,
        'metadata': {
            'created_on': json_response2['submission']['created_on'],
            'submission_set_persistent_id': new_submission_set_dict["persistent_id"],
            'submitter': 'tester',
            'datum': "GDA94",
            'datatype': 'Systematic survey data',
            'name': 'Second Survey',
            'summary': 'TestSurveySummary',
            'from_date': "2020-01-01",
            'to_date': "2020-12-31",
            'has_threatened_species': True,
            'participants': "Aaa,Bbb,Ccc",
            "tags": ["Lake", "Fauna"],
            "bounding_box_north_west": {"type": "Point", "coordinates": [116.11223, -50.0]},
            "bounding_box_south_east": {"type": "Point", "coordinates": [118.0, -55.11228]},
            'supporting_files': None,
        },
        'submitter_id': 1,
    }
    assert DandjooId.is_valid(new_submission2_dict['persistent_id'])
    # check submission_set not updated in DB
    submission_set_dict_not_updated = submission_sets.find_one({"_id": ObjectId(json_response2['submission_set']['_id'])})
    assert submission_set_dict_not_updated == new_submission_set_dict


def test_create_submission_missing_auth_header():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json'},
                           json=data)

    assert response.status_code == status.HTTP_403_FORBIDDEN

    json_response = response.json()

    assert json_response == {'detail': 'Access forbidden'}


def test_create_submission_unauthorised_auth_header():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'unauthorised@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_403_FORBIDDEN

    json_response = response.json()

    assert json_response == {'detail': 'Access forbidden'}


def test_create_terms_and_conditions_flag_false():
    new_submission = get_new_submission()
    data = new_submission.dict()
    data["accept_terms_and_conditions"] = False
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    json_response = response.json()

    assert json_response == {'detail': 'Must contain accept_terms_and_conditions flag set as true'}


def test_create_no_terms_and_conditions_flag():
    new_submission = get_new_submission()
    data = new_submission.dict()
    data.pop("accept_terms_and_conditions")
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_partially_update_occurrence_submission_metadata(test_settings):
    submissions = get_submission_collection(test_settings)
    new_submission = get_new_submission(datatype=DataType.SPECIES_OCCURRENCE)
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)
    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})
    assert submission_dict['metadata'] == {
        'created_on': ANY,
        'datatype': 'Species occurrence data',
        'datum': "GDA94",
        'sourcefile': None,
        'submitter': 'tester',
        "dataset": "test-dataset",
        "comments": "test comments",
    }

    # setup and test a value change to the metadata for the submission
    metadata = get_metadata(datatype=DataType.SPECIES_OCCURRENCE)
    metadata.__root__.datum = "WGS84"
    metadata.__root__.submitter = "New Submitter"
    assert result_submission.submission.__root__.datum != metadata.__root__.datum
    metadata_dict = metadata.__root__.dict()

    response = client.patch(f'/submission/{submission_id}/metadata', headers={'x-email': 'submitter@test.net'},
                           json=metadata_dict)
    json_response = response.json()

    assert response.status_code == status.HTTP_200_OK

    result = Metadata(__root__=json_response)

    assert result.__root__.datum == metadata.__root__.datum
    assert result.__root__.submitter == metadata.__root__.submitter

    updated_submission_dict = submissions.find_one({'_id': ObjectId(submission_id)})
    assert updated_submission_dict['metadata'] == {
        'created_on': submission_dict['metadata']['created_on'],
        'datatype': 'Species occurrence data',
        'sourcefile': None,
        "dataset": "test-dataset",
        "comments": "test comments",
        # Updated
        'datum': "WGS84",
        'submitter': 'New Submitter',
    }


def test_partially_update_survey_submission_metadata(test_settings):
    submissions = get_submission_collection(test_settings)
    submission_set = submission_set_factory(test_settings)
    # Create Submission with initial metadata
    create_response = client.post('/submission',
                                  headers={'x-email': 'submitter@test.net'},
                                  json={
                                      "accept_terms_and_conditions": True,
                                      "submission": {"__root__": {
                                          "datatype": "Systematic survey data",
                                          "submitter": "TestSubmitter",
                                          "submission_set_persistent_id": submission_set.persistent_id,
                                          "name": "MySurvey",
                                          "summary": "Found some cool stuff",
                                          "from_date": "1999-03-23",
                                          "to_date": "2000-01-20",
                                          "participants": "Aaa,Bbb,Ccc",
                                          'has_threatened_species': True,
                                      }},
                                  })
    assert create_response.status_code == status.HTTP_201_CREATED
    submission_id = ObjectId(create_response.json()['new_submission_id'])
    submission_dict = submissions.find_one({'_id': submission_id})
    assert submission_dict['metadata'] == {
        'datatype': 'Systematic survey data',
        # fields specified on creation
        'created_on': ANY,
        'participants': "Aaa,Bbb,Ccc",
        "submission_set_persistent_id": submission_set.persistent_id,
        'submitter': "TestSubmitter",
        'supporting_files': None,
        "from_date": "1999-03-23",
        "to_date": "2000-01-20",
        'name': "MySurvey",
        # fields to be updated with PATCH
        "summary": "Found some cool stuff",
        'has_threatened_species': True,
        # omitted fields to be updated on with PATCH
        'datum': None,
        'tags': None,
        "bounding_box_north_west": None,
        "bounding_box_south_east": None,
    }

    # update metadata with a PATCH
    update_response = client.patch(f'/submission/{submission_id}/metadata',
                                   headers={'x-email': 'submitter@test.net'},
                                   json={
                                       "__root__": {
                                           "summary": "updated summary",
                                           'has_threatened_species': False,
                                           "datatype": "Systematic survey data",
                                           "datum": "AGD84",
                                           "tags": ["Foo", "Bar", "Cat"],
                                           "bounding_box_north_west": {
                                               "type": "Point",
                                               "coordinates": [116, -50],
                                           },
                                           "bounding_box_south_east": {
                                               "type": "Point",
                                               "coordinates": [118, -55],
                                           },
                                       },
                                   })
    assert update_response.status_code == status.HTTP_200_OK, update_response.content
    assert update_response.json() == {
        'datatype': 'Systematic survey data',
        # unchanged fields
        'created_on': submission_dict['metadata']['created_on'],
        'participants': "Aaa,Bbb,Ccc",
        "submission_set_persistent_id": submission_set.persistent_id,
        'submitter': "TestSubmitter",
        'supporting_files': None,
        "from_date": "1999-03-23",
        "to_date": "2000-01-20",
        'name': "MySurvey",
        # updated fields
        "summary": "updated summary",
        'has_threatened_species': False,
        'datum': 'AGD84',
        'tags': ['Foo', 'Bar', 'Cat'],
        "bounding_box_north_west": {
            "type": "Point",
            "coordinates": [116, -50],
        },
        "bounding_box_south_east": {
            "type": "Point",
            "coordinates": [118, -55],
        },
    }
    updated_submission_dict = submissions.find_one({'_id': submission_id})
    assert updated_submission_dict['metadata'] == {
        # unchanged
        'created_on': ANY,
        'datatype': 'Systematic survey data',
        'participants': "Aaa,Bbb,Ccc",
        "submission_set_persistent_id": submission_set.persistent_id,
        'submitter': "TestSubmitter",
        'supporting_files': None,
        "from_date": "1999-03-23",
        "to_date": "2000-01-20",
        'name': "MySurvey",
        # updated
        "summary": "updated summary",
        'has_threatened_species': False,
        'datum': 'AGD84',
        'tags': ['Foo', 'Bar', 'Cat'],
        "bounding_box_north_west": {
            "type": "Point",
            "coordinates": [116, -50],
        },
        "bounding_box_south_east": {
            "type": "Point",
            "coordinates": [118, -55],
        },
    }


def test_partially_update_metadata_invalid_submission_id():
    fake_submission_id = '6213455db129abec0d66d9a6'
    metadata = get_metadata(datatype=DataType.SPECIES_OCCURRENCE)
    metadata_dict = metadata.__root__.dict()

    response = client.patch(f'/submission/{fake_submission_id}/metadata', headers={'x-email': 'submitter@test.net'},
                            json=metadata_dict)

    assert response.status_code == status.HTTP_404_NOT_FOUND

    response_json = response.json()

    assert response_json['detail'] == 'Submission not found'


def test_partially_update_metadata_with_wrong_datatype(test_settings):
    # setup species occurrence submission
    new_submission = get_new_submission(datatype=DataType.SPECIES_OCCURRENCE)
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=new_submission.dict())
    assert response.status_code == status.HTTP_201_CREATED
    result_submission = NewSubmissionMetadata(**response.json())
    submission_id = result_submission.new_submission_id
    assert result_submission.submission.__root__.datatype.value == "Species occurrence data"

    # try to update it with Systematic Survey metadata
    response = client.patch(f'/submission/{submission_id}/metadata', headers={'x-email': 'submitter@test.net'},
                            json={"datatype": "Systematic survey data", "datum": "WGS84"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "Submission datatype must not be changed"}


def test_upload_csv_file(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    response_json = response.json()

    assert response_json == {
        'Abundance': '1',
        'Author': 'Ecoscape',
        'Citation': 'Ecoscape (2010), Armstrong Reserve, Dunsborough '
                    '- Flora and Vegetation Assessment. Unpublished '
                    'report for Ray Village Aged Services',
        'Comments': '1 plant/s',
        'DateObs': '2001-01-03',
        'Easting_m': '324165.443',
        'HerbRef': '',
        'Lat_GDA94': '-33.797409',
        'Long_GDA94': '115.147705',
        'Northing_m': '6279491.554',
        'SiteName': 'SBopp-1',
        'TaxonName': 'Eucalyptus rudis subsp. cratyantha',
        'WAConStat': 'P4'
    }

    assert os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE))


def test_upload_csv_file_unsupported_encoding(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_UNSUPPORTED_ENCODING)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_UNSUPPORTED_ENCODING, open(test_file_path, 'rb'),
                                                  'text/csv')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': ['File character encoding must be one of utf-8, ascii, ISO-8859-1; Big5 detected']
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE_UNSUPPORTED_ENCODING))


def test_upload_csv_file_missing_header(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_MISSING_HEADER)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_MISSING_HEADER, open(test_file_path, 'rb'),
                                                  'text/csv')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Header Error': ['The header row must contain data'],
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE_MISSING_HEADER))


def test_upload_csv_file_invalid_header(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_INVALID_HEADER)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_INVALID_HEADER, open(test_file_path, 'rb'),
                                                  'text/csv')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Header Error': [
            'All header cells must contain unique values',
            'All header cells must be a string (text)',
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE_INVALID_HEADER))


def test_upload_excel_file(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_EXCEL_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_201_CREATED

    response_json = response.json()

    assert response_json == {
        'Abundance': 1,
        'Author': 'Ecoscape',
        'Citation': 'Ecoscape (2010), Armstrong Reserve, Dunsborough '
                    '- Flora and Vegetation Assessment. Unpublished '
                    'report for Ray Village Aged Services',
        'Comments': '1 plant/s',
        'DateObs': '2001-01-03T00:00:00',
        'Easting_m': 324165.443,
        'HerbRef': None,
        'Lat_GDA94': -33.797409,
        'Long_GDA94': 115.147705,
        'Northing_m': 6279491.554,
        'SiteName': 'SBopp-1',
        'TaxonName': 'Eucalyptus rudis subsp. cratyantha',
        'WAConStat': 'P4'
    }

    assert os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_EXCEL_FILE))


def test_upload_corrupt_excel_file(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CORRUPT_EXCEL_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CORRUPT_EXCEL_FILE, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': ['File is not a zip file'],
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CORRUPT_EXCEL_FILE))


def test_upload_excel_file_missing_header(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_EXCEL_FILE_MISSING_HEADER)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE_MISSING_HEADER, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Header Error': ['The header row must contain data'],
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_EXCEL_FILE_MISSING_HEADER))


def test_upload_excel_file_invalid_header(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_EXCEL_FILE_INVALID_HEADER)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE_INVALID_HEADER, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Header Error': [
            'All header cells must contain unique values',
            'All header cells must be a string (text)'
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_EXCEL_FILE_INVALID_HEADER))


def test_upload_point_shapefile(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POINTS_SHAPEFILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_POINTS_SHAPEFILE, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_201_CREATED

    response_json = response.json()

    assert response_json == \
           {
               'TaxonName': 'Eucalyptus rudis subsp. cratyantha',
               'SiteName': 'SBopp-1',
               'Abundance': 1,
               'HerbRef': '',
               'WAConStat': 'P4',
               'DateObs': '2001-01-03',
               'Author': 'Ecoscape',
               'Comments': '1 plant/s', 'Citation': 'Ecoscape (2010), Armstrong Reserve, Dunsborough - Flora and '
                                                    'Vegetation Assessment. Unpublished report for Ray Village Aged '
                                                    'Services'
           }

    assert os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_POINTS_SHAPEFILE))


def test_upload_polygon_shapefile(test_settings):
    new_submission = get_new_submission()
    new_submission.submission.__root__.datatype = DataType.VEGETATION_ASSOCIATION
    data = new_submission.dict()

    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POLYGONS_SHAPEFILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_POLYGONS_SHAPEFILE, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_201_CREATED

    response_json = response.json()

    assert response_json == {
        'DATE_SUPPL': '2001-01-05',
        'EXTENSION': 0,
        'HECTARES': 676.971,
        'JURISDICTI': 'WA',
        'LISTED_ARE': 677,
        'OBJECTID': 1,
        'RAMSARNAME': 'Becher Point Wetlands',
        'SOURCE': 'State agencies 1:25000',
        'STATUS': 'Existing',
        'Shape_area': 6766640.88279,
        'Shape_len': 12724.5013996
    }

    assert os.path.exists(os.path.join(test_settings.temp_file_storage_path, TEST_POLYGONS_SHAPEFILE))


def test_upload_wrong_shapefile_geometry_type(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POLYGONS_SHAPEFILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           data={'geometry_type': 'POINTS'},
                           files={'source_file': (TEST_POLYGONS_SHAPEFILE, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': [
            'Shapefile must contain POINT/POINTZ based geometry'
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_POLYGONS_SHAPEFILE))


def test_upload_corrupt_zip_file(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CORRUPT_ZIP_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CORRUPT_ZIP_FILE, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': [
            'File is not a zip file'
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CORRUPT_ZIP_FILE))


def test_upload_shapefile_missing_shp(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_SHAPEFILE_MISSING_SHP)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_SHAPEFILE_MISSING_SHP, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': [
            "Zipfile must contain exactly one '.shp' file",
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_SHAPEFILE_MISSING_SHP))


def test_upload_shapefile_invalid_file_types(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_INVALID_FILE_TYPES)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_INVALID_FILE_TYPES, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': [
            'Zipfile must only contain files with shapefile-related '
            'extensions (.shp/.shx/.dbf/.prj/.xml/.sbn/.sbx/.cpg)',
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_SHAPEFILE_MISSING_SHP))


def test_upload_shapefile_inadequate_dbf(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_SHAPEFILE_MISSING_DBF)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_SHAPEFILE_MISSING_DBF, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response_json = response.json()

    assert response_json == {
        'File Format Error': [
            'Shapefile is missing DBF file or has less than 2 non-default attributes',
        ]
    }

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_SHAPEFILE_MISSING_SHP))


def test_upload_source_with_no_submission_in_progress():
    fake_submission_id = '6213455db129abec0d66d9a6'

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_EXCEL_FILE)

    response = client.post(f'/submission/{fake_submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_404_NOT_FOUND

    response_json = response.json()

    assert response_json['detail'] == 'Submission not found'


def test_delete_source_file(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    assert os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE))

    response = client.delete(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert response.text == ''

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE))


def test_add_mappings():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'lat',
            'longitude': 'long',
        },
        'taxon': {
            'field_scientific_name': 'species',
        },
        'date_observed_collected': 'date collected'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response_json = response.json()

    mappings = {
        **mappings,
        'sub_species': None,
        'area_locality_of_occurrence': None,
        'collector': None,
        'count': None,
        'date_identified': None,
        'field_identification': None,
        'genomic_sequence_information': None,
        'habitat': None,
        'identification_ambiguity': None,
        'identification_basis': None,
        'identification_notes': None,
        'identified_by': None,
        'life_stage': None,
        'method_protocol': None,
        'native_introduced_feral': None,
        'organism_remarks': None,
        'preparations': None,
        'presence_absence': None,
        'reproductive_state': None,
        'scientific_name_publisher': None,
        'taxonomic_rank': None,
        'geographic_uncertainty': None,
    }

    assert response_json == mappings


def test_delete_mappings():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'lat',
            'longitude': 'long',
        },
        'taxon': {
            'field_scientific_name': 'species',
        },
        'date_observed_collected': 'date collected'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.delete(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},)

    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_validate_csv():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'Lat_GDA94',
            'longitude': 'Long_GDA94',
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == []


def test_validate_csv_missing_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_MISSING_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_MISSING_DATA, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'Lat_GDA94',
            'longitude': 'Long_GDA94',
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Source file must contain data (excluding header row)'
    ]


def test_validate_csv_invalid_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_INVALID_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_INVALID_DATA, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'easting': 'Easting_m',
            'northing': 'Northing_m',
            'zone': 'zone'
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Row 2: Values should be provided for the following headers: TaxonName',
        'Row 3: The value 23 02 2012 is not a valid date format for header DateObs',
        'Row 4: The value -6279422.141 must be a positive number for header Northing_m',
        'Row 5: The value text is not a decimal number for header Easting_m',
        'Row 6: The value 48 must be one of 49, 50, 51, 52 for header zone'
    ]


def test_validate_csv_invalid_data_file_response():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_CSV_FILE_INVALID_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE_INVALID_DATA, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'easting': 'Easting_m',
            'northing': 'Northing_m',
            'zone': 'zone'
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'}, params={
        'format': 'file'
    })

    assert response.status_code == status.HTTP_200_OK

    file_data = response.content.splitlines()

    assert file_data == [
        b'Row 2: Values should be provided for the following headers: TaxonName',
        b'Row 3: The value 23 02 2012 is not a valid date format for header DateObs',
        b'Row 4: The value -6279422.141 must be a positive number for header Northing_m',
        b'Row 5: The value text is not a decimal number for header Easting_m',
        b'Row 6: The value 48 must be one of 49, 50, 51, 52 for header zone'
    ]


def test_validate_excel():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_EXCEL_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'Lat_GDA94',
            'longitude': 'Long_GDA94',
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == []


def test_validate_excel_missing_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_EXCEL_FILE_MISSING_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE_MISSING_DATA, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'latitude': 'Lat_GDA94',
            'longitude': 'Long_GDA94',
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Source file must contain data (excluding header row)'
    ]


def test_validate_excel_invalid_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_EXCEL_FILE_INVALID_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_EXCEL_FILE_INVALID_DATA, open(test_file_path, 'rb'),
                                                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'location': {
            'easting': 'Easting_m',
            'northing': 'Northing_m',
            'zone': 'zone'
        },
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Row 2: Values should be provided for the following headers: TaxonName',
        'Row 3: The value 2001-01-0 is not a valid date format for header DateObs',
        'Row 4: The value -6279422.005 must be a positive number for header Northing_m',
        'Row 5: The value text is not a decimal number for header Easting_m',
        'Row 6: The value 48 must be one of 49, 50, 51, 52 for header zone'
    ]


def test_validate_shapefile():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POINTS_SHAPEFILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={
                               'source_file': (TEST_POINTS_SHAPEFILE, open(test_file_path, 'rb'), 'application/zip')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == []


def test_validate_shapefile_missing_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POINTS_SHAPEFILE_MISSING_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_POINTS_SHAPEFILE_MISSING_DATA, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Source file must contain data'
    ]


def test_validate_shapefile_invalid_data():
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY,
                                  TEST_POINTS_SHAPEFILE_INVALID_DATA)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_POINTS_SHAPEFILE_INVALID_DATA, open(test_file_path, 'rb'),
                                                  'application/zip')})

    assert response.status_code == status.HTTP_201_CREATED

    mappings = {
        'taxon': {
            'field_scientific_name': 'TaxonName',
        },
        'date_observed_collected': 'DateObs'
    }

    response = client.post(f'/submission/{submission_id}/mappings', headers={'x-email': 'submitter@test.net'},
                           json=mappings)

    assert response.status_code == status.HTTP_201_CREATED

    response = client.get(f'/submission/{submission_id}/validate', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == [
        'Feature 1: Values should be provided for the following attributes: TaxonName',
        'Feature 2: The value 2001-01-0 is not a valid date format for attribute DateObs',
    ]


def test_delete_submisssion(get_test_settings):
    new_submission = get_new_submission()
    data = new_submission.dict()
    response = client.post('/submission',
                           headers={'accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'x-email': 'submitter@test.net'},
                           json=data)

    assert response.status_code == status.HTTP_201_CREATED
    json_response = response.json()
    result_submission = NewSubmissionMetadata(**json_response)
    submission_id = result_submission.new_submission_id

    test_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    response = client.post(f'/submission/{submission_id}/source-file', headers={'x-email': 'submitter@test.net'},
                           files={'source_file': (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_201_CREATED

    assert os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE))

    response = client.delete(f'/submission/{submission_id}', headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert not os.path.exists(os.path.join(get_test_settings().temp_file_storage_path, TEST_CSV_FILE))


def test_get_supporting_file_usages_no_files(test_settings):
    submissions = get_submission_collection(test_settings)
    test_submission = Submission(
        metadata=SurveyMetadata(datatype=DataType.SYSTEMATIC_SURVEY),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.get(f'/submission/{submission_id}/supporting-file-usages',
                          headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_get_supporting_file_usages(test_settings):
    submissions = get_submission_collection(test_settings)
    supporting_file = supporting_file_factory(test_settings)
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            supporting_files=[
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=supporting_file.id,
                    document_type=DocumentType.RECORD_DATA,
                    private=True,
                ),
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=supporting_file.id,
                    document_type=DocumentType.SITE_DATA,
                    private=False,
                ),
            ],
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.get(f'/submission/{submission_id}/supporting-file-usages',
                          headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            'usage_id': str(test_submission.metadata.supporting_files[0].usage_id),
            'file_id': str(supporting_file.id),
            'document_type': "RECORD_DATA",
            "private": True,
        },
        {
            'usage_id': str(test_submission.metadata.supporting_files[1].usage_id),
            'file_id': str(supporting_file.id),
            'document_type': 'SITE_DATA',
            "private": False,
        }
    ]


@pytest.mark.parametrize(
    "supporting_files_initial_value",
    [
        pytest.param([], id='empty array'),
        pytest.param(None, id='null'),
    ],
)
def test_upload_submission_supporting_file(test_settings, supporting_files_initial_value):
    submissions = get_submission_collection(test_settings)
    supporting_files = get_supporting_file_collection(test_settings)

    submission_set = submission_set_factory(test_settings)
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            supporting_files=supporting_files_initial_value,
            submission_set_persistent_id=submission_set.persistent_id,
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id
    test_file_path = os.path.join(os.path.dirname(__file__), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    # upload first file
    response = client.post(f'/submission/{submission_id}/supporting-file',
                           headers={'x-email': 'submitter@test.net'},
                           files={"supporting_file": (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    file_id = response_json["supporting_file"]["_id"]
    assert isinstance(file_id, str)
    assert response_json == {
        'supporting_file': {
            '_id': file_id,
            'file_name': 'test.csv',
             'file_size': 245412,
             'internal_file_name': f'submission-sets/{submission_set.persistent_id}/test.csv',
             "submission_set_persistent_id": submission_set.persistent_id,
             'uploaded_at': ANY,
        },
        'usage': {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': file_id,
            'private': False,
            'usage_id': ANY,
        },
    }
    new_file = supporting_files.find_one({'_id': ObjectId(file_id)})
    assert new_file == {
        '_id': ObjectId(file_id),
        'file_name': 'test.csv',
        'file_size': 245412,
        'internal_file_name': f'submission-sets/{submission_set.persistent_id}/test.csv',
        "submission_set_persistent_id": submission_set.persistent_id,
        'uploaded_at': ANY,
    }
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': ObjectId(file_id),
            'private': False,
            'usage_id': ANY,
        },
    ]
    assert str(updated_submission['metadata']['supporting_files'][0]['usage_id']) == response_json['usage']['usage_id']

    # upload second file, check it gets appended to list, and unique file name chosen
    response_2 = client.post(f'/submission/{submission_id}/supporting-file',
                           headers={'x-email': 'submitter@test.net'},
                           files={"supporting_file": (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})

    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()
    file_id_2 = response_json_2["supporting_file"]["_id"]
    assert isinstance(file_id_2, str)
    assert file_id_2 != file_id
    assert response_json_2 == {
        'supporting_file': {
            '_id': file_id_2,
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{submission_set.persistent_id}/test(1).csv',
            "submission_set_persistent_id": submission_set.persistent_id,
            'uploaded_at': ANY,
        },
        'usage': {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': file_id_2,
            'private': False,
            'usage_id': ANY,
        },
    }
    assert response_json_2['supporting_file']['internal_file_name'] != response_json['supporting_file']['internal_file_name']
    new_file_2 = supporting_files.find_one({'_id': ObjectId(file_id_2)})
    assert new_file_2 == {
        '_id': ObjectId(file_id_2),
        'file_name': 'test.csv',
        'file_size': 245412,
        'internal_file_name': f'submission-sets/{submission_set.persistent_id}/test(1).csv',
        "submission_set_persistent_id": submission_set.persistent_id,
        'uploaded_at': ANY,
    }
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': ObjectId(file_id),
            'private': False,
            'usage_id': ANY,
        },
        {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': ObjectId(file_id_2),
            'private': False,
            'usage_id': ANY,
        },
    ]
    assert str(updated_submission['metadata']['supporting_files'][1]['usage_id']) == response_json_2['usage']['usage_id']

    assert sorted(os.listdir(
        os.path.join(test_settings.temp_file_storage_path, "submission-sets", submission_set.persistent_id)
    )) == ['test(1).csv', 'test.csv']


@pytest.mark.parametrize(
    "supporting_files_initial_value",
    [
        pytest.param([], id='empty array'),
        pytest.param(None, id='null'),
    ],
)
def test_create_submission_supporting_file_usage(test_settings, supporting_files_initial_value):
    """Test creating a new usage of an existing supporting file"""
    submissions = get_submission_collection(test_settings)

    submission_set = submission_set_factory(test_settings)
    supporting_file_1 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    # create submission with no usages
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
            supporting_files=supporting_files_initial_value,
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.post(f'/submission/{submission_id}/supporting-file-usage',
                            headers={'x-email': 'submitter@test.net'},
                            json={
                                "file_id": str(supporting_file_1.id),
                                "document_type": DocumentType.RECORD_DATA,
                                "private": True,
                            })

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json == {
        'usage': {
            'document_type': 'RECORD_DATA',
            'file_id': str(supporting_file_1.id),
            'private': True,
            'usage_id': ANY,
        },
        'sample_data': {'name': 'test', 'date': '2024-02-02', 'lat': '-40', 'long': '123'},
    }
    assert isinstance(response_json['usage']['usage_id'], str)
    # check submission usage is updated in DB
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            'document_type': 'RECORD_DATA',
            'file_id': supporting_file_1.id,
            'private': True,
            'usage_id': ObjectId(response_json['usage']['usage_id']),
        },
    ]


def test_update_submission_supporting_file_usage(test_settings):
    submissions = get_submission_collection(test_settings)

    submission_set = submission_set_factory(test_settings)
    supporting_file_1 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    supporting_file_2 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    # create submission with two usages
    usage_to_update_id = PyObjectId()
    other_usage_id = PyObjectId()
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
            supporting_files=[
                SupportingFileUsage(
                    usage_id=usage_to_update_id,
                    file_id=supporting_file_1.id,
                    document_type=DocumentType.SUPPLEMENTARY_DOCUMENTATION,
                    private=False,
                ),
                SupportingFileUsage(
                    usage_id=other_usage_id,
                    file_id=supporting_file_2.id,
                    document_type=DocumentType.SUPPLEMENTARY_DOCUMENTATION,
                    private=False,
                ),
            ],
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.patch(f'/submission/{submission_id}/supporting-file-usage/{usage_to_update_id}',
                            headers={'x-email': 'submitter@test.net'},
                            json={
                                "document_type": DocumentType.RECORD_DATA,
                                "private": True,
                            })

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json == {
        'usage': {
            'document_type': 'RECORD_DATA',
            'file_id': str(supporting_file_1.id),
            'private': True,
            'usage_id': str(usage_to_update_id),
        },
        'sample_data': {'name': 'test', 'date': '2024-02-02', 'lat': '-40', 'long': '123'},
    }
    # check only one submission file is updated in DB
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            'document_type': 'RECORD_DATA',
            'file_id': supporting_file_1.id,
            'private': True,
            'usage_id': usage_to_update_id,
        },
        {
            'document_type': 'SUPPLEMENTARY_DOCUMENTATION',
            'file_id': supporting_file_2.id,
            'private': False,
            'usage_id': other_usage_id,
        },
    ]


def test_update_submission_supporting_file_usage_not_found(test_settings):
    submissions = get_submission_collection(test_settings)
    # create submission with one usage
    submission_set = submission_set_factory(test_settings)
    supporting_file_1 = supporting_file_factory(test_settings, submission_set_persistent_id=submission_set.persistent_id)
    # create submission with two usages
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
            supporting_files=[
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=supporting_file_1.id,
                    document_type=DocumentType.SUPPLEMENTARY_DOCUMENTATION,
                    private=False,
                ),
            ],
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.patch(f'/submission/{submission_id}/supporting-file-usage/{PyObjectId()}',
                            headers={'x-email': 'submitter@test.net'},
                            json={"document_type": DocumentType.RECORD_DATA, "private": True})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Submission and/or file usage not found'}


def test_delete_submission_supporting_file_usage(test_settings):
    submissions = get_submission_collection(test_settings)
    supporting_files = get_supporting_file_collection(test_settings)

    test_submission_set = submission_set_factory(test_settings)
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=test_submission_set.persistent_id,
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id
    test_file_path = os.path.join(os.path.dirname(__file__), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    # upload file 1
    response_1 = client.post(f'/submission/{submission_id}/supporting-file',
                           headers={'x-email': 'submitter@test.net'},
                           files={"supporting_file": (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})
    assert response_1.status_code == status.HTTP_200_OK
    response_json_1 = response_1.json()
    assert isinstance(response_json_1['supporting_file']['_id'], str)

    # upload file 2
    response_2 = client.post(f'/submission/{submission_id}/supporting-file',
                             headers={'x-email': 'submitter@test.net'},
                             files={"supporting_file": (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})
    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()
    assert isinstance(response_json_2['supporting_file']['_id'], str)

    # Check submission has file usages
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            "usage_id": ANY,
            'file_id': ObjectId(response_json_1['supporting_file']['_id']),
            'private': False,
            'document_type': "SUPPLEMENTARY_DOCUMENTATION"
        },
        {
            "usage_id": ANY,
            'file_id': ObjectId(response_json_2['supporting_file']['_id']),
            'private': False,
            'document_type': "SUPPLEMENTARY_DOCUMENTATION"
        },
    ]
    # check files are in project, and on disk
    assert list(supporting_files.find(
        filter={"submission_set_persistent_id": test_submission_set.persistent_id},
        sort=[("_id", pymongo.ASCENDING)],
    )) == [
        {
            '_id': ObjectId(response_json_1['supporting_file']['_id']),
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{test_submission_set.persistent_id}/test.csv',
            'submission_set_persistent_id': test_submission_set.persistent_id,
            'uploaded_at': ANY,
        },
        {
            '_id': ObjectId(response_json_2['supporting_file']['_id']),
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{test_submission_set.persistent_id}/test(1).csv',
            'submission_set_persistent_id': test_submission_set.persistent_id,
            'uploaded_at': ANY,
        },
    ]
    assert os.path.isfile(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test.csv'
    ))
    assert os.path.isfile(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test(1).csv'
    ))

    # delete file 1 usage
    # this will also delete the supporting file itself, because it has no other usages.
    delete_response = client.delete(f'/submission/{submission_id}/supporting-file-usage/{response_json_1["usage"]["usage_id"]}',
                                    headers={'x-email': 'submitter@test.net'})
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # check file 1 is deleted from usages, but not file 2
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            "usage_id": ANY,
            'file_id': ObjectId(response_json_2['supporting_file']['_id']),
            'private': False,
            'document_type': "SUPPLEMENTARY_DOCUMENTATION"
        },
    ]
    # Check file 1 is deleted from project, but not file 2
    assert list(supporting_files.find(
        filter={"submission_set_persistent_id": test_submission_set.persistent_id},
        sort=[("_id", pymongo.ASCENDING)],
    )) == [
        {
            '_id': ObjectId(response_json_2['supporting_file']['_id']),
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{test_submission_set.persistent_id}/test(1).csv',
            'submission_set_persistent_id': test_submission_set.persistent_id,
            'uploaded_at': ANY,
        },
    ]
    assert not os.path.exists(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test.csv'
    ))
    assert os.path.isfile(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test(1).csv'
    ))


def test_delete_submission_supporting_file_usage_but_not_supporting_file_itself(test_settings):
    submissions = get_submission_collection(test_settings)
    supporting_files = get_supporting_file_collection(test_settings)
    test_file_path = os.path.join(os.path.dirname(__file__), TEST_FILE_DIRECTORY, TEST_CSV_FILE)

    test_submission_set = submission_set_factory(test_settings)
    # Create submission that uses a supporting file twice
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=test_submission_set.persistent_id,
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id
    response_1 = client.post(f'/submission/{submission_id}/supporting-file',
                           headers={'x-email': 'submitter@test.net'},
                           files={"supporting_file": (TEST_CSV_FILE, open(test_file_path, 'rb'), 'text/csv')})
    assert response_1.status_code == status.HTTP_200_OK
    response_json_1 = response_1.json()
    assert isinstance(response_json_1['supporting_file']['_id'], str)
    file_id = ObjectId(response_json_1['supporting_file']['_id'])
    # Create second usage of the same supporting file
    response_2 = client.post(f'/submission/{submission_id}/supporting-file-usage',
                             headers={'x-email': 'submitter@test.net'},
                             json={
                                 "file_id": str(file_id),
                                 "document_type": DocumentType.REPORT,
                                 "private": True,
                             })
    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()

    # Check submissions have file usages
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            "usage_id": ObjectId(response_json_1['usage']['usage_id']),
            'file_id': file_id,
            'private': False,
            'document_type': "SUPPLEMENTARY_DOCUMENTATION"
        },
        {
            "usage_id": ObjectId(response_json_2['usage']['usage_id']),
            'file_id': file_id,
            'private': True,
            'document_type': "REPORT"
        },
    ]
    # check files are in project, and on disk
    assert list(supporting_files.find(
        filter={"submission_set_persistent_id": test_submission_set.persistent_id},
        sort=[("_id", pymongo.ASCENDING)],
    )) == [
        {
            '_id': file_id,
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{test_submission_set.persistent_id}/test.csv',
            'submission_set_persistent_id': test_submission_set.persistent_id,
            'uploaded_at': ANY,
        },
    ]
    assert os.path.isfile(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test.csv'
    ))

    # delete file usage 1
    # this won't delete the supporting file itself, because it has another usage
    delete_response = client.delete(f'/submission/{submission_id}/supporting-file-usage/{response_json_1["usage"]["usage_id"]}',
                                    headers={'x-email': 'submitter@test.net'})
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # check usage 1 is deleted from usages, but not usage 2
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission['metadata']['supporting_files'] == [
        {
            "usage_id": ObjectId(response_json_2['usage']['usage_id']),
            'file_id': file_id,
            'private': True,
            'document_type': "REPORT"
        },
    ]
    # Check file is still present in project
    assert list(supporting_files.find(
        filter={"submission_set_persistent_id": test_submission_set.persistent_id},
        sort=[("_id", pymongo.ASCENDING)],
    )) == [
        {
            '_id': file_id,
            'file_name': 'test.csv',
            'file_size': 245412,
            'internal_file_name': f'submission-sets/{test_submission_set.persistent_id}/test.csv',
            'submission_set_persistent_id': test_submission_set.persistent_id,
            'uploaded_at': ANY,
        },
    ]
    assert os.path.isfile(os.path.join(
        test_settings.temp_file_storage_path, f'submission-sets/{test_submission_set.persistent_id}/test.csv'
    ))


def test_delete_submission_supporting_file_usage_file_not_found(test_settings):
    supporting_file = supporting_file_factory(test_settings)
    submissions = get_submission_collection(test_settings)
    # create submission with one file
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            supporting_files=[
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=supporting_file.id,
                    document_type=DocumentType.REPORT,
                    private=True,
                ),
            ],
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    response = client.delete(f'/submission/{submission_id}/supporting-file-usage/{PyObjectId()}',
                             headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {'detail': 'Submission and/or usage not found'}


def test_mark_survey_unmappable(test_settings):
    submissions = get_submission_collection(test_settings)
    # create survey submission with file and mappings
    submission_set = submission_set_factory(test_settings)
    test_submission = Submission(
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submission_set_persistent_id=submission_set.persistent_id,
        ),
        submitter_id="some_test_submitter",
        mappings=Mappings(taxon=Mappings.SpeciesMappings(field_scientific_name="test_name"), date_observed_collected="2020-01-01"),
    )
    submission_id = submissions.insert_one(test_submission.dict(exclude_unset=True)).inserted_id

    # mark survey as unmappable
    response = client.post(f'/submission/{submission_id}/mark-unmappable',
                             headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'persistent_id': ANY,
        'submission_id': str(submission_id),
        'unmappable': True,
        "sent_to_curation": False,
    }
    persistent_id = response.json()['persistent_id']
    assert isinstance(persistent_id, str) and len(persistent_id) == 16

    # check submission is updated in DB
    updated_submission = submissions.find_one({'_id': submission_id})
    assert updated_submission == {
        '_id': submission_id,
        'metadata': {
            'datatype': 'Systematic survey data',
            "submission_set_persistent_id": submission_set.persistent_id,
        },
        "submitter_id": "some_test_submitter",
        'mappings': {'taxon': {'field_scientific_name': 'test_name'}, 'date_observed_collected': '2020-01-01'},
        # Updated fields
        'persistent_id': persistent_id,
        'unmappable': True,
    }


def test_submit_species_occurrence_submission_to_curation(mocked_responses, test_settings):
    source_file_name = "test_data_to_submit_001.csv"
    source_file_path = os.path.join(test_settings.temp_file_storage_path, source_file_name)
    source_file_content = b"name,lat,long,date\nkoala,-40,123,2024-02-02\n"
    with open(source_file_path, "wb") as file:
        file.write(source_file_content)
    submissions = get_submission_collection(test_settings)
    # create species submission with file and mappings
    test_submission = Submission(
        submitter_id="some_test_submitter",
        persistent_id="2024_test_001",
        metadata=OccurrenceMetadata(
            datatype=DataType.SPECIES_OCCURRENCE,
            submitter="Test Co",
            datum=DatumEnum.AGD66,
            dataset="Drop Bear Observations",
            comments="We found lots",
            sourcefile=source_file_name,
        ),
        mappings=SpreadsheetMappings(
            taxon=SpreadsheetMappings.SpeciesMappings(field_scientific_name="name"),
            date_observed_collected="date",
            location=SpreadsheetMappings.GeographicLocationMappings(latitude="lat", longitude="long"),
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict()).inserted_id
    # register a mocked Curation endpoint
    mock_submit_endpoint = mocked_responses.add(
        mocked_responses.POST,
        "http://mock-curation.localhost/api/v1/submissions/",
        # what the mock endpoint will return
        json=test_submission.persistent_id,
        status=status.HTTP_201_CREATED,
    )

    response = client.post(f'/submission/{submission_id}/submit',
                             headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "persistent_id": test_submission.persistent_id,
        "submission_id": str(submission_id),
        "unmappable": False,
        "sent_to_curation": True,
    }
    # check submission persistent_id hasn't changed, sent_to_curation flag is set
    submission_dict = submissions.find_one({"_id": submission_id})
    assert submission_dict['persistent_id'] == test_submission.persistent_id
    assert submission_dict['sent_to_curation'] is True
    assert submission_dict.get("unmappable") is not True
    # check file was deleted
    assert not os.path.exists(source_file_path)
    # Check Curation endpoint received correct POST content
    assert mock_submit_endpoint.call_count == 1
    matcher = responses.matchers.multipart_matcher(
        data={
            "submission_json": json.dumps({
                "submitter_id": "some_test_submitter",
                "metadata": {
                    "submitter": "Test Co",
                    "datum": "AGD66",
                    "created_on": None,
                    "datatype": "Species occurrence data",
                    "dataset": "Drop Bear Observations",
                    "comments": "We found lots",
                    "sourcefile": "test_data_to_submit_001.csv"
                },
                "mappings": {
                    "taxon": {"field_scientific_name": "name"},
                    "date_observed_collected":
                    "date", "sub_species": None,
                    "count": None,
                    "method_protocol": None,
                    "identification_basis": None,
                    "field_identification": None,
                    "date_identified": None,
                    "collector": None,
                    "identified_by": None,
                    "identification_ambiguity": None,
                    "identification_notes": None,
                    "scientific_name_publisher": None,
                    "taxonomic_rank": None,
                    "organism_remarks": None,
                    "presence_absence": None,
                    "preparations": None,
                    "genomic_sequence_information": None,
                    "life_stage": None,
                    "reproductive_state": None,
                    "native_introduced_feral": None,
                    "geographic_uncertainty": None,
                    "area_locality_of_occurrence": None,
                    "habitat": None,
                    "location": {"latitude": "lat", "longitude": "long"}
                },
                "persistent_id": "2024_test_001",
            }),
        },
        files=[("source_file", (source_file_name, source_file_content))],
    )
    is_a_match, reason = matcher(mock_submit_endpoint.calls[0].request)
    assert is_a_match, reason


def test_submit_systematic_survey_submission_to_curation(mocked_responses, test_settings):
    submission_sets = get_submission_set_collection(test_settings)

    project = submission_set_factory(
        test_settings,
        metadata={"datatype": DataType.SYSTEMATIC_SURVEY, "purpose": "testing submit"},
        persistent_id="2024_project_001",
        submitter_id="some_test_submitter",
        name="A Project",
        submitter="Test Cp",
        comments="This wil be submitted",
    )
    file_1 = supporting_file_factory(
        test_settings,
        submission_set_persistent_id=project.persistent_id,
        file_name='records.csv',
        file_content=b"this,is,the\nfirst,file,content\n",
    )
    file_2 = supporting_file_factory(
        test_settings,
        submission_set_persistent_id=project.persistent_id,
        file_name='site_info.csv',
        file_content=b"this,is,the\r\nsecond,file,content\r\n",
    )
    file_3 = supporting_file_factory(
        test_settings,
        submission_set_persistent_id=project.persistent_id,
        file_name='report.csv',
        file_content=b"this,is,the\nthird,file,content\n",
    )
    file_4 = supporting_file_factory(
        test_settings,
        submission_set_persistent_id=project.persistent_id,
        # file 4 has the same filename as 3, but will be handled correctly and separately.
        file_name='report.csv',
        file_content=b"this,is,the\nfourth,file,content\n",
    )
    file_5 = supporting_file_factory(
        test_settings,
        submission_set_persistent_id=project.persistent_id,
        file_name='some_other_file.csv',
        file_content=b"this,is,the\nfifth,file,content\n",
    )

    submissions = get_submission_collection(test_settings)
    # create species submission with file and mappings
    test_submission = Submission(
        submitter_id="some_test_submitter",
        persistent_id="2024_test_002",
        metadata=SurveyMetadata(
            datatype=DataType.SYSTEMATIC_SURVEY,
            submitter="Test Co",
            datum=DatumEnum.AGD66,
            created_on="2024-01-01T09:30:00",
            submission_set_persistent_id=project.persistent_id,
            name="Looking for animals",
            summary="Didn't find anything",
            from_date="2023-01-01",
            to_date="2023-12-31",
            participants="Aaa,Bbb",
            has_threatened_species=True,
            tags=["Tag1", "Tag2", "Tag3"],
            bounding_box_north_west=Point(type="Point", coordinates=(110.0, -50.0)),
            bounding_box_south_east=Point(type="Point", coordinates=(115.0, -57.0)),
            supporting_files=[
                # File 1 is used twice
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_1.id,
                    document_type=DocumentType.RECORD_DATA,
                    private=False,
                ),
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_1.id,
                    document_type=DocumentType.SUPPLEMENTARY_DOCUMENTATION,
                    private=True,
                ),
                # File 2 is used once
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_2.id,
                    document_type=DocumentType.SITE_DATA,
                    private=False,
                ),
                # File 3 is used once
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_3.id,
                    document_type=DocumentType.REPORT,
                    private=False,
                ),
                # File 4 is used once
                SupportingFileUsage(
                    usage_id=PyObjectId(),
                    file_id=file_4.id,
                    document_type=DocumentType.REPORT,
                    private=True,
                )
                # File 5 is not used, should not be sent
            ]
        ),
        mappings=SpreadsheetMappings(
            taxon=SpreadsheetMappings.SpeciesMappings(field_scientific_name="name"),
            date_observed_collected="date",
            location=SpreadsheetMappings.GeographicLocationMappings(latitude="lat", longitude="long"),
            collector="collector_field",
            count="number_found",
        ),
    )
    submission_id = submissions.insert_one(test_submission.dict()).inserted_id
    # register a mocked Curation endpoint
    mock_submit_endpoint = mocked_responses.add(
        mocked_responses.POST,
        "http://mock-curation.localhost/api/v1/submissions/",
        # what the mock endpoint will return
        json=test_submission.persistent_id,
        status=status.HTTP_201_CREATED,
    )

    response = client.post(f'/submission/{submission_id}/submit',
                             headers={'x-email': 'submitter@test.net'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "persistent_id": test_submission.persistent_id,
        "submission_id": str(submission_id),
        "unmappable": False,
        "sent_to_curation": True,
    }
    # check submission persistent_id hasn't changed, sent to curation flag is set
    submission_dict = submissions.find_one({"_id": submission_id})
    assert submission_dict['persistent_id'] == test_submission.persistent_id
    assert submission_dict['sent_to_curation'] is True
    assert submission_dict.get("unmappable") is not True
    # check supporting files are not deleted (so they can be re-used by future surveys)
    assert os.path.exists(os.path.join(test_settings.temp_file_storage_path, file_1.internal_file_name))
    assert os.path.exists(os.path.join(test_settings.temp_file_storage_path, file_2.internal_file_name))
    assert os.path.exists(os.path.join(test_settings.temp_file_storage_path, file_3.internal_file_name))
    # Check submission_set was updated with sent_to_curation flag
    submission_set_dict = submission_sets.find_one({"_id": project.id})
    assert submission_dict['sent_to_curation'] is True
    # Check Curation endpoint received correct POST content
    assert mock_submit_endpoint.call_count == 1
    matcher = responses.matchers.multipart_matcher(
        data={
            "submission_json": json.dumps({
                "submitter_id": "some_test_submitter", 
                "metadata": {
                    "submitter": "Test Co",
                    "datum": "AGD66",
                    "created_on": "2024-01-01T09:30:00",
                    "datatype": "Systematic survey data",
                    "submission_set_persistent_id": "2024_project_001",
                    "name": "Looking for animals",
                    "summary": "Didn't find anything",
                    "from_date": "2023-01-01",
                    "to_date": "2023-12-31",
                    "participants": "Aaa,Bbb",
                    "has_threatened_species": True,
                    "tags": ["Tag1", "Tag2", "Tag3"],
                    "bounding_box_north_west": {"type": "Point", "coordinates": [110.0, -50.0]},
                    "bounding_box_south_east": {"type": "Point", "coordinates": [115.0, -57.0]},
                    "supporting_files": [
                        {
                            "document_type": "RECORD_DATA",
                            "private": False,
                            "supporting_file_id": str(file_1.id),
                            "file_name": "records.csv",
                            "file_size": 31,
                            "file_location": "records.csv"
                        },
                        {
                            "document_type": "SUPPLEMENTARY_DOCUMENTATION",
                            "private": True,
                            "supporting_file_id": str(file_1.id),
                            "file_name": "records.csv",
                            "file_size": 31,
                            "file_location": "records.csv"
                        },
                        {
                            "document_type": "SITE_DATA",
                            "private": False,
                            "supporting_file_id": str(file_2.id),
                            "file_name": "site_info.csv",
                            "file_size": 34,
                            "file_location": "site_info.csv"
                        },
                        {
                            "document_type": "REPORT",
                            "private": False,
                            "supporting_file_id": str(file_3.id),
                            "file_name": "report.csv",
                            "file_size": 31,
                            "file_location": "report.csv"
                        },
                        {
                            "document_type": "REPORT",
                            "private": True,
                            "supporting_file_id": str(file_4.id),
                            "file_name": "report.csv",
                            "file_size": 32,
                            "file_location": "report(1).csv"
                        },
                    ],
                },
                "mappings": {
                    "taxon": {"field_scientific_name": "name"}, 
                    "date_observed_collected": 
                    "date", "sub_species": None, 
                    "count": "number_found",
                    "method_protocol": None,
                    "identification_basis": None, 
                    "field_identification": None,
                    "date_identified": None,
                    "collector": "collector_field",
                    "identified_by": None,
                    "identification_ambiguity": None,
                    "identification_notes": None,
                    "scientific_name_publisher": None,
                    "taxonomic_rank": None,
                    "organism_remarks": None,
                    "presence_absence": None,
                    "preparations": None,
                    "genomic_sequence_information": None,
                    "life_stage": None,
                    "reproductive_state": None,
                    "native_introduced_feral": None,
                    "geographic_uncertainty": None,
                    "area_locality_of_occurrence": None,
                    "habitat": None,
                    "location": {"latitude": "lat", "longitude": "long"}
                }, 
                "persistent_id": "2024_test_002",
                "submission_set": {
                    "persistent_id": "2024_project_001",
                    "submitter_id": "some_test_submitter",
                     "metadata": {
                         "name": "A Project", "submitter": "Test Cp",
                         "comments": "This wil be submitted",
                         "datatype": "Systematic survey data",
                         "purpose": "testing submit",
                     },
                },
            }),
        },
        files=[
            ("supporting_files", ('records.csv', b"this,is,the\nfirst,file,content\n")),
            ("supporting_files", ('site_info.csv', b"this,is,the\r\nsecond,file,content\r\n")),
            ("supporting_files", ('report.csv', b"this,is,the\nthird,file,content\n")),
            ("supporting_files", ('report(1).csv', b"this,is,the\nfourth,file,content\n")),
        ],
    )
    is_a_match, reason = matcher(mock_submit_endpoint.calls[0].request)
    assert is_a_match, reason
