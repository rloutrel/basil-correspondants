"""Minimal JSON Schema subset validator.

Validates the keyword subset used by the capability catalogs: type, enum,
required, properties, additionalProperties, minItems, minProperties, minimum,
maximum, items. Hand-rolled on purpose: the catalogs only need this subset and
it keeps the dependency stack permissive-only (see spec §8.1).
"""

BOOLEAN_FIELDS = ("case_sensitive", "strip", "multiple")


class SchemaValidationError(Exception):
    """Raised when a payload does not conform to its schema."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _type_ok(expected, value):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    raise ValueError(f"Unsupported schema type: {expected}")


def _validate(schema, value, path, errors):
    if "anyOf" in schema:
        branch_errors = []
        for branch in schema["anyOf"]:
            candidate = list(errors)
            errors.clear()
            _validate(branch, value, path, errors)
            if not errors:
                return
            branch_errors.extend(errors)
            errors.clear()
        errors.append(f"{path}: does not match any allowed form")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        return
    expected = schema.get("type")
    if expected is not None and not _type_ok(expected, value):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return
    if expected == "object" or isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        min_props = schema.get("minProperties")
        if min_props is not None and len(value) < min_props:
            errors.append(f"{path}: expected at least {min_props} properties")
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            if key in properties:
                _validate(properties[key], item, child, errors)
            elif additional is False:
                errors.append(f"{child}: additional property not allowed")
            elif isinstance(additional, dict):
                _validate(additional, item, child, errors)
    elif expected == "array" or isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items")
        items = schema.get("items")
        if items:
            for index, item in enumerate(value):
                _validate(items, item, f"{path}[{index}]", errors)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: must be <= {schema['maximum']}")


def validate(schema, payload):
    """Validate a payload against a schema; raise SchemaValidationError."""
    errors = []
    _validate(schema, payload, "", errors)
    if errors:
        raise SchemaValidationError(errors)
