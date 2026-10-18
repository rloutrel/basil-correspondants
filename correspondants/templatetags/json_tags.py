import json

from django import template

register = template.Library()


@register.filter
def to_json(value):
    """Serialize a value (dict/list) as indented JSON for text areas."""
    return json.dumps(value, indent=2, ensure_ascii=False)
