import csv
import json
import io
import zipfile
import re
from datetime import datetime
from enum import Enum
from typing import Optional, List, Tuple, Union, Literal
from collections import defaultdict, OrderedDict
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING

import pytz
import shapefile
import pymongo
import numpy
import pysupercluster
import redis
import pickle
import pdfkit
from pdfkit.api import configuration

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, Response, HTTPException, Query, Body
from fastapi_key_auth import AuthorizerDependency
from geojson_pydantic import FeatureCollection, Feature
from pydantic import BaseModel, Field
from pymongo import ReturnDocument, UpdateOne, DeleteOne
from starlette import status
from starlette.requests import Request

from app.dependencies import get_settings
from app.helpers.export_field_mappings import (get_record_csv_mapping, get_record_csv_row, get_record_geojson_mapping,
                                               get_properties_for_geojson_feature, get_record_shapefile_row,
                                               get_record_shapefile_mapping)
from app.helpers.authorisation import is_authorised, Permission
from app.helpers.lookup import on_record_invalidation
from app.helpers.mongo import get_lookup_data_provider_collection, get_lookup_dataset_collection, get_lookup_project_collection, get_lookup_survey_collection, get_record_collection, get_published_submission_set_collection, get_published_submission_collection
from app.helpers.record_search import Coordinate, RecordSearch, SpeciesListPipeline
from app.helpers.taxonomic_rank import get_taxonomic_autocomplete_results
from app.models.common_enums import DataType
from app.models.published_submission_sets import PublishedSubmissionSet
from app.models.records import Record, PublicRecord
from app.settings import Settings

ACCEPTED_NAME_LENGTH = 50
DATE_COLLECTED_LENGTH = 50
DATA_PROVIDER_LENGTH = 100

router = APIRouter()

authorizer = AuthorizerDependency(key_pattern="API_SYSTEM_KEY")

def get_filename(export_label, settings: Settings = Depends(get_settings)) -> str:
    """
    Generate standard filename for data exports.
    """
    filename = f'bio_{export_label}_{datetime.now(pytz.timezone(settings.local_timezone)).isoformat()}'

    # sanitise the filename by removing or replacing invalid characters.
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


class ViewPort(BaseModel):
    # ViewPort defaults view the whole of WA
    class Defaults:
        DEFAULT_ZOOM = 5
        DEFAULT_NE = Coordinate(lat=-9.925565912405494, lng=149.76562500000003)
        DEFAULT_SW = Coordinate(lat=-41.145569731009495, lng=89.4287109375)

    zoom: int = Defaults.DEFAULT_ZOOM
    ne: Coordinate = Defaults.DEFAULT_NE
    sw: Coordinate = Defaults.DEFAULT_SW
    subviewport: bool = False

    @staticmethod
    def _scale_coordinate(coordinate: Coordinate, corner: Literal['ne', 'sw'], scale: str):
        """
        Scale a geographic coordinate to the nearest grid point based on the specified corner.

        This method is used for results caching where the search area is set from the viewport.
        Scaling the coordinates allows the caching process to return results when the user views the same
        general area at the same zoom factor, instead of requiring the exact same gps coordinates.

        Args:
            coordinate (Coordinate): The input geographic coordinate to be scaled.
            corner (Literal['ne', 'sw']): The corner of the grid to which the coordinate
                should be scaled. Use 'ne' for the northeast corner and 'sw' for the southwest corner.
            scale (String): A string representation of a float. This uses significant trailing zeros with the float
                value to determine how to scale the number.
                Example: "1." == scale to full number, "1.1" == "1.0" == "0.1" == scale to tenths.

        Returns:
            Coordinate: A new Coordinate object representing the scaled coordinate.
        """

        decimal_lat = Decimal(coordinate.lat)
        decimal_lng = Decimal(coordinate.lng)
        if corner == 'sw':
            # -- Reusing coordinate calculation technique from obfuscation implementation
            # Find the southwest corner,
            # This means 'rounding down' to the nearest grid size,
            # but numbers should always lose value, i.e.
            # negative numbers should get more negative, positive numbers should get less positive
            # This means a floor operation, rather than a 'round down'
            rounding = ROUND_FLOOR
        else:
            # logical constraint from parameter typing, corner == 'ne'
            # -- swapping logic to round up for the north east corner
            rounding = ROUND_CEILING
        lat = float(decimal_lat.quantize(Decimal(scale), rounding=rounding))
        lng = float(decimal_lng.quantize(Decimal(scale), rounding=rounding))
        return Coordinate(lat=lat, lng=lng)


    @property
    def scaled_ne(self):
        return self._scale_coordinate(coordinate=self.ne, corner='ne', scale='1.')

    @property
    def scaled_sw(self):
        return self._scale_coordinate(coordinate=self.sw, corner='sw', scale='1.')


class RecordsResult(BaseModel):
    total: int
    count: int
    offset: int
    limit: int
    next: Optional[str]
    previous: Optional[str]
    results: List[PublicRecord]
    total_includes_systematic_survey_results: bool


class SpeciesListEntry(BaseModel):
    accepted_name: str = Field(alias='accepted_name_usage')
    nomos_id: Optional[int] = None
    scientific_name: str = Field(alias='scientific_name')
    scientific_name_authorship: Optional[str] = Field(alias='scientific_name_authorship')
    verbatim_identification: Optional[str] = Field(alias='verbatim_identification')
    accepted_name_without_author: str = ""
    threat_code: Optional[str] = Field(alias='threat_status')
    establishment_means: Optional[str] = Field(alias='establishment_means')
    kingdom: Optional[str] = Field(alias='dwc:kingdom')
    phylum: Optional[str] = Field(alias='dwc:phylum')
    class_: Optional[str] = Field(alias='dwc:class')
    order: Optional[str] = Field(alias='dwc:order')
    family: Optional[str] = Field(alias='dwc:family')
    vernacular_name: Optional[List[str]] = Field(alias='dwc:vernacularName')
    search_area: Optional[str]
    search_parameters: Optional[str]

    def __hash__(self):
        # Define the hash for pythonic set-comprehension
        return hash((self.accepted_name, self.threat_code))

    @staticmethod
    def csv_headers():
        return [
            'Accepted Name (dwc:acceptedNameUsage)',
            'Accepted Name Without Authorship',
            'Author',
            'Conservation code (dwc:threatStatus)',
            'Kingdom (dwc:kingdom)',
            'Phylum (dwc:phylum)',
            'Class (dwc:class)',
            'Order (dwc:order)',
            'Family (dwc:family)',
            'Native/introduced/feral (dwc:establishmentMeans)',
            'Search Area',
            'Search Parameters',
            'Common Name'
            ]

    def csv_values(self):
        # Return the attribute values for CSV export

        if self.scientific_name_authorship is None:
            self.accepted_name_without_author: str = self.accepted_name
        else: 
            self.accepted_name_without_author: str = self.accepted_name.replace(self.scientific_name_authorship, "")

        return [self.accepted_name,
                self.accepted_name_without_author,
                self.scientific_name_authorship,
                self.threat_code,
                self.kingdom,
                self.phylum,
                self.class_,
                self.order,
                self.family,
                self.establishment_means,
                self.search_area,
                self.search_parameters,
                self.vernacular_name]


