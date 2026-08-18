"""
This test validates species_list implementation and obfuscated bounding box interactions with mongo $geoIntersects searches

Four data points are inserted into the database, with varying locations, species, and threat statuses, as shown here:
[
{species: Type_A, location: Loc_A, threat_status: Status_A},
{species: Type_A, location: Loc_B, threat_status: Status_A},
{species: Type_B, location: Loc_B, threat_status: Status_None},
{species: Type_B, location: Loc_C, threat_status: Status_None}
]

Part 1 of the test uses the common location 'Loc_B' to test multiple variations of search boxes to confirm the
threatened species bounding box is selected when a search area intersects a bounding box.

Part 2 of the test uses overlapping locations to confirm the species list returns the correct number of entries
when multiple data points are included in the search area.


The following is a standalone helper utility used during creation of the test points to visually validate locations.

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Coordinates of the "b_box" square
b_box = [[127.7, -19.2], [127.8, -19.2], [127.8, -19.1], [127.7, -19.1], [127.7, -19.2]]

# Coordinates of search boxes, using counterclockwise winding
search_boxes = [
    [[127.75, -19.19], [127.7, -19.3], [127.8, -19.3], [127.75, -19.19]],
    [[127.71, -19.15], [127.6, -19.1], [127.6, -19.2], [127.71, -19.15]]
    ]

# Extracting x and y coordinates from the square
b_box_x = [point[0] for point in b_box]
b_box_y = [point[1] for point in b_box]

# Plot the square
plt.plot(b_box_x, b_box_y, 'b-', label='b_box square')

# Plot each box
for idx, box in enumerate(search_boxes):
    box_x = [point[0] for point in box]
    box_y = [point[1] for point in box]
    plt.plot(box_x + [box_x[0]], box_y + [box_y[0]], 'r-')

    # Annotate each corner with the point number (1, 2, 3, etc)
    # to confirm counterclockwise winding
    for i, point in enumerate(box, 1):
        plt.text(point[0], point[1], str(i), ha='center', va='center', fontsize=12, fontweight='bold')

# Add labels and legend
plt.xlabel('Longitude')
plt.ylabel('Latitude')
plt.legend()

# Format tick labels to have two decimal places
plt.gca().xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))
plt.gca().yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

# Data point to show
wc_point = (127.7950, -19.1719)
swc_point = (127.7017, -19.5656)
nwc_point = (127.9642, -18.8075)


# Plot the data point
plt.plot(wc_point[0], wc_point[1], 'go')
plt.plot(swc_point[0], swc_point[1], 'go')
plt.plot(nwc_point[0], nwc_point[1], 'go')

# Show the plot
plt.grid(True)
plt.show()

"""
import json
import os
from typing import List
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette import status

from app import main
from app.helpers.mongo import get_record_collection
from tests.helpers import mock_authentication


client = TestClient(main.app)


@pytest.fixture(scope='module', autouse=True)
def is_authorised_mock():
    "This will use the mock is_authorised for all test functions"
    with patch('app.helpers.record_search.is_authorised', mock_authentication.is_authorised) as _fixture:
        yield _fixture


@pytest.fixture(scope='module')
def test_record_data():
    with open(os.path.join(os.path.dirname(__file__), 'test-data', 'delivery', 'bulk-threatened-records.json')) as file:
        test_records = json.load(file)
    for record in test_records:
        if record.get("dwc:scientificName") == "Anas castanea":
            record["dwc:threatStatus"] = None
    return test_records


@pytest.fixture(scope='function')
def insert_test_record_data(test_record_data) -> None:
    """ Populate the test DB with fake data records"""
    response = client.post('/records/bulk-upload/', json=test_record_data, headers={'x-api-key': 'test_password'})
    assert response.status_code == status.HTTP_200_OK


