from datetime import datetime

from app.models.submission import Mappings, SpreadsheetMappings
from app.validators.utils import get_model_required_fields_values, is_float_string, is_int_string

DATE_FIELD_NAME = 'date_observed_collected'
LATITUDE_FIELD_NAME = 'latitude'
LONGITUDE_FIELD_NAME = 'longitude'
EASTING_FIELD_NAME = 'easting'
NORTHING_FIELD_NAME = 'northing'
ZONE_FIELD_NAME = 'zone'

VALID_DATE_FORMATS = ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S%z',
                      '%Y-%m-%dT%H:%M:%S', '%d.%m.%Y', '%d/%m/%Y', '%d %b %Y', '%d.%m.%y', '%d/%m/%y', '%d %b %y')
VALID_ZONES = ['49', '50', '51', '52']

MANDATORY_FIELD_ERROR = 'Mandatory field error'
INVALID_DATE_ERROR = 'Invalid date error'
INVALID_LOCATION_ERROR = 'Invalid location error'


class DataValidator:
    def __init__(self, mappings: Mappings, records: iter, is_spreadsheet=True):
        self._mappings = mappings
        self._mandatory_field_names_values = get_model_required_fields_values(self._mappings)
        self._records = records
        self._is_spreadsheet = is_spreadsheet
        self._errors = None

    def _add_non_record_error(self, error):
        self._errors.append(error)

    def _add_record_error(self, source_record_index, error):
        record_type = 'Row' if self._is_spreadsheet else 'Feature'

        self._errors.append(f'{record_type} {source_record_index}: {error}')

    def _add_record_field_error(self, source_record_index, source_record_field, error):
        record_type, field_type = ('Row', 'header') if self._is_spreadsheet else ('Feature', 'attribute')

        self._errors.append(f'{record_type} {source_record_index}: {error} for {field_type} {source_record_field}')

    def validate(self) -> list:
        self._errors = []

        has_data_records = False
        first_record_index = 2 if self._is_spreadsheet else 1
        for index, record in enumerate(self._records, first_record_index):
            # check record is not empty or have at least one value not None
            if bool(record) and any([val is not None for val in list(record.values())]):
                has_data_records = True
            else:
                # occasionally reader iterates through empty rows after the data rows, so skip these rows
                continue

            self.validate_record(record, index)

        if not has_data_records:
            missing_data_message = 'Source file must contain data'
            if self._is_spreadsheet:
                missing_data_message = missing_data_message + ' (excluding header row)'

            self._add_non_record_error(missing_data_message)

        return self._errors

    def validate_record(self, source_record: dict, source_record_index: int) -> list:
        missing_mandatory_fields = self.validate_mandatory_fields(source_record, source_record_index)

        if DATE_FIELD_NAME not in missing_mandatory_fields:
            self.validate_date_field(source_record, source_record_index)

        # spreadsheet sources (CSV / Excel) require testing mapping against location fields
        if isinstance(self._mappings, SpreadsheetMappings):
            if isinstance(self._mappings.location, SpreadsheetMappings.GeographicLocationMappings):
                if LATITUDE_FIELD_NAME not in missing_mandatory_fields:
                    self.validate_latitude(source_record, source_record_index)
                if LONGITUDE_FIELD_NAME not in missing_mandatory_fields:
                    self.validate_longitude(source_record, source_record_index)
            if isinstance(self._mappings.location, SpreadsheetMappings.GeometricLocationMappings):
                if EASTING_FIELD_NAME not in missing_mandatory_fields:
                    self.validate_easting(source_record, source_record_index)
                if NORTHING_FIELD_NAME not in missing_mandatory_fields:
                    self.validate_northing(source_record, source_record_index)
                if ZONE_FIELD_NAME not in missing_mandatory_fields:
                    self.validate_zone(source_record, source_record_index)

    def validate_mandatory_fields(self, source_record: dict, source_record_index: int) -> list:
        missing_mandatory_fields = []
        missing_mandatory_source_fields = []
        for mandatory_field_name, source_field_name in self._mandatory_field_names_values:
            if not source_record[source_field_name]:
                missing_mandatory_fields.append(mandatory_field_name)
                missing_mandatory_source_fields.append(source_field_name)

        field_type = 'header' if self._is_spreadsheet else 'attribute'

        if len(missing_mandatory_source_fields) > 0:
            self._add_record_error(source_record_index,
                                   f'Values should be provided for the following {field_type}s: ' \
                                   f"{' '.join(missing_mandatory_source_fields)}")

        return missing_mandatory_fields

    def validate_date_field(self, source_record: dict, source_record_index: int):
        source_date_field_name = getattr(self._mappings, DATE_FIELD_NAME)
        source_date_value = source_record[source_date_field_name]

        if isinstance(source_date_value, datetime):
            return

        for date_format in VALID_DATE_FORMATS:
            try:
                datetime.strptime(str(source_date_value), date_format)
                return
            except ValueError:
                pass

        return self._add_record_field_error(source_record_index, source_date_field_name,
                                            f'The value {source_date_value} is not a valid date format')

    def validate_latitude(self, source_record: dict, source_record_index: int):
        source_field_name = getattr(self._mappings.location, LATITUDE_FIELD_NAME)
        source_value = source_record[source_field_name]

        if not is_float_string(source_value):
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is not a decimal number')

    def validate_longitude(self, source_record: dict, source_record_index: int):
        source_field_name = getattr(self._mappings.location, LONGITUDE_FIELD_NAME)
        source_value = source_record[source_field_name]

        if not is_float_string(source_value):
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is not a decimal number')

    def validate_easting(self, source_record: dict, source_record_index: int):
        source_field_name = getattr(self._mappings.location, EASTING_FIELD_NAME)
        source_value = source_record[source_field_name]

        if not is_float_string(source_value):
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is not a decimal number')
        elif float(source_value) < 0:
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is must be a positive number')

    def validate_northing(self, source_record: dict, source_record_index: int):
        source_field_name = getattr(self._mappings.location, NORTHING_FIELD_NAME)
        source_value = source_record[source_field_name]

        if not is_float_string(source_value):
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is not a decimal number')
        elif float(source_value) < 0:
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} must be a positive number')

    def validate_zone(self, source_record: dict, source_record_index: int):
        source_field_name = getattr(self._mappings.location, ZONE_FIELD_NAME)
        source_value = source_record[source_field_name]

        if not is_int_string(source_value):
            self._add_record_field_error(source_record_index, source_field_name,
                                         f'The value {source_value} is not a integer number')
        elif str(source_value) not in VALID_ZONES:
            self._add_record_field_error(source_record_index, source_field_name,
                                         f"The value {source_value} must be one of {', '.join(VALID_ZONES)}")