class SpeciesListExportEntry(SpeciesListEntry):
    @staticmethod
    def csv_headers():
        return ['NomosID', *SpeciesListEntry.csv_headers()]

    def csv_values(self):
        return [self.nomos_id, *super().csv_values()]




class SpeciesListResult(BaseModel):
    search_area: str
    threat_statuses: dict
    species_list: List[SpeciesListEntry]
    total: int
    count: int
    offset: int
    limit: int
    next: Optional[str]
    previous: Optional[str]


class BulkOperationResult(BaseModel):
    created_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0


class Cluster(BaseModel):
    n: int
    cid: str
    records: List[PublicRecord]
    limit: int
    p: Tuple[float, float]


class ClusterResult(BaseModel):
    total: int
    count: int
    results: List[Cluster]
    zoom: int


class PublishedSubmissionSetsResult(BaseModel):
    total: int
    count: int
    results: List[PublishedSubmissionSet]

    class Config:
        json_encoders = {
            ObjectId: str,
        }


class AutocompleteSearchResult(BaseModel):
    total: int
    results: List[str]


class RecordLocationEntry(BaseModel):
    id: str = Field(alias='persistent_id')
    coordinates: List[float]

    class Config:
        allow_population_by_field_name = True


class RecordLocationsResult(BaseModel):
    total: int
    count: int
    results: List[RecordLocationEntry]


class SortEnum(str, Enum):
    DATE = 'date'
    SPECIES = 'species'
    SPECIES_RECORDED = 'species_recorded'
    DATASET = 'dataset'
    DATA_PROVIDER = 'data_provider'
    LAT = 'lat'
    LNG = 'lng'


SORT_CLAUSE_MAP = {
    SortEnum.DATE: 'event_date',
    SortEnum.SPECIES: 'accepted_name_usage',
    SortEnum.SPECIES_RECORDED: 'scientific_name',
    SortEnum.DATASET: 'dcterms_title',
    SortEnum.DATA_PROVIDER: 'institution_code',
    SortEnum.LAT: 'location.coordinates.1',
    SortEnum.LNG: 'location.coordinates.0',
}


def get_redis_client(settings: Settings) -> Union[redis.Redis, None]:
    """
    Establishes a connection to a Redis server using the provided settings.

    Args:
        settings (Settings): An object containing Redis connection settings, including:
            - redis_host (str): The Redis server hostname.
            - redis_port (int): The Redis server port.
            - redis_password (str): The password for the Redis server.

    Returns:
        Union[redis.Redis, None]: A Redis client if the connection is successful,
        otherwise returns None. In case of a successful connection, the client is
        also checked for responsiveness using a ping.

    Raises:
        None: This function does not raise any exceptions explicitly.
        Connection issues are handled internally, and the function returns None
        if the connection cannot be established.
    """
    try:
        if (settings.redis_host is not None
                and settings.redis_port is not None
                and settings.redis_password is not None):
            # Set up Redis client
            redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=0,
                password=settings.redis_password
            )

            # --- Build complete records cache key and check cache
            if redis_client.ping():
                return redis_client
            else:
                return None

    except redis.ConnectionError as e:
        # redis not available, continue without a cache
        return None

class SortSearch(BaseModel):
    sort: Optional[SortEnum] = None
    descending: Optional[bool] = False

class LimitSearch(BaseModel):
    offset: int = Field(0, ge=0, le=50000000000,
                                  description="Offset parameter bound to positive integer, "
                                              "less than the logical maximum size of the database table.")
    limit: int = Field(100, ge=0, le=500,
                                 description="Limit parameter bound to positive integer, "
                                             "less than the logical maximum pagination limit.")

class ViewportSearch(BaseModel):
    viewport: Optional[str] = None

class DataTypeSearch(BaseModel):
    datatype: DataType

class RecordFilterParams(RecordSearch, SortSearch, LimitSearch):
    pass

class RecordLocationsParams(RecordSearch, SortSearch):
    pass

@router.get("/records/locations/", response_model=RecordLocationsResult, response_model_by_alias=False)
def get_record_locations(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters  
    search: RecordLocationsParams = Query(),
):
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission 
    )
    record_collection = get_record_collection(settings)
    
    # Count total records
    count = record_collection.count_documents(records_filter)
    
    # Project only the fields we need: persistent_id and location.coordinates
    projection = {
        'persistent_id': 1,
        'location.coordinates': 1,
        '_id': 0
    }
    
    # Include _id as last sort field so results are in a consistent order for pagination
    sort_fields = [("_id", pymongo.ASCENDING)]
    
    cursor = record_collection.find(records_filter, projection=projection, sort=sort_fields)
    
    # Transform results to match our response model
    results = []
    for item in cursor:
        if item.get('location') and item.get('location', {}).get('coordinates'):
            results.append(RecordLocationEntry(
                persistent_id=item['persistent_id'],
                coordinates=item['location']['coordinates']
            ))
    
    return RecordLocationsResult(
        total=count,
        count=len(results),
        results=results,
    )


@router.post("/records/", response_model=RecordsResult, response_model_by_alias=False)
def get_records(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordFilterParams = Body(...),
):
    offset = search.offset
    limit = search.limit
    sort = search.sort
    descending = search.descending

    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission 
    )
    record_collection = get_record_collection(settings)
    # Summarise the documents matched by the filter
    summary_cursor = record_collection.aggregate([
        {'$match': records_filter},
        {'$facet': {
            # Count all the matching records
            'count': [
                {'$count': 'count'},
            ],
            # See if there is at least 1 matching SSD record
            'ssd_records': [
                {'$match': {'datatype': DataType.SYSTEMATIC_SURVEY.value}},
                {'$limit': 1},
            ],
        }}
    ])
    with summary_cursor:
        summary = next(summary_cursor)
    count = summary['count'][0]['count'] if len(summary['count']) > 0 else 0
    includes_ssd = True if len(summary['ssd_records']) > 0 else False

    _next = f'/records/?offset={offset + limit}&limit={limit}' if (offset + limit) < count else None
    previous = f'/records/?offset={offset - limit if offset > limit else 0}&limit={limit}' if offset > 0 else None
    # Include _id as last sort field so results are in a consistent order for pagination
    if sort is not None:
        sort_fields = [
            (SORT_CLAUSE_MAP[sort], pymongo.DESCENDING if descending else pymongo.ASCENDING),
            ("_id", pymongo.ASCENDING),
        ]
    else:
        sort_fields = [("_id", pymongo.ASCENDING)]

    cursor = record_collection.find(records_filter, sort=sort_fields)
    records = [PublicRecord(**item) for item in cursor.skip(offset).limit(limit)]

    return RecordsResult(
        total=count,
        count=len(records),
        offset=offset,
        limit=limit,
        next=_next,
        previous=previous,
        results=records,
        total_includes_systematic_survey_results=includes_ssd,
    )