def test_database(get_test_settings, insert_test_record_data):
    with open(os.path.join(os.path.dirname(__file__), 'test-data', 'delivery', 'bulk-threatened-records.json')) as file:
        test_records = json.load(file)

    records_collection = get_record_collection(get_test_settings())
    count = records_collection.count_documents({})
    assert(count == len(test_records))
    assert records_collection.count_documents({'obfuscated_location': {'$exists': True, '$ne': None}}) == 2

# values for manipulating tests
# locations for records in the bulk-threatened-records.json
loc_wc = {
    "raw": {"lat": -19.1719, "lon": 127.7950},
    "obfuscated": {"lat": -19.2, "lon": 127.7},
    "b_box": [[127.7, -19.2], [127.8, -19.2], [127.8, -19.1], [127.7, -19.1], [127.7, -19.2]],
}

loc_swc = {
    "raw": {"lat": -19.5656, "lon": 127.7017},
    "obfuscated": {"lat": -19.6, "lon": 127.7},
    "b_box": [[127.7, -19.6], [127.8, -19.6], [127.8, -19.5], [127.7, -19.5], [127.7, -19.6]]
}

loc_nwc = {
    "raw": {"lat": -18.8075, "lon": 127.9642},
    "obfuscated": {"lat": -18.9, "lon": 127.9},
    "b_box": [[127.9, -18.9], [128.0, -18.9], [128.0, -18.8], [127.9, -18.8], [127.9, -18.9]]
}

# linking locations to ids for test records
record_1 = {"id": "2022GPEBgbcd8c56", "loc": loc_wc, "name": "Anas castanea"}
record_2 = {"id": "2022GPEBgbcef78a", "loc": loc_swc, "name": "Anas castanea"}
record_3 = {"id": "2022GPEBgc458d76", "loc": loc_wc, "name": "Himantopus himantopus"}
record_4 = {"id": "2022GPEBgc474c67", "loc": loc_nwc, "name": "Himantopus himantopus"}

# Geojson polygons for testing bounding boxes with location searches

# polygons that overlap with the b_box. small overlap area through the side,
# does not overlap with corner gps point, does not include the raw point
wc_bbox_side_intersections = [
    [[127.75, -19.19], [127.7, -19.3], [127.8, -19.3], [127.75, -19.19]],
    [[127.71, -19.15], [127.6, -19.1], [127.6, -19.2], [127.71, -19.15]],
    [[127.75, -19.11], [127.8, -19.0], [127.7, -19.0], [127.75, -19.11]],
    [[127.79, -19.15], [127.9, -19.2], [127.9, -19.1], [127.79, -19.15]]]

# polygons that overlap with the b_box. small overlap area with a corner gps point, does not include the raw point
wc_bbox_corner_intersections = [
    [[127.6, -19.3], [127.71, -19.3], [127.71, -19.19], [127.6, -19.19], [127.6, -19.3]],
    [[127.6, -19], [127.6, -19.11], [127.71, -19.11], [127.71, -19], [127.6, -19]],
    [[127.79, -19.11], [127.9, -19.11], [127.9, -19], [127.79, -19], [127.79, -19.11]],
    [[127.79, -19.3], [127.9, -19.3], [127.9, -19.19], [127.79, -19.19], [127.79, -19.3]]
]

# polygons that overlap with the b_box. large overlap area, does not include the raw point.
wc_bbox_overlap_exclude = [
    [[127.6, -19], [127.6, -19.2], [127.78, -19.2], [127.78, -19], [127.6, -19]],
    [[127.6, -19.1], [127.6, -19.3], [127.78, -19.3], [127.78, -19.1], [127.6, -19.1]]
]

# polygons that overlap with the b_box. large overlap area, includes the raw point.
wc_bbox_overlap_include = [
    [[127.71, -19], [127.71, -19.2], [127.9, -19.2], [127.9, -19], [127.71, -19]],
    [[127.71, -19.1], [127.71, -19.3], [127.9, -19.3], [127.9, -19.1], [127.71, -19.1]],
    [[127.6, -19], [127.6, -19.3], [127.9, -19.3], [127.9, -19], [127.6, -19]]
]

