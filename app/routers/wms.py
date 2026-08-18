from fastapi import APIRouter, Request, Response, Depends
import requests

from app.dependencies import get_settings
from app.settings import Settings

router = APIRouter()


# TODO: GetCapabilities is munted, but unnecessary for the intended use case
@router.get("/wms/")
async def wmsProxy(request: Request, settings: Settings = Depends(get_settings)):
    response = requests.get(f'{settings.geoserver_url}/wms?', request.query_params)
    return Response(content=response.content, media_type=response.headers['content-type'])


@router.get("/ows/")
async def wmsProxy(request: Request, settings: Settings = Depends(get_settings)):
    response = requests.get(f'{settings.geoserver_url}/ows?', request.query_params)
    return Response(content=response.content, media_type=response.headers['content-type'])