class SpeciesListParams(RecordSearch, LimitSearch):
    pass

@router.post("/records/species_list/")
def get_species_list(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: SpeciesListParams = Body(...),
) -> SpeciesListResult:
    offset = search.offset
    limit = search.limit
    record_collection = get_record_collection(settings)

    # -- Paginated results (Limited in size for display to the user)
    records_filter = search.get_species_list_filter(request, settings)
    faceted_pipeline = SpeciesListPipeline.faceted_pipeline(species_list_filter=records_filter, offset=offset, limit=limit)

    # Get and extract query results and total count
    search_area_ = search.get_search_area_summary(settings=settings)
    mongo_faceted_command_cursor = record_collection.aggregate(faceted_pipeline)
    faceted_result = next(mongo_faceted_command_cursor)
    paginated_species_list_ = [SpeciesListEntry(**item) for item in faceted_result['species_list_results']]
    if paginated_species_list_ and faceted_result['total_query_results_count'][0]['total_count']:
        count = faceted_result['total_query_results_count'][0]['total_count']
    else:
        # The query has no results, return an empty object.
        return SpeciesListResult(search_area=search_area_,
                                 threat_statuses={},
                                 species_list=[],
                                 total=0,
                                 count=0,
                                 offset=0,
                                 limit=0,
                                 next=None,
                                 previous=None)

    # record pagination values for frontend
    next_ = f'/records/species_list/?offset={offset + limit}&limit={limit}' if (offset + limit) < count else None
    previous = f'/records/species_list/?offset={offset - limit if offset > limit else 0}&limit={limit}' if offset > 0 else None

    # -- Full search criteria results (for reporting totals summary information to the user)
    # get cache key
    search_key = search.get_search_key(request, settings)
    if search.area is None and search.region_id is None:
        search_area_key = "none_specified"
    else:
        search_area_key = search.get_search_key_area()
    species_list_key = ":".join(["species_list", search_key, "area", search_area_key])

    records_cache = None
    using_redis = False

    redis_client = get_redis_client(settings)
    if redis_client is not None:
        records_cache = redis_client.get(species_list_key)
        using_redis = True

    if records_cache is not None:
        # Get results from cache
        cached_results = pickle.loads(records_cache)
        full_species_list_ = cached_results["full_species_list"]
    else:
        # Get results from db query
        simple_pipeline = SpeciesListPipeline.simplified_pipeline(species_list_filter=records_filter)
        mongo_pipeline_command_cursor = record_collection.aggregate(simple_pipeline)
        full_species_list_ = [SpeciesListEntry(**item) for item in mongo_pipeline_command_cursor]

        try:
            if full_species_list_ and using_redis:
                # Save results to cache
                pickled_cache = pickle.dumps({"full_species_list": full_species_list_})
                redis_client.set(species_list_key, pickled_cache, ex=settings.redis_cache_ttl_seconds)
        except Exception:
            pass


    # Count species threat code occurrences
    total_threat_statuses_ = defaultdict(int)
    for entry in full_species_list_:
        threat_code = entry.threat_code
        total_threat_statuses_[threat_code if threat_code is not None else "None"] += 1

    # Create result object
    species_list_result = SpeciesListResult(search_area=search_area_,
                                            threat_statuses=total_threat_statuses_,
                                            species_list=paginated_species_list_,
                                            total=count,
                                            count=len(paginated_species_list_),
                                            offset=offset,
                                            limit=limit,
                                            next=next_,
                                            previous=previous,
                                            )

    return species_list_result


@router.post("/records/export-species_list/")
def species_list_csv(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordSearch = Body(...),
):
    record_collection = get_record_collection(settings)
    records_filter = search.get_species_list_filter(request, settings)
    pipeline = SpeciesListPipeline.simplified_pipeline(species_list_filter=records_filter)

    # Get and extract query results and total count
    search_area_ = search.get_search_area_summary(settings=settings)
    search_parameters_ = search.get_search_parameters_summary()
    mongo_pipeline_command_cursor = record_collection.aggregate(pipeline)
    species_list_ = [SpeciesListExportEntry(search_area=search_area_, search_parameters=search_parameters_, **item) for item in mongo_pipeline_command_cursor]
    count = len(species_list_) if species_list_ else 0

    if count > settings.max_export_size and not is_authorised(Permission.FULL_DATA_DOWNLOAD, request, settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'A maximum of {settings.max_export_size} can be exported')

    stream = io.StringIO()
    csv_writer = csv.writer(stream)
    csv_writer.writerow(SpeciesListExportEntry.csv_headers())

    for item in species_list_:
        csv_writer.writerow(item.csv_values())

    auth_name_string = "public"
    if is_authorised(Permission.SENSITIVE, request, settings):
        auth_name_string = "restricted"

    
    export_label = f'species_list_{auth_name_string}'
    export_filename = f'{get_filename(export_label, settings)}.csv'

    csv_bytes = stream.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_filename}"'

    return response