# polygons that do not intersect with or touch the bounding box.
wc_bbox_no_intersection = [
    [[127.6, -19.1], [127.6, -19.2], [127.69, -19.2], [127.69, -19.1], [127.6, -19.1]],
    [[127.7, -19.21], [127.7, -19.3], [127.8, -19.3], [127.8, -19.21], [127.7, -19.21]],
    [[127.81, -19.1], [127.81, -19.2], [127.9, -19.2], [127.9, -19.1], [127.81, -19.1]],
    [[127.7, -19.09], [127.8, -19.09], [127.8, -19], [127.7, -19], [127.7, -19.09]]
]

# polygon that contains raw points for three observations (comprised of two species)
multipoint_overlap = [[127.6, -19.7], [127.9, -19.7], [127.9, -19], [127.6, -19], [127.6, -19.7]]


def get_polygon_search_string(location: List[List[float]]):
    return f'{{"geojson_feature": {{"geometry": {{"type": "Polygon","coordinates": [{json.dumps(location)}]}}}}}}'

# Part 1: Test bounding box interaction with area search and permissions
@pytest.mark.parametrize("search_box",
                         wc_bbox_side_intersections
                         + wc_bbox_corner_intersections
                         + wc_bbox_overlap_exclude)
def test_polygon_search_intersection_with_obfuscation_not_authorised(insert_test_record_data, search_box):
    """ search box touches the bounding box of one obfuscated record but does not contain any specific locations"""
    area_string = get_polygon_search_string(search_box)
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': 'not_authorized@test.net'})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 1


@pytest.mark.parametrize("search_box", wc_bbox_overlap_include)
def test_polygon_search_overlap_with_obfuscation_not_authorised(insert_test_record_data, search_box):
    """ search box contains the specific location of two records, one threatened and one not threatened"""
    area_string = get_polygon_search_string(search_box)
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': 'not_authorized@test.net'})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 2


@pytest.mark.parametrize("search_box",
                         wc_bbox_side_intersections
                         + wc_bbox_corner_intersections
                         + wc_bbox_overlap_exclude)
def test_polygon_search_intersection_with_obfuscation_authorised(insert_test_record_data, search_box):
    """ search box touches the bounding box of one obfuscated record but does not contain any specific locations"""
    area_string = get_polygon_search_string(search_box)
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': 'sensitive@test.net'})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 0


@pytest.mark.parametrize("search_box", wc_bbox_overlap_include)
def test_polygon_search_overlap_with_obfuscation_authorised(insert_test_record_data, search_box):
    """ search box contains the specific location of two records, one threatened and one not threatened"""
    area_string = get_polygon_search_string(search_box)
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': 'sensitive@test.net'})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 2


# Part 2: Test species list entries with multiple observations in search area
@pytest.mark.parametrize("auth", ['sensitive@test.net', 'not_authorized@test.net'])
def test_polygon_search_multiple_observations(insert_test_record_data, auth: str):
    """ validates that the species list has one entry per species regardless of the number of observations """
    area_string = get_polygon_search_string(multipoint_overlap)
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': auth})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 2


@pytest.mark.parametrize("auth", ['sensitive@test.net', 'not_authorized@test.net'])
def test_circle_search_multiple_observations(insert_test_record_data, auth: str):
    """ validates that the species list has one entry per species regardless of the number of observations """
    area_string = f'{{"radius": 50000, "geojson_feature": {{"geometry": {{"type": "Point", "coordinates": [{loc_wc["raw"]["lon"]}, {loc_wc["raw"]["lat"]}]}}}}}}'
    response = client.get('/records/species_list/',
                          params={'json_encoded_area': area_string},
                          headers={'x-email': auth})

    assert response.status_code == 200
    assert len(response.json()['species_list']) == 2

