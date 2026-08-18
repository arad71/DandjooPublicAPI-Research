from pydantic import BaseModel


def is_float_string(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    else:
        return True


def is_int_string(value: str) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    else:
        return True


def get_model_required_fields_values(model: BaseModel) -> list:
    model_schema = model.schema()

    required_fields = []
    for field in model_schema['required']:
        # if field is another BaseModel subclass instance, get its fields (flattened) and add
        if 'anyOf' in model_schema['properties'][field]:
            required_fields.extend(get_model_required_fields_values(getattr(model, field)))
        else:
            value = getattr(model, field)
            required_fields.append((field, value))

    return required_fields
