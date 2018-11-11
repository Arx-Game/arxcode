import time

from evennia.utils.create import create_script

from .scripts import Script
from server.conf import settings
from evennia.server.models import ServerConfig

SERVER_START = time.time()
SERVER_RUNTIME = 0.0

TIMEFACTOR = settings.TIME_FACTOR

GAMETIME_SCRIPT_NAME = "sys_game_time"

MIN = 60
HOUR = MIN * 60
DAY = HOUR * 24
WEEK = DAY * 7
MONTH = WEEK * 4
YEAR = MONTH * 12


class GameTime(Script):
    """
    This script maintains IC game time, allowing you to set a multiplier.
    It remembers at what point the multipliers were changed, so it doesn't
    alter the IC game time when you alter the multiplier; it merely changes
    things going forward.
    """

    def _upgrade(self):
        """
        Internal function to upgrade from the old gametime script
        """
        from evennia.utils import logger
        if not ServerConfig.objects.conf(key="run_time", default=None):
            logger.log_info("Upgrading or configuring gametime as ServerConfig value...")
            run_time = self.attributes.get("run_time", default=0.0)
            ServerConfig.objects.conf(key="run_time", value=run_time)
        if not self.attributes.has("intervals"):
            # Convert from old script style
            run_time = ServerConfig.objects.conf("run_time", default=0.0)
            game_time = run_time * 2
            self.mark_time(runtime=run_time, gametime=game_time, multiplier=TIMEFACTOR)

    def mark_time(self, runtime=0.0, gametime=0.0, multiplier=TIMEFACTOR):
        """
        Mark a time interval
        :param runtime: The amount of RL time the game has been running, in seconds,
                        minus downtime.
        :param gametime: The IC timestamp since the IC epoch, in seconds.
        :param multiplier: The multiplier.
        :return:
        """
        tdict = {'run': runtime, 'game': gametime, "multiplier": multiplier, "real": time.time()}
        times = list(self.intervals)
        times.append(tdict)
        self.attributes.add("intervals", times)

        from evennia.utils import logger
        logger.log_info("Gametime: Marked new time {}".format(tdict))

    @property
    def runtime_marks(self):
        """
        The runtime/realtime marker pairs.
        """
        return self.attributes.get("runtime_marks") or []

    @property
    def intervals(self):
        """
        The runtime/gametime marker pairs.
        """
        return self.attributes.get("intervals") or []

    @property
    def last_mark(self):
        """
        The last runtime / gametime / multiplier marker, returned in that order.
        """
        if len(self.intervals) == 0:
            return 0, 0, 2.0

        tdict = self.intervals[-1]
        return tdict['run'], tdict['game'], tdict['multiplier']

    @property
    def runtime(self):
        """
        How long we've been running, total, since our first run,
        minus downtimes.
        """
        return SERVER_RUNTIME + self.uptime

    @property
    def uptime(self):
        """
        How long we've been running since our last restart.
        """
        return time.time() - SERVER_START

    @property
    def gametime(self):
        """
        The game time, in seconds since the in-game epoch
        """
        run, game, multi = self.last_mark
        timesince = self.runtime - run
        return game + (timesince * multi)

    def at_script_creation(self):
        """
        Setup the script
        """
        self.key = GAMETIME_SCRIPT_NAME
        self.desc = "Keeps track of the game time"
        self.interval = 60
        self.persistent = True
        self.start_delay = True

    def at_repeat(self):
        """
        Called every minute to update the timers.
        """
        ServerConfig.objects.conf(key="run_time", value=self.runtime)
        self.attributes.add("run_time", self.runtime)
        # Despite having checks elsewhere, apparently sometimes
        # the script can restart without ever calling at_start
        # or at_script_creation. So a final check here, just
        # to make absolutely sure it loads the correct values if
        # it reset.
        try:
            if SERVER_RUNTIME < 1000:
                self.at_start()
        except Exception:
            from evennia.utils import logger
            logger.log_trace()

    def at_start(self):
        """
        This is called once every server restart.
        We reset the up time and load the relevant
        times.
        """
        global SERVER_RUNTIME
        self._upgrade()
        SERVER_RUNTIME = ServerConfig.objects.conf("run_time")
        from evennia.utils import logger
        if self.attributes.has("check_run_time_since") or not self.attributes.has("runtime_marks"):
            last_realtime = self.attributes.get("check_run_time_since") or 0
            self.attributes.remove("check_run_time_since")
            if time.time() - last_realtime > 300:
                runtime_marks = self.runtime_marks
                runtime_marks.append({'runtime': self.runtime, 'realtime': time.time()})
                self.attributes.add('runtime_marks', runtime_marks)

    def at_server_shutdown(self):
        """
        This is called when the server is shutting down; we
        store a marker so we know to map our run-time to our
        IC time.
        """
        self.attributes.add("check_run_time_since", time.time())

    def at_server_reload(self):
        """
        This is called when the server is reloading; we
        store a marker so we know to map our run-time to our
        IC time.
        """
        self.attributes.add("check_run_time_since", time.time())


def get_script():
    """
    Returns the ScriptDB instance
    :return:
    """
    from evennia.scripts.models import ScriptDB
    try:
        script = ScriptDB.objects.get(db_key=GAMETIME_SCRIPT_NAME)
        return script
    except ScriptDB.DoesNotExist:
        return create_script(GameTime)


# Legacy definitions

