import functools

from pymongo import MongoClient

from app.settings import Settings


def get_mongo_client(setting: Settings) -> MongoClient:
    return _get_cached_mongo_client(setting.mongodb_host, setting.mongodb_port, setting.mongondb_direct_connection)


@functools.lru_cache(maxsize=None)
def _get_cached_mongo_client(host: str, port: int, direct_connection: bool) -> MongoClient:
    """
    Get a MongoClient instance for the specified host and port.

    MongoClient class is thread-safe and has a connection pool.
    https://pymongo.readthedocs.io/en/stable/api/pymongo/mongo_client.html#pymongo.mongo_client.MongoClient
    So we cache it per host/port to take advantage of this and avoid constructing it
    repeatedly for each request.
    """
    return MongoClient(host=host, port=port, directConnection=direct_connection)


# # # Data Delivery collections # # #

def get_record_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.records


def get_region_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.regions


def get_published_submission_collection(settings: Settings):
    """
    The "published_submissions" collection holds submissions (e.g. Surveys)
    that have been published from Curation, and are available in the data delivery part of Dandjoo.
    As opposed to the plain "submissions" collection which records submissions made by Users to Curation.
    """
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.published_submissions


def get_published_submission_set_collection(settings: Settings):
    """
    The "published_submission_sets" collection holds submission sets (e.g. Projects)
    that have been published from Curation,
    and are available in the data delivery part of Dandjoo.
    As opposed to the plain "submission_sets" collection,
    which records Submissions Sets submitted by Users to Curation.
    """
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.published_submission_sets


# # # Data Submission collections # # #

def get_submission_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.submissions


def get_submission_set_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.submission_sets


def get_supporting_file_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.supporting_files

def get_lookup_taxon_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.lookup_taxon

def get_lookup_dataset_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.lookup_dataset

def get_lookup_data_provider_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.lookup_data_provider

def get_lookup_survey_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.lookup_survey

def get_lookup_project_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.lookup_project


def get_filters_collection(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.filters

def get_cadastre_address(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.cadastre_address

def get_cadastre_polygon(settings: Settings):
    mongo_client = get_mongo_client(settings)
    database = mongo_client[settings.db_name]
    return database.cadastre_polygon