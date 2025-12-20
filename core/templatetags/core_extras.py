from django import template
from urllib.parse import urlencode

register = template.Library()

@register.filter(name="get_item")
def get_item(d, key):
    try:
        return d.get(key, "")
    except Exception:
        return ""

@register.filter(name="player_image")
def player_image(row):
    try:
        data = getattr(row, "data", {}) or {}
        for key in ("Picture", "Image", "Photo", "Headshot", "PlayerPic"):
            val = data.get(key)
            if isinstance(val, str) and (val.startswith("http") or val.startswith("/media")):
                return val
        return ""
    except Exception:
        return ""

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    query = context['request'].GET.copy()
    for key, value in kwargs.items():
        query[key] = value
    return query.urlencode()