@router.post("/records/export-species_pdf/")
def record_pdf(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordSearch = Body(...),
):
    

    record_collection = get_record_collection(settings)
    records_filter = search.get_species_list_filter(request, settings)
    pipeline = SpeciesListPipeline.simplified_pipeline(species_list_filter=records_filter)
    # Get and extract query results and total count
    search_area_ = search.get_search_area_summary(settings=settings)
    search_parameters_ = search.get_search_parameters_summary()
    mongo_pipeline_command_cursor = record_collection.aggregate(pipeline)
    species_list_ = [SpeciesListExportEntry(search_area=search_area_, search_parameters=search_parameters_, **item) for item in mongo_pipeline_command_cursor]
    count = len(species_list_) if species_list_ else 0

    if count > settings.max_export_size and not is_authorised(Permission.FULL_DATA_DOWNLOAD, request, settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'A maximum of {settings.max_export_size} can be exported')
    

    # Count species threat code occurrences and kingdoms
    total_threat_statuses_ = defaultdict(int)
    total_unique_kingdoms_ = defaultdict(int)
    for entry in species_list_:
        threat_code = entry.threat_code
        total_threat_statuses_[threat_code if threat_code is not None else "None"] += 1
        kingdom_type = entry.kingdom
        total_unique_kingdoms_[kingdom_type if kingdom_type is not None else "None"] += 1

    total_threat_statuses_sorted_ = {key: value for key, value in sorted(total_threat_statuses_.items())}

    stream = io.StringIO()

    #Threat Codes
    stream.write("""
        <table style="width: 100%; margin-bottom: 1rem;" cellpadding="0" cellspacing="0">
            <thead style="display: table-header-group; text-align: left; background: rgb(48,108,120); color: white; font-size: 13px; font-weight: 400;">
                <tr>
                    <th style="padding: 10px 3px;">Conservation status summary</th>
                    <th style="padding: 10px 3px; width: 20%;">Count</th>
                </tr>
            </thead>
            <tbody style="font-size: 13px;">
""")
    total=0
    for key, value in total_threat_statuses_sorted_.items():
        stream.write(f"""
                <tr>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{key}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{value}</td>
                </tr>
""")
        total = total + value
    stream.write(f"""
                <tr>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235); font-weight: 800;">Total</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235); font-weight: 800;">{total}</td>
                </tr>
""")
    stream.write("""
            </tbody>
        </table>
 """)

    #Kingdoms
    stream.write("""
        <table style="width: 100%; margin-bottom: 1rem;" cellpadding="0" cellspacing="0">
            <thead style="display: table-header-group; text-align: left; background: rgb(48,108,120); color: white; font-size: 13px; font-weight: 400;">
                <tr>
                    <th style="padding: 10px 3px;">Kingdoms</th>
                    <th style="padding: 10px 3px; width: 20%;">Count</th>
                </tr>
            </thead>
            <tbody style="font-size: 13px;">
""")
    total=0
    for key, value in total_unique_kingdoms_.items():
        stream.write(f"""
                <tr>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{key}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{value}</td>
                </tr>
""")
        total = total + value
    stream.write(f"""
                <tr>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235); font-weight: 800;">Total unique species</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235); font-weight: 800;">{total}</td>
                </tr>
""")
    stream.write("""
            </tbody>
        </table>

        <table style="width: 100%; margin-bottom: 1rem;" cellpadding="0" cellspacing="0">
            <thead style="display: table-header-group; text-align: left; background: rgb(48,108,120); color: white; font-size: 13px; font-weight: 400;">
                <tr>
                    <th style="padding: 10px 3px;">#</th>
                    <th style="padding: 10px 3px;">NomosID</th>
                    <th style="padding: 10px 3px;">Class</th>
                    <th style="padding: 10px 3px;">Family</th>
                    <th style="padding: 10px 3px;">Name</th>
                    <th style="padding: 10px 3px;">Establishment</th>
                    <th style="padding: 10px 3px;">Conservation</th>
                </tr>
            </thead>
            <tbody style="font-size: 13px; line-height: 1.4;">
""")
    row=0
    header='blank'
    for item in species_list_:
        row += 1
        cl = ''
        est = ''
        cc = ''
        nomos_id = '' if item.nomos_id is None else item.nomos_id
        vern_names_str = ''
        #if item.vernacular_names != None:
        for x in item.vernacular_name or []:
            if item.vernacular_name.index(x) == 0:
                vern_names_str += x
            else:
                vern_names_str += ", " + x
        if vern_names_str != '':
            vern_names_str = vern_names_str.strip()
            vern_names_str = '<em>(' + vern_names_str + ')</em>'
        if item.establishment_means != None:
            est = item.establishment_means.strip()
        if item.threat_code != None:
            cc = item.threat_code.strip()
        if header != item.kingdom:
            stream.write(f"""
                <tr>
                    <td colspan="7" style="padding: 20px 3px 10px; font-size: 16px; font-weight: 800;">{item.kingdom}</td>
                </tr>
""")
            header = item.kingdom
        stream.write(f"""
                <tr>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{row}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{nomos_id}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{item.class_}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{item.family}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{item.scientific_name} {vern_names_str}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{est}</td>
                    <td style="padding: 3px; border: 1px solid rgb(235,235,235);">{cc}</td>
                </tr>
""")
    stream.write("""
            </tbody>
        </table>
""")


    auth_name_string = "public"
    if is_authorised(Permission.SENSITIVE, request, settings):
        auth_name_string = "restricted"
        disclaimer = '<p>The production and usage of this report is deemed acceptance of Dandjoo&rsquo;s conditions of use.  Details available via our web - <a href="https://bio.wa.gov.au/dandjoo/knowledge/documentation/dandjoo-conditions-use">Dandjoo Conditions of Use | Biodiversity Information Office</a></p>'
    else:
        disclaimer = '<p>The production and usage of this report is deemed acceptance of Dandjoo&rsquo;s conditions of use.  Details available via our web - <a href="https://bio.wa.gov.au/dandjoo/knowledge/documentation/dandjoo-conditions-use">Dandjoo Conditions of Use | Biodiversity Information Office</a></p><p>Further note, precise locations of <a href="https://www.dbca.wa.gov.au/management/threatened-species-and-communities/nominations-listing">conservation listed species</a> are considered sensitive. To protect this information, <a href="https://bio.wa.gov.au/blog/dandjoo/new-feature-obfuscation">obfuscation</a> has been applied to conservation-listed species records. For these species, the true location is &plusmn;10km from the search area used to generate this species list.</p>'    


    export_label = f'species_list_{auth_name_string}'
    export_filename = f'{get_filename(export_label, settings)}.pdf'

    date_string = datetime.now(pytz.timezone(settings.local_timezone)).isoformat()
    date_string_short = datetime.now().strftime("%d %b %G")
    
    user = "Guest User"

    html = f"""
                <html style="font-family: sans-serif;">
                    <body>
                        <img src="https://bio.wa.gov.au/sites/default/files/2024-08/DBCA%20logo.png" alt="DBCA Logo" style="position: absolute; top: 0; left: 0; width: 10%;" />
                        <h1 style="text-align: center; font-weight: 400; padding-top: 10px;">Dandjoo Species List Export</h1>
                        <h2  style="text-align: center; font-weight: 400;">Created by {user} on {date_string_short}</h2>
                        <div style="background: rgb(235,235,235); padding: 20px; margin: 60px 0;">
                            <table style="width: 100%;">
                                <tr>
                                    <td style="padding: 5px 3px; width: 20%;">Source</td>
                                    <td style="padding: 5px 3px;">Dandjoo &ndash; Department of Biodiversity, Conservation and Attractions</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 3px; width: 20%;">Method</td>
                                    <td style="padding: 5px 3px;">{search_area_}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 5px 3px;">Date time</td>
                                    <td style="padding: 5px 3px;">{date_string}</td>
                                </tr>
                            </table>
                        </div>
                        {stream.getvalue()}
                        <div>
                            <h2 style="page-break-before: always;">Conservation status definitions</h2>
                            <p><strong>Threatened species</strong></p>
                            <ul style="line-height: 1.5;">
                                <li>CR &ndash; Critically Endangered</li>
                                <li>EN &ndash; Endangered</li>
                                <li>VU &ndash; Vulnerable</li>
                                <li>EX &ndash; Extinct</li>
                                <li>EW &ndash; Extinct in the Wild</li>
                                <li>CD &ndash; Species of special conservation interest (conservation dependent)</li>
                                <li>OS &ndash; Species otherwise in need of special protection (other specially protected)</li>
                                <li>MI &ndash; Migratory</li>
                                <li>SP &ndash; Specially protected species</li>
                            </ul>

                            <p><strong>Priority species</strong></p>
                            <ul style="line-height: 1.5;">
                                <li>P1 &ndash; Priority 1: Poorly-known species &ndash; known from few locations, none on conservation lands</li>
                                <li>P2 &ndash; Priority 2: Poorly-known species &ndash; known from few locations, some on conservation lands</li>
                                <li>P3 &ndash; Priority 3: Poorly-known species &ndash; known from several locations</li>
                                <li>P4 &ndash; Priority 4: Rare, Near Threatened and other species in need of monitoring</li>
                            </ul>
                            
                            <p><strong>Dandjoo specific codes</strong></p>
                            <ul style="line-height: 1.5;">
                                <li>Parent of conservation listed taxa</li>
                                <li>Cons code inherited from parent, X</li>
                            </ul>
                            <p>Read full definitions at <a href="https://bio.wa.gov.au/guide/conservation-status-definitions">https://bio.wa.gov.au/guide/conservation-status-definitions</a></p>
                            <p>&nbsp;</p>
                            <p>&nbsp;</p>
                            <p>&nbsp;</p>
                            <h2>Disclaimer</h2>
                            {disclaimer}

                        </div>
                    </body>
                </html>
            """

    options = {
        'page-size': 'A4',
        'encoding': "UTF-8",
        'no-outline': None,
        'footer-left': 'Department of Biodiversity, Conservation and Attractions',
        'footer-right' : '[page] of [topage]',
        'footer-font-size':'8',
        'margin-bottom': '2cm',
        'footer-spacing': 5,
    }
    
    if settings.wkhtml_path == 'default':
        pdf = pdfkit.from_string(html, False, options=options)
    else:
        
        wkhtml_path = pdfkit.configuration(wkhtmltopdf = settings.wkhtml_path)  #by using configuration.
        pdf = pdfkit.from_string(html, False, options=options,configuration=wkhtml_path)


    headers = {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename="{export_filename}"'
    }

    response = Response(pdf, headers=headers)

    return response



