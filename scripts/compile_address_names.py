# Filter to find documents where 'properties.display_address' is missing or null
from app.helpers.mongo import get_cadastre_address
from app.settings import Settings


""" 
Script to compile 'display_address' field in cadastre_address collection based on existing fields.
This script updates documents where 'properties.display_address' is missing or null. If you would like to write over existing values, modify the filter_query accordingly.  
Note: ensure that variables in settings.py / env varriables are set to connect to the correct database.
"""
print("Checking settings and connecting to database...")
settings = Settings()
print("Connected to database: ", settings.db_name)


filter_query = {
    "$or": [
        {"properties.display_address": {"$exists": False}},
        {"properties.display_address": None}
    ]
}
pipeline = [
    {
        "$set": {
            "properties.display_address": {
                "$switch": {
                    "branches": [
                        {
                            "case": { "$eq": ["$properties.road_number_type", "H"] },
                            "then": {
                                "$reduce": {
                                    "input": {
                                        "$concatArrays": [
                                            [
                                                {
                                                    "$trim": {
                                                        "input": {
                                                            "$concat": [
                                                                {
                                                                    "$cond": [
                                                                        { "$and": ["$properties.road_number_1", "$properties.road_number_2"] },
                                                                        { "$concat": ["$properties.road_number_1", "-", "$properties.road_number_2"] },
                                                                        "$properties.road_number_1"
                                                                    ]
                                                                },
                                                                " ",
                                                                "$properties.road_name",
                                                                { "$cond": [ { "$ifNull": ["$properties.road_type", False] }, " ", "" ] },
                                                                { "$ifNull": ["$properties.road_type", ""] },
                                                            ]
                                                        }
                                                    }
                                                }
                                            ],
                                            [ "$properties.locality" ],
                                            [ "WA" ]
                                        ]
                                    },
                                    "initialValue": "",
                                    "in": {
                                        "$concat": [
                                            "$$value",
                                            { "$cond": [ { "$eq": ["$$value", ""] }, "", ", " ] },
                                            "$$this"
                                        ]
                                    }
                                }
                            }
                        },
                        {
                            "case": { "$eq": ["$properties.road_number_type", "L"] },
                            "then": {
                                "$reduce": {
                                    "input": {
                                        "$concatArrays": [
                                            [
                                                {
                                                    "$trim": {
                                                        "input": {
                                                            "$concat": [
                                                                "Lot ",
                                                                "$properties.lot_number",
                                                                { "$cond": [ { "$ifNull": ["$properties.road_name", False] }, " ", "" ] },
                                                                { "$ifNull": ["$properties.road_name", ""] },
                                                                { "$cond": [ { "$ifNull": ["$properties.road_type", False] }, " ", "" ] },
                                                                { "$ifNull": ["$properties.road_type", ""] },
                                                            ]
                                                        }
                                                    }
                                                }
                                            ],
                                            [ "$properties.locality" ],
                                            [ "WA" ]
                                        ]
                                    },
                                    "initialValue": "",
                                    "in": {
                                        "$concat": [
                                            "$$value",
                                            { "$cond": [ { "$eq": ["$$value", ""] }, "", ", " ] },
                                            "$$this"
                                        ]
                                    }
                                }
                            }
                        }
                    ],
                    "default": None
                }
            }
        }
    }
]

collection = get_cadastre_address(settings)
print(collection.count_documents(filter_query), "documents to update in", collection.name)

proceed = input(f"Proceed to update {collection.count_documents(filter_query)} documents? (y/n): ")
if proceed.lower() != 'y':
    print("Operation cancelled.")
    exit()

collection.update_many(filter_query, pipeline)

print("Address names compilation completed.")
