import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import ANY

import pytest
from bson import ObjectId
from fastapi import status
from fastapi.testclient import TestClient

from app import main
from app.helpers.mongo import get_record_collection
from app.models.records import Record


client = TestClient(main.app)

# test data can use Darwin Core terms, which via aliases are turned into pythonic terms
test_record_data = {
    "persistent_id": "627bbfec45ab7f0c79ec7ab4",
    "submission_id": "2022D4A7abcdefgh",
    "version": 0,
    "last_updated": "2022-07-07T09:53:35.721707",
    "datatype": "Species occurrence data",
    "dcterms:title": "Happy Point",
    "dwc:RightsHolder": None,
    "dwc:acceptedNameUsage": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
    "dwc:scientificName": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
    "dwc:associatedSequences": None,
    "dwc:basisOfRecord": None,
    "dwc:coordinateUncertaintyInMeters": None,
    "dwc:datasetID": None,
    "dwc:verbatimIdentification": None,
    "dwc:dateIdentified": None,
    "dwc:decimalLatitude": -23.08,
    "dwc:decimalLongitude": 124.504,
    "dwc:establishmentMeans": None,
    "dwc:eventDate": "2004-01-30T00:00:00",
    "dwc:habitat": None,
    "dwc:identificationQualifier": None,
    "dwc:identificationRemarks": None,
    "dwc:identifiedBy": None,
    "dwc:individualCount": None,
    "dwc:infraspecificEpithet": None,
    "dwc:institutionCode": "WA Herbarium",
    "dwc:lifeStage": None,
    "dwc:locality": None,
    "dwc:materialSampleID": None,
    "dwc:occurrenceID": None,
    "dwc:occurrenceStatus": None,
    "dwc:organismRemarks": None,
    "dwc:preparations": None,
    "dwc:recordedBy": None,
    "dwc:reproductiveCondition": None,
    "dwc:samplingProtocol": None,
    "dwc:scientificNameAuthorship": None,
    "dwc:taxonRank": None,
    "dwc:threatStatus": None,
    "dwc:kingdom": None
}

BULK_RECORDS_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test-data/delivery/bulk-records.json')
BULK_THREATENED_RECORDS_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test-data/delivery/bulk-threatened-records.json')

test_record = Record(**test_record_data)

test_record_id = '627bbfec45ab7f0c79ec7ab4'


@pytest.mark.no_db
def test_record_mongo_dict_stores_nomos_id_with_public_field_name():
    record = Record(**{**test_record_data, 'NomosID': 340})

    record_dict = record.mongo_dict()

    assert record_dict['NomosID'] == 340
    assert 'nomos_id' not in record_dict


@pytest.fixture(scope="function")
def setup_one_record_document(get_test_settings):
    records_collection = get_record_collection(get_test_settings())
    records_collection.insert_one(test_record.mongo_dict())


def test_get_record(setup_one_record_document):
    response = client.get(f'/records/{test_record_id}/')

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json == test_record.dict()