@router.post("/records/export-csv/")
def record_csv(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordSearch = Body(...),
):
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission 
    )
    record_collection = get_record_collection(settings)
    count = record_collection.count_documents(records_filter)

    if count > settings.max_export_size and not is_authorised(Permission.FULL_DATA_DOWNLOAD, request, settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'A maximum of {settings.max_export_size} can be exported')

    stream = io.StringIO()
    csv_writer = csv.writer(stream)

    csv_export_mapping = get_record_csv_mapping(
        settings=settings,
        has_sensitive_permission=has_sensitive_permission,
    )
    csv_writer.writerow(mapping.header for mapping in csv_export_mapping)

    for record_dict in record_collection.find(records_filter):
        csv_writer.writerow(get_record_csv_row(Record(**record_dict), csv_export_mapping))

    #export_filename = f'bio_export_{datetime.now(pytz.timezone(settings.local_timezone)).isoformat()}.csv'
    export_label = f'records'
    export_filename = f'{get_filename(export_label, settings)}.csv'

    csv_bytes = stream.getvalue().encode("utf-8-sig")
    response = Response(csv_bytes, media_type="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_filename}"'
    return response


@router.post("/records/export-geojson/")
def record_geojson(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordSearch = Body(...),
):
    # Perform record search query
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission
    )
    record_collection = get_record_collection(settings)
    count = record_collection.count_documents(records_filter)

    # Validate results size and user permissions before performing export
    if count > settings.max_export_size and not is_authorised(Permission.FULL_DATA_DOWNLOAD, request, settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'A maximum of {settings.max_export_size} can be exported')

    # create export from query results
    features = []
    geojson_export_mapping = get_record_geojson_mapping(
        settings=settings,
        has_sensitive_permission=has_sensitive_permission,
    )
    for record_dict in record_collection.find(records_filter):
        record = Record(**record_dict)
        features.append(Feature(
            type='Feature',
            geometry=record.location,
            properties=get_properties_for_geojson_feature(record, geojson_export_mapping),
        ))
    feature_collection = FeatureCollection(features=features)
    #export_filename = f'bio_export_{datetime.now(pytz.timezone(settings.local_timezone)).isoformat()}.json'
    export_label = f'export'
    export_filename = f'{get_filename(export_label, settings)}.json'

    geojson_data = feature_collection.json()

    # export results
    response = Response(content=geojson_data, media_type="application/geo+json")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_filename}"'

    return response


@router.post("/records/export-shp/")
def record_shp(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: RecordSearch = Body(...),
):
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission
    )
    record_collection = get_record_collection(settings)
    count = record_collection.count_documents(records_filter)

    if count > settings.max_export_size and not is_authorised(Permission.FULL_DATA_DOWNLOAD, request, settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'A maximum of {settings.max_export_size} can be exported')

    shp = io.BytesIO()
    shx = io.BytesIO()
    dbf = io.BytesIO()

    shp_writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf)

    # create a point shapefile
    shp_writer.shapeType = 1

    shp_writer.autoBalance = True

    shapefile_export_mapping = get_record_shapefile_mapping(
        settings=settings,
        has_sensitive_permission=has_sensitive_permission,
    )
    for mapping in shapefile_export_mapping:
        shp_writer.field(
            mapping.header,
            fieldType='C',
            size=str(mapping.shapefile_field_size),
        )

    for counter, record_dict in enumerate(record_collection.find(records_filter), 1):
        record = Record(**record_dict)
        shp_writer.point(*record.location.coordinates)
        shp_writer.record(*get_record_shapefile_row(record, shapefile_export_mapping))

    export_label = "shape"
    filename_prefix = get_filename(export_label, settings)


    # shp_writer.close method needs to be called to add some critical header information to the respective files.
    # However, it will also close the three file-like objects, which prevents getvalue being called, so this hack
    # is needed to stop the closure of the shp, shx and dbf when calling shp_writer.close.
    shp.close = lambda: None
    shx.close = lambda: None
    dbf.close = lambda: None

    shp_writer.close()

    stream = io.BytesIO()


    wgs84_prj = """GEOGCS["WGS 84",
            DATUM["WGS_1984",
                SPHEROID["WGS 84",6378137,298.257223563]],
            PRIMEM["Greenwich",0],
            UNIT["degree",0.0174532925199433]]
        """

    zf = zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED)
    zf.writestr(f'{filename_prefix}.shp', shp.getvalue())
    zf.writestr(f'{filename_prefix}.shx', shx.getvalue())
    zf.writestr(f'{filename_prefix}.dbf', dbf.getvalue())
    zf.writestr(f'{filename_prefix}.prj', wgs84_prj)
    zf.close()

    # need to use close class method as close instance methods were changed above
    io.BytesIO.close(shp)
    io.BytesIO.close(shx)
    io.BytesIO.close(dbf)

    return Response(stream.getvalue(), media_type="application/x-zip-compressed",
                    headers={'Content-Disposition': f'attachment; filename="{filename_prefix}.zip"'})


class ClustersSearchParams(RecordSearch, ViewportSearch):
    pass

