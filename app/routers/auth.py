from fastapi import APIRouter, Request, Depends

from app.dependencies import get_settings
from app.helpers.authorisation import is_authorised, Permission
from app.settings import Settings

router = APIRouter()


@router.get("/auth/can-submit/")
async def can_submit(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    return is_authorised(Permission.SUBMIT, request, settings)


@router.get("/auth/can-view-sensitive/")
async def can_view_sensitive(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    return is_authorised(Permission.SENSITIVE, request, settings)
