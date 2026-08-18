from os import path
from typing import Tuple, Union, Collection, FrozenSet, Mapping

from app.models.supporting_files import SupportingFile
from app.models.common_enums import DocumentType
from app.readers.file_readers import CSVFileReader, ExcelFileReader, ShapeFileReader
from app.settings import Settings
from app.validators.file_validators import CSVFileValidator, ExcelFileValidator, ShapeFileValidator


_ALL_FILE_TYPES: FrozenSet[str] = frozenset(
    {
        # usable as record data
        "csv", "xlsx", "xlsm", "zip",
        # images
        "jpeg", "jpg", "png",
        # documents
        "pdf", "doc", "docx", "odt", "ppt", "pptx",
        # other
        "shp",  "xml", "json", "geojson", "txt",
    }
)


_DOCUMENT_TYPE_ALLOWED_FILE_TYPES: Mapping[DocumentType, Collection[str]] = {
    DocumentType.RECORD_DATA: frozenset({"csv", "xlsx", "xlsm", "zip"}),
    DocumentType.REPORT: _ALL_FILE_TYPES,
    DocumentType.SITE_DATA: _ALL_FILE_TYPES,
    # SUPPLEMENTARY_DOCUMENTATION should allow all file types that are allowed by the other document types
    DocumentType.SUPPLEMENTARY_DOCUMENTATION: _ALL_FILE_TYPES,
}


def accepted_file_types(document_type: DocumentType) -> Collection[str]:
    """Get the accepted file types (extensions) for a given document type."""
    return _DOCUMENT_TYPE_ALLOWED_FILE_TYPES[document_type]


def validate_and_get_sample_record_data(
    *,
    supporting_file: SupportingFile,
    settings: Settings,
) -> Tuple[Union[dict, None], Union[dict, None]]:
    """
    Validate a supporting file that is being used as RECORD_DATA, and if successful get a sample data row.

    :return: Tuple of (errors, None) or (None, sample_data)
    """
    file_path = path.join(settings.temp_file_storage_path, supporting_file.internal_file_name)
    file_extension = supporting_file.file_extension
    if file_extension == "csv":
        validator = CSVFileValidator(file_path)
        reader = CSVFileReader(file_path)
    elif file_extension == 'xlsx' or file_extension == 'xlsm':
        validator = ExcelFileValidator(file_path)
        reader = ExcelFileReader(file_path)
    elif file_extension == 'zip':
        geometry_types = ['POINT', 'POINTZ']
        validator = ShapeFileValidator(file_path, geometry_types)
        reader = ShapeFileReader(file_path)
    else:
        raise Exception(
            "Unexpected file type. _DOCUMENT_TYPE_ALLOWED_FILE_TYPES allowed type not handled here"
        )

    validator.validate()
    if not validator.is_valid:
        return validator.errors, None
    else:
        return None, reader.get_data_sample()


def uniquify(settings: Settings, filepath: str) -> str:
    """
    Take a filepath and "uniquify" it so that it reflects a path not currently used.

    This will return the input path unchanged, if that path is not currently used.
    This is used to generate filepaths for uploaded files that are guaranteed not to overwrite an existing file.
    Input and output paths are relative to settings.temp_file_storage_path.
    """
    root, extension = path.splitext(filepath)
    counter = 0

    while path.exists(path.join(settings.temp_file_storage_path, filepath)):
        counter += 1
        filepath = f"{root}({counter}){extension}"

    return filepath