def _format(seconds, *divisors) :
    """
    Helper function. Creates a tuple of even dividends given
    a range of divisors.

    Inputs
      seconds - number of seconds to format
      *divisors - a number of integer dividends. The number of seconds will be
                  integer-divided by the first number in this sequence, the remainder
                  will be divided with the second and so on.
    Output:
        A tuple of length len(*args)+1, with the last element being the last remaining
        seconds not evenly divided by the supplied dividends.

    """
    results = []
    seconds = int(seconds)
    for divisor in divisors:
        results.append(seconds / divisor)
        seconds %= divisor
    results.append(seconds)
    return tuple(results)


def runtime(format=False):
    """
    Returns the amount of time, in seconds, the game has been running, not
    counting downtime.  If format is True, splits it into year, month, week,
    day, hour, min.
    :param format: Whether to parse into elements.
    """
    script = get_script()
    run_time = script.runtime
    if format:
        return _format(run_time, YEAR, MONTH, WEEK, DAY, HOUR, MIN)
    return run_time


def uptime(format=False):
    """
    Returns the amount of time, in seconds, since the last server restart.  If format
    is true, splits it into year, month, week, day, hour, min.
    :param format: Whether to parse into elements.
    """
    script = get_script()
    up_time = script.uptime
    if format:
        return _format(up_time, YEAR, MONTH, WEEK, DAY, HOUR, MIN)
    return up_time


def gametime(game_time=None, format=False):
    """
    Returns the amount of time, in seconds, since the in-game epoch.  If format
    is true, splits it into year, month, week, day, hour, min.
    :param game_time: A specific game time, in seconds, to parse.
    :param format: Whether to parse into elements.
    """
    if not game_time:
        script = get_script()
        game_time = script.gametime
    if format:
        return _format(game_time, YEAR, MONTH, WEEK, DAY, HOUR, MIN)
    return game_time


def time_factor():
    """
    Returns the current IC time multiplier.
    """
    script = get_script()
    _, _, multiplier = script.last_mark
    return multiplier


def set_time_factor(factor=2):
    """
    Sets the IC time multiplier going forward.
    :param factor: The new IC time multiplier.
    """
    script = get_script()
    script.mark_time(runtime=runtime(), gametime=gametime(), multiplier=factor)


def time_intervals():
    """
    Return all our historical time-intervals
    """
    script = get_script()
    return script.intervals


def runtime_to_gametime(runtime, format=False):
    intervals = time_intervals()
    last_runtime = 0
    last_gametime = 0
    last_timescale = 2
    for interval in reversed(intervals):
        if interval['run'] < runtime:
            last_runtime = interval['run']
            last_gametime = interval['game']
            last_timescale = interval['multiplier']

    timediff = runtime - last_runtime
    game_time = last_gametime + (timediff * last_timescale)

    current_game_time = get_script().gametime

    if format:
        return _format(game_time, YEAR, MONTH, WEEK, DAY, HOUR, MIN)
    return game_time


def realtime_to_gametime(realtime_secs, format=False):
    script = get_script()
    runtime_marks = script.runtime_marks

    # This is not accurate, but it's the best we can do for defaults
    last_realtime = time.time() - script.runtime
    last_runtime = 0

    current_runtime = script.runtime

    # Try to find better default
    for mark in reversed(script.intervals):
        if mark['real'] < realtime_secs:
            last_runtime = mark['run']
            last_realtime = mark['real']

    for mark in reversed(runtime_marks):
        if mark['realtime'] < realtime_secs:
            last_realtime = mark['realtime']
            last_runtime = mark['runtime']

    time_diff = realtime_secs - last_realtime
    run_time = last_runtime + time_diff
    return runtime_to_gametime(run_time, format=format)


# Initialize our values only once.
MONTHS_PER_YEAR = 12
SEASONAL_BOUNDARIES = (3 / 12.0, 6 / 12.0, 9 / 12.0)
HOURS_PER_DAY = 24
DAY_BOUNDARIES = (0, 6 / 24.0, 12 / 24.0, 18 / 24.0)


def get_time_and_season():
    # get the current time as parts of year and parts of day
    # returns a tuple (years,months,weeks,days,hours,minutes,sec)
    current_time = gametime(format=True)
    month, hour = current_time[1], current_time[4]
    season = float(month) / MONTHS_PER_YEAR
    timeslot = float(hour) / HOURS_PER_DAY

    # figure out which slots these represent
    if SEASONAL_BOUNDARIES[0] <= season < SEASONAL_BOUNDARIES[1]:
        curr_season = "spring"
    elif SEASONAL_BOUNDARIES[1] <= season < SEASONAL_BOUNDARIES[2]:
        curr_season = "summer"
    elif SEASONAL_BOUNDARIES[2] <= season < 1.0 + SEASONAL_BOUNDARIES[0]:
        curr_season = "autumn"
    else:
        curr_season = "winter"

    if DAY_BOUNDARIES[0] <= timeslot < DAY_BOUNDARIES[1]:
        curr_timeslot = "night"
    elif DAY_BOUNDARIES[1] <= timeslot < DAY_BOUNDARIES[2]:
        curr_timeslot = "morning"
    elif DAY_BOUNDARIES[2] <= timeslot < DAY_BOUNDARIES[3]:
        curr_timeslot = "afternoon"
    else:
        curr_timeslot = "evening"
    return curr_season, curr_timeslot


def init_gametime():
    """
    This is called once, when the server starts for the very first time.
    """
    # create the GameTime script and start it
    game_time = create_script(GameTime)
    game_time.start()
