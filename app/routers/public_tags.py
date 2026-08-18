from typing import Sequence

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class PublicSubmissionsTags(BaseModel):
    habitat: Sequence[str] = Field(
        alias="Habitat",
        default=(
            "Desert",
            "Arid",
            "Savanna",
            "Plains",
            "Grassland",
            "Riparian zone",
            "River",
            "Floodplain",
            "Estuary",
            "Freshwater",
            "Wetland",
            "Mangrove",
            "Subterranean",
            "Intertidal",
            "Coastal",
            "Marine",
            "Forest",
            "Heathland",
            "Rainforest",
            "Shrubland",
            "Woodlands",
            "Urban",
            "Subtropical forest",
            "Temperate forest",
            "Mallee",
            "Island",
            "Agricultural",
        ),
    )
    type: Sequence[str] = Field(
        alias="Type",
        default=(
            "Vegetation",
            "Fauna",
            "Terrestrial invertebrate",
            "Terrestrial vertebrate",
            "Targeted",
            "Long term monitoring",
            "Subterranean invertebrate",
            "Marine invertebrate",
            "Marine vertebrate",
            "Freshwater",
        )
    )
    highlights: Sequence[str] = Field(
        alias="Highlights",
        default=(
            "Soil information",
            "Short range endemics (SRE's)",
            "Presence/absence data",
            "Disturbance data",
            "Invasive species",
            "Water characteristics",
        ),
    )


@router.get("/tags/submissions/public/", response_model=PublicSubmissionsTags)
def get_public_submission_tags() -> PublicSubmissionsTags:
    """
    Get all public tags for Submissions.

    These are the tags used by published Submissions.
    """
    return PublicSubmissionsTags()
