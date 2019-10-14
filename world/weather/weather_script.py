from typeclasses.scripts.scripts import Script
from . import utils
from evennia.utils import create


class WeatherScript(Script):

    def at_script_creation(self):
        self.key = "Weather Patterns"
        self.desc = "Keeps weather moving on the game."
        self.interval = 3600
        self.persistent = True
        self.start_delay = False

    def at_repeat(self, **kwargs):
        utils.advance_weather()
        emit = utils.choose_current_weather()
        utils.announce_weather(emit)


def init_weather():
    """
    This is called only once, when you want to enable the weather system.
    """
    weather = create.create_script(WeatherScript)
    weather.start()
