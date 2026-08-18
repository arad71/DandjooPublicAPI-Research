from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request

from app.dependencies import get_settings
from app.helpers.authorisation import get_user_id
from app.helpers.mongo import get_filters_collection, get_cadastre_address, get_cadastre_polygon
from app.models.filters import FiltersCreate, Filters, FiltersResponse
from app.settings import Settings

router = APIRouter()


@router.post("/filters/", response_model=FiltersResponse)
async def create_filters(
    filters: FiltersCreate, request: Request, settings: Settings = Depends(get_settings)
):
    user_id = get_user_id(request, settings)
    if not user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Validate that at least one filter field is provided
    filter_data = filters.dict(by_alias=True, exclude_unset=True)
    if not filter_data:
        raise HTTPException(status_code=400, detail="At least one filter field must be provided")

    # Validate referenced IDs exist
    if filters.street_address_id:
        try:
            address = get_cadastre_address(settings).find_one({"_id": ObjectId(filters.street_address_id)})
            if not address:
                raise HTTPException(status_code=400, detail="Street address ID not found")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid street address ID format")
    
    if filters.land_title_id:
        land_title = get_cadastre_polygon(settings).find_one({"properties.land_id": filters.land_title_id})
        if not land_title:
            raise HTTPException(status_code=400, detail="Land title ID not found")
    
    if filters.deposited_plan:
        dp = get_cadastre_polygon(settings).find_one({
            "properties.survey_number": filters.deposited_plan.survey_number,
            "properties.lot_number": filters.deposited_plan.lot_number
        })
        if not dp:
            raise HTTPException(status_code=400, detail="Deposited plan not found")

    collection = get_filters_collection(settings)

    filter_data["user_id"] = str(user_id)
    filter_data["created_at"] = datetime.now()

    result = collection.insert_one(filter_data)
    filter_id = str(result.inserted_id)

    return FiltersResponse(filter_id=filter_id)


@router.get("/filters/{filter_id}", response_model=Filters)
async def get_filters(filter_id: str, settings: Settings = Depends(get_settings)):
    collection = get_filters_collection(settings)

    try:
        filter_doc = collection.find_one({"_id": ObjectId(filter_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filter ID")

    if not filter_doc:
        raise HTTPException(status_code=404, detail="Filters not found")

    # Convert MongoDB document to response format
    filter_doc["id"] = str(filter_doc["_id"])
    del filter_doc["_id"]

    return Filters(**filter_doc)

