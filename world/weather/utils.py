"""
Utilities to make the weather system a little more friendly to write.
"""

from world.weather.models import WeatherType, WeatherEmit
from typeclasses.scripts import gametime
from evennia.server.models import ServerConfig
from evennia.server.sessionhandler import SESSION_HANDLER
from evennia.utils import logger
from random import randint
from server.utils.picker import WeightedPicker


def weather_emits(weathertype, season=None, time=None, intensity=5):
    """
    Return all emits matching the given values.
    :param weathertype: The type of weather to use, a WeatherType object
    :param season: The season (summer, spring, autumn, winter)
    :param time: The time (morning, afternoon, evening, night)
    :param intensity: The intensity of weather to pick an emit for, from 1 to 10
    :return: A QuerySet of matching WeatherEmit objects
    """
    if not season:
        season, _ = gametime.get_time_and_season()
    season = season.lower()

    if not time:
        _, time = gametime.get_time_and_season()
    time = time.lower()

    qs = WeatherEmit.objects.filter(weather=weathertype)
    qs = qs.filter(intensity_min__lte=intensity, intensity_max__gte=intensity)
    if season == "spring":
        qs = qs.filter(in_spring=True)
    elif season == "summer":
        qs = qs.filter(in_summer=True)
    elif season == "autumn" or season == "fall":
        qs = qs.filter(in_fall=True)
    elif season == "winter":
        qs = qs.filter(in_winter=True)

    if time == "night":
        qs = qs.filter(at_night=True)
    elif time == "morning":
        qs = qs.filter(at_morning=True)
    elif time == "afternoon":
        qs = qs.filter(at_afternoon=True)
    elif time == "evening":
        qs = qs.filter(at_evening=True)

    return qs


def pick_emit(weathertype, season=None, time=None, intensity=None):
    """
    Given weather conditions, pick a random emit.  If a GM-set weather
    override is present, will always return that value.
    :param weathertype: A WeatherType object, integer ID, or None.  If None,
                        defaults to the first weather type.
    :param season: 'summer', 'autumn', 'winter', 'spring', or None.  If None,
                    defaults to the current IC season.
    :param time: 'morning', 'afternoon', 'evening', 'night', or None.  If None,
                 defaults to the current IC time of day.
    :param intensity: The intensity of the weather, from 1 to 10.
    :return:
    """
    # Do we have a GM-set override?
    custom_weather = ServerConfig.objects.conf("weather_custom", default=None)
    if custom_weather:
        return custom_weather

    if weathertype is None:
        weathertype = ServerConfig.objects.conf("weather_type_current", default=1)

    if isinstance(weathertype, int):
        weathertype = WeatherType.objects.get(pk=weathertype)

    if not isinstance(weathertype, WeatherType):
        raise ValueError

    if intensity is None:
        intensity = ServerConfig.objects.conf("weather_intensity_current", default=5)

    emits = weather_emits(weathertype, season=season, time=time, intensity=intensity)

    if emits.count() == 0:
        logger.log_err(
            "Weather: Unable to find any matching emits for {} intensity {} on a {} {}.".format(
                weathertype.name, intensity, season, time
            )
        )
        return None

    if emits.count() == 1:
        return emits[0].text

    picker = WeightedPicker()

    for emit in emits:
        picker.add_option(emit, emit.weight)

    result = picker.pick()

    return result.text


def set_weather_type(value=1):
    """
    Sets the weather type, as an integer value.
    :param value: A value mapping to the primary key of a WeatherType object
    """
    ServerConfig.objects.conf(key="weather_type_current", value=value)


def set_weather_target_type(value=1):
    """
    Sets the weather target, as an integer value.
    :param value: A value mapping to the primary key of a WeatherType object
    :return:
    """
    ServerConfig.objects.conf(key="weather_type_target", value=value)


def get_weather_type():
    """
    Returns the current weather type, as an integer.
    :return: An integer mapping to the primary key of a WeatherType object
    """
    return ServerConfig.objects.conf("weather_type_current", default=1)


def get_weather_target_type():
    """
    Returns the target weather type, as an integer.
    :return: An integer mapping to the primary key of a WeatherType object
    """
    return ServerConfig.objects.conf("weather_type_target", default=1)


def set_weather_intensity(value=5):
    """
    Sets the weather intensity, as an integer value.
    :param value: A value from 1 to 10.
    """
    ServerConfig.objects.conf(key="weather_intensity_current", value=value)


def set_weather_target_intensity(value=5):
    """
    Sets the weather intensity, as an integer value.
    :param value: A value from 1 to 10.
    """
    ServerConfig.objects.conf(key="weather_intensity_target", value=value)


def get_weather_intensity():
    """
    Returns the current weather intensity, as an integer from 1 to 10
    :return: The current intensity.
    """
    return ServerConfig.objects.conf("weather_intensity_current", default=5)


def get_weather_target_intensity():
    """
    Returns the target weather intensity, as an integer.
    :return: An integer value from 1 to 10.
    """
    return ServerConfig.objects.conf("weather_intensity_target", default=5)


