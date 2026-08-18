from fastapi import APIRouter, Depends
from fastapi_key_auth import AuthorizerDependency

from app.dependencies import get_settings
from app.helpers.lookup import (
    generate_lookup_data_provider,
    generate_lookup_dataset,
    generate_lookup_project,
    generate_lookup_survey,
    generate_taxon_lookup,
)
from app.settings import Settings

router = APIRouter()

authorizer = AuthorizerDependency(key_pattern="API_SYSTEM_KEY")


@router.post("/lookup/invalidate", dependencies=[Depends(authorizer)])
def generate_all_lookup_collections(settings: Settings = Depends(get_settings)):
    # recreate the lookup collections
    generate_lookup_data_provider(settings)
    generate_lookup_dataset(settings)
    generate_lookup_project(settings)
    generate_lookup_survey(settings)
    generate_taxon_lookup(settings)


@router.post("/lookup/records/invalidate", dependencies=[Depends(authorizer)])
def generate_record_lookups(settings: Settings = Depends(get_settings)):
    # recreate the lookup collections related to records
    generate_lookup_data_provider(settings)
    generate_lookup_dataset(settings)
    generate_taxon_lookup(settings)


@router.post(
    "/lookup/public_submission_sets/invalidate", dependencies=[Depends(authorizer)]
)
def generate_public_submission_sets_lookup(settings: Settings = Depends(get_settings)):
    # recreate the lookup collections related to public_submission_sets
    generate_lookup_project(settings)


@router.post("/lookup/public_submissions/invalidate", dependencies=[Depends(authorizer)])
def generate_public_submissions_lookup(settings: Settings = Depends(get_settings)):
    # recreate the lookup collections related to public_submissions
    generate_lookup_survey(settings)