# Provides geojson clusters for a given search as vi
@router.post("/records/clusters/", response_model=ClusterResult, response_model_by_alias=False)
def record_clusters(
    request: Request,
    settings: Settings = Depends(get_settings),
    # Record search parameters
    search: ClustersSearchParams = Body(...),
) -> ClusterResult:
    viewport = search.viewport
    # --- setup process variables ---
    # create a viewport object from the incoming data, or create one from default values if none is given.
    viewport_data = json.loads(viewport) if viewport else None
    client_viewport = ViewPort(**viewport_data) if viewport_data else ViewPort()
    # if the search doesn't already have an area defined,
    # we can clip to the viewport vertices.
    if search.area is None and search.region_id is None:
        scaled_ne = client_viewport.scaled_ne
        scaled_sw = client_viewport.scaled_sw
        search._parsed_area = {
            "geojson_feature": {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [scaled_ne.lng, scaled_ne.lat],
                        [scaled_sw.lng, scaled_ne.lat],
                        [scaled_sw.lng, scaled_sw.lat],
                        [scaled_ne.lng, scaled_sw.lat],
                        [scaled_ne.lng, scaled_ne.lat]  # start point
                    ]]
                }
            }
        }
        search_area_key = search.get_search_key_area_scaled()
    else:
        search_area_key = search.get_search_key_area()

    # Limit the search if it's at a 'far' zoom level
    limit_search_results = client_viewport.zoom <= settings.cluster_min_zoom_threshold

    # get search filter and cache key
    has_sensitive_permission = is_authorised(Permission.SENSITIVE, request, settings)
    has_restricted_permission = is_authorised(Permission.RESTRICTED, request, settings)
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=has_sensitive_permission,
        include_restricted_records=has_restricted_permission
    )
    search_key = search.get_search_key(request, settings)
    records_key = ":".join(["records", "limit", str(limit_search_results), search_key, "area", search_area_key])
    # example records cache key:
    # records:limit:True:user_id:1:authorised:True:species:acacia:area:polygon#location_representation#890.2428130659893

    # empty results
    total = 0
    records = []
    count = 0
    sc_clusters = []
    sc_index = None
    records_cache = None
    using_redis = False

    redis_client = get_redis_client(settings)
    if redis_client is not None:
        records_cache = redis_client.get(records_key)
        using_redis = True

    if records_cache is not None:
        cached_results = pickle.loads(records_cache)
        total = int(cached_results["total"])
        records = cached_results["records"]
    else:
        # --- Get database records ---
        record_collection = get_record_collection(settings)
        try:
            if limit_search_results:
                total = record_collection.count_documents(records_filter, limit=settings.cluster_min_zoom_limit)
                records = [PublicRecord(**item) for item in
                           record_collection.find(records_filter).limit(settings.cluster_min_zoom_limit).sort("_id", pymongo.DESCENDING)]
            else:
                total = record_collection.count_documents(records_filter)
                records = [PublicRecord(**item) for item in
                           record_collection.find(records_filter).sort("_id", pymongo.DESCENDING)]
            if records and using_redis:
                pickled_cache = pickle.dumps({"records": records, "total": total})
                redis_client.set(records_key, pickled_cache, ex=settings.redis_cache_ttl_seconds)
        except Exception:
            total = 0
            records = []

    # --- build cluster index ---
    count = len(records)
    if count > 0:
        # build a numpy list of lat/long
        np_points = numpy.array([item.location.coordinates for item in records])
        # to keep the ids, we need to pass them in as tags
        # itemtags = [str(item.id) for item in records]
        # build a supercluster index constrained to one zoom level
        sc_index = pysupercluster.SuperCluster(
            np_points,
            records,
            min_zoom=client_viewport.zoom,
            max_zoom=client_viewport.zoom,
            radius=settings.cluster_radius,
            extent=settings.cluster_extent
        )

        # --- build cluster results ---
        # prepare results for return
        west = client_viewport.sw.lng
        east = client_viewport.ne.lng
        if east >= west:  # Normal case
            sc_clusters = sc_index.getClusters(
                top_left=(west, client_viewport.ne.lat),
                bottom_right=(east, client_viewport.sw.lat),
                zoom=client_viewport.zoom
            )
        else:  # Edge case: view port crosses 180°E/W line.
            # Bug in pysupercluster library https://github.com/wemap/pysupercluster/issues/13 means
            # getClusters() fails to get clusters if viewport crosses 180°E/W.
            # Instead call getClusters() once for each side of 180, and combine the results.
            # This is not perfect (clusters won't combine across 180 line) but it's better than nothing.
            sc_clusters = sc_index.getClusters(
                top_left=(west, client_viewport.ne.lat),
                bottom_right=(180.0, client_viewport.sw.lat),
                zoom=client_viewport.zoom
            )
            sc_clusters.extend(sc_index.getClusters(
                top_left=(-180.0, client_viewport.ne.lat),
                bottom_right=(east, client_viewport.sw.lat),
                zoom=client_viewport.zoom
            ))
        # only embed records in clusters if it's a single point cluster or above a certain zoom level
        for cluster in sc_clusters:
            if cluster["count"] > 1 and client_viewport.zoom < settings.cluster_max_zoom_without_records:
                cluster["tags"] = []

    clusters = [Cluster(
        n=cluster["count"],  # count
        cid=cluster["id"],  # cluster id
        records=cluster["tags"],  # list of records
        limit=limit_search_results,  # were cluster results limited?
        p=(cluster["latitude"], cluster["longitude"])  # position
    ) for cluster in sc_clusters]
    return ClusterResult(total=total, count=count, results=clusters, zoom=client_viewport.zoom)

class SubmissionSetParams(RecordSearch, LimitSearch, DataTypeSearch):
    pass