def emits_for_season(season="fall"):
    """
    Returns all valid emits for the season given.
    :param season: 'summer', 'autumn', 'winter', or 'spring'
    """
    qs = WeatherEmit.objects.all()
    season = season.lower()
    if season == "spring":
        qs = qs.filter(in_spring=True)
    elif season == "summer":
        qs = qs.filter(in_summer=True)
    elif season == "autumn" or season == "fall":
        qs = qs.filter(in_fall=True)
    elif season == "winter":
        qs = qs.filter(in_winter=True)

    return qs


def random_weather(season="fall"):
    """
    Given a season, picks a weighted random weather type from the list
    of valid weathers.
    :param season: 'summer', 'autumn', 'winter', or 'spring'
    :return: A WeatherType object with emits valid in the given season.
    """
    emits = emits_for_season(season)

    # Build a list of all weathers and the combined weight
    # of their valid emits
    weathers = {}
    total_weight = 0
    for emit in emits:
        if emit.weather.automated:
            weatherweight = (
                weathers[emit.weather.id] if emit.weather.id in weathers else 0
            )
            weatherweight += emit.weight
            weathers[emit.weather.id] = weatherweight * emit.weather.multiplier
            total_weight += emit.weight

    # Create our picker list
    picker = WeightedPicker()
    for k, v in weathers.items():
        picker.add_option(k, v)

    result = picker.pick()

    weather = WeatherType.objects.get(pk=result)
    return weather


def advance_weather():
    """
    Advances the weather by one 'step', towards our target weather and intensity.
    If we have met our target, pick a new one for the next run.
    :return: Current weather ID as an integer, current weather intensity as an integer
    """
    if ServerConfig.objects.conf("weather_locked", default=False):
        return get_weather_type(), get_weather_intensity()

    target_weather = ServerConfig.objects.conf("weather_type_target", default=None)
    target_intensity = ServerConfig.objects.conf(
        "weather_intensity_target", default=None
    )

    season, time = gametime.get_time_and_season()

    if not target_weather:
        new_weather = random_weather(season=season)
        target_weather = new_weather.id
        set_weather_type(target_weather)

    if not target_intensity:
        target_intensity = randint(1, 10)
        set_weather_intensity(target_intensity)

    current_weather = ServerConfig.objects.conf("weather_type_current", default=1)
    current_intensity = ServerConfig.objects.conf(
        "weather_intensity_current", default=1
    )

    if current_weather != target_weather:
        current_intensity -= randint(1, 6)
        if current_intensity <= 0:
            current_intensity = abs(current_intensity)
            if current_intensity == 0:
                current_intensity = 1
            current_weather = target_weather
    else:
        if current_intensity < target_intensity:
            current_intensity += randint(1, 4)
            if current_intensity > target_intensity:
                current_intensity = target_intensity
        else:
            current_intensity -= randint(1, 4)
            if current_intensity < target_intensity:
                current_intensity = target_intensity

    set_weather_type(current_weather)
    set_weather_intensity(current_intensity)

    if current_weather == target_weather and current_intensity == target_intensity:
        # We hit our target.  Let's pick a new one and return.
        new_weather = random_weather(season=season)
        target_weather = new_weather.id
        set_weather_target_type(target_weather)
        target_intensity = randint(1, 10)
        set_weather_target_intensity(target_intensity)

    return current_weather, current_intensity


def choose_current_weather():
    """
    Picks a new emit for the current weather conditions, and locks it in.
    :return: The emit to use.
    """

    weather_type = get_weather_type()
    weather_intensity = get_weather_intensity()
    max_attempts = 10
    # There wasn't any limitation in the original code
    # Had an infinite loop as a result

    emit = pick_emit(weather_type, intensity=weather_intensity)
    attempt_count = 0
    while not emit and attempt_count < max_attempts:
        # Just in case there's no available weather for a given
        # target intensity of during our current season/time;
        # we'll advance the weather until we do have something.
        season, time = gametime.get_time_and_season()
        logger.log_err(
            "Weather: No available weather for type {} intensity {} during {} {}".format(
                weather_type, weather_intensity, season, time
            )
        )
        weather_type, weather_intensity = advance_weather()
        emit = pick_emit(weather_type, intensity=weather_intensity)
        attempt_count += 1
    ServerConfig.objects.conf(key="weather_last_emit", value=emit)
    return emit


def get_last_emit():
    """
    Returns the last emit chosen by the weather system.
    :return: The last emit chosen by the weather system.
    """
    return ServerConfig.objects.conf(key="weather_last_emit", default=None)


def announce_weather(text=None):
    """
    Announces weather to everyone who cares about it.
    :param text: The emit to show.
    """
    if not text:
        return

    for sess in SESSION_HANDLER.get_sessions():
        account = sess.get_account()
        if account:
            ignore_weather = account.db.ignore_weather or False
            if not ignore_weather:
                sess.msg("|wWeather:|n {}".format(text))
