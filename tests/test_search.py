import json
import os
from unittest.mock import patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from fastapi import status

from app import main
from app.helpers.mongo import get_record_collection, get_region_collection, \
    get_published_submission_collection, get_published_submission_set_collection
from app.models.common_enums import DataType
from tests.helpers import mock_authentication


client = TestClient(main.app)

with open(os.path.join(os.path.dirname(__file__), 'test-data', 'delivery', 'records.json')) as file:
    test_records = json.load(file)


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.routers.records.is_authorised', mock_authentication.is_authorised) as _fixture:
        yield _fixture


@pytest.fixture(scope="function")
def insert_test_records(get_test_settings):
    records_collection = get_record_collection(get_test_settings())
    records_collection.insert_many(test_records)


def test_database(get_test_settings, insert_test_records):
    records_collection = get_record_collection(get_test_settings())
    count = records_collection.count_documents({})
    assert (count == len(test_records))
    assert len(test_records) == 1004


def test_search_species_occurrence_record_returned_fields(insert_test_records):
    """
    Test that record search returns the fields defined in PublicRecord model
    """
    response = client.get(
        "/records/", params={"species": "Melaleuca linophylla"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert len(response_json['results']) == 1
    assert response_json['results'][0] == {
        'id': '61efbf944b15c32c6b26e043',
        # datatype defaults to this when record has no datatype
        'datatype': 'Species occurrence data',
        'location': {
            'coordinates': [116.971583, -21.074028011977738],
            'type': 'Point',
        },
        'obfuscated_location': None,
        'conservation_status': None,
        'data_provider': 'WA Herbarium',
        'dataset': 'WA Herbarium records-2021-08-31',
        'date': '2005-08-29T00:00:00+08:00',
        'kingdom': 'Plantae',
        'recorded_species': 'Melaleuca linophylla',
        'species': 'Melaleuca linophylla',
        "submission_name": None,
        "submission_set_name": None,
    }


def test_search_systematic_survey_record_returned_fields(test_settings):
    """
    Test that record search returns the fields defined in PublicRecord model
    """
    # Create one systematic survey record
    response = client.post(
        "/records/",
        headers={"x-api-key": "test_password"},
        json={
            # core fields
            "persistent_id": "2022BBA7abcde000",
            "submission_id": "2022BBA7abcdefgh",
            "version": 0,
            "datatype": "Systematic survey data",
            # SSD fields
            "submission_name": "A Survey",
            "submission_set_name": "A Project",
            # Other fields
            "dwc:decimalLatitude": -22.934,
            "dwc:decimalLongitude": 117.362,
            "dwc:eventDate": "2015-05-28T00:00:00",
            "dwc:scientificName": "Quercus agrifolia var. oxyadenia (Torr.)",
            "dwc:acceptedNameUsage": "Quercus agrifolia var. oxyadenia",
            "dwc:institutionCode": "WA Herbarium",
            "dwc:threatStatus": None,
            "dwc:kingdom": "Animals",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.content

    response = client.get("/records/")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json['results'] == [
        {
            'id': '2022BBA7abcde000',
            'datatype': 'Systematic survey data',
            'dataset': None,
            'submission_name': 'A Survey',
            'submission_set_name': 'A Project',
            'date': '2015-05-28T00:00:00',
            'conservation_status': None,
            'data_provider': 'WA Herbarium',
            'kingdom': "Animals",
            'location': {'coordinates': [117.362, -22.934], 'type': 'Point'},
            'obfuscated_location': None,
            'recorded_species': 'Quercus agrifolia var. oxyadenia (Torr.)',
            'species': 'Quercus agrifolia var. oxyadenia',
        },
    ]


def test_search_by_species(insert_test_records):
    response = client.get(f'/records/', params={
        "species": "Leucopogon paradoxus"
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert len(response_json['results']) == 4
    assert response_json['count'] == 4
    assert response_json['total'] == 4

    for result in response_json['results']:
        assert result['species'] == 'Leucopogon paradoxus'

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_by_data_provider(insert_test_records):
    response = client.get(f'/records/', params={
        "data_provider": "WA Museum"
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json['total'] == 3
    assert response_json['count'] == 3
    assert len(response_json['results']) == 3

    for result in response_json['results']:
        assert result['data_provider'] == 'WA Museum'

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_by_dataset(test_settings, insert_test_records):
    # insert record with non-SPECIES_OCCURRENCE datatype but matching dcterms_title that will be ignored
    get_record_collection(test_settings).insert_one(
        {
            "persistent_id": "2024EMPVZ10849c8",
            "datatype": "Systematic survey data",
            "location": {"type": "Point", "coordinates": [128.98777, -15.68777]},
            "event_date": "2009-05-19T00:00:00+08:00",
            "accepted_name_usage": "Rattus tunneyi",
            "dcterms_title": "RAW Invasive species - SENSITIVE",
            "kingdom": "Animalia",
            "institution_code": "Department of Primary Industries and Regional Development",
            "scientific_name": "Rattus tunneyi",
            "decimal_longitude": 128.98777,
            "decimal_latitude": -15.68777
        },
    )

    response = client.get('/records/', params={
        'dataset': 'RAW Invasive species - SENSITIVE'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json['count'] == 13
    assert response_json['count'] == len(response_json['results'])

    for result in response_json['results']:
        assert result['dataset'] == 'RAW Invasive species - SENSITIVE'


def test_search_by_survey_name(test_settings, insert_test_records):
    # Search by a survey name
    response = client.get(
        '/records/',
        params={'survey_name': 'Forest Survey Winter 2024'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json['total'] == 2
    assert response_json['count'] == 2
    assert len(response_json['results']) == 2

    for result in response_json['results']:
        assert result['submission_name'] == 'Forest Survey Winter 2024'
        assert result['datatype'] == "Systematic survey data"

    # Search by a dataset name - no results
    response2 = client.get(
        '/records/',
        params={'survey_name': 'WA Herbarium records-2021-08-31'},
    )

    assert response2.status_code == status.HTTP_200_OK
    response_json2 = response2.json()
    assert response_json2['total'] == 0
    assert response_json2['count'] == 0
    assert len(response_json2['results']) == 0


def test_search_by_project_name(test_settings, insert_test_records):
    # Search by a survey name
    response = client.get(
        '/records/',
        params={'project_name': 'South-west Forest Surveys'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json['total'] == 2
    assert response_json['count'] == 2
    assert len(response_json['results']) == 2

    for result in response_json['results']:
        assert result['submission_set_name'] == 'South-west Forest Surveys'
        assert result['datatype'] == "Systematic survey data"

    # Search by a dataset name - no results
    response2 = client.get(
        '/records/',
        params={'project_name': 'WA Herbarium records-2021-08-31'},
    )

    assert response2.status_code == status.HTTP_200_OK
    response_json2 = response2.json()
    assert response_json2['total'] == 0
    assert response_json2['count'] == 0
    assert len(response_json2['results']) == 0


def test_search_by_date(insert_test_records):
    response = client.get('/records/', params={
        'date_to': '2009-05-23',
        'date_from': '2009-05-19'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert len(response_json['results']) == 5
    assert response_json['count'] == 5
    assert response_json['total'] == 5

    for result in response.json()['results']:
        assert result['date'] >= '2009-05-19' or result['date'] <= '2009-05-23'

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_by_species_and_date(insert_test_records):
    response = client.get('/records/', params={
        'species': 'Leucopogon paradoxus',
        'date_to': '2009-05-23',
        'date_from': '2009-05-22'
    })

    response_json = response.json()

    assert len(response_json['results']) == 2
    assert response_json['count'] == len(response_json['results'])

    for result in response_json['results']:
        assert result['date'] >= '2009-05-22' or result['Date'] <= '2009-05-23'
        assert result['species'] == 'Leucopogon paradoxus'


def test_search_by_distance(insert_test_records):
    response = client.get('/records/', params={
        'json_encoded_area': json.dumps({
            "radius": 10,
            "geojson_feature": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [126.8881, -13.98209]
                }
            }
        }),
    })

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert len(response_json['results']) == 2
    assert response_json['count'] == 2
    assert response_json['total'] == 2

    for result in response_json['results']:
        point = (result['location']['coordinates'][1],
                 result['location']['coordinates'][0])
        target = (-13.98209, 126.8881)
        # TODO: Replace haversine library with single function
        # distance = hs.haversine(point, target)
        # assert distance < 11

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_by_polygon(insert_test_records):
    response = client.get('/records/', params={
        'json_encoded_area': json.dumps({
            "geojson_feature": {
                "geometry": {"type": "Polygon", "coordinates": [
                    [[126.8885, -13.9810],  # NE
                     [126.8885, -13.9830],  # SE
                     [126.8870, -13.9830],  # SW
                     [126.8870, -13.9810],  # NW
                     [126.8885, -13.9810]]  # NE
                ]}
            },
        }),
    })

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert len(response_json['results']) == 2
    assert response_json['count'] == 2
    assert response_json['total'] == 2

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_by_region(test_settings, insert_test_records):
    # Insert a test region to search by
    get_region_collection(test_settings).insert_one({
        "_id": ObjectId("664717560300d93c95ae33aa"),
        "name": "Test region",
        "source": "Manual",
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[
                    [126.9, -13.9],
                    [126.9, -13.999],
                    [126.8, -13.999],
                    [126.8, -13.9],
                    [126.9, -13.9]
                ]]],
            },
        },
    })

    response = client.get('/records/', params={
        'region_id': "664717560300d93c95ae33aa",
    })

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert len(response_json['results']) == 2
    assert response_json['count'] == 2
    assert response_json['total'] == 2

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_search_with_cluster(insert_test_records):
    # A viewport search without a defined area scales the viewport coordinates to standardize the area for caching.
    # This viewport produces 8 visible points in 7 clusters with size distribution [1, 1, 2, 1, 1, 1, 1].
    # The record search encompassing the scaled area contains 24 additional non-visible points, for a total of 32.
    response_viewport = client.get('/records/clusters/', params={
        'viewport': json.dumps({
            "zoom": 12,
            "ne": {
                "lat": -32.086937830943626,
                "lng": 115.93151092529298
            },
            "sw": {
                "lat": -32.31992368630914,
                "lng": 115.4601287841797
            }
        }),
    })
    assert response_viewport.status_code == status.HTTP_200_OK
    response_json_viewport = response_viewport.json()
    assert response_json_viewport['total'] == 32
    cluster_sizes = [cluster['n']
                     for cluster in response_json_viewport['results']]
    assert cluster_sizes == [1, 1, 2, 1, 1, 1, 1]

    # A viewport search with a defined area searches only the defined area without scaling.
    # The explicit search area produces 8 visible points in 7 clusters with size distribution [1, 1, 2, 1, 1, 1, 1].
    response_area = client.get('/records/clusters', params={
        'json_encoded_area': json.dumps(
            {
                "geojson_feature": {
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[115.4601287841797, -32.31992368630914],
                             [115.93151092529298, -32.31992368630914],
                             [115.93151092529298, -32.086937830943626],
                             [115.4601287841797, -32.086937830943626],
                             [115.4601287841797, -32.31992368630914]]
                        ]
                    }
                }
            },
        ),
        'viewport': json.dumps(
            {
                "zoom": 12,
                "ne": {
                    "lat": -32.086937830943626,
                    "lng": 115.93151092529298
                },
                "sw": {
                    "lat": -32.31992368630914,
                    "lng": 115.4601287841797
                }
            },
        ),
    })

    assert response_area.status_code == status.HTTP_200_OK
    response_json_area = response_area.json()
    assert response_json_area['total'] == 8
    cluster_sizes = [cluster['n'] for cluster in response_json_area['results']]
    assert cluster_sizes == [1, 1, 2, 1, 1, 1, 1]

    # A tiny polygon that produces
    # no results, should produce no clusters.
    response_none = client.get('/records/clusters', params={
        'json_encoded_area': json.dumps({
            "geojson_feature": {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[115.84400653839113, -32.54080782599324],
                         [115.84400653839113, -32.54171227149179],
                         [115.84469318389894, -32.54171227149179],
                         [115.84482192993165, -32.540844003988084],
                         [115.84400653839113, -32.54080782599324]]
                    ]
                }
            }
        }),
    })
    assert response_none.status_code == status.HTTP_200_OK
    response_json_none = response_none.json()
    assert response_json_none['total'] == 0
    assert len(response_json_none['results']) == 0

    # Searching on the full test recordset, no params at all.
    # This clusters at the radius for the default viewport (at zoom 5)
    response_all = client.get('/records/clusters', params={})
    assert response_all.status_code == status.HTTP_200_OK
    response_json_all = response_all.json()
    cluster_sizes = [cluster['n'] for cluster in response_json_all['results']]
    assert cluster_sizes == [142, 84, 104, 112, 519, 6, 24, 9, 1, 1]
    assert sum(cluster_sizes) == response_json_all['total']
    assert response_json_all['total'] == 1002


def test_search_clusters_include_ssd_records(insert_test_records):
    response_viewport = client.get('/records/clusters/', params={
        'viewport': json.dumps({
            "zoom": 16,
            "ne": {
                "lat": -13.98208,
                "lng": 126.8884,
            },
            "sw": {
                "lat": -13.98213,
                "lng": 126.8879,
            },
        }),
    })
    assert response_viewport.status_code == status.HTTP_200_OK
    response_json_viewport = response_viewport.json()
    # Should get 1 cluster with 2 records in it
    assert response_json_viewport['total'] == 2
    assert response_json_viewport['count'] == 2
    assert len(response_json_viewport['results']) == 1
    assert response_json_viewport['results'][0]['n'] == 2
    assert len(response_json_viewport['results'][0]['records']) == 2

    # Check clusters include records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json_viewport['results'][0]['records'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json_viewport['results'][0]['records'])


def test_search_sorting(insert_test_records):
    for key in ['date', 'species', 'dataset', 'data_provider']:
        response = client.get('/records/', params={
            "sort": key
        })
        response_json = response.json()
        last_value = None
        for record in response_json['results']:
            if last_value is not None:
                assert (record[key] >= last_value)
            last_value = record[key]

        response = client.get('/records/', params={
            "sort": key,
            "descending": True
        })
        response_json = response.json()
        last_value = None
        for record in response_json['results']:
            if last_value is not None:
                assert (record[key] <= last_value)
            last_value = record[key]


def test_sensitive_records_shown_to_logged_in_user_with_permission(insert_test_records):
    response = client.get('/records/', params={
        'offset': '0',
        'limit': '500',
    }, headers={
        'x-email': 'sensitive@test.net'
    })
    response2 = client.get('/records/', params={
        'offset': '500',
        'limit': '500',
    }, headers={
        'x-email': 'sensitive@test.net'
    })
    response3 = client.get('/records/', params={
        'offset': '1000',
        'limit': '500',
    }, headers={
        'x-email': 'sensitive@test.net'
    })
    assert response.status_code == response2.status_code == response3.status_code == status.HTTP_200_OK

    results = response.json()['results']
    results.extend(response2.json()['results'])
    results.extend(response3.json()['results'])

    results_contain_threatened = False
    results_contain_threatened_ssd_record = False
    for result in results:
        if 'conservation_status' in result and result['conservation_status'] is not None:
            results_contain_threatened = True
            if result['datatype'] == DataType.SYSTEMATIC_SURVEY:
                results_contain_threatened_ssd_record = True

    assert results_contain_threatened
    assert results_contain_threatened_ssd_record


def test_sensitive_records_not_shown_to_anonymous_user(insert_test_records):
    response = client.get('/records/', params={
        'offset': '0',
        'limit': '500',
    })
    response2 = client.get('/records/', params={
        'offset': '500',
        'limit': '500',
    })
    response3 = client.get('/records/', params={
        'offset': '1000',
        'limit': '500',
    })
    assert response.status_code == response2.status_code == response3.status_code == status.HTTP_200_OK

    results = response.json()['results']
    results.extend(response2.json()['results'])
    results.extend(response3.json()['results'])

    # check all results are not sensitive (have conservation_status == None)
    for record in results:
        assert 'conservation_status' in record
        assert record['conservation_status'] is None

    # Check search includes Survey records
    assert any(record['datatype'] ==
               DataType.SYSTEMATIC_SURVEY for record in results)


def test_records_by_kingdom_no_results(insert_test_records):
    response = client.get('/records/', params={
        'kingdoms': 'Bacteria'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    assert response_json['count'] == 0
    assert response_json['count'] == len(response_json['results'])


def test_records_by_single_kingdom_with_results(insert_test_records):
    response = client.get('/records/', params={
        'kingdoms': 'Animalia'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()
    assert response_json['count'] == 15
    assert response_json['total'] == 15
    assert len(response_json['results']) == 15

    # Check search returns records of both datatypes
    assert any(record['datatype'] == DataType.SPECIES_OCCURRENCE
               for record in response_json['results'])
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json['results'])


def test_records_by_multiple_kingdoms_with_results(insert_test_records):
    response = client.get('/records/', params={
        'kingdoms': ['Animalia', 'Fungi']
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()
    assert response_json['count'] == 17
    assert response_json['total'] == 17
    assert len(response_json['results']) == 17


def test_records_by_multiple_kingdoms_with_no_results(insert_test_records):
    response = client.get('/records/', params={
        'kingdoms': ['other','some_other']
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()
    assert response_json['count'] == 0
    assert response_json['count'] == len(response_json['results'])


def test_search_records_by_submission_id_for_survey(insert_test_records):
    response = client.get('/records/', params={
        'submission_id': '2024FRPLddad39c2'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    # 2 records returned. 1 threatened record in Survey not returned to public user.
    assert response_json['count'] == 2
    assert response_json['total'] == 2
    assert len(response_json['results']) == response_json['count']
    assert response_json['results'][0]['id'] == "2024FRPKg8008c78"
    assert response_json['results'][0]['datatype'] == "Systematic survey data"
    assert response_json['results'][1]['id'] == "2024FRRDt1d05e52"
    assert response_json['results'][1]['datatype'] == "Systematic survey data"


def test_search_records_by_submission_id_for_species_submission(insert_test_records):
    response = client.get('/records/', params={
        'submission_id': '2024FRQ35e2f51c3'
    })

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    # 1 record returned.
    assert response_json['count'] == 1
    assert response_json['total'] == 1
    assert len(response_json['results']) == response_json['count']
    assert response_json['results'][0]['id'] == "2024FRQ3Sb343733"
    assert response_json['results'][0]['datatype'] == "Species occurrence data"


def test_search_records_by_submission_set_id_for_project(insert_test_records):
    # Insert published submission, this is required to search by submission_set_id
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FRPLddad39c2",
            "version": 0,
            "submission_set_id": "2024GLOxmeffaf55",
            "visibility": "RESTRICTED",
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "Forest Survey Winter 2024",
                "summary": "",
                "submitter": "",
                "rights_holder": "",
                "from_date": "2024-01-01",
                "to_date": "2024-01-30",
                "participants": "One,Two,Three",
                "tags": [],
                "bounding_box_north_west": {"type": "Point", "coordinates": [30, -40]},
                "bounding_box_south_east": {"type": "Point", "coordinates": [35, -45]},
                "supporting_files": [],
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK

    response = client.get(
        '/records/',
        params={'submission_set_id': '2024GLOxmeffaf55'},
    )

    assert response.status_code == status.HTTP_200_OK

    response_json = response.json()

    # 2 records returned. 1 threatened record in Project not returned to public user.
    assert response_json['count'] == 2
    assert response_json['total'] == 2
    assert len(response_json['results']) == response_json['count']
    assert response_json['results'][0]['id'] == "2024FRPKg8008c78"
    assert response_json['results'][0]['datatype'] == "Systematic survey data"
    assert response_json['results'][0]['submission_set_name'] == "South-west Forest Surveys"
    assert response_json['results'][1]['id'] == "2024FRRDt1d05e52"
    assert response_json['results'][1]['datatype'] == "Systematic survey data"
    assert response_json['results'][1]['submission_set_name'] == "South-west Forest Surveys"


def test_record_search_includes_ssd_records_flag(test_settings, insert_test_records):
    """
    Test that the total_includes_systematic_survey_results flag is set in the response,
    even when the ssd records are not in the page of records returned.
    """
    # make a search that matches an SSD record, which is in the page of results returned
    response_1 = client.get(f'/records/', params={
        "species": "Leucopogon paradoxus",
        "sort": "data_provider",  # "institution_code" in backend
        "descending": False,
    })
    assert response_1.status_code == status.HTTP_200_OK
    response_json_1 = response_1.json()
    assert response_json_1['total'] == 4
    assert response_json_1['count'] == 4
    assert any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
               for record in response_json_1['results'])
    assert response_json_1['total_includes_systematic_survey_results'] is True

    # make a search that matches an SSD record, but it is not in the page of results returned
    response_2 = client.get(f'/records/', params={
        "species": "Leucopogon paradoxus",
        # sort + limit ensures ssd record is not in page returned
        "sort": "data_provider",  # "institution_code" in backend
        "descending": False,
        "limit": 2,
    })
    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()
    assert response_json_2['total'] == 4
    assert response_json_2['count'] == 2
    assert not any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
                   for record in response_json_2['results'])
    # Flag is still true when SSD record not in returned page
    assert response_json_2['total_includes_systematic_survey_results'] is True

    # make a search that doesn't match any SSD records
    response_2 = client.get(f'/records/', params={
        "dataset": "WA Herbarium records-2021-08-31",
    })
    assert response_2.status_code == status.HTTP_200_OK
    response_json_2 = response_2.json()
    assert response_json_2['total'] == 986
    assert response_json_2['count'] == 100
    assert not any(record['datatype'] == DataType.SYSTEMATIC_SURVEY
                   for record in response_json_2['results'])
    assert response_json_2['total_includes_systematic_survey_results'] is False


def test_species_list_includes_records_for_all_datatypes(insert_test_records, get_test_settings):
    records_collection = get_record_collection(get_test_settings())
    records_collection.update_many(
        {'accepted_name_usage': 'Leucopogon paradoxus'},
        {'$set': {'NomosID': 1234}},
    )

    response = client.post(
        "/records/species_list",
        json={
            "data_provider": ["WA Museum"],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    assert response_json['count'] == 4
    assert response_json['total'] == 4
    assert response_json['threat_statuses'] == {"None": 3, "LC": 1}
    assert response_json['species_list'] == [
        {
            'accepted_name_usage': 'Leucopogon paradoxus',
            'accepted_name_without_author': '',
            'nomos_id': 1234,
            'dwc:class': None,
            'dwc:family': None,
            'dwc:kingdom': 'Animalia',
            'dwc:order': None,
            'dwc:phylum': None,
            'dwc:vernacularName': None,
            'establishment_means': None,
            'scientific_name': 'Leucopogon paradoxus',
            'scientific_name_authorship': None,
            'search_area': None,
            'search_parameters': None,
            'threat_status': None,
            'verbatim_identification': None,
        },
        {
            'accepted_name_usage': 'Made up name for SSD record',
            'accepted_name_without_author': '',
            'nomos_id': None,
            'dwc:class': None,
            'dwc:family': None,
            'dwc:kingdom': 'Animalia',
            'dwc:order': None,
            'dwc:phylum': None,
            'dwc:vernacularName': None,
            'establishment_means': None,
            'scientific_name': 'Made up name for SSD record',
            'scientific_name_authorship': None,
            'search_area': None,
            'search_parameters': None,
            'threat_status': None,
            'verbatim_identification': None,
        },
        {
            'accepted_name_usage': 'Paraporpidia glauca',
            'accepted_name_without_author': '',
            'nomos_id': None,
            'dwc:class': None,
            'dwc:family': None,
            'dwc:kingdom': 'Animalia',
            'dwc:order': None,
            'dwc:phylum': None,
            'dwc:vernacularName': None,
            'establishment_means': None,
            'scientific_name': 'Paraporpidia glauca',
            'scientific_name_authorship': None,
            'search_area': None,
            'search_parameters': None,
            'threat_status': 'LC',
            'verbatim_identification': None,
        },
        {
            'accepted_name_usage': 'made up name for occurrence record',
            'accepted_name_without_author': '',
            'nomos_id': None,
            'dwc:class': None,
            'dwc:family': None,
            'dwc:kingdom': 'Plantae',
            'dwc:order': None,
            'dwc:phylum': None,
            'dwc:vernacularName': None,
            'establishment_means': None,
            'scientific_name': 'made up name for occurrence record',
            'scientific_name_authorship': None,
            'search_area': None,
            'search_parameters': None,
            'threat_status': None,
            'verbatim_identification': None,
        }
    ]
