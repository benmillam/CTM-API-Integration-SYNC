import json
from collections.abc import Mapping, Sequence


TARGET_FIELDS = ("valid_lead", "lead_summary", "is_spam")

FIELD_PATH_PRIORITY = (
    ("custom_fields",),
    ("contact", "custom_fields"),
    ("contact",),
    ("score", "custom_fields"),
    ("score",),
)

TRUE_VALUES = {"true", "t", "yes", "y", "1"}
FALSE_VALUES = {"false", "f", "no", "n", "0"}


def enrich_call_custom_fields(call):
    """Add normalized CTM lead custom-field columns to a call record."""
    valid_lead_raw = raw_string(find_custom_field_value(call, "valid_lead"))
    is_spam_raw = raw_string(find_custom_field_value(call, "is_spam"))
    lead_summary = raw_string(find_custom_field_value(call, "lead_summary"))

    call["valid_lead"] = normalize_boolean(valid_lead_raw)
    call["valid_lead_raw"] = valid_lead_raw
    call["lead_summary"] = lead_summary
    call["is_spam"] = normalize_boolean(is_spam_raw)
    call["is_spam_raw"] = is_spam_raw
    return call


def find_custom_field_value(record, field_name):
    field_name = field_name.lower()
    candidates = list(_walk_field_candidates(record, field_name))
    if not candidates:
        return None

    path, value = sorted(candidates, key=lambda item: _candidate_sort_key(item[0], field_name))[0]
    return value


def normalize_boolean(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def raw_string(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def _walk_field_candidates(value, field_name, path=()):
    if isinstance(value, Mapping):
        custom_field_value = _custom_field_object_value(value, field_name)
        if custom_field_value is not _Missing:
            yield path + (field_name,), custom_field_value

        for key, child in value.items():
            key_text = str(key)
            child_path = path + (key_text,)
            if key_text.lower() == field_name:
                yield child_path, child
            yield from _walk_field_candidates(child, field_name, child_path)
    elif _is_sequence(value):
        for index, child in enumerate(value):
            yield from _walk_field_candidates(child, field_name, path + (f"[{index}]",))


def _custom_field_object_value(value, field_name):
    name = _first_present(value, ("name", "key", "field", "label"))
    if name is _Missing or raw_string(name).strip().lower() != field_name:
        return _Missing

    custom_value = _first_present(value, ("value", "values", "text", "content"))
    if custom_value is _Missing:
        return _Missing
    return custom_value


def _first_present(mapping, keys):
    lower_mapping = {str(key).lower(): key for key in mapping.keys()}
    for key in keys:
        actual_key = lower_mapping.get(key)
        if actual_key is not None:
            return mapping[actual_key]
    return _Missing


def _candidate_sort_key(path, field_name):
    normalized_path = tuple(part.lower() for part in path if not part.startswith("["))
    for priority, prefix in enumerate(FIELD_PATH_PRIORITY):
        expected_path = prefix + (field_name,)
        if normalized_path == expected_path:
            return (priority, len(normalized_path), ".".join(normalized_path))
    return (len(FIELD_PATH_PRIORITY), len(normalized_path), ".".join(normalized_path))


def _is_sequence(value):
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


class _MissingType:
    pass


_Missing = _MissingType()