def test_create_record(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    new_record_data = {
        "persistent_id": "627bbfec45ab7f0c79ec7b3b",
        "submission_id": "2022GdA7abcdefgh",
        "version": 0,
        "datatype": "Species occurrence data",
        "dcterms:title": "Happy Point",
        "dwc:RightsHolder": None,
        "dwc:acceptedNameUsage": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:scientificName": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:associatedSequences": None,
        "dwc:basisOfRecord": None,
        "dwc:coordinateUncertaintyInMeters": None,
        "dwc:datasetID": None,
        "dwc:verbatimIdentification": None,
        "dwc:dateIdentified": None,
        "dwc:decimalLatitude": -22.934,
        "dwc:decimalLongitude": 117.362,
        "dwc:establishmentMeans": None,
        "dwc:eventDate": "2015-05-28T00:00:00",
        "dwc:habitat": None,
        "dwc:identificationQualifier": None,
        "dwc:identificationRemarks": None,
        "dwc:identifiedBy": None,
        "dwc:individualCount": None,
        "dwc:infraspecificEpithet": None,
        "dwc:institutionCode": "WA Herbarium",
        "dwc:lifeStage": None,
        "dwc:locality": None,
        "dwc:materialSampleID": None,
        "dwc:occurrenceID": None,
        "dwc:occurrenceStatus": None,
        "dwc:organismRemarks": None,
        "dwc:preparations": None,
        "dwc:recordedBy": None,
        "dwc:reproductiveCondition": None,
        "dwc:samplingProtocol": None,
        "dwc:scientificNameAuthorship": None,
        "dwc:taxonRank": None,
        "dwc:threatStatus": None,
    }

    assert records_collection.count_documents({}) == 1

    response = client.post('/records/', json=new_record_data)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response = client.post('/records/', json=new_record_data, headers={'x-api-key': 'wrong_password'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post('/records/', json=new_record_data, headers={'x-api-key': 'test_password'})

    assert response.status_code == status.HTTP_201_CREATED

    assert records_collection.count_documents({}) == 2

    response_record = response.json()

    # need to use last_update that was in response record will be different to a newly created one (by milliseconds)
    new_record = Record(last_updated=response_record['last_updated'], **new_record_data)

    assert response_record == new_record


def test_create_systematic_survey_record(get_test_settings):
    records_collection = get_record_collection(get_test_settings())
    new_record_data = {
        # core fields
        "persistent_id": "2022GdA7abcde000",
        "submission_id": "2022GdA7abcdefgh",
        "version": 0,
        "datatype": "Systematic survey data",
        # SSD fields
        "tern:survey": "A Survey",
        "abis:project": "A Project",
        # Other fields
        "dwc:decimalLatitude": -22.934,
        "dwc:decimalLongitude": 117.362,
        "dwc:eventDate": "2015-05-28T00:00:00",
        "dwc:scientificName": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:acceptedNameUsage": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:institutionCode": "WA Herbarium",
        "dwc:infraspecificEpithet": "AAA",
        "dwc:RightsHolder": "BBB",
        "dwc:samplingProtocol": "CCC",
        "NomosID": 340,
    }

    response = client.post('/records/bulk-upload/', json=[new_record_data], headers={'x-api-key': 'test_password'})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"created_count": 1, "updated_count": 0, "deleted_count": 0}

    record_dict = records_collection.find_one({"persistent_id": "2022GdA7abcde000"})
    assert record_dict == {
        '_id': ANY,
        'accepted_name_usage': 'Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell',
        'associated_sequences': None,
        'basis_of_record': None,
        'class_': None,
        'datatype': 'Systematic survey data',
        'date_identified': None,
        'dcterms_title': None,
        'decimal_latitude': -22.934,
        'decimal_longitude': 117.362,
        'establishment_means': None,
        'event_date': '2015-05-28T00:00:00',
        'family': None,
        'geographic_uncertainty': None,
        'habitat': None,
        'identification_qualifier': None,
        'identification_remarks': None,
        'identified_by': None,
        'individual_count': None,
        'informal_groups': None,
        'infraspecific_epithet': 'AAA',
        'institution_code': 'WA Herbarium',
        'kingdom': None,
        'last_updated': ANY,
        'life_stage': None,
        'locality': None,
        'location': {'coordinates': [117.362, -22.934], 'type': 'Point'},
        'material_sample_id': None,
        'NomosID': 340,
        'obfuscated_location': None,
        'occurrence_id': None,
        'occurrence_status': None,
        'order': None,
        'organism_remarks': None,
        'persistent_id': '2022GdA7abcde000',
        'phylum': None,
        'preparations': None,
        'recorded_by': None,
        'reproductive_condition': None,
        'rights_holder': "BBB",
        'sampling_protocol': "CCC",
        'scientific_name': 'Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell',
        'scientific_name_authorship': None,
        'submission_id': '2022GdA7abcdefgh',
        'submission_name': 'A Survey',
        'submission_set_name': 'A Project',
        'taxon_rank': None,
        'threat_status': None,
        'verbatim_identification': None,
        'vernacular_name': None,
        'version': 0,
    }
    assert isinstance(record_dict['_id'], ObjectId)
    assert isinstance(record_dict['last_updated'], str)
    assert datetime.fromisoformat(record_dict['last_updated'])


def test_create_systematic_survey_record_but_fields_are_missing():
    new_record_data = {
        # core fields
        "persistent_id": "2022GdA7abcde000",
        "submission_id": "2022GdA7abcdefgh",
        "version": 0,
        "datatype": "Systematic survey data",
        # SSD fields missing
        # "tern:survey": "A Survey",
        # "abis:project": "A Project",
        # Other fields
        "dwc:decimalLatitude": -22.934,
        "dwc:decimalLongitude": 117.362,
        "dwc:eventDate": "2015-05-28T00:00:00",
        "dwc:scientificName": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:acceptedNameUsage": "Quercus agrifolia var. oxyadenia (Torr.) J.T. Howell",
        "dwc:institutionCode": "WA Herbarium",
    }

    response = client.post('/records/bulk-upload/', json=[new_record_data], headers={'x-api-key': 'test_password'})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json() == {
        'detail': [
            {'loc': ['body', 0, 'tern:survey'],
             'msg': 'Systematic survey Record must have tern:survey',
             'type': 'value_error'},
            {'loc': ['body', 0, 'abis:project'],
             'msg': 'Systematic survey Record must have abis:project',
             'type': 'value_error'},
        ],
    }


def test_update_record(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    assert records_collection.count_documents({}) == 1

    existing_record = records_collection.find_one({'persistent_id': test_record_id})

    assert existing_record is not None

    existing_last_updated = existing_record['last_updated']

    existing_record['institution_code'] = 'Different institution'

    del existing_record['_id']
    del existing_record['last_updated']

    response = client.post('/records/', json=existing_record)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response = client.post('/records/', json=existing_record, headers={'x-api-key': 'wrong_password'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post('/records/', json=existing_record, headers={'x-api-key': 'test_password'})

    assert response.status_code == status.HTTP_200_OK

    # check updated record in response
    json_response = response.json()

    assert json_response['institution_code'] == 'Different institution'

    assert json_response['last_updated'] != existing_last_updated

    assert records_collection.count_documents({}) == 1

    # check updated record in database
    updated_record = records_collection.find_one({'persistent_id': test_record_id})
    assert updated_record['institution_code'] == 'Different institution'


def test_bulk_upload_create(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    assert records_collection.count_documents({}) == 1

    bulk_records = json.load(open(BULK_RECORDS_PATH))

    response = client.post('/records/bulk-upload/', json=bulk_records, headers={'x-api-key': 'test_password'})

    response_json = response.json()

    assert response_json['created_count'] == len(bulk_records)
    assert response_json['updated_count'] == 0

    assert records_collection.count_documents({}) == 1 + len(bulk_records)


def test_bulk_upload_update(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    assert records_collection.count_documents({}) == 1

    bulk_records = json.load(open(BULK_RECORDS_PATH))

    records_collection.insert_many([Record(**record).mongo_dict() for record in bulk_records])

    assert records_collection.count_documents({}) == len(bulk_records) + 1

    for record in bulk_records[:int(len(bulk_records) / 2)]:
        record['dcterms:title'] = 'New title'

    response = client.post('/records/bulk-upload/', json=bulk_records, headers={'x-api-key': 'test_password'})

    response_json = response.json()

    assert response_json['created_count'] == 0
    assert response_json['updated_count'] == len(bulk_records)

    assert records_collection.count_documents({}) == 1 + len(bulk_records)


def test_delete_record(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    assert records_collection.count_documents({}) == 1

    existing_record = records_collection.find_one({'persistent_id': test_record_id})

    assert existing_record is not None

    response = client.delete(f'/records/{test_record_id}/')

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response = client.delete(f'/records/{test_record_id}/', headers={'x-api-key': 'wrong_password'})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.delete(f'/records/{test_record_id}/', headers={'x-api-key': 'test_password'})

    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert records_collection.count_documents({}) == 0

    deleted_record = records_collection.find_one({'persistent_id': test_record_id})

    assert deleted_record is None


def test_bulk_delete_records_by_persistent_ids(get_test_settings, setup_one_record_document):
    records_collection = get_record_collection(get_test_settings())

    assert records_collection.count_documents({}) == 1

    bulk_records = json.load(open(BULK_RECORDS_PATH))

    records_collection.insert_many([Record(**record).mongo_dict() for record in bulk_records])

    assert records_collection.count_documents({}) == len(bulk_records) + 1

    list_data = [record['persistent_id'] for record in bulk_records]

    response = client.request("DELETE", '/records/', json=list_data, headers={'x-api-key': 'test_password'})

    response_json = response.json()

    assert response_json['deleted_count'] == len(bulk_records)

    assert records_collection.count_documents({}) == 1


def test_record_has_attributes(setup_one_record_document):
    # retrieve a record
    response = client.get(f'/records/{test_record_id}/')

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    # assert the retrieved record has certain attributes
    record_attributes = {"kingdom", "phylum", "class_", "order", "family", "informal_groups", "vernacular_name"}
    assert record_attributes.issubset(set(response_json.keys()))


def test_record_obfuscation(monkeypatch: pytest.MonkeyPatch, get_test_settings, setup_one_record_document):
    """
    Test case for record obfuscation implementation

    Test 1.a: Bulk submission - Obfuscation data added.
            - Validate the existence of the 'obfuscated_location' field for all threatened records.
    Test 1.b: Bulk submission - Obfuscation data valid.
            - Validate that the submission process applies obfuscation.
    Test 2.a: Manual rerun basic obfuscation rules - records newly delisted.
            - Validate that manual obfuscation rerun removes obfuscation after manual removal of threat status.
    Test 2.b: Manual rerun basic obfuscation rules - records newly listed.
            - Validate that manual obfuscation rerun applies obfuscation after manual application of threat status.
    Test 3: Single record submission.
            - Validate that single record upload applies obfuscation.
    Test 4: Obfuscation timestamps.
            - Validate record timestamps as accrued from tests 1, 2, and 3.
    Test 5: Manual rerun basic obfuscation rules - Scale change in environment settings.
            - Validate that manual obfuscation rerun recalculates obfuscation after scale change in environment settings.
    Test 6: Manual rerun custom obfuscation rules - Specify record Persistent IDs.
            - Validate that manual obfuscation rerun, which specifies record IDs, recalculates all specified records.
    Test 7: Manual rerun custom obfuscation rules - rerun rules for all records.
            - Validate that manual obfuscation rerun, which specifies all records, recalculates all records.
    """
    # Obfuscation test setup:
    # recreate basic bulk upload test before beginning specific obfuscation implementation checks
    records_collection = get_record_collection(get_test_settings())
    assert records_collection.count_documents({}) == 1
    bulk_records = json.load(open(BULK_THREATENED_RECORDS_PATH))
    operation_result = client.post('/records/bulk-upload/', json=bulk_records, headers={'x-api-key': 'test_password'})
    operation_result_json = operation_result.json()
    assert operation_result_json['created_count'] == len(bulk_records)
    assert operation_result_json['updated_count'] == 0
    assert records_collection.count_documents({}) == 1 + len(bulk_records)

    # setup obfuscation check values to correspond to the four records in bulk-threatened-records.json
    point_wc = {
        "raw": {"lat": -19.1719, "lon": 127.7950},
        "ob1": {"lat": -19.2, "lon": 127.7},
        "ob01": {"lat": -19.18, "lon": 127.79}}
    point_swc = {
        "raw": {"lat": -19.5656, "lon": 127.7017},
        "ob1": {"lat": -19.6, "lon": 127.7},
        "ob01": {"lat": -19.57, "lon": 127.70}}
    point_nwc = {
        "raw": {"lat": -18.8075, "lon": 127.9642},
        "ob1": {"lat": -18.9, "lon": 127.9},
        "ob01": {"lat": -18.81, "lon": 127.96}}
    record_1 = {"id": "2022GPEBgbcd8c56", "point": point_wc, "name": "Anas castanea"}
    record_2 = {"id": "2022GPEBgbcef78a", "point": point_swc, "name": "Anas castanea"}
    record_3 = {"id": "2022GPEBgc458d76", "point": point_wc, "name": "Himantopus himantopus"}
    record_4 = {"id": "2022GPEBgc474c67", "point": point_nwc, "name": "Himantopus himantopus"}
    all_records_check = [record_1, record_2, record_3, record_4]

    # Obfuscation test: 1.a Bulk submission - Obfuscation data added
    # Validate obfuscated_location field exists for all threatened records
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 4

    # Obfuscation test 1.b: Bulk submission - Obfuscation data valid
    # Validate submission process applies obfuscation
    for check in all_records_check:
        selected_record = records_collection.find_one({'persistent_id': check['id']})
        assert selected_record['obfuscated_location']['latitude'] == check['point']['ob1']['lat']
        assert selected_record['obfuscated_location']['longitude'] == check['point']['ob1']['lon']

    # Obfuscation test 2.a: Manual rerun basic obfuscation rules - records newly delisted
    # Validate manual obfuscation rerun removes obfuscation after manual removal of threat status
    records_collection.update_one({'persistent_id': record_3['id']}, {'$set': {'threat_status': None}})
    records_collection.update_one({'persistent_id': record_4['id']}, {'$set': {'threat_status': None}})
    operation_result = client.post('/records/apply_obfuscation_logic/', headers={'x-api-key': 'test_password'})
    operation_result_json = operation_result.json()
    assert operation_result_json['updated_count'] == 2
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 2
    time.sleep(1)  # pausing for future timestamp test

    # Obfuscation test 2.b: Manual rerun basic obfuscation rules - records newly listed
    # Validate manual obfuscation rerun applies obfuscation after manual application of threat status
    records_collection.update_one({'persistent_id': record_3['id']}, {'$set': {'threat_status': "CR"}})
    operation_result = client.post('/records/apply_obfuscation_logic/', headers={'x-api-key': 'test_password'})
    operation_result_json = operation_result.json()
    assert operation_result_json['updated_count'] == 1
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 3
    time.sleep(1)  # pausing for future timestamp test

    # Obfuscation test 3: Single record submission
    # Validate single record upload applies obfuscation
    selected_record = next((record for record in bulk_records if record['persistent_id'] == record_4['id']), None)
    record_response = client.post('/records/', json=selected_record, headers={'x-api-key': 'test_password'})
    assert record_response.status_code == status.HTTP_200_OK
    record_check = records_collection.find_one({'persistent_id': record_4['id']})
    assert record_check['obfuscated_location']['latitude'] == record_4['point']['ob1']['lat']
    assert record_check['obfuscated_location']['longitude'] == record_4['point']['ob1']['lon']
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 4

    # Obfuscation test 4: Obfuscation timestamps
    # Validate record timestamps as accrued from tests 1, 2, and 3
    # Find the documents and save the results
    r_1 = records_collection.find_one({'persistent_id': record_1['id']})
    r_2 = records_collection.find_one({'persistent_id': record_2['id']})
    r_3 = records_collection.find_one({'persistent_id': record_3['id']})
    r_4 = records_collection.find_one({'persistent_id': record_4['id']})
    # Parse datetime strings into datetime objects
    r_1_datetime = datetime.strptime(r_1['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_2_datetime = datetime.strptime(r_2['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_3_datetime = datetime.strptime(r_3['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_4_datetime = datetime.strptime(r_4['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    # Perform datetime comparisons
    # r_1 and r_2 timestamps set in test 1.
    assert abs(r_1_datetime - r_2_datetime) < timedelta(milliseconds=1)  # approximate same age
    # r_3 modified in test 2.b
    assert r_3_datetime > r_2_datetime and abs(r_3_datetime - r_2_datetime) > timedelta(milliseconds=500)
    # r_4 modified in test 3
    assert r_4_datetime > r_3_datetime and abs(r_4_datetime - r_3_datetime) > timedelta(milliseconds=500)

    # Obfuscation test 5: Manual rerun basic obfuscation rules - Scale change in environment settings
    # Validate manual obfuscation rerun recalculates obfuscation after scale change in environment settings
    monkeypatch.setenv(name='OBFUSCATION_GRID_SIZE', value='0.01')
    operation_result = client.post('/records/apply_obfuscation_logic/', headers={'x-api-key': 'test_password'})
    operation_result_json = operation_result.json()
    assert operation_result_json['updated_count'] == 4
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 4
    for check in all_records_check:
        selected_record = records_collection.find_one({'persistent_id': check['id']})
        assert selected_record['obfuscated_location']['latitude'] == check['point']['ob01']['lat']
        assert selected_record['obfuscated_location']['longitude'] == check['point']['ob01']['lon']
    # revert change to environment settings before leaving this test sequence
    monkeypatch.setenv(name='OBFUSCATION_GRID_SIZE', value='0.1')
    client.post('/records/apply_obfuscation_logic/', headers={'x-api-key': 'test_password'})
    time.sleep(1)  # pausing for future timestamp test

    # Obfuscation test 6: Manual rerun custom obfuscation rules - Specify record Persistent ID's
    # Validate manual obfuscation rerun that specifies record ids recalculates only specified records
    rerun_request_data = json.dumps([record_3["id"], record_4["id"]])
    client.post('/records/apply_obfuscation_logic/', data=rerun_request_data, headers={'x-api-key': 'test_password'})
    # Validate record timestamps
    # Find the documents and save the results
    r_1 = records_collection.find_one({'persistent_id': record_1['id']})
    r_2 = records_collection.find_one({'persistent_id': record_2['id']})
    r_3 = records_collection.find_one({'persistent_id': record_3['id']})
    r_4 = records_collection.find_one({'persistent_id': record_4['id']})
    # Parse datetime strings into datetime objects
    r_1_datetime = datetime.strptime(r_1['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_2_datetime = datetime.strptime(r_2['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_3_datetime = datetime.strptime(r_3['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_4_datetime = datetime.strptime(r_4['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    # Perform datetime comparisons
    assert abs(r_1_datetime - r_2_datetime) < timedelta(milliseconds=1)  # approximate same age, modified in test 5
    assert abs(r_3_datetime - r_4_datetime) < timedelta(milliseconds=1)  # approximate same age, modified in test 6
    # r_3 and r_4 modified after r_2 and r_1
    assert r_4_datetime > r_1_datetime and abs(r_4_datetime - r_1_datetime) > timedelta(milliseconds=500)

    # Obfuscation test 7: Manual rerun custom obfuscation rules - rerun rules for all records
    # Validate manual obfuscation rerun that specifies all records recalculates all records
    previous_test = r_4_datetime
    time.sleep(1)  # pausing for future timestamp test
    client.post('/records/apply_obfuscation_logic/?rerun_all_records=true', headers={'x-api-key': 'test_password'})
    # Validate record timestamps
    # Find the documents and save the results
    r_1 = records_collection.find_one({'persistent_id': record_1['id']})
    r_2 = records_collection.find_one({'persistent_id': record_2['id']})
    r_3 = records_collection.find_one({'persistent_id': record_3['id']})
    r_4 = records_collection.find_one({'persistent_id': record_4['id']})
    # Parse datetime strings into datetime objects
    r_1_datetime = datetime.strptime(r_1['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_2_datetime = datetime.strptime(r_2['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_3_datetime = datetime.strptime(r_3['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    r_4_datetime = datetime.strptime(r_4['obfuscated_location']['date_obfuscated'], '%Y-%m-%dT%H:%M:%S.%f')
    # Perform datetime comparisons
    assert abs(r_1_datetime - r_2_datetime) < timedelta(milliseconds=1)  # approximate same age
    assert abs(r_2_datetime - r_3_datetime) < timedelta(milliseconds=1)  # approximate same age
    assert abs(r_3_datetime - r_4_datetime) < timedelta(milliseconds=1)  # approximate same age
    # all records modified since last test
    assert r_1_datetime > previous_test and abs(r_1_datetime - previous_test) > timedelta(milliseconds=500)
