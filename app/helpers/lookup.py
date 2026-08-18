from app.helpers.mongo import (
    get_published_submission_set_collection,
    get_record_collection,
    get_published_submission_collection,
)
from app.models.common_enums import DataType
from app.settings import Settings

TAXON_CONTEXT_FIELDS = [
    "kingdom",
    "phylum",
    "class_",
    "order",
    "family",
    "species",
]


def build_flat_field_pipeline(field):
    return [
        {"$match": {field: {"$nin": [None, ""], "$exists": True}}},
        {"$project": {field: 1, **{k: 1 for k in TAXON_CONTEXT_FIELDS[:TAXON_CONTEXT_FIELDS.index(field)] if k != field}}},
        {
            "$group": {
                "_id": f"${field}",
                **{
                    context_field: {
                        "$first": "$scientific_name"
                        if context_field == "species"
                        else f"${context_field}"
                    }
                    for context_field in TAXON_CONTEXT_FIELDS[
                        : TAXON_CONTEXT_FIELDS.index(field)
                    ]
                    if context_field != field
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "value": "$_id",
                "field": {"$literal": field},
                **{
                    k: 1
                    for k in TAXON_CONTEXT_FIELDS[: TAXON_CONTEXT_FIELDS.index(field)]
                    if k != field
                },
            }
        },
    ]


def build_species_pipeline(field: str):
    return [
        {"$match": {field: {"$nin": [None, ""]}}},
        {
            "$project": {
            field: 1,
            **{k: 1 for k in TAXON_CONTEXT_FIELDS},
            }
        },
        {
            "$group": {
                "_id": f"${field}",
                **{
                    k: {"$first": f"${field}" if k == "species" else f"${k}"}
                    for k in TAXON_CONTEXT_FIELDS[
                        : TAXON_CONTEXT_FIELDS.index("species")
                    ]
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "value": "$_id",
                "field": {"$literal": "species"},
                **{k: 1 for k in TAXON_CONTEXT_FIELDS},
            }
        },
    ]


def build_vernacular_pipeline():
    return [
        {"$match": {"vernacular_names": {"$exists": True, "$nin": [None, ""]}}},
        {
            "$project": {
                "names": {
                    "$reduce": {
                        "input": "$vernacular_names",
                        "initialValue": [],
                        "in": {
                            "$cond": [
                                {"$isArray": "$$this"},
                                {"$concatArrays": ["$$value", "$$this"]},
                                {"$concatArrays": ["$$value", ["$$this"]]},
                            ]
                        },
                    }
                },
                "scientific_name": 1,
                **{k: 1 for k in TAXON_CONTEXT_FIELDS if k != "species"},
            }
        },
        {"$unwind": "$names"},
        {"$match": {"names": {"$ne": None}}},
        {
            "$group": {
                "_id": "$names",
                **{
                    k: {"$first": "$scientific_name"}
                    if k == "species"
                    else {"$first": f"${k}"}
                    for k in TAXON_CONTEXT_FIELDS
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "value": "$_id",
                "field": {"$literal": "vernacular_name"},
                **{k: 1 for k in TAXON_CONTEXT_FIELDS},
            }
        },
    ]


def generate_taxon_lookup(
    settings: Settings,
):
    output_collection = "lookup_taxon"

    pipelines = {
        field: build_flat_field_pipeline(field)
        for field in ["phylum", "class_", "order", "family", "kingdom"]
    }

    pipelines["accepted_name_usage"] = build_species_pipeline(
        "accepted_name_usage"
    )
    pipelines["scientific_name"] = build_species_pipeline("scientific_name")
    pipelines["vernacular_name"] = build_vernacular_pipeline()

    for field, pipeline in pipelines.items():
        try:
            pipeline_with_merge = pipeline + [
                {"$merge": {
                    "into": output_collection,
                    "whenMatched": "replace", 
                    "on": ["value", "field"]
                }}
            ]
            get_record_collection(settings).aggregate(pipeline_with_merge, allowDiskUse=True)
        
        except Exception as e:
            print(f"Error processing {field}: {e}")
            continue


def generate_lookup_data_provider(settings: Settings):
    output_collection = "lookup_data_provider"

    aggregation_pipeline = [
        {"$match": {"institution_code": {"$nin": [None, ""], "$exists": True}}},
        {
            "$group": {
                "_id": "$institution_code",
            }
        },
        {"$project": {"_id": 0, "value": "$_id"}},
        {"$merge": {"into": output_collection, "whenMatched": "replace", "on": "value"}},
    ]

    get_record_collection(settings).aggregate(aggregation_pipeline, allowDiskUse=True)


def generate_lookup_dataset(settings: Settings):
    output_collection = "lookup_dataset"

    aggregation_pipeline = [
        {
            "$match": {
                "datatype": {"$in": [DataType.SPECIES_OCCURRENCE.value, None]},
                "dcterms_title": {"$nin": [None, ""], "$exists": True},
            }
        },
        {
            "$group": {
                "_id": "$dcterms_title",
            }
        },
        {"$project": {"_id": 0, "value": "$_id"}},
        {"$merge": {"into": output_collection, "whenMatched": "replace", "on": "value"}},
    ]

    get_record_collection(settings).aggregate(aggregation_pipeline, allowDiskUse=True)


def generate_lookup_project(settings: Settings):
    output_collection = "lookup_project"

    aggregation_pipeline = [
        {
            "$match": {
                "metadata.datatype": DataType.SYSTEMATIC_SURVEY,
                "metadata.name": {"$nin": [None, ""], "$exists": True},
            }
        },
        {
            "$group": {
                "_id": "$metadata.name",
            }
        },
        {"$project": {"_id": 0, "value": "$_id"}},
        {"$merge": {"into": output_collection, "whenMatched": "replace", "on": "value"}},
    ]

    get_published_submission_set_collection(settings).aggregate(
        aggregation_pipeline, allowDiskUse=True
    )


def generate_lookup_survey(settings: Settings):
    output_collection = "lookup_survey"

    aggregation_pipeline = [
        {
            "$match": {
                "metadata.datatype": DataType.SYSTEMATIC_SURVEY,
                "metadata.name": {"$nin": [None, ""], "$exists": True},
            }
        },
        {
            "$group": {
                "_id": "$metadata.name",
            }
        },
        {"$project": {"_id": 0, "value": "$_id"}},
        {"$merge": {"into": output_collection, "whenMatched": "replace", "on": "value"}},
    ]

    get_published_submission_collection(settings).aggregate(
        aggregation_pipeline, allowDiskUse=True
    )


def on_record_invalidation(settings: Settings):
    generate_taxon_lookup(settings)
    generate_lookup_dataset(settings)
    generate_lookup_data_provider(settings)


def on_published_submission_set_invalidation(settings: Settings):
    generate_lookup_project(settings)


def on_published_submission_invalidation(settings: Settings):
    generate_lookup_survey(settings)
