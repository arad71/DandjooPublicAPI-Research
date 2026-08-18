import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi import status

from app import main
from app.helpers.mongo import get_lookup_taxon_collection
from tests.helpers import mock_authentication


client = TestClient(main.app)


@pytest.fixture(scope="module", autouse=True)
def is_authorised_mock():
    """This will use the mock is_authorised for all test functions"""
    with patch(
        "app.routers.records.is_authorised", mock_authentication.is_authorised
    ) as _fixture:
        yield _fixture


@pytest.fixture(scope="function", autouse=True)
def cleanup_database(get_test_settings) -> None:
    """
    Autouse fixture to ensure each test starts with an empty collection

    Other autouse fixtures that create DB content should request this one, to ensure that they run after this.
    """
    pass


@pytest.fixture(scope="session")
def insert_test_taxonomic_data(get_test_settings):
    """Insert a broader set of taxonomic data into the database for testing."""
    test_settings = get_test_settings()
    taxon_autocomplete_collection = get_lookup_taxon_collection(test_settings)

    test_records = [
        # Kingdoms
        {
            "value": "Animalia",
            "field": "kingdom",
            "phylum": None,
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Plantae",
            "field": "kingdom",
            "phylum": None,
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Fungi",
            "field": "kingdom",
            "phylum": None,
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        # Phylum
        {
            "value": "Chordata",
            "field": "phylum",
            "kingdom": "Animalia",
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Arthropoda",
            "field": "phylum",
            "kingdom": "Animalia",
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Bryophyta",
            "field": "phylum",
            "kingdom": "Plantae",
            "class_": None,
            "order": None,
            "family": None,
            "species": None,
        },
        # Classes
        {
            "value": "Mammalia",
            "field": "class_",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Insecta",
            "field": "class_",
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "order": None,
            "family": None,
            "species": None,
        },
        {
            "value": "Musci",
            "field": "class_",
            "kingdom": "Plantae",
            "phylum": "Bryophyta",
            "order": None,
            "family": None,
            "species": None,
        },
        # Orders
        {
            "value": "Primates",
            "field": "order",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "class_": "Mammalia",
            "family": None,
            "species": None,
        },
        {
            "value": "Diptera",
            "field": "order",
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "class_": "Insecta",
            "family": None,
            "species": None,
        },
        # Families
        {
            "value": "Hominidae",
            "field": "family",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "class_": "Mammalia",
            "order": "Primates",
            "species": None,
        },
        {
            "value": "Drosophilidae",
            "field": "family",
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "class_": "Insecta",
            "order": "Diptera",
            "species": None,
        },
        # Species
        {
            "value": "Homo sapiens",
            "field": "species",
            "kingdom": "Animalia",
            "phylum": "Chordata",
            "class_": "Mammalia",
            "order": "Primates",
            "family": "Hominidae",
        },
        {
            "value": "Drosophila melanogaster",
            "field": "species",
            "kingdom": "Animalia",
            "phylum": "Arthropoda",
            "class_": "Insecta",
            "order": "Diptera",
            "family": "Drosophilidae",
        },
    ]

    taxon_autocomplete_collection.insert_many(test_records)
    # FIXES cannot query search index while in state INITIAL_SYNC
    time.sleep(2)


def test_phylum_list_no_filters(insert_test_taxonomic_data):
    """Test getting phylum/division list without any filters"""
    response = client.get("/records/phylum")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    # print(response_json)
    # taxon_autocomplete_collection = get_taxon_autocomplete_collection(test_settings)
    # print(taxon_autocomplete_collection.find().to_list())

    # Should return all unique phyla across all kingdoms
    assert response_json["total"] == 3
    assert set(response_json["results"]) == {
        "Chordata",
        "Arthropoda",
        "Bryophyta",
    }


def test_phylum_list_with_search(insert_test_taxonomic_data):
    """Test getting phylum/division list with search term"""
    response = client.get("/records/phylum", params={"search": "chor"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Chordata"]


def test_phylum_list_with_kingdom_filter(insert_test_taxonomic_data):
    """Test getting phylum/division list filtered by kingdom"""
    response = client.get("/records/phylum", params={"kingdoms": "Animalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()
    print(response_json)

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Chordata", "Arthropoda"}


def test_phylum_list_with_multiple_kingdoms(insert_test_taxonomic_data):
    """Test getting phylum/division list filtered by multiple kingdoms"""
    response = client.get(
        "/records/phylum", params={"kingdoms": ["Animalia", "Plantae"]}
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 3
    assert set(response_json["results"]) == {
        "Chordata",
        "Arthropoda",
        "Bryophyta",
    }


def test_phylum_list_with_search_and_kingdom(insert_test_taxonomic_data):
    """Test getting phylum/division list with both search term and kingdom filter"""
    response = client.get(
        "/records/phylum", params={"search": "Chor", "kingdoms": "Animalia"}
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Chordata"]


def test_phylum_list_no_results(insert_test_taxonomic_data):
    """Test getting phylum/division list with filters that return no results"""
    response = client.get(
        "/records/phylum", params={"search": "NonExistent", "kingdoms": "Animalia"}
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 0
    assert response_json["results"] == []


def test_class_list_no_filters(insert_test_taxonomic_data):
    """Test getting class list without any filters"""
    response = client.get("/records/class")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    # Should return all unique classes across all kingdoms and phyla
    assert response_json["total"] == 3
    assert set(response_json["results"]) == {
        "Musci",
        "Mammalia",
        "Insecta",
    }


def test_class_list_with_search(insert_test_taxonomic_data):
    """Test getting class list with search term"""
    response = client.get("/records/class", params={"search": "Mam"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Mammalia"]


def test_class_list_with_kingdom_filter(insert_test_taxonomic_data):
    """Test getting class list filtered by kingdom"""
    response = client.get("/records/class", params={"kingdoms": "Plantae"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert set(response_json["results"]) == {"Musci"}


def test_class_list_with_phylum_filter(insert_test_taxonomic_data):
    """Test getting class list filtered by phylum"""
    response = client.get("/records/class", params={"phylum": "Chordata"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert set(response_json["results"]) == {"Mammalia"}


def test_class_list_with_kingdom_and_phylum(insert_test_taxonomic_data):
    """Test getting class list filtered by both kingdom and phylum"""
    response = client.get(
        "/records/class", params={"kingdoms": "Plantae", "phylum": "Chordata"}
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Mammalia", "Musci"}


def test_class_list_with_all_filters(insert_test_taxonomic_data):
    """Test getting class list with search term, kingdom and phylum filters"""
    response = client.get(
        "/records/class",
        params={"search": "Mam", "kingdoms": "Animalia", "phylum": "Chordata"},
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Mammalia"]


def test_class_list_case_insensitive_search(insert_test_taxonomic_data):
    """Test that class list search is case insensitive"""
    response = client.get("/records/class", params={"search": "mammalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Mammalia"]


def test_order_list_no_filters(insert_test_taxonomic_data):
    """Test getting order list without any filters"""
    response = client.get("/records/order")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    # Should return all unique orders across all kingdoms, phyla and classes
    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Primates", "Diptera"}


def test_order_list_with_search(insert_test_taxonomic_data):
    """Test getting order list with search term"""
    response = client.get("/records/order", params={"search": "Dip"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Diptera"]


def test_order_list_with_kingdom_filter(insert_test_taxonomic_data):
    """Test getting order list filtered by kingdom"""
    response = client.get("/records/order", params={"kingdoms": "Animalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Primates", "Diptera"}


def test_order_list_with_phylum_filter(insert_test_taxonomic_data):
    """Test getting order list filtered by phylum"""
    response = client.get("/records/order", params={"phylum": "Chordata"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Primates"]


def test_order_list_with_class_filter(insert_test_taxonomic_data):
    """Test getting order list filtered by class"""
    response = client.get("/records/order", params={"class": "Mammalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Primates"]


def test_order_list_with_all_filters(insert_test_taxonomic_data):
    """Test getting order list with all filters"""
    response = client.get(
        "/records/order",
        params={
            "search": "Prima",
            "kingdoms": "Animalia",
            "phylum": "Chordata",
            "class": "Arthropoda",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Primates"]


def test_order_list_with_multiple_phylum(insert_test_taxonomic_data):
    """Test getting order list filtered by multiple kingdoms"""
    response = client.get(
        "/records/order", params={"phylum": ["Chordata", "Arthropoda"]}
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Primates", "Diptera"}


def test_family_list_no_filters(insert_test_taxonomic_data):
    """Test getting family list without any filters"""
    response = client.get("/records/family")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    # Should return all unique families across all taxonomic levels
    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Drosophilidae", "Hominidae"}


def test_family_list_with_search(insert_test_taxonomic_data):
    """Test getting family list with search term"""
    response = client.get("/records/family", params={"search": "Homin"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Hominidae"]


def test_family_list_with_kingdom_filter(insert_test_taxonomic_data):
    """Test getting family list filtered by kingdom"""
    response = client.get("/records/family", params={"kingdoms": "Animalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Drosophilidae", "Hominidae"}


def test_family_list_with_phylum_filter(insert_test_taxonomic_data):
    """Test getting family list filtered by phylum"""
    response = client.get("/records/family", params={"phylum": "Arthropoda"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == [ "Drosophilidae" ]


def test_family_list_with_class_filter(insert_test_taxonomic_data):
    """Test getting family list filtered by class"""
    response = client.get("/records/family", params={"class": "Insecta"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Drosophilidae"]


def test_family_list_with_order_filter(insert_test_taxonomic_data):
    """Test getting family list filtered by order"""
    response = client.get("/records/family", params={"order": "Diptera"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Drosophilidae"]


def test_family_list_with_all_filters(insert_test_taxonomic_data):
    """Test getting family list with all filters"""
    response = client.get(
        "/records/family",
        params={
            "search": "Homin",
            "kingdoms": "Animalia",
            "phylum": "Arthropoda",
            "class": "Mammalia",
            "order": "Primates",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Hominidae"]


def test_family_list_with_multiple_filters(insert_test_taxonomic_data):
    """Test getting family list with multiple filter values"""
    response = client.get(
        "/records/family",
        params={"order": ["Primates", "Diptera"]},
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {"Drosophilidae", "Hominidae"}

def test_species_list_no_filters(insert_test_taxonomic_data):
    """Test getting species list without any filters"""
    response = client.get("/records/species")

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {
        "Homo sapiens",
        "Drosophila melanogaster",
    }


def test_species_list_with_search(insert_test_taxonomic_data):
    """Test getting species list with search term"""
    response = client.get("/records/species", params={"search": "Homo"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Homo sapiens"]


def test_species_list_with_kingdom_filter(insert_test_taxonomic_data):
    """Test getting species list filtered by kingdom"""
    response = client.get("/records/species", params={"kingdoms": "Animalia"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 2
    assert set(response_json["results"]) == {
        "Homo sapiens",
        "Drosophila melanogaster",
    }


def test_species_list_with_phylum_filter(insert_test_taxonomic_data):
    """Test getting species list filtered by phylum"""
    response = client.get("/records/species", params={"phylum": "Chordata"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Homo sapiens"]


def test_species_list_with_class_filter(insert_test_taxonomic_data):
    """Test getting species list filtered by class"""
    response = client.get("/records/species", params={"class": "Insecta"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Drosophila melanogaster"]


def test_species_list_with_order_filter(insert_test_taxonomic_data):
    """Test getting species list filtered by order"""
    response = client.get("/records/species", params={"order": "Diptera"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Drosophila melanogaster"]


def test_species_list_with_family_filter(insert_test_taxonomic_data):
    """Test getting species list filtered by family"""
    response = client.get("/records/species", params={"family": "Hominidae"})

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Homo sapiens"]


def test_species_list_with_all_filters(insert_test_taxonomic_data):
    """Test getting species list with all filters"""
    response = client.get(
        "/records/species",
        params={
            "search": "melano",
            "kingdoms": "Animalia",
            "phylum": "Arthropoda",
            "class": "Insecta",
            "order": "Diptera",
            "family": "Drosophilidae",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 1
    assert response_json["results"] == ["Drosophila melanogaster"]


def test_species_list_with_no_results(insert_test_taxonomic_data):
    """Test species list with filters returning no results"""
    response = client.get(
        "/records/species",
        params={"search": "xyz", "kingdoms": "Fungi"},
    )

    assert response.status_code == status.HTTP_200_OK
    response_json = response.json()

    assert response_json["total"] == 0
    assert response_json["results"] == []
