from typing import Literal, Tuple

from pydantic import BaseModel, validator


class Point(BaseModel):
    """
    A GeoJSON Point object

    https://www.mongodb.com/docs/manual/reference/geojson/#point
    """
    type: Literal["Point"]
    # longitude first (positive=East, negative=West), then latitude (positive=North, negative=South)
    coordinates: Tuple[float, float]

    @validator("coordinates")
    # @field_validator("coordinates")
    def validate_coordinates(cls, v: Tuple[float, float]):
        longitude, latitude = v
        if not (-180 <= longitude <= 180) or not (-90 <= latitude <= 90):
            raise ValueError("coordinates are outside acceptable range")
        return v