@router.post("/records/submission_sets", response_model=PublishedSubmissionSetsResult)
def get_record_submission_sets(
    request: Request,
    settings: Settings = Depends(get_settings),
    # # # Record search parameters # # #
    search: SubmissionSetParams = Body(...),
) -> PublishedSubmissionSetsResult:
    datatype = search.datatype
    offset = search.offset
    limit = search.limit
    """
    Get the Submission Sets and Submissions for the records that match the search.
    """
    # Get filter for Records according to search parameters
    #
    # Note that conservation listed Records are included, even for public users,
    # because the actual Records matching this filter are not returned to the user,
    # they are just used to determine *which* Submission Sets and Submissions should
    # be returned by this endpoint.
    #
    # In fact, a Submission (Set) with ALL conservation listed records, should still
    # be shown to a public user, and filtering out those records here would stop that.
    records_filter = search.get_record_filter(
        settings,
        include_threatened_records=True,
        include_restricted_records=True
    )

    # record datatype filter needs special case for SPECIES_OCCURRENCE
    if datatype == DataType.SPECIES_OCCURRENCE:
        record_datatype_filter = {"datatype": {"$in": [None, DataType.SPECIES_OCCURRENCE]}}
    else:
        record_datatype_filter = {"datatype": datatype.value}

    record_collection = get_record_collection(settings)
    submissions_collection = get_published_submission_collection(settings)
    submission_sets_collection = get_published_submission_set_collection(settings)

    # Step 1: Aggregation to find the Submissions for the matching Records.
    cursor = record_collection.aggregate([
        # Get the Matching records, for the datatype we are interested in.
        {"$match": {"$and": [
            records_filter,
            record_datatype_filter,
            {"submission_id": {"$ne": None}},
        ]}},
        # Then get the unique submission ids for those records.
        {"$group": {"_id": "$submission_id"}},
    ])
    matching_submission_ids: List[str] = [row["_id"] for row in cursor]

    # Step 2: Get the Submission Set ids for those Submissions
    cursor = submissions_collection.aggregate([
        {"$match": {
            "persistent_id": {"$in": matching_submission_ids},
            "metadata.datatype": datatype.value,
            "submission_set_id": {"$ne": None},
        }},
        {"$group": {"_id": "$submission_set_id"}},
    ])
    matching_submission_set_ids: List[str] = [row["_id"] for row in cursor]

    # Step 3: Get the Published Submission Sets to return,
    # With Submission info attached with a $lookup/$addFields
    published_submission_sets_filter = {
        "persistent_id": {"$in": matching_submission_set_ids},
        "metadata.datatype": datatype.value,
    }
    # Get total count for pagination
    total = submission_sets_collection.count_documents(published_submission_sets_filter)
    cursor = submission_sets_collection.aggregate([
        # Part 1: Get the matching Submission Sets for the request page
        {"$match": published_submission_sets_filter},
        {"$sort": OrderedDict([("persistent_id", pymongo.ASCENDING)])},
        {"$skip": offset},
        {"$limit": limit},
        # Part 2: Lookup ALL the submissions for each Submission Set
        {"$lookup": {
            "from": "published_submissions",
            "localField": "persistent_id",
            "foreignField": "submission_set_id",
            "as": "all_submissions",
        }},
        # Part 3: Compute derived fields from $all_submission array.
        {"$addFields": {
            "from_date": {"$min": "$all_submissions.metadata.from_date"},
            "to_date": {"$max": "$all_submissions.metadata.to_date"},
            "total_submissions": {"$size": "$all_submissions"},
            "set_submissions": {"$sortArray": {
                "sortBy": OrderedDict([("persistent_id", pymongo.ASCENDING)]),
                "input": "$all_submissions",
            }},
            "matching_submissions": {"$sortArray": {
                "sortBy": OrderedDict([("persistent_id", pymongo.ASCENDING)]),
                "input": {"$filter": {
                    "cond": {"$in": ["$$this.persistent_id", matching_submission_ids]},
                    "input": "$all_submissions",
                }},
            }},
        }},
        {"$unset": ["all_submissions"]},
    ])
    submission_sets = [PublishedSubmissionSet(**row) for row in cursor]

    # redact information for public users
    authorised = is_authorised(Permission.SENSITIVE, request, settings)
    if not authorised:
        for submission_set in submission_sets:
            submission_set.redact_for_public_user()

    return PublishedSubmissionSetsResult(
        total=total,
        count=len(submission_sets),
        results=submission_sets,
    )

