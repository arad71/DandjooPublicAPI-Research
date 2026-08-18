from fastapi import FastAPI

# Always include this line. If you rename "app" then you need to change the command you use to start
# the app (ie. change "uvicorn main:app --reload" to "uvicorn main:<whatever you rename it to> --reload"

from starlette.middleware.cors import CORSMiddleware

from app.dependencies import get_settings
from app.routers import (regions, records, submission, wms, auth, submission_set,
                         publishing, public_tags, downloads, lookup, property_search)
from importlib import metadata
version= metadata.version("dandjoopublicapi")

settings = get_settings()

def create_app(app_settings=settings) -> FastAPI:
    app = FastAPI(root_path=app_settings.root_path,
                  version=version)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )

    # Add all the instances of APIRouter() that you create in each file here
    app.include_router(records.router)
    app.include_router(publishing.router)
    app.include_router(regions.router)
    app.include_router(property_search.router)
    app.include_router(submission.router)
    app.include_router(wms.router)
    app.include_router(auth.router)
    app.include_router(submission_set.router)
    app.include_router(public_tags.router)
    app.include_router(downloads.router)
    app.include_router(lookup.router)

    from app.routers.filters import router as filters_router
    app.include_router(filters_router)

    return app


app = create_app()
