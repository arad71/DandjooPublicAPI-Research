from enum import Enum


class DataType(str, Enum):
    SPECIES_OCCURRENCE = 'Species occurrence data'
    SYSTEMATIC_SURVEY = 'Systematic survey data'
    VEGETATION_ASSOCIATION = 'Vegetation association data'


class DocumentType(str, Enum):
    """Each survey supporting file is labelled with a type from this enum."""
    RECORD_DATA = "RECORD_DATA"
    REPORT = "REPORT"
    SITE_DATA = "SITE_DATA"
    SUPPLEMENTARY_DOCUMENTATION = "SUPPLEMENTARY_DOCUMENTATION"