@router.get(
    "/records/phylum",
    response_model=AutocompleteSearchResult,
)
def phylum_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query([]),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of phylum/division for a given kingdom
    """
    filter_conditions = []
    
    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    results = get_taxonomic_autocomplete_results(
        field="phylum",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   


@router.get(
    "/records/class",
    response_model=AutocompleteSearchResult,
)
def class_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query(None),
    phylum: Optional[List[str]] = Query(None),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of classes for a given kingdom and phylum/division
    """
    filter_conditions = []
    
    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    if phylum and len(phylum) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(phylum), "defaultPath": "phylum"}})
    
    results = get_taxonomic_autocomplete_results(
        field="class_",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   


@router.get(
    "/records/order",
    response_model=AutocompleteSearchResult,
)
def order_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query(None),
    phylum: Optional[List[str]] = Query(None),
    class_: Optional[List[str]] = Query(None, alias="class"),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of orders for a given kingdom, phylum/division, and class
    """
    filter_conditions = []
    
    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    if phylum and len(phylum) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(phylum), "defaultPath": "phylum"}})

    if class_ and len(class_) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(class_), "defaultPath": "class_"}})
    
    results = get_taxonomic_autocomplete_results(
        field="order",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   

@router.get(
    "/records/family",
    response_model=AutocompleteSearchResult,
)
def family_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query(None),
    phylum: Optional[List[str]] = Query(None),
    class_: Optional[List[str]] = Query(None, alias="class"),
    order: Optional[List[str]] = Query(None),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of families for a given kingdom, phylum/division, and class
    """

    filter_conditions = []

    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    if phylum and len(phylum) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(phylum), "defaultPath": "phylum"}})

    if class_ and len(class_) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(class_), "defaultPath": "class_"}})
    
    if order and len(order) > 0: 
        filter_conditions.append({"queryString": {"query": " OR ".join(order), "defaultPath": "order"}})
    
    results = get_taxonomic_autocomplete_results(
        field="family",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   


@router.get(
    "/records/species",
    response_model=AutocompleteSearchResult,
)
def species_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query(None),
    phylum: Optional[List[str]] = Query(None),
    class_: Optional[List[str]] = Query(None, alias="class"),
    order: Optional[List[str]] = Query(None),
    family: Optional[List[str]] = Query(None),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of families for a given kingdom, phylum/division, and class
    """

    filter_conditions = []
    
    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    if phylum and len(phylum) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(phylum), "defaultPath": "phylum"}})

    if class_ and len(class_) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(class_), "defaultPath": "class_"}})
    
    if order and len(order) > 0: 
        filter_conditions.append({"queryString": {"query": " OR ".join(order), "defaultPath": "order"}})

    if family and len(family) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(family), "defaultPath": "family"}})
    
    results = get_taxonomic_autocomplete_results(
        field="species",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   

@router.get(
    "/records/vernacular",
    response_model=AutocompleteSearchResult,
)
def vernacular_list(
    search: Optional[str] = Query(None),
    kingdoms: Optional[List[str]] = Query(None),
    phylum: Optional[List[str]] = Query(None),
    class_: Optional[List[str]] = Query(None, alias="class"),
    order: Optional[List[str]] = Query(None),
    family: Optional[List[str]] = Query(None),
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    """
    Get a list of venacular names for a given kingdom, phylum/division, class, order, and family
    """

    filter_conditions = []
    
    if kingdoms and len(kingdoms) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(kingdoms), "defaultPath": "kingdom"}})

    if phylum and len(phylum) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(phylum), "defaultPath": "phylum"}})

    if class_ and len(class_) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(class_), "defaultPath": "class_"}})
    
    if order and len(order) > 0: 
        filter_conditions.append({"queryString": {"query": " OR ".join(order), "defaultPath": "order"}})

    if family and len(family) > 0:
        filter_conditions.append({"queryString": {"query": " OR ".join(family), "defaultPath": "family"}})
    
    results = get_taxonomic_autocomplete_results(
        field="vernacular_name",
        search_term=search,
        filter_conditions=filter_conditions,
        settings=settings
    )

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )   


@router.get(
    "/records/data_providers/",
    response_model=AutocompleteSearchResult,
)
def record_providers_list(
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    query = (
        [{ "$search": { "autocomplete": {"query": search, "path": "value"}}}]
        if search 
        else []
    )

    results = []
    for dataset in get_lookup_data_provider_collection(settings).aggregate(query):
        results.append(dataset['value'])

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )


@router.get(
    "/records/datasets/",
    response_model=AutocompleteSearchResult,
)
def dataset_list(
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    query = (
        [{ "$search": { "autocomplete": {"query": search, "path": "value"}}}]
        if search 
        else []
    )

    results = []
    for dataset in get_lookup_dataset_collection(settings).aggregate(query):
        results.append(dataset['value'])

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )


@router.get(
    "/records/surveys/",
    response_model=AutocompleteSearchResult,
)
def survey_list(
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    query = (
        [{ "$search": { "autocomplete": {"query": search, "path": "value"}}}]
        if search 
        else []
    )

    results = []
    for dataset in get_lookup_survey_collection(settings).aggregate(query):
        results.append(dataset['value'])

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )


@router.get(
    "/records/projects/",
    response_model=AutocompleteSearchResult,
)
def project_list(
    search: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> AutocompleteSearchResult:
    query = (
        [{ "$search": { "autocomplete": {"query": search, "path": "value"}}}]
        if search 
        else []
    )

    results = []
    for dataset in get_lookup_project_collection(settings).aggregate(query):
        results.append(dataset['value'])

    return AutocompleteSearchResult(
        total=len(results),
        results=results
    )


@router.get('/records/{persistent_id}/', status_code=status.HTTP_200_OK, response_model=Record,
            response_model_by_alias=False)
def get_record(persistent_id: str, settings: Settings = Depends(get_settings)) -> Record:
    record_collection = get_record_collection(settings)

    record_dict = record_collection.find_one({'persistent_id': persistent_id})

    if record_dict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Record not found')

    return Record(**record_dict)


@router.post('/records/', response_model=Record, response_model_by_alias=False, dependencies=[Depends(authorizer)])
def create_or_update_record(record: Record, response: Response, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)) \
        -> Record:
    record_collection = get_record_collection(settings)

    if not record.persistent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Record must have non-empty persistent_id')

    # add obfuscated location data if a threat status is defined
    if record.threat_status:
        record.obfuscated_location = record.create_obfuscated_location(lng=record.decimal_longitude,
                                                                       lat=record.decimal_latitude,
                                                                       settings=settings)

    # check if record exists (in order to return the correct response code
    record_exists = record_collection.find_one({'persistent_id': record.persistent_id}) is not None

    # update record if it exists or create if it does not
    record_dict = record_collection.find_one_and_update({'persistent_id': record.persistent_id},
                                                        {'$set': record.mongo_dict()},
                                                        upsert=True, return_document=ReturnDocument.AFTER)

    # return different response code depending on whether record is created or modified
    response.status_code = status.HTTP_201_CREATED if not record_exists else status.HTTP_200_OK

    background_tasks.add_task(on_record_invalidation, settings)
    return Record(**record_dict)


@router.post('/records/bulk-upload/', dependencies=[Depends(authorizer)])
def create_or_update_records(records: List[Record], background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)) -> \
        BulkOperationResult:
    record_collection = get_record_collection(settings)

    if any(not record.persistent_id for record in records):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='All records must have non-empty persistent_id')

    upsert_operations = []
    for record in records:
        if record.threat_status:
            record.obfuscated_location = record.create_obfuscated_location(lng=record.decimal_longitude,
                                                                           lat=record.decimal_latitude,
                                                                           settings=settings)
        upsert_operations.append(UpdateOne({'persistent_id': record.persistent_id}, {'$set': record.mongo_dict()},
                                           upsert=True))
    result = record_collection.bulk_write(upsert_operations)

    background_tasks.add_task(on_record_invalidation, settings)
    return BulkOperationResult(created_count=result.upserted_count, updated_count=result.modified_count)


@router.post('/records/apply_obfuscation_logic/', dependencies=[Depends(authorizer)])
def validate_obfuscated_locations(rerun_persistent_ids: List[str] = None,
                                        rerun_all_records: bool = False,
                                        settings: Settings = Depends(get_settings)) -> BulkOperationResult:

    record_collection = get_record_collection(settings)
    operations = []
    updated = 0
    # get all records with a threat status and evaluate for each record whether obfuscation needs to be performed
    records_with_threat_status = record_collection.find({"threat_status": {"$ne": None}})
    for threatened_record in records_with_threat_status:
        apply_obfuscation = False
        # keeping the entry conditions for applying obfuscation separate for logical clarification
        # and allowing for additional entry conditions
        if rerun_all_records:
            # user defined all records should have obfuscation logic applied
            apply_obfuscation = True
        elif rerun_persistent_ids and threatened_record['persistent_id'] in rerun_persistent_ids:
            # user supplied a list of id's to have obfuscation logic applied
            apply_obfuscation = True
        elif 'obfuscated_location' not in threatened_record or not threatened_record['obfuscated_location']:
            # the record has a threatened status but does not have obfuscation data
            # (probably from a manual change to threat status)
            apply_obfuscation = True
        elif not threatened_record['obfuscated_location']['scale'] == settings.obfuscation_grid_size:
            # the obfuscation information in the record is outdated
            apply_obfuscation = True
        if apply_obfuscation:
            operations.append(UpdateOne({'persistent_id': threatened_record['persistent_id']},
                                        {'$set': {'obfuscated_location': Record.create_obfuscated_location(
                                            lng=threatened_record['decimal_longitude'],
                                            lat=threatened_record['decimal_latitude'],
                                            settings=settings).dict()}}, upsert=True))

    # Removing obfuscation information from records that have had the threat status removed
    newly_delisted_records = record_collection.find({"threat_status": None, "obfuscated_location": {"$ne": None}})
    for delisted_record in newly_delisted_records:
        operations.append(UpdateOne({'persistent_id': delisted_record['persistent_id']}, {'$unset': {'obfuscated_location': ""}}, upsert=True))

    if operations:
        result = record_collection.bulk_write(operations)
        updated = result.modified_count

    return BulkOperationResult(updated_count=updated)


@router.delete("/records/{persistent_id}/", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(authorizer)])
def delete_record(persistent_id: str, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)) -> Response:
    record_collection = get_record_collection(settings)
    record_dict = record_collection.find_one({"persistent_id": persistent_id})

    if record_dict is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Record not found')

    delete_result = record_collection.delete_one({'persistent_id': persistent_id})

    if delete_result.deleted_count == 1:
        background_tasks.add_task(on_record_invalidation, settings)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Record could not be deleted')


@router.delete('/records/', dependencies=[Depends(authorizer)])
def delete_records(persistent_ids: List[str], background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings)) -> \
        BulkOperationResult:
    record_collection = get_record_collection(settings)
    deleted_count = 0

    delete_operations = []
    for persistent_id in persistent_ids:
        delete_operations.append(DeleteOne({'persistent_id': persistent_id}))
    if delete_operations:
        result = record_collection.bulk_write(delete_operations)
        deleted_count = result.deleted_count
        background_tasks.add_task(on_record_invalidation, settings)

    return BulkOperationResult(deleted_count=deleted_count)
