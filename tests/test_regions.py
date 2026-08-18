import os
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import main
from app.helpers.mongo import get_region_collection


client = TestClient(main.app)

with open(os.path.join(os.path.dirname(__file__), 'test-data', 'delivery', 'regions.json')) as file:
    test_regions = json.load(file)

@pytest.fixture(scope="function", autouse=True)
def cleanup_database(get_test_settings) -> None:
    """
    Autouse fixture to ensure each test starts with an empty collection

    Other autouse fixtures that create DB content should request this one, to ensure that they run after this.
    """
    pass

@pytest.fixture(scope="session")
def insert_test_regions(get_test_settings):
    regions_collection = get_region_collection(get_test_settings())
    regions_collection.insert_many(test_regions)
    # FIXES cannot query search index while in state INITIAL_SYNC
    time.sleep(2)


def test_region_lookup(insert_test_regions):
    place_name = 'Wooroloo'
    response = client.get(f"/regions?search={place_name}")
    response_json = response.json()
    results = response_json['results']
    assert (response_json['total'] == len(results))

    for result in results:
        assert place_name.lower() in result['name'].lower()


def test_region_get(insert_test_regions):
    place_name = 'Herdsman Lake'
    response = client.get(f"/regions?search={place_name}")
    results = response.json()['results']
    for result in results:
        if result['name'] == "Herdsman Lake (DBCA Regional Parks)":
            id = result['id']
            break
    assert id

    region_response = client.get(f"/region?_id={id}")
    region_response_json = region_response.json()

    assert region_response_json == test_regions[0]['geojson']
