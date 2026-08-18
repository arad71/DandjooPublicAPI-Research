import csv
import json
import os
import io
from unittest.mock import patch

import pytest
import shapefile
import zipfile

from fastapi import status
from fastapi.testclient import TestClient

from app import main
from app.helpers.export_field_mappings import convert_lists_for_csv_export
from app.helpers.mongo import get_record_collection
from app.models.records import Record
from tests.helpers import mock_authentication

TEST_EXPORT_CSV_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test-data/delivery/test-export.csv')
TEST_EXPORT_ZIP_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test-data/delivery/test-export.zip')

client = TestClient(main.app)

with open(os.path.join(os.path.dirname(__file__), 'test-data', 'delivery', 'records.json')) as file:
    test_records = json.load(file)


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.routers.records.is_authorised', mock_authentication.is_authorised) as _fixture:
        yield _fixture


@pytest.fixture(scope="function")
def insert_test_records(test_settings):
    records_collection = get_record_collection(test_settings)
    records_collection.insert_many(test_records)


@pytest.fixture(scope="function")
def insert_published_submission_and_submission_set(test_settings):
    """
    Insert published submissions and submission sets to accompany SSD Records.
    """
    response = client.post(
        "/published_submissions/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024FRPLddad39c2",
            "version": 0,
            "submission_set_id": "2024GLOxmeffaf55",
            "visibility": "RESTRICTED",  # Survey contains a threatened record.
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
    response = client.post(
        "/published_submission_sets/",
        headers={"x-api-key": "test_password"},
        json={
            "persistent_id": "2024GLOxmeffaf55",
            "version": 0,
            "metadata": {
                "datatype": "Systematic survey data",
                "name": "South-west Forest Surveys",
                "purpose": "",
                "comments": "",
                "submitter": "",
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK


def test_export_species_list(insert_test_records, test_settings):
    """
    This test validates the species list export by confirming that the route provides a csv file, and that the csv is
    in the expected form for the species list (i.e. types of species, not observation counts). Detailed testing of logic
    for species list queries, selected data, or output are covered in test_search_obfuscation, not here.
    """
    # using a random search parameter to work with a smaller set of data and generate expected validation criteria
    target_records_names = [item['accepted_name_usage'] for item in test_records
                      if 'Department of Primary Industries and Regional Development' in item['institution_code']]
    expected_species_list_names = set(target_records_names)
    expected_nomos_ids = {
        name: index for index, name in enumerate(sorted(expected_species_list_names), start=1000)
    }

    records_collection = get_record_collection(test_settings)
    for name, nomos_id in expected_nomos_ids.items():
        records_collection.update_many(
            {'accepted_name_usage': name},
            {'$set': {'NomosID': nomos_id}},
        )

    # This step guarantees that possible future changes to the test data does not invalidate the test
    assert len(target_records_names) > len(expected_species_list_names)

    response = client.post('/records/export-species_list/', json={
        "data_provider": ['Department of Primary Industries and Regional Development']})

    assert response.status_code == status.HTTP_200_OK

    response_csv_file_pointer = io.StringIO(response.content.decode('utf-8-sig'))
    response_csv = csv.DictReader(response_csv_file_pointer)
    response_rows = list(response_csv)
    assert response_csv.fieldnames[0] == 'NomosID'
    assert len(response_rows) == len(expected_species_list_names)
    assert {
        row['Accepted Name (dwc:acceptedNameUsage)']: int(row['NomosID'])
        for row in response_rows
    } == expected_nomos_ids


def test_export_species_pdf_includes_nomos_id(insert_test_records, test_settings):
    target_name = next(
        item['accepted_name_usage'] for item in test_records
        if 'Department of Primary Industries and Regional Development' in item['institution_code']
    )
    records_collection = get_record_collection(test_settings)
    records_collection.update_many(
        {'accepted_name_usage': target_name},
        {'$set': {'NomosID': 987654}},
    )

    with patch('app.routers.records.pdfkit.from_string', return_value=b'%PDF') as pdf_from_string:
        response = client.post('/records/export-species_pdf/', json={
            'data_provider': ['Department of Primary Industries and Regional Development'],
        })

    assert response.status_code == status.HTTP_200_OK
    generated_html = pdf_from_string.call_args.args[0]
    assert '<th style="padding: 10px 3px;">NomosID</th>' in generated_html
    assert '<td style="padding: 3px; border: 1px solid rgb(235,235,235);">987654</td>' in generated_html


def test_export_csv_for_species_occurrence_records(insert_test_records):
    response = client.get('/records/export-csv/', params={
        "data_provider": 'Department of Primary Industries and Regional Development'
    })

    assert response.status_code == status.HTTP_200_OK

    test_csv_file_pointer = open(TEST_EXPORT_CSV_PATH)
    response_csv_file_pointer = io.StringIO(response.content.decode())

    test_csv = csv.reader(test_csv_file_pointer)
    response_csv = csv.reader(response_csv_file_pointer)

    for test_row, response_row in zip(test_csv, response_csv):
        assert test_row == response_row

    test_csv_file_pointer.close()
    response_csv_file_pointer.close()


@pytest.mark.parametrize(
    "authorised_user",
    [
        pytest.param(False, id="public-user"),
        pytest.param(True, id="authorised-user"),
    ],
)
def test_export_csv_for_systematic_survey_records(
    test_settings,
    insert_test_records,
    insert_published_submission_and_submission_set,
    authorised_user,
):
    headers = {}
    if authorised_user:
        headers["x-email"] = "sensitive@test.net"

    response = client.get(
        '/records/export-csv/',
        headers=headers,
        params={
            "project_name": 'South-west Forest Surveys',
        }
    )

    assert response.status_code == status.HTTP_200_OK

    response_csv_file_obj = io.StringIO(response.content.decode())
    response_csv_reader = csv.DictReader(response_csv_file_obj)
    response_rows = list(response_csv_reader)

    assert response_csv_reader.fieldnames == [
        'Record_ID',
        'Data type (dwc:eventType)',
        'Latitude (dwc:decimalLatitude)',
        'Longitude (dwc:decimalLongitude)',
        'Date (dwc:eventDate)',
        'Recorded name (dwc:scientificName)',
        'Accepted name (dwc:acceptedNameUsage)',
        'Data provider (dwc:institutionCode)',
        'Dataset (dcterms:title)',
        'Project name (abis:project)',
        'Project ID (dwc:parentEventID)',
        'Survey name (tern:survey)',
        'Survey ID (dwc:eventID)',
        'Survey participants (dcterms:contributor)',
        'Survey date range start (tern:survey; prov:startedAtTime)',
        'Survey date range end (tern:survey; prov:endedAtTime)',
        'Bounding box (dwc:footprintWKT)',
        'Count (dwc:individualCount)',
        'Rights holder (rightsHolder)',
        'Method/protocol (dwc:samplingProtocol)',
        'Conservation code (threatStatus)',
        'Identification basis (dwc:basisOfRecord)',
        'Field identification (dwc:verbatimIdentification)',
        'Date identified (dwc:dateIdentified)',
        'Identification ambiguity (dwc:identificationQualifier)',
        'Identification notes (dwc:identificationRemarks)',
        'Scientific name publisher (dwc:scientificNameAuthorship)',
        'Taxon rank (dwc:taxonRank)',
        'Organism remarks (dwc:organismRemarks)',
        'Presence/Absence (dwc:occurrenceStatus)',
        'Preparations (dwc:preparations)',
        'Genomic sequence information (dwc:associatedSequences)',
        'Life stage (dwc:lifeStage)',
        'Reproductive condition (dwc:reproductiveCondition)',
        'Native/introduced/feral (dwc:establishmentMeans)',
        'Geographic uncertainty (dwc:coordinateUncertaintyInMeters)',
        'Area/locality (dwc:locality)',
        'Habitat (dwc:habitat)',
        'Vernacular name (dwc:vernacularName)',
        'Informal groups',
        'Kingdom (dwc:kingdom)',
        'Phylum (dwc:phylum)',
        'Class (dwc:class)',
        'Order (dwc:order)',
        'Family (dwc:family)',
    ]

    assert len(response_rows) == (3 if authorised_user else 2)
    # check rows have expected SSD values
    for row in response_rows:
        assert row['Data type (dwc:eventType)'] == 'Systematic survey data'
        assert row['Project name (abis:project)'] == "South-west Forest Surveys"
        assert row['Project ID (dwc:parentEventID)'] == "2024GLOxmeffaf55"
        assert row['Survey name (tern:survey)'] == "Forest Survey Winter 2024"
        assert row['Survey ID (dwc:eventID)'] == "2024FRPLddad39c2"
        assert row['Survey participants (dcterms:contributor)'] == "One,Two,Three"
        assert row['Survey date range start (tern:survey; prov:startedAtTime)'] == "2024-01-01"
        assert row['Survey date range end (tern:survey; prov:endedAtTime)'] == "2024-01-30"
        assert row['Bounding box (dwc:footprintWKT)'] == (
            "POLYGON ((30.0 -40.0, 30.0 -45.0, 35.0 -45.0, 35.0 -40.0, 30.0 -40.0))"
            if authorised_user
            else ""
        )


def test_record_list_datatype_export_format():
    """
    This test explicitly tests ticket 6190: Dandjoo public export - add semi colon as a delimiter

    Tests the function to change the data type from a list of strings,
    to a string with a semicolon delimiter.
    """
    value = ['list', 'of', 'vernacular', 'names']

    formatted_value = convert_lists_for_csv_export(value)

    assert formatted_value == "list; of; vernacular; names"


def test_export_shp_for_species_occurrence_records(insert_test_records):
    response = client.get('/records/export-shp/', params={
        "data_provider": 'Department of Primary Industries and Regional Development'
    })

    assert response.status_code == status.HTTP_200_OK

    # load in test shapefile
    test_shp_reader = shapefile.Reader(TEST_EXPORT_ZIP_PATH)
    # load in response shapefile from zip
    response_zipped_shapefile = zipfile.ZipFile(io.BytesIO(response.content))

    assert len(response_zipped_shapefile.namelist()) == 3

    response_file_streams = {file_type: io.BytesIO() for file_type in ['shp', 'shx', 'dbf']}

    # load in-memory zip-file components into respective byte streams
    for filename in response_zipped_shapefile.namelist():
        file_type = os.path.splitext(filename)[1][1:]
        response_file_streams[file_type].write(response_zipped_shapefile.read(filename))

    response_shp_reader = shapefile.Reader(**response_file_streams)

    # compare test and response shapefile shapes and records
    assert response_shp_reader.shapeType == test_shp_reader.shapeType
    assert response_shp_reader.numShapes == test_shp_reader.numShapes
    assert response_shp_reader.numRecords == test_shp_reader.numRecords

    for response_shape, test_shape in zip(response_shp_reader.shapes(), test_shp_reader.shapes()):
        assert response_shape.points == test_shape.points

    for response_record, test_record in zip(response_shp_reader.records(), test_shp_reader.records()):
        assert response_record == test_record

    # tidy up various files and streams (io.BytesIO streams are closed by zip/shapefile readers)
    response_zipped_shapefile.close()
    test_shp_reader.close()
    response_shp_reader.close()


@pytest.mark.parametrize(
    "authorised_user",
    [
        pytest.param(False, id="public-user"),
        pytest.param(True, id="authorised-user"),
    ],
)
def test_export_shp_for_systematic_survey_records(
    test_settings,
    insert_test_records,
    insert_published_submission_and_submission_set,
    authorised_user,
    tmp_path,
):
    headers = {}
    if authorised_user:
        headers["x-email"] = "sensitive@test.net"

    response = client.get(
        '/records/export-shp/',
        headers=headers,
        params={
            "species": 'Made up name for SSD record',
        },
    )
    assert response.status_code == status.HTTP_200_OK

    # load in response shapefile from zip
    response_tmp_file = tmp_path / "response_shapefile.zip"
    response_tmp_file.write_bytes(response.content)
    response_shp_reader = shapefile.Reader(response_tmp_file)

    # Check response shapefile shapes and records
    assert response_shp_reader.shapeType == shapefile.POINT
    response_shapes = response_shp_reader.shapes()
    assert response_shp_reader.numShapes == len(response_shapes) == 1
    response_records = response_shp_reader.records()
    assert response_shp_reader.numRecords == len(response_records) == 1

    assert response_shapes[0].shapeType == shapefile.POINT
    assert len(response_shapes[0].points) == 1
    assert response_shapes[0].points[0][0] == pytest.approx(124.3647)
    assert response_shapes[0].points[0][1] == pytest.approx(-33.8463)

    assert response_shp_reader.fields[0] == ('DeletionFlag', 'C', 1, 0)
    dandjoo_export_fields = response_shp_reader.fields[1:]
    assert len(dandjoo_export_fields) == len(response_records[0])
    # check fields along with value for each field
    assert list(zip(dandjoo_export_fields, response_records[0])) == [
        (['Record_ID', 'C', 50, 0],   "2024FRRDt1d05e52"),
        (['Data_type', 'C', 50, 0],   "Systematic survey data"),
        (['Latitude', 'C', 50, 0],    "-33.8463"),
        (['Longitude', 'C', 50, 0],   "124.3647"),
        (['Date', 'C', 50, 0],        "2009-05-21T00:00:00+08:00"),
        (['Kingdom', 'C', 50, 0],     "Animalia"),
        (['Rcrdd_name', 'C', 50, 0],  "Made up name for SSD record"),
        (['Acptd_name', 'C', 50, 0],  "Made up name for SSD record"),
        (['Data_prvdr', 'C', 50, 0],  "WA Museum"),
        (['Dataset', 'C', 50, 0],     ""),
        (['Prjct_name', 'C', 50, 0],  "South-west Forest Surveys"),
        (['Prjct_ID', 'C', 50, 0],    "2024GLOxmeffaf55"),
        (['Srvy_name', 'C', 50, 0],   "Forest Survey Winter 2024"),
        (['Srvy_ID', 'C', 50, 0],     "2024FRPLddad39c2"),
        (['Srvy_prtcp', 'C', 50, 0],  "One,Two,Three"),
        (['Srvy_start', 'C', 50, 0],  "2024-01-01"),
        (['Srvy_end', 'C', 50, 0],    "2024-01-30"),
        (['Srvy_bbox', 'C', 125, 0],
         ("POLYGON ((30.0 -40.0, 30.0 -45.0, 35.0 -45.0, 35.0 -40.0, 30.0 -40.0))"
          if authorised_user else "")),
        (['Count', 'C', 50, 0],       ""),
        (['Rghts_hldr', 'C', 50, 0],  ""),
        (['Method', 'C', 50, 0],      ""),
        (['Csvtn_code', 'C', 50, 0],  ""),
        (['ID_basis', 'C', 50, 0],    ""),
        (['Field_ID', 'C', 50, 0],    ""),
        (['Date_IDed', 'C', 50, 0],   ""),
        (['ID_ambgty', 'C', 50, 0],   ""),
        (['ID_notes', 'C', 50, 0],    ""),
        (['Name_pblsh', 'C', 50, 0],  ""),
        (['Taxon_rank', 'C', 50, 0],  ""),
        (['Orgnsm_rem', 'C', 50, 0],  ""),
        (['Pres_Abs', 'C', 50, 0],    ""),
        (['Preprtn', 'C', 50, 0],     ""),
        (['Genome_seq', 'C', 50, 0],  ""),
        (['Life_stage', 'C', 50, 0],  ""),
        (['Repr_Condt', 'C', 50, 0],  ""),
        (['Native_fer', 'C', 50, 0],  ""),
        (['Geo_uncert', 'C', 50, 0],  ""),
        (['Area_local', 'C', 50, 0],  ""),
        (['Habitat', 'C', 50, 0],     ""),
    ]

    response_shp_reader.close()


def test_export_geojson_for_species_occurrence_records(test_settings, insert_test_records):
    record_collection = get_record_collection(test_settings)

    response = client.get(
        '/records/export-geojson/',
        params={
            "data_provider": 'Department of Primary Industries and Regional Development',
        }
    )
    result = response.json()

    assert len(result['features']) == 13

    # test all features have expected attributes
    for feature in result['features']:
        assert set(feature['properties'].keys()) == {
            'id',
            "datatype",
            'date',
            'recorded_species',
            'kingdom',
            'species',
            'dataset',
            'data_provider',
            'conservation_status',
            'project_id',
            'project_name',
            'survey_id',
            'survey_name',
            'survey_participants',
            'survey_date_range_end',
            'survey_date_range_start',
            'survey_bounding_box',
        }

    # test all features have certain attributes from Record
    for feature in result['features']:
        raw_record = record_collection.find_one(
            {'persistent_id': feature['properties']['id']},
        )
        assert raw_record is not None
        record = Record(**raw_record)

        assert feature['geometry'] == record.location
        assert feature['properties']['id'] == record.persistent_id
        assert feature['properties']['datatype'] == record.logical_datatype
        assert feature['properties']['date'] == record.event_date
        assert feature['properties']['recorded_species'] == record.scientific_name
        assert feature['properties']['kingdom'] == record.kingdom
        assert feature['properties']['species'] == record.accepted_name_usage
        assert feature['properties']['data_provider'] == record.institution_code
        assert feature['properties']['conservation_status'] == record.threat_status
        assert feature['properties']['dataset'] == record.dcterms_title

        assert feature['properties']['project_name'] is None
        assert feature['properties']['project_id'] is None
        assert feature['properties']['survey_name'] is None
        assert feature['properties']['survey_id'] is None
        assert feature['properties']['survey_participants'] is None
        assert feature['properties']['survey_date_range_start'] is None
        assert feature['properties']['survey_date_range_end'] is None
        assert feature['properties']['survey_bounding_box'] is None


@pytest.mark.parametrize(
    "authorised_user",
    [
        pytest.param(False, id="public-user"),
        pytest.param(True, id="authorised-user"),
    ],
)
def test_export_geojson_for_systematic_survey_records(
    test_settings,
    insert_test_records,
    insert_published_submission_and_submission_set,
    authorised_user,
):
    record_collection = get_record_collection(test_settings)

    headers = {}
    if authorised_user:
        headers["x-email"] = "sensitive@test.net"

    response = client.get(
        '/records/export-geojson/',
        headers=headers,
        params={
            "project_name": 'South-west Forest Surveys',
        }
    )
    result = response.json()

    assert len(result['features']) == (3 if authorised_user else 2)

    # test all features have expected attributes
    for feature in result['features']:
        assert set(feature['properties'].keys()) == {
            'id',
            "datatype",
            'date',
            'recorded_species',
            'kingdom',
            'species',
            'dataset',
            'data_provider',
            'conservation_status',
            'project_id',
            'project_name',
            'survey_id',
            'survey_name',
            'survey_participants',
            'survey_date_range_end',
            'survey_date_range_start',
            'survey_bounding_box',
        }

    # test all features have certain attributes from Record
    for feature in result['features']:
        raw_record = record_collection.find_one(
            {'persistent_id': feature['properties']['id']},
        )
        assert raw_record is not None
        record = Record(**raw_record)

        assert feature['geometry'] == record.location
        assert feature['properties']['id'] == record.persistent_id
        assert feature['properties']['datatype'] == record.logical_datatype
        assert feature['properties']['date'] == record.event_date
        assert feature['properties']['recorded_species'] == record.scientific_name
        assert feature['properties']['kingdom'] == record.kingdom
        assert feature['properties']['species'] == record.accepted_name_usage
        assert feature['properties']['data_provider'] == record.institution_code
        assert feature['properties']['conservation_status'] == record.threat_status
        assert feature['properties']['dataset'] == record.dcterms_title

        assert feature['properties']['project_name'] == "South-west Forest Surveys"
        assert feature['properties']['project_id'] == "2024GLOxmeffaf55"
        assert feature['properties']['survey_name'] == "Forest Survey Winter 2024"
        assert feature['properties']['survey_id'] == "2024FRPLddad39c2"
        assert feature['properties']['survey_participants'] == "One,Two,Three"
        assert feature['properties']['survey_date_range_start'] == "2024-01-01"
        assert feature['properties']['survey_date_range_end'] == "2024-01-30"
        if not authorised_user:
            assert feature['properties']['survey_bounding_box'] is None
        else:
            assert feature['properties']['survey_bounding_box'] == {
                'type': 'Polygon',
                'coordinates': [[[30.0, -40.0],
                                 [30.0, -45.0],
                                 [35.0, -45.0],
                                 [35.0, -40.0],
                                 [30.0, -40.0]]],
            }
