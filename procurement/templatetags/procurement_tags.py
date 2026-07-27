from django import template

register = template.Library()

@register.filter(name='dict_key')
def dict_key(dictionary, key):
    """Retrieves a value from a dictionary using a variable key."""
    if dictionary:
        val = dictionary.get(key)
        if val is None:
            val = dictionary.get(str(key))
        if val is None:
            try:
                val = dictionary.get(int(key))
            except (ValueError, TypeError):
                pass
        return val
    return None
