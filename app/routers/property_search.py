from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, status

from app.dependencies import get_settings
from app.helpers.mongo import get_cadastre_address, get_cadastre_polygon
from app.settings import Settings

router = APIRouter()


@router.get("/property_address/")
def get_address_list(
    search: Optional[str] = None, settings: Settings = Depends(get_settings)
):
    address_query = []
    if search is not None and len(search):
        
        address_query.append(
                {
                    "$search": {
                        "autocomplete": {
                            "query": search,
                            "path": "properties.display_address",
                        },
                    }
                },
        )
        address_query.append({
            "$limit": 500
        })
        address_query.append({
            "$project": {
                "_id": 1,
                "properties.display_address": 1
            }
        })

    results = []
    addresses = get_cadastre_address(settings).aggregate(address_query)
    for address in addresses:
        results.append(
            {
                "id": str(address["_id"]),
                "display_address": address['properties']['display_address']
            }
        )
    return {"total": len(results), "results": results}


@router.get("/property_boundary/")
def get_property_boundary(_id: str, settings: Settings = Depends(get_settings)):
    for item in get_cadastre_address(settings).find({"_id": ObjectId(_id.strip())}):
        print('found', item)
        return item["geometry"]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such property")


@router.get("/property_address/{property_id}/")
def get_property_details(property_id: str, settings: Settings = Depends(get_settings)):
    try:
        address = get_cadastre_address(settings).find_one({"_id": ObjectId(property_id.strip())})
        if not address:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
        
        return {
            "id": str(address["_id"]),
            "display_address": address.get("properties", {}).get("display_address", ""),
            "geometry": address.get("geometry")
        }
    except Exception as e:
        if "not found" in str(e).lower():
            raise e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid property ID format")


@router.get("/land_id/")
def get_land_id_list(land_id: int, settings: Settings = Depends(get_settings)):
    for item in get_cadastre_polygon(settings).find({"properties.land_id": land_id}):
        print('found', item)
        return item["geometry"]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No polygon found for this land_id")


@router.get("/land_title/{land_id}/")
def get_land_title_details(land_id: int, settings: Settings = Depends(get_settings)):
    land_title = get_cadastre_polygon(settings).find_one({"properties.land_id": land_id})
    if not land_title:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Land title not found")
    
    return {
        "land_id": land_id,
        "properties": land_title.get("properties", {}),
        "geometry": land_title.get("geometry")
    }

@router.get("/dp_boundary/")
def get_deposited_plan(survey_number: int, lot_number: int, settings: Settings = Depends(get_settings)):
    for item in get_cadastre_polygon(settings).find({"properties.survey_number": survey_number, "properties.lot_number": lot_number}):
        return item["geometry"]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No polygon found for this dp_number")

