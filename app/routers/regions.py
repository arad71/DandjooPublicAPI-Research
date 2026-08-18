from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status

from app.dependencies import get_settings
from app.helpers.mongo import get_region_collection
from app.settings import Settings

router = APIRouter()


@router.get("/regions/")
def get_regions_list(
    search: Optional[str] = None, settings: Settings = Depends(get_settings)
):
    regions_query = []
    if search is not None and len(search):
        regions_query.append(
                {
                    "$search": {
                        "autocomplete": {
                            "query": search,
                            "path": "name",
                        },
                    }
                },
        )
        regions_query.append({
            "$limit": 500
        })
        regions_query.append({
            "$project": {
                "_id": 1,
                "name": 1
            }
        })


    results = []
    regions = get_region_collection(settings).aggregate(regions_query)
    for spatial in regions:
        results.append(
            {
                "id": str(spatial["_id"]),
                "name": spatial['name']
            }
        )
    return {"total": len(results), "results": results}


@router.get("/region/")
def get_region(_id: str, settings: Settings = Depends(get_settings)):
    for item in get_region_collection(settings).find({"_id": ObjectId(_id.strip())}):
        return {"name": item['name'], "geojson": item["geojson"]}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such region")
