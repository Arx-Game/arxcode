from django import template
from django.utils.safestring import mark_safe
from evennia.utils.ansi import parse_ansi

register = template.Library()


@register.filter
def mush_to_html(value):
    if not value:
        return value
    value = value.replace('&', '&amp')
    value = value.replace('<', '&lt')
    value = value.replace('>', '&gt')
    value = value.replace('%r', '<br>')
    value = value.replace('%R', '<br>')
    value = value.replace('\n', '<br>')
    value = value.replace('%b', ' ')
    value = value.replace('%t', '&nbsp&nbsp&nbsp&nbsp')
    value = value.replace('|/', '<br>')
    value = value.replace('{/', '<br>')
    value = parse_ansi(value, strip_ansi=True)
    return mark_safe(value)


@register.filter
def doc_str(value):
    return value.__doc__


@register.filter
def date_from_header(header):
    """
    When given a Msg object's header, extract and return IC date
    Args:
        header: str

    Returns:
        str: IC date of the header
    """
    hlist = header.split(";")
    keyvalpairs = [pair.split(":") for pair in hlist]
    keydict = {pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2}
    date = keydict.get('date', None)
    return date
