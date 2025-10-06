from django import template

register = template.Library()


@register.filter(name="pad")
def pad(value, width: int = 0):
    """Zero-pad numeric values; pass through strings unchanged.

    Usage: {{ episode|pad:2 }} -> '03' when episode=3, or 'Special' when episode='Special'.
    """
    try:
        w = int(width)
    except Exception:
        w = 0
    try:
        num = int(value)
        return str(num).zfill(w)
    except Exception:
        return "" if value is None else str(value)
