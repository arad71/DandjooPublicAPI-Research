#!/usr/bin/env python3

import argparse
import pymongo
from pymongo.operations import SearchIndexModel
from pymongo import ASCENDING

parser = argparse.ArgumentParser(description='Setup MongoDB collection for records with indices')

parser.add_argument('-mh', '--mongo_host', dest='mongo_host', action='store', default='localhost',
                    help='specify the mongo host uri')

parser.add_argument('-mp', '--mongo_port', dest='mongo_port', action='store', default=27017,
                    help='specify the mongo host port')

parser.add_argument('-mu', '--mongo_user', dest='mongo_username', action='store', default='',
                    help='specify the mongo username')

parser.add_argument('-mpw', '--mongo_password', dest='mongo_password', action='store', default='',
                    help='specify the mongo password')

parser.add_argument('-mdb', '--mongo_database', dest='mongo_database', action='store', default='public',
                    help='specify the mongo database')

parser.add_argument('-dc', '--direct_connection', dest='direct_connection', action='store', default='false',
                    help='enable direct connection')

args = parser.parse_args()

client = pymongo.MongoClient(args.mongo_host, int(args.mongo_port), username=args.mongo_username,
                             password=args.mongo_password, directConnection=args.direct_connection)

# get or create dandjoo_public database
db = client[args.mongo_database]


# NOTE: Any unique indexes added here should also be added to the conftest.py `setup_database` fixture,
# so that the unique indexes are present for unit tests.


# # # Data Delivery collections # # #

# get or create record collection
records = db['records']
# setup record indexes
records.create_index([('location', pymongo.GEOSPHERE)], sparse=True)
records.create_index([('obfuscated_location.bounding_box', pymongo.GEOSPHERE)], sparse=True)
records.create_index('persistent_id')
records.create_index('accepted_name_usage')
records.create_index('scientific_name')
records.create_index('verbatim_identification')
records.create_index('event_date')
records.create_index("kingdom")
records.create_index("phylum")
records.create_index("order")
records.create_index("class_")
records.create_index("family")
records.create_index("species")
records.create_index("vernacular_names")
records.create_index("verbatim_identification")
records.create_index('institution_code')
records.create_index('dcterms_title')
records.create_index("submission_id")
records.create_index("submission_name", sparse=True)
records.create_index("submission_set_name", sparse=True)
records.create_index("restricted")

# get or create published_submissions collection
published_submissions = db['published_submissions']
# setup published_submissions indexes
published_submissions.create_index("persistent_id", unique=True)
published_submissions.create_index("submission_set_id")

# get or create published_submissions collection
published_submission_sets = db['published_submission_sets']
# setup published_submissions indexes
published_submission_sets.create_index("persistent_id", unique=True)


# # # Submission collections # # #

# get or create submissions collection
submissions = db['submissions']
# setup submissions indexes
# "persistent_id" index must be sparse because of all the existing submissions with no persistent_id field.
submissions.create_index("persistent_id", unique=True, sparse=True)
submissions.create_index("metadata.submission_set_persistent_id")

# get or create submission_sets collection
submission_sets = db['submission_sets']
# setup submission_sets indexes
submission_sets.create_index("persistent_id", unique=True)

# get or create supporting_files collection
supporting_files = db['supporting_files']
# setup supporting_files indexes
supporting_files.create_index("submission_set_persistent_id")


lookup_taxon_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "phylum": { "type": "string", },
                "field": { "type": "string", },
                "species": { "type": "string", },
                "class_": { "type": "string", },
                "family": { "type": "string", },
                "order": { "type": "string", },
                "kingdom": { "type": "string", },
                "value": [
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

lookup_taxon = db['lookup_taxon'] 
if len(list(lookup_taxon.list_search_indexes(name="default"))) > 0:
    lookup_taxon.drop_search_index(name="default")
lookup_taxon.create_search_index(model=lookup_taxon_index)

lookup_taxon.create_index([("field", ASCENDING), ("value", ASCENDING)], unique=True)

lookup_data_provider_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "value": [
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

lookup_data_provider = db['lookup_data_provider'] 
if len(list(lookup_data_provider.list_search_indexes(name="default"))) > 0:
    lookup_data_provider.drop_search_index(name="default")
lookup_data_provider.create_search_index(model=lookup_data_provider_index)

lookup_data_provider.create_index([("value", ASCENDING)], unique=True)

lookup_dataset_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "value": [
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

lookup_dataset = db['lookup_dataset'] 
if len(list(lookup_dataset.list_search_indexes(name="default"))) > 0:
    lookup_dataset.drop_search_index(name="default")
lookup_dataset.create_search_index(model=lookup_dataset_index)

lookup_dataset.create_index([("value", ASCENDING)], unique=True)

lookup_project_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "value": [
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

lookup_project = db['lookup_project'] 
if len(list(lookup_project.list_search_indexes(name="default"))) > 0:
    lookup_project.drop_search_index(name="default")
lookup_project.create_search_index(model=lookup_project_index)

lookup_project.create_index([("value", ASCENDING)], unique=True)

lookup_survey_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "value": [
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

lookup_survey = db['lookup_survey'] 
if len(list(lookup_survey.list_search_indexes(name="default"))) > 0:
    lookup_survey.drop_search_index(name="default")
lookup_survey.create_search_index(model=lookup_survey_index)

lookup_survey.create_index([("value", ASCENDING)], unique=True)

# # # Cadastre collections # # #
cadastre_addresses = db['cadastre_address']
cadastre_addresses.create_index([("properties.display_address", ASCENDING)])
cadastre_addresses.create_index([("properties.land_id", ASCENDING)])

cadastre_addresses_index = SearchIndexModel(
    definition={
        "mappings": {
            "dynamic": False,
            "fields": {
                "properties": {
                    "type": "document",
                    "dynamic": False,
                    "fields": {
                        "display_address": [
                            {
                                "type": "autocomplete",
                                "minGrams": 1,
                                "maxGrams": 15,
                                "foldDiacritics": True,
                                "tokenization": "nGram"
                            },
                            {
                                "type": "string",
                                "indexOptions": "offsets",
                                "store": True,
                                "norms": "include"
                            }
                        ]
                    }
                }
            }
        }
    },
    name="default",
)
if len(list(cadastre_addresses.list_search_indexes(name="default"))) > 0:
    cadastre_addresses.drop_search_index(name="default")
cadastre_addresses.create_search_index(model=cadastre_addresses_index)

cadastre_polygon = db['cadastre_polygon']
cadastre_polygon.create_index([("properties.land_id", ASCENDING)])
cadastre_polygon.create_index([("properties.survey_number", ASCENDING)])
cadastre_polygon.create_index([("properties.lot_number", ASCENDING)])

