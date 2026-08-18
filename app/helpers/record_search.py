import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from bson import ObjectId

from fastapi import Query
from pydantic import BaseModel, Field, PrivateAttr
from starlette.requests import Request

from app.helpers.authorisation import is_authorised, Permission, get_user_id
from app.helpers.circle_to_polygon import CircleToPolygon
from app.models.common_enums import DataType
from app.settings import Settings
from app.routers import regions
from app.helpers.mongo import get_published_submission_collection, get_cadastre_address, get_cadastre_polygon

from shapely.geometry import shape
from shapely.ops import transform
import pyproj

EARTH_RADIUS = 6378000.0


class Coordinate(BaseModel):
    lat: float = Query(ge=-90, le=90)
    lng: float = Query(ge=-180, le=180)


class RecordSearch(BaseModel):
    """
    Defines Query Parameters for record searching that are common between endpoints.

    Also has helper methods to generate filters from the criteria.
    """
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    json_encoded_area: Optional[str] = None 
    dataset: Optional[List[str]] = None
    survey_name: Optional[List[str]] = None
    project_name: Optional[List[str]] = None
    data_provider: Optional[List[str]] = None
    region_id: Optional[str] = None
    street_address_id: Optional[str] = None
    land_title_id: Optional[int] = None
    deposited_plan_survey_number: Optional[int] = None
    deposited_plan_lot_number: Optional[int] = None
    kingdoms: Optional[List[str]] = None    
    phylum: Optional[List[str]] = None
    class_taxon: Optional[List[str]] = None
    order: Optional[List[str]] = None
    family: Optional[List[str]] = None
    species: Optional[List[str]] = None
    vernacular_name: Optional[List[str]] = None
    submission_id: Optional[str] = None
    submission_set_id: Optional[str] = None
    buffer: Optional[float] = None

    _parsed_area: Optional[Dict[str, Any]] = PrivateAttr(default=None)

    def __init__(self, **data):
        super().__init__(**data)

        if self.json_encoded_area is not None:
            try:
                self._parsed_area = json.loads(self.json_encoded_area)
                assert isinstance(self._parsed_area, dict), "Not a JSON object"
            except Exception as e:
                raise Exception("Could not parse area as JSON object") from e

    @property
    def area(self) -> Optional[Dict[str, Any]]:
        return self._parsed_area

    def get_search_key(self, request: Request, settings: Settings) -> str:
        """
        Used as part of the process for generating a unique key to cache search results

        This method returns a string that represents the search parameters,
        using all available search parameters except area and region_id.

        Parameters:
            request (Request): An object representing the user's request for records.
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            str: string defining the search parameters (excluding area and region)

        Separator schema to identify search parameters and sub-parameters in the key string
        [:] First level
        [#] Second level
        [,] Third level

        Example: user_id:testing:authorised:True:date_from:2023-07-02:date_to:2023-09-01:species:acacia:dataset:b--02
        """
        first: str = ":"
        second: str = "#"
        third: str = ","
        authorised = str(is_authorised(Permission.SENSITIVE, request, settings))
        user_id = str(get_user_id(request, settings))

        def _sanitize_string(data_in: str) -> str:
            # remove all whitespace from the string
            return "".join(data_in.split())

        key_string = first.join(["user_id", user_id, "authorised", authorised])
        if self.date_from:
            date_from = _sanitize_string(self.date_from)
            key_string = first.join([key_string, "date_from", date_from])
        if self.date_to:
            date_to = _sanitize_string(self.date_to)
            key_string = first.join([key_string, "date_to", date_to])
        if self.species:
            species = _sanitize_string("".join(self.species))
            key_string = first.join([key_string, "species", species])
        if self.dataset:
            dataset = _sanitize_string("".join(self.dataset))
            key_string = first.join([key_string, "dataset", dataset])
        if self.survey_name:
            survey_name = _sanitize_string("".join(self.survey_name))
            key_string = first.join([key_string, "survey_name", survey_name])
        if self.project_name:
            project_name = _sanitize_string("".join(self.project_name))
            key_string = first.join([key_string, "project_name", project_name])
        if self.data_provider:
            data_provider = _sanitize_string("".join(self.data_provider))
            key_string = first.join([key_string, "data_provider", data_provider])
        if self.kingdoms:
            kingdoms = second.join(_sanitize_string(k) for k in self.kingdoms)
            key_string = first.join([key_string, "kingdoms", kingdoms])
        if self.submission_id:
            key_string = first.join([key_string, "submission_id", self.submission_id])
        if self.submission_set_id:
            key_string = first.join([key_string, "submission_set_id", self.submission_set_id])
        if self.phylum:
            phylum = _sanitize_string("".join(self.phylum))
            key_string = first.join([key_string, "phylum", phylum])
        if self.class_taxon:
            class_taxon = _sanitize_string("".join(self.class_taxon))
            key_string = first.join([key_string, "class", class_taxon])
        if self.order:  # noqa: E501
            order = _sanitize_string("".join(self.order))
            key_string = first.join([key_string, "order", order])
        if self.family:
            family = _sanitize_string("".join(self.family))
            key_string = first.join([key_string, "family", family])
        if self.vernacular_name:
            vernacular_name = _sanitize_string("".join(self.vernacular_name))
            key_string = first.join([key_string, "vernacular_name", vernacular_name])
        if self.street_address_id:
            key_string = first.join([key_string, "street_address_id", self.street_address_id])
        if self.land_title_id:
            key_string = first.join([key_string, "land_title_id", str(self.land_title_id)])
        if self.deposited_plan_survey_number:
            key_string = first.join([key_string, "dp_survey", str(self.deposited_plan_survey_number)])
        if self.deposited_plan_lot_number:
            key_string = first.join([key_string, "dp_lot", str(self.deposited_plan_lot_number)])
        if self.buffer:
            key_string = first.join([key_string, "buffer", str(self.buffer)])

        return key_string

    @staticmethod
    def _flatten_nested_list(nested_list: Dict[str, Any]) -> List[Any]:
        """
        Used as part of the process for generating a unique key to cache search results

        Extracts nested list elements into a flat list

        Parameters:
            nested_list (Dict[str, Any]): A nested list containing elements to be flattened.

        Returns:
            List[Any]: A flat list containing all the elements from the input nested list.


        This method was created to unpack geojson polygon or point descriptions (example: List[List[List[float]]]) into
        a format that can be used for creating a descriptive string to uniquely identify the location.
        """
        flat_list = []

        def recursive_flatten(nested_element):
            if isinstance(nested_element, list):
                for item in nested_element:
                    recursive_flatten(item)
            else:
                flat_list.append(nested_element)

        recursive_flatten(nested_list)
        return flat_list

    def get_search_key_area_scaled(self) -> Optional[str]:
        """
        Used as part of the process for generating a unique key to cache search results

        Extracts search area gps coordinates

        Returns:
            str: string defining the search area

        Returns a string representation of absolute values used for the search area coordinates.
        This method is only used when the search area is defined by the scaled viewport parameters.
        Using this method with any other area format may result in extreemly long strings.

        Example: polygon#location_representation#117.0,29.0,113.0,29.0,113.0,32.0,117.0,32.0,117.0,29.0
        """
        first: str = ":"
        second: str = "#"
        third: str = ","

        if self.area and 'geojson_feature' in self.area:
            location = self._flatten_nested_list(self.area['geojson_feature']['geometry']['coordinates'])
            if location:
                data_points = [str(abs(num)) for num in location]
                location_representation = third.join(data_points)
                coordinates = second.join(['location_representation', location_representation])
                area = second.join(['polygon', coordinates])
                return area
        return None

    def get_search_key_area(self) -> Optional[str]:
        """
        Used as part of the process for generating a unique key to cache search results

        Generates a compact unique string for user defined search areas (region, polygon, circle)

        Returns:
            str: string defining the search area

        This method should be used where the search area is specified by the user.

        Method: GPS coordinates are converted into a hash-like semi-unique number value by summing the absolute values
        of all GPS coordinates provided in the search criteria.

        Output descriptions:
            Region: Uses the mongodb id number for the specified region
            Polygon: Uses the unique coordinate value
            Circle: Uses the unique coordinate value and radius

        Examples:
            Region: region#64d08b07b1200228eee628c3
            Polygon: location_representation#890.2428130659893
            Circle: location_representation#144.3653810262292#radius#422057.66323236836
        """
        first: str = ":"
        second: str = "#"
        third: str = ","

        if self.region_id:
            area = second.join(["region", self.region_id])
            return area
        elif self.street_address_id:
            area = second.join(["street_address", self.street_address_id])
            return area
        elif self.land_title_id:
            area = second.join(["land_title", str(self.land_title_id)])
            return area
        elif self.deposited_plan_survey_number and self.deposited_plan_lot_number:
            area = second.join(["deposited_plan", str(self.deposited_plan_survey_number), str(self.deposited_plan_lot_number)])
            return area
        elif self.area:
            if 'geojson_feature' in self.area:
                location = self._flatten_nested_list(self.area['geojson_feature']['geometry']['coordinates'])
                if location:
                    location_representation = str(sum([abs(num) for num in location]))
                    coordinates = second.join(['location_representation', location_representation])
                    if 'radius' in self.area:
                        # format example [area:circle#location_representation#43.5735081#radius#56.7]
                        data_point = str(self.area['radius'])
                        radius = second.join(['radius', data_point])
                        area = second.join(['circle', coordinates, radius])
                        return area
                    else:
                        # format example [area:polygon#location_representation#743.5735081474995]
                        area = second.join(['polygon', coordinates])
                        return area



    def get_record_filter(
        self,
        settings: Settings,
        *,
        include_threatened_records: bool,
        include_restricted_records: bool,
    ) -> Dict[str, Any]:
        """
        Returns a combined filter for searching groups of records based on the given request and settings.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.
            include_threatened_records: If threatened records will be matched by the returned filter.

        Returns:
            Dict[str, Any]: A dictionary representing the combined filter to search for groups of records.
        """
        search_filter = self._generate_filters_search_parameters(settings=settings)
        spatial_filter = self._generate_filters_spatial_specific(settings=settings)
        # turn the search and spacial filter dictionaries into a single dict
        combined_filter = {**search_filter, **spatial_filter}
        if not include_threatened_records:
            # Add filter to exclude threatened species if not included.
            combined_filter['threat_status'] = {'threat_status': None}
        if not include_restricted_records:
            # Add filter to exclude restricted species if not included.
            combined_filter['restricted'] = {'restricted': {"$ne": True}}

        # Overall search, spatial, and threat status filters should be "and"ed together
        record_filter = self._join_filters_with_operator(combined_filter, '$and')

        return record_filter

    def get_species_list_filter(self, request: Request, settings: Settings) -> Dict[str, Any]:
        """
        Returns a filter for searching for a list of observed species based on the given request and settings.

        Parameters:
            request (Request): An object representing the user's request for records.
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the combined filter to search for groups of records.
        """
        authorised = is_authorised(Permission.SENSITIVE, request, settings)

        # generate common filter groups
        #
        # filter for user specified search criteria (species, timeframe, dataset, etc)
        search_filter = self._generate_filters_search_parameters(settings=settings)

        # filter for specific spatial location search (uses $geoNear or $geoWithin with the observed location point)
        spatial_filter_specific = self._generate_filters_spatial_specific(settings=settings)
        if not spatial_filter_specific:
            # no location provided for search parameters, authorised and un-authorised users both use the same results
            non_spatial_filter_components = {**search_filter}
            non_spatial_filter = self._join_filters_with_operator(non_spatial_filter_components, '$and')

            return non_spatial_filter

        if not authorised:
            # generate unauthorised filter groups
            # This filter uses a somewhat complicated process to search for specific locations of non-threatened species
            # and obfuscated locations of threatened species, while also accounting for search parameters provided by
            # the user. The formula for creating the filter is:
            # filter = search-criteria AND ((not-threatened AND specific-location) OR (obfuscated-location))

            # filter creation for segment: (obfuscated-location)
            spatial_filter_obfuscated = self._generate_filters_spatial_obfuscated(settings=settings)

            # filter creation for segment: (not-threatened AND specific-location)
            unauthorised_specific_components = {**spatial_filter_specific,
                                                'threat_status': {'threat_status': None}}
            unauthorised_specific = self._join_filters_with_operator(unauthorised_specific_components, '$and')

            # filter creation for segment: (not-threatened AND specific-location) OR (obfuscated-location)
            location_filter_components = {'specific': unauthorised_specific,
                                          **spatial_filter_obfuscated}
            unauthorised_location_filter = self._join_filters_with_operator(location_filter_components, '$or')

            # final filter: search-criteria AND ((not-threatened AND specific-location) OR (obfuscated-location))
            unauthorised_filter_components = {**search_filter, "location": unauthorised_location_filter}
            unauthorised_filter = self._join_filters_with_operator(unauthorised_filter_components, '$and')

            return unauthorised_filter
        else:
            # Combine authorised filter groups
            authorised_filter_components = {**search_filter, **spatial_filter_specific}
            authorised_filter = self._join_filters_with_operator(authorised_filter_components, '$and')

            return authorised_filter

    def _generate_filters_search_parameters(self, *, settings: Settings) -> Dict[str, Any]:
        """Generate a filter for non-spatial elements of the search parameters.

        Returns:
            Dict[str, Any]: A dictionary representing the filter for non-spatial search parameters.
        """
        filters: Dict[str, Any] = {}

        if self.submission_id:
            filters["submission_id"] = {"submission_id": self.submission_id}
        if self.submission_set_id:
            # Translate the submission set ID to a list of submission IDs to filter by.
            # This is required because Records don't have a submission_set_id field.
            submissions_collection = get_published_submission_collection(settings)
            submissions_cursor = submissions_collection.find(
                filter={
                    "submission_set_id": self.submission_set_id,
                    "persistent_id": {"$ne": None},
                },
                projection=["persistent_id"],
            )
            submission_ids = [row["persistent_id"] for row in submissions_cursor]
            filters["submission_set_id"] = {"submission_id": {"$in": submission_ids}}

        if self.species:
            filters['species'] = {
                '$or': [
                    {
                        'accepted_name_usage': {'$in': self.species}
                    },
                    {
                        'scientific_name': {'$in': self.species}
                    },
                    {
                        'verbatim_identification': {'$in': self.species}
                    },
                    
                ]
            }

        if self.data_provider:
            filters['data_provider'] = {
                    'institution_code': { "$in": self.data_provider }
            }
        if self.dataset:
            filters['dataset'] = {
                'dcterms_title': { "$in": self.dataset },
                # Only for SPECIES_OCCURRENCE records is the dcterms_title field populated from dataset.
                "datatype": {"$in": [DataType.SPECIES_OCCURRENCE.value, None]},
            }
        if self.survey_name:
            filters['survey_name'] = {
                'submission_name': { "$in": self.survey_name },
                # Only for SYSTEMATIC_SURVEY records
                # is the submission_name field populated from survey name.
                "datatype": DataType.SYSTEMATIC_SURVEY.value,
            }
        if self.project_name:
            filters['project_name'] = {
                'submission_set_name': { "$in": self.project_name },
                # Only for SYSTEMATIC_SURVEY records
                # is the submission_set_name field populated from project name.
                "datatype": DataType.SYSTEMATIC_SURVEY.value,
            }

        if self.kingdoms:
            filters['kingdom'] = {
                'kingdom': {'$in': self.kingdoms}
            }
        if self.phylum:
            filters['phylum'] = {
                'phylum': {'$in': self.phylum}
            }
        if self.class_taxon:
            filters['class_'] = {
                'class_': {'$in': self.class_taxon}
            }
        if self.order:
            filters['order'] = {
                'order': {'$in': self.order}
            }
        if self.family:
            filters['family'] = {
                'family': {'$in': self.family }
            }
        if self.vernacular_name:
            filters['vernacular_name'] = {
                'vernacular_name': {'$in': self.vernacular_name}
            }
        date_searching = {}
        if self.date_to:
            # need to add a day to the date_to so that the search includes records within that day
            date_to = datetime.fromisoformat(self.date_to)
            date_to += timedelta(days=1)
            date_searching['$lt'] = date_to.strftime('%Y-%m-%d')
        if self.date_from:
            date_searching['$gte'] = self.date_from
        if bool(date_searching):
            filters['event_date'] = {
                'event_date': date_searching
            }

        return filters

    def _spatial_bounds_regions(self, settings: Settings) -> Optional[Dict[str, Any]]:
        """Generate a sub-filter for the location specified by region.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the sub-filter for the specified region's location.
        """
        if self.region_id is None:
            return None
        geojson = regions.get_region(self.region_id, settings)['geojson']
        bounds = None
        if geojson:
            geometry = geojson['geometry']
            if self.buffer:
                geometry = self._apply_buffer_to_geometry(geometry)
            bounds = {
                '$geometry': geometry
            }
        return bounds

    def _spatial_bounds_street_address(self, settings: Settings) -> Optional[Dict[str, Any]]:
        """Generate a sub-filter for the location specified by street address ID.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the sub-filter for the specified street address location.
        """
        if self.street_address_id is None:
            return None
        address = get_cadastre_address(settings).find_one({"_id": ObjectId(self.street_address_id)})
        if address and 'geometry' in address:
            geometry = address['geometry']
            if self.buffer:
                geometry = self._apply_buffer_to_geometry(geometry)
            return {
                '$geometry': geometry
            }
        return None

    def _spatial_bounds_land_title(self, settings: Settings) -> Optional[Dict[str, Any]]:
        """Generate a sub-filter for the location specified by land title ID.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the sub-filter for the specified land title location.
        """
        if self.land_title_id is None:
            return None
        land_title = get_cadastre_polygon(settings).find_one({"properties.land_id": self.land_title_id})
        if land_title and 'geometry' in land_title:
            geometry = land_title['geometry']
            if self.buffer:
                geometry = self._apply_buffer_to_geometry(geometry)
            return {
                '$geometry': geometry
            }
        return None

    def _spatial_bounds_deposited_plan(self, settings: Settings) -> Optional[Dict[str, Any]]:
        """Generate a sub-filter for the location specified by deposited plan survey and lot numbers.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the sub-filter for the specified deposited plan location.
        """
        if self.deposited_plan_survey_number is None or self.deposited_plan_lot_number is None:
            return None
        dp = get_cadastre_polygon(settings).find_one({
            "properties.survey_number": self.deposited_plan_survey_number,
            "properties.lot_number": self.deposited_plan_lot_number
        })
        if dp and 'geometry' in dp:
            geometry = dp['geometry']
            if self.buffer:
                geometry = self._apply_buffer_to_geometry(geometry)
            return {
                '$geometry': geometry
            }
        return None

    def _spatial_bounds_area(self, use_obfuscated_location: bool) -> Optional[Dict[str, Any]]:
        """Generate a sub-filter for the location specified by the area.

        Parameters:
            use_obfuscated_location (bool): A flag indicating whether to use obfuscated location search or specific location search.

        Returns:
            Dict[str, Any]: A dictionary representing the sub-filter for the specified area's location.
       """
        area = self.area
        bounds = None
        if area and 'geojson_feature' in area:
            bounds = {}
            if 'radius' in area:
                if use_obfuscated_location:
                    area_lng = float(area['geojson_feature']['geometry']['coordinates'][0])
                    area_lat = float(area['geojson_feature']['geometry']['coordinates'][1])
                    area_radius_km = float(area['radius'])/1000

                    # Obfuscated location search uses $geoIntersects which requires polygon $geometry
                    center = Coordinate(lng=area_lng, lat=area_lat)
                    coordinates = CircleToPolygon.generate_polygon_points(center_lon=center.lng,
                                                                                  center_lat=center.lat,
                                                                                  radius_km=area_radius_km)
                    bounds['$geometry'] = {'type': 'Polygon', 'coordinates': [coordinates]}
                else:
                    # Specific location search uses $geoWithin which can use $centerSphere
                    # search distance is measured in RADIANS so need to divide distance by radius of the Earth first
                    bounds['$centerSphere'] = [area['geojson_feature']['geometry']['coordinates'],
                                               area['radius'] / EARTH_RADIUS]

            else:
                # avoid zero length geometry loops
                # this can happen if the front end passes through a 'cleared' poly.
                geometry = area['geojson_feature']['geometry']
                if geometry['type'] == 'Point' or (
                    geometry['type'] in ['Polygon', 'MultiPolygon', 'LineString'] and 
                    all(len(c) for c in geometry['coordinates'] if isinstance(c, list))
                ):
                    if self.buffer:
                        geometry = self._apply_buffer_to_geometry(geometry)
                    bounds['$geometry'] = geometry
        return bounds

    def _generate_filters_spatial_specific(self, settings: Settings) -> Dict[str, Any]:
        """Generate spatial filters for specific location searches using observation precise GPS coordinates.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the spatial filters for specific location searches.
        """
        filters: Dict[str, Any] = {}

        # searching by area may be specified by either a point/radius, polygon or a pre-defined polygonal region
        bounds = None
        if self.region_id is not None:
            bounds = self._spatial_bounds_regions(settings=settings)
        elif self.street_address_id is not None:
            bounds = self._spatial_bounds_street_address(settings=settings)
        elif self.land_title_id is not None:
            bounds = self._spatial_bounds_land_title(settings=settings)
        elif self.deposited_plan_survey_number is not None and self.deposited_plan_lot_number is not None:
            bounds = self._spatial_bounds_deposited_plan(settings=settings)
        elif self.area:
            bounds = self._spatial_bounds_area(use_obfuscated_location=False)

        # If there were loop errors, bounds will be empty, so don't use it.
        if bounds is not None and ('$geometry' in bounds or '$centerSphere' in bounds):
            filters['bounds'] = {
                'location': {
                    "$geoWithin": bounds
                }
            }
        return filters

    def _generate_filters_spatial_obfuscated(self, settings: Settings) -> Dict[str, Any]:
        """Generate spatial filters for obfuscated location searches using threatened observation bounding boxes.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            Dict[str, Any]: A dictionary representing the spatial filters for obfuscated location searches.
       """
        filters: Dict[str, Any] = {}

        # searching by area may be specified by either a point/radius, polygon or a pre-defined polygonal region
        bounds = None
        if self.region_id is not None:
            bounds = self._spatial_bounds_regions(settings=settings)
        elif self.street_address_id is not None:
            bounds = self._spatial_bounds_street_address(settings=settings)
        elif self.land_title_id is not None:
            bounds = self._spatial_bounds_land_title(settings=settings)
        elif self.deposited_plan_survey_number is not None and self.deposited_plan_lot_number is not None:
            bounds = self._spatial_bounds_deposited_plan(settings=settings)
        elif self.area:
            bounds = self._spatial_bounds_area(use_obfuscated_location=True)

        # If there were loop errors, bounds will be empty, so don't use it.
        if bounds is not None and ('$geometry' in bounds):
            filters['bounds'] = {
                'obfuscated_location.bounding_box': {
                    "$geoIntersects": bounds
                }
            }
        return filters

    @staticmethod
    def _join_filters_with_operator(filters: Dict[str, Any], operator: str) -> Dict[str, Any]:
        """
        Apply a logical operator to a list of filter values and return the joined filter.

        Parameters:
            filters (Dict[str, Any]): A dictionary containing filter values in 'key:val' format.
            operator (str): The logical operator to be applied for joining the filter values ($and, $or, etc.).

        Returns:
            Dict[str, Any]: A dictionary representing the joined filter.

        This method applies a logical operator to a list of filter values provided in the 'filters' dictionary.

        Parameters:
        - 'filters': A dictionary containing the filter values, where the keys represent the filter names
            and the values are the filter conditions.
        - 'operator': The logical operator to be applied for joining the filter values.
            The valid operator values are dependent on the context and the database system being used.

        The method extracts the filter values from the 'filters' dictionary and creates a list of these values.
        If the list contains more than one element, it generates a new dictionary with the specified 'operator'
        as the key and the filter values as the value. If there is only one element in the list, the method returns
        that element directly as the joined filter. If the list is empty, it returns an empty dictionary.

        The generated joined filter is intended to be used as a component of a larger filter for searching records with logical
        conditions combined using the specified operator.
        """
        filter_values = [val for key, val in filters.items()]
        if len(filter_values) > 1:
            return {
                operator: filter_values
            }
        elif len(filter_values) == 1:
            return filter_values[0]
        else:
            return {}

    def get_search_area_summary(self, settings: Settings) -> str:
        """
        Get a summary of the search area based on the provided location search criteria.

        Parameters:
            settings (Settings): An object containing the settings for record filtering.

        Returns:
            str: A string representing the summary of the search area.
        """
        summary = "Not defined."
        if self.region_id:
            region = regions.get_region_collection(settings).find_one({"_id": ObjectId(self.region_id.strip())})
            if region:
                if 'source' in region and region['source'] and len(region['source']):
                    summary = f"Region: {region['name']} ({region['source']})"
                else:
                    summary = f"Region: {region['name']}"
        elif self.street_address_id:
            address = get_cadastre_address(settings).find_one({"_id": ObjectId(self.street_address_id)})
            if address and 'properties' in address and 'display_address' in address['properties']:
                summary = f"Street Address: {address['properties']['display_address']}"
            else:
                summary = f"Street Address: {self.street_address_id}"
        elif self.land_title_id:
            summary = f"Land Title: {self.land_title_id}"
        elif self.deposited_plan_survey_number and self.deposited_plan_lot_number:
            summary = f"Deposited Plan: Survey {self.deposited_plan_survey_number}, Lot {self.deposited_plan_lot_number}"
        elif self.area:
            if 'geojson_feature' in self.area:
                if 'radius' in self.area:
                    name = "User defined circle: "
                    coordinates = f"[{self.area['geojson_feature']['geometry']['coordinates']}] "
                    radius = f"{float(self.area['radius']) / 1000} km."
                    summary = name + coordinates + radius
                else:
                    name = "User defined polygon: "
                    coordinates = f"[{self.area['geojson_feature']['geometry']['coordinates']}]."
                    summary = name + coordinates
        
        if self.buffer and self.buffer > 0:
            summary += f" (buffered by {self.buffer}m)"
        
        return summary

    def _apply_buffer_to_geometry(self, geometry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply buffer to a GeoJSON geometry using shapely.
        
        Parameters:
            geometry (Dict[str, Any]): GeoJSON geometry dict
            
        Returns:
            Dict[str, Any]: Buffered GeoJSON geometry dict
        """
        if not self.buffer or self.buffer <= 0:
            return geometry
            
        try:
            # Convert GeoJSON to shapely geometry
            geom = shape(geometry)
            
            # Create a local UTM projection for accurate buffering in meters
            # Using WGS84 to UTM transformation for the centroid
            centroid = geom.centroid
            utm_crs = pyproj.CRS.from_epsg(
                32600 + int((centroid.x + 180) / 6) + 1 if centroid.y >= 0 
                else 32700 + int((centroid.x + 180) / 6) + 1
            )
            
            # Set up transformations
            wgs84 = pyproj.CRS('EPSG:4326')
            project_to_utm = pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True).transform
            project_to_wgs84 = pyproj.Transformer.from_crs(utm_crs, wgs84, always_xy=True).transform
            
            # Transform to UTM, apply buffer, transform back to WGS84
            utm_geom = transform(project_to_utm, geom)
            buffered_utm = utm_geom.buffer(self.buffer)
            buffered_wgs84 = transform(project_to_wgs84, buffered_utm)
            
            # Convert back to GeoJSON geometry
            return buffered_wgs84.__geo_interface__
            
        except Exception as e:
            # If buffering fails, return original geometry
            return geometry

    def get_search_parameters_summary(self) -> str:
        """
        Generate a summary string of search parameters.

        Search parameters 'area' and 'region_id' are excluded and summarised in the area summary.

        Returns:
        str: A formatted string containing search parameters and their values.
        """
        summary_parts = []

        if self.submission_id:
            summary_parts.append("submission_id: " + str(self.submission_id))
        if self.submission_set_id:
            summary_parts.append("submission_set_id: " + str(self.submission_set_id))
        if self.date_from:
            summary_parts.append("date_from: " + str(self.date_from))
        if self.date_to:
            summary_parts.append("date_to: " + str(self.date_to))
        if self.species:
            summary_parts.append("species: " + str(self.species))
        if self.dataset:
            summary_parts.append("dataset: " + str(self.dataset))
        if self.survey_name:
            summary_parts.append("survey: " + str(self.survey_name))
        if self.project_name:
            summary_parts.append("project: " + str(self.project_name))
        if self.data_provider:
            summary_parts.append("data_provider: " + str(self.data_provider))
        if self.kingdoms:
            summary_parts.append("kingdoms: " + str(self.kingdoms))
        if self.phylum:
            summary_parts.append("phylum: " + str(self.phylum))
        if self.class_taxon:
            summary_parts.append("class: " + str(self.class_taxon))
        if self.order:
            summary_parts.append("order: " + str(self.order))
        if self.family:
            summary_parts.append("family: " + str(self.family))
        if self.vernacular_name:
            summary_parts.append("vernacular_name: " + str(self.vernacular_name))
        if self.buffer:
            summary_parts.append("buffer: " + str(self.buffer) + "m")
            
        return ", ".join(summary_parts)



class SpeciesListPipeline(BaseModel):
    # Pipeline segments for mongodb species list
    # Step 1: Use the provided search filter to select the desired database entries
    @staticmethod
    def _pipe_match(search_filter: Dict[str, Any]) -> Dict[str, Any]:
        """Static method to generate the match filter at runtime."""
        return {'$match': search_filter}

    # Step 2: Use the $group functionality to eliminate duplicate records
    # Fields in _id are used for uniqueness testing during grouping
    # Fields outside _id are added to the aggregation with $first to make the fields available for further pipline steps
    _pipe_group = {
        '$group': {
            '_id': {
                'accepted_name_usage': '$accepted_name_usage'
            },
            'scientific_name': {'$first': '$scientific_name'},
            'scientific_name_authorship': {'$first': '$scientific_name_authorship'},
            'verbatim_identification': {'$first': '$verbatim_identification'},
            'nomos_id': {
                '$first': {
                    '$ifNull': [
                        '$NomosID',
                        {'$ifNull': ['$nomos_id', '$nomosID']}
                    ]
                }
            },
            'dwc:kingdom': {'$first': '$kingdom'},
            'dwc:phylum': {'$first': '$phylum'},
            'dwc:class': {'$first': '$class_'},
            'dwc:order': {'$first': '$order'},
            'dwc:family': {'$first': '$family'},
            'dwc:vernacularName': {'$first': '$vernacular_name'},
            'threat_status': {'$first': '$threat_status'},
            'establishment_means': {'$first': '$establishment_means'}
        }
    }

    # Step 3: Include the data columns we need for the results
    _pipe_project = {
        '$project': {
            '_id': 0,
            'accepted_name_usage': '$_id.accepted_name_usage',
            'scientific_name': 1,
            'scientific_name_authorship': 1,
            'verbatim_identification': 1,
            'nomos_id': 1,
            'dwc:kingdom': 1,
            'dwc:phylum': 1,
            'dwc:class': 1,
            'dwc:order': 1,
            'dwc:family': 1,
            'dwc:vernacularName': 1,
            'threat_status': 1,
            'establishment_means': 1
        }
    }

    # Step 4: Sort the results alphabetically by name for logical pagination and display
    _pipe_sort = {
        '$sort': {
            'dwc:kingdom': 1,
            'dwc:class': 1,
            'dwc:family': 1,
            'accepted_name_usage': 1
        }
    }

    # Step 5.a: Apply pagination skip
    @staticmethod
    def _pipe_skip(offset: int):
        """Static method to generate the skip filter at runtime."""
        return {'$skip': offset}

    # Step 5.b: Apply pagination limit
    @staticmethod
    def _pipe_limit(limit: int):
        """Static method to generate the limit filter at runtime."""
        return {'$limit': limit}

    @classmethod
    def faceted_pipeline(cls, species_list_filter: Dict[str, Any], offset: int, limit: int) -> List[Dict[str, Any]]:
        """
        Creates a $facet pipeline for a species list with pagination.

        Parameters:
            species_list_filter (Dict[str, Any]): A dictionary representing the search filter for the species list.
            offset (int): The offset value for pagination, indicating the number of documents to skip.
            limit (int): The limit value for pagination, indicating the maximum number of documents to retrieve.

        Returns:
            List[Dict[str, Any]]: A list containing the faceted pipeline for species list with pagination.
        """
        # Generate process steps for multiple independent actions
        # Process step: Use steps 1 and 2 to make a pipeline to get the total number of records that can be generated
        # for the species list based on the provided search filter
        pipeline_count = [cls._pipe_group]
        # Process step: Use steps 1 - 5 to generate results for the species list based on the provided search filter
        # and the specified pagination settings
        pipeline_results = [cls._pipe_group,
                            cls._pipe_project,
                            cls._pipe_sort,
                            cls._pipe_skip(offset=offset),
                            cls._pipe_limit(limit=limit)]

        # Generate final pipeline command to utilise $facet functionality to allow multiple pipelines to be executed
        # concurrently to create a segment of paginated results and a count for total results from the query filter.
        # Pipeline Structure:
        # - 'results': Stores the paginated results of the main data processing pipeline.
        # - 'count': Stores the total count of documents that match the specified filter criteria.
        # Pipeline Components:
        # - 'pipeline_results': Performs multiple steps to generate the species list output results
        # - 'pipeline_count': Determines the total count of documents without applying pagination or limiting.
        faceted_pipeline = [
            cls._pipe_match(search_filter=species_list_filter), 
            {
                '$facet': {
                    'species_list_results': pipeline_results,
                    'total_query_results_count': pipeline_count + [{'$count': 'total_count'}]
                }
            }
        ]
        return faceted_pipeline

    @classmethod
    def simplified_pipeline(cls, species_list_filter: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Creates a simple pipeline for species list export.

        Parameters:
            species_list_filter (Dict[str, Any]): A dictionary representing the search filter for the species list.

        Returns:
            List[Dict[str, Any]]: A list containing the simplified pipeline for species list export.
        """
        # Generate pipeline for querying all results without pagination
        # Process step: Use steps 1 - 4 to generate results for the species list based on the provided search filter
        simple_pipeline = [cls._pipe_match(search_filter=species_list_filter),
                           cls._pipe_group,
                           cls._pipe_project,
                           cls._pipe_sort]

        return simple_pipeline
