from world.weather import utils as weather_utils
from world.weather.models import WeatherType
from .models import Alignment, Affinity


def weather(caster, target, weather_type):
    try:
        weather_type = int(weather_type)
    except ValueError:
        try:
            weather_model = WeatherType.objects.get(name__iexact=weather_type)
            weather_type = weather_model.id
        except WeatherType.DoesNotExist:
            return False

    return weather_type == weather_utils.get_weather_type()


def hastag(caster, target, tag_name, tag_category):
    if not caster:
        return False

    if not caster.character:
        return False

    tag = caster.character.tags.get(key=tag_name, category=tag_category)
    return tag is not None


def _alignment_from_string(alignstring):
    try:
        align_id = int(alignstring)
        return Alignment.objects.get(id=align_id)
    except ValueError:
        pass
    except Alignment.DoesNotExist:
        return None

    alignments = Alignment.objects.filter(name__iexact=alignstring)
    if alignments.count() == 1:
        return alignments[0]

    return None


def _affinity_from_string(affinitystring):
    try:
        affinity_id = int(affinitystring)
        return Affinity.objects.get(id=affinity_id)
    except ValueError:
        pass
    except Affinity.DoesNotExist:
        return None

    affinities = Affinity.objects.filter(name__iexact=affinitystring)
    if affinities.count() == 1:
        return affinities[0]

    return None


def caster_alignment(caster, target, alignment_string):
    alignment = _alignment_from_string(alignment_string)
    if not alignment:
        return False

    return alignment == caster.alignment


def caster_affinity(caster, target, affinity_string):
    affinity = _affinity_from_string(affinity_string)
    if not affinity:
        return False

    return affinity == caster.affinity


def target_alignment(caster, target, alignment_string):
    alignment = _alignment_from_string(alignment_string)
    if not alignment:
        return False

    return alignment == target.alignment


def target_affinity(caster, target, affinity_string):
    affinity = _affinity_from_string(affinity_string)
    if not affinity:
        return False

    return affinity == target.affinity
