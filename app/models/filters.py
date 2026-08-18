from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from bson import ObjectId


class DepositedPlan(BaseModel):
    survey_number: int
    lot_number: int


class FiltersCreate(BaseModel):
    kingdoms: Optional[List[str]] = None
    phylum: Optional[List[str]] = None
    class_: Optional[List[str]] = Field(None, alias="class")
    order: Optional[List[str]] = None
    family: Optional[List[str]] = None
    species: Optional[List[str]] = None
    buffer: Optional[float] = None
    vernacular: Optional[List[str]] = None
    location: Optional[dict] = None
    region: Optional[str] = None
    street_address_id: Optional[str] = None
    land_title_id: Optional[int] = None
    deposited_plan: Optional[DepositedPlan] = None
    data_provider: Optional[List[str]] = None
    dataset: Optional[List[str]] = None
    project: Optional[List[str]] = None
    survey: Optional[List[str]] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    @validator('*', pre=True)
    # @field_validator('*', mode='before')
    def validate_single_location_method(cls, v, values, field):
        # Only validate for location-related fields
        location_fields = ['region', 'location', 'street_address_id', 'land_title_id', 'deposited_plan']
        if field.name not in location_fields:
            return v
            
        # Count how many location fields are provided (including current field if not None)
        provided_fields = []
        for field_name in location_fields:
            field_value = values.get(field_name)
            if field_name == field.name:
                field_value = v
            if field_value is not None:
                provided_fields.append(field_name)
        
        if len(provided_fields) > 1:
            raise ValueError(f"Only one location method can be specified. Found: {', '.join(provided_fields)}")
        
        return v

    class Config:
        allow_population_by_field_name = True


class Filters(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    kingdoms: Optional[List[str]] = None
    phylum: Optional[List[str]] = None
    class_: Optional[List[str]] = Field(None, alias="class")
    order: Optional[List[str]] = None
    family: Optional[List[str]] = None
    species: Optional[List[str]] = None
    vernacular: Optional[List[str]] = None
    location: Optional[dict] = None
    region: Optional[str] = None
    buffer: Optional[float] = None
    street_address_id: Optional[str] = None
    land_title_id: Optional[int] = None
    deposited_plan: Optional[DepositedPlan] = None
    data_provider: Optional[List[str]] = None
    dataset: Optional[List[str]] = None
    project: Optional[List[str]] = None
    survey: Optional[List[str]] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    created_at: datetime

    class Config:
        allow_population_by_field_name = True


class FiltersResponse(BaseModel):
    filter_id: str
