"""
The autouse fixtures here will together, ensure that each test starts with an
empty database with unique indexes present, and an empty temp_file_storage_path directory.
This is important to isolate each test from the others, regardless of if tests are run individually or all at once.

The fixtures do not tear down / drop the databases or directories after the test finishes,
to enable debugging a test by inspecting what is left after.

For information about fixtures and how they work see
https://docs.pytest.org/en/stable/explanation/fixtures.html
https://docs.pytest.org/en/stable/how-to/fixtures.html
"""

import os
from typing import Iterator, Callable

from pymongo.operations import SearchIndexModel
import pytest
import responses

from app.dependencies import get_settings
from app.helpers.mongo import get_mongo_client
from app.main import app
from app.settings import Settings


def pytest_configure(config):
    config.addinivalue_line("markers", "no_db: test does not require MongoDB setup")


# # # ----------- SETTINGS FIXTURES ----------- # # #


@pytest.fixture(scope="session", autouse=True)
def get_test_settings() -> Iterator[Callable[[], Settings]]:
    """
    Auto-use session-level fixture to override the get_settings FastAPI dependency.

    Returns the test version of get_settings function that can be called to get the settings.
    """
    # define test version of get_settings
    def _get_test_settings() -> Settings:
        return Settings(
            db_name='test',
            # Not a real url. Any test that attempts to reach Curation needs to use the "responses" library
            # to register mock responses to the Curation endpoints it uses.
            dandjoo_curation_api_url="http://mock-curation.localhost/api/v1/",
        )

    # override FastAPI dependency
    app.dependency_overrides[get_settings] = _get_test_settings

    # return function so other fixtures or individual tests can get the test settings
    yield _get_test_settings

    # remove the override on teardown
    app.dependency_overrides.pop(get_settings)


@pytest.fixture(scope="function")
def test_settings(
    get_test_settings,
    # Depend on other fixtures that modify env vars,
    # so those changes are included in the settings object this returns.
    setup_temp_file_storage_path,
    setup_api_password,
) -> Settings:
    """
    Fixture to shortcut getting the test settings object.

    Note that changes made to settings in `os.environ` after this fixture is requested,
    will not be reflected in the returned settings object.
    Call get_test_settings() again after making the changes to `os.environ` to pick up the changes.
    """
    return get_test_settings()


# # # ----------- DATABASE FIXTURES ----------- # # #

@pytest.fixture(scope="session", autouse=True)
def setup_database(get_test_settings, request) -> None:
    """
    Autouse fixture to ensure each session starts with an empty database, with unique indexes present.

    Unique indexes are important to have for tests, since they change the behavior of the database.

    Other autouse fixtures that create DB content should request this one, to ensure that they run after this.
    """
    if request.session.items and all(
        item.get_closest_marker("no_db") for item in request.session.items
    ):
        return

    test_settings = get_test_settings()
    client = get_mongo_client(test_settings)
    # drop DB and recreate so each test starts with a clean slate
    client.drop_database(test_settings.db_name)
    database = client[test_settings.db_name]

    # Create unique indexes that change DB behavior.
    # These should be kept in sync with scripts/setup_mongo_collections.py
    submissions = database['submissions']
    submissions.create_index("persistent_id", unique=True, sparse=True)
    submission_sets = database['submission_sets']
    submission_sets.create_index("persistent_id", unique=True)
    published_submissions = database['published_submissions']
    published_submissions.create_index("persistent_id", unique=True)
    published_submission_sets = database['published_submission_sets']
    published_submission_sets.create_index("persistent_id", unique=True)


    taxon_autocomplete = database.create_collection("lookup_taxon")

    search_index_model = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "phylum": {
                        "type": "string",
                    },
                    "field": {
                        "type": "string",
                    },
                    "species": {
                        "type": "string",
                    },
                    "class_": {
                        "type": "string",
                    },
                    "order": {
                        "type": "string",
                    },
                    "family": {
                        "type": "string",
                    },
                    "kingdom": {
                        "type": "string",
                    },
                    "value": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        {
                            "type": "string",
                        },
                    ],
                },
            }
        },
        name="default",
    )

    taxon_autocomplete.create_search_index(model=search_index_model)


    region_search_index_model = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        {
                            "type": "string",
                        },
                    ],
                },
            }
        },
        name="default",
    )

    regions = database.create_collection("regions")
    regions.create_search_index(model=region_search_index_model)


    lookup_data_provider_index = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "data_provider": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        { "type": "string", },
                    ],
                },
            }
        },
        name="default",
    )

    lookup_data_provider = database.create_collection('lookup_data_provider')
    lookup_data_provider.create_search_index(model=lookup_data_provider_index)

    lookup_dataset_index = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "dataset": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        { "type": "string", },
                    ],
                },
            }
        },
        name="default",
    )

    lookup_dataset = database.create_collection('lookup_dataset')
    lookup_dataset.create_search_index(model=lookup_dataset_index)

    lookup_project_index = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "project_name": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        { "type": "string", },
                    ],
                },
            }
        },
        name="default",
    )

    lookup_project = database.create_collection('lookup_project')
    lookup_project.create_search_index(model=lookup_project_index)


    lookup_survey_index = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "project_name": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        { "type": "string", },
                    ],
                    "survey_name": [
                        {
                            "type": "autocomplete",
                            "minGrams": 1,
                            "tokenization": "nGram",
                        },
                        { "type": "string", },
                    ],
                },
            }
        },
        name="default",
    )

    lookup_survey = database.create_collection('lookup_survey')
    lookup_survey.create_search_index(model=lookup_survey_index)


    # Dropping the whole DB and then re-creating indexes on empty collections,
    # is generally faster that clearing existing collections and updating the existing indexes,
    # which is why we use this approach.


@pytest.fixture(scope="function", autouse=True)
def cleanup_database(get_test_settings, request) -> None:
    """
    Autouse fixture to ensure each test starts with an empty collection

    Other autouse fixtures that create DB content should request this one, to ensure that they run after this.
    """
    if request.node.get_closest_marker("no_db"):
        return

    test_settings = get_test_settings()
    client = get_mongo_client(test_settings)
    # drop DB and recreate so each test starts with a clean slate
    db = client.get_database(test_settings.db_name)

    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        collection.delete_many({})

# # # --------- TEMP STORAGE FIXTURES --------- # # #

@pytest.fixture(scope="function", autouse=True)
def setup_temp_file_storage_path(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Autouse fixture to ensure each test starts with an empty temp_file_storage_path directory.
    """
    test_temp_file_storage_path = tmp_path_factory.mktemp('test_temp_file_storage_path_')
    monkeypatch.setenv(name="TEMPORARY_FILE_STORAGE_PATH", value=str(test_temp_file_storage_path))


# # # ------------- OTHER FIXTURES ------------ # # #

@pytest.fixture(scope="session", autouse=True)
def setup_api_password() -> None:
    """
    Autouse fixture to set the password for certain API endpoints.
    """
    os.environ['API_SYSTEM_KEY'] = 'test_password'


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as requests_mock:
        yield requests_mock
