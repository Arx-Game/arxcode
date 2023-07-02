from __future__ import unicode_literals
from mock import Mock
from world.weather.models import WeatherType, WeatherEmit
from server.utils.test_utils import ArxCommandTest
from world.weather import weather_commands, weather_script, utils
from evennia.server.models import ServerConfig


class TestWeatherCommands(ArxCommandTest):
    def setUp(self):
        super(TestWeatherCommands, self).setUp()
        self.weather1 = WeatherType.objects.create(name="Test", gm_notes="Test weather")
        self.emit1 = WeatherEmit.objects.create(
            weather=self.weather1, text="Test1 weather happens."
        )
        self.weather2 = WeatherType.objects.create(
            name="Test2", gm_notes="Test weather"
        )
        self.emit2 = WeatherEmit.objects.create(
            weather=self.weather2, text="Test2 weather happens."
        )
        ServerConfig.objects.conf("weather_type_current", value=1)
        ServerConfig.objects.conf("weather_intensity_current", value=5)
        ServerConfig.objects.conf("weather_type_target", value=2)
        ServerConfig.objects.conf("weather_intensity_target", value=5)

    def test_cmd_adminweather(self):
        self.setup_cmd(weather_commands.CmdAdminWeather, self.char1)
        self.call_cmd(
            "",
            "Weather pattern is Test (intensity 5), moving towards Test2 (intensity 5).",
        )
        self.call_cmd("/lock", "Weather is now locked and will not change.")
        self.call_cmd(
            "/unlock", "Weather is now unlocked and will change again as normal."
        )
        self.call_cmd(
            "/set Pigs soar through the sky.",
            "Custom weather emit set.  "
            "Remember to @admin_weather/announce if you want the "
            "players to know.",
        )
        self.call_cmd(
            "/set",
            "Custom weather message cleared.  Remember to @admin_weather/announce if you want the "
            "players to see a new weather emit.",
        )

    def test_choose_current_weather_max_attempts(self):
        # Set automated flag to False for all existing weather types
        for wt in WeatherType.objects.all():
            wt.automated = False
            wt.save()

        # Create a new weather type with no emits and automated flag set to False
        self.weather3 = WeatherType.objects.create(
            name="Test3", gm_notes="Test weather", automated=False
        )

        # Set the weather type current to the new weather type ID and a high intensity
        ServerConfig.objects.conf(key="weather_type_current", value=self.weather3.id)
        ServerConfig.objects.conf(key="weather_intensity_current", value=999)

        # Call choose_current_weather() and expect a WeatherSelectionError to be raised
        with self.assertRaises(utils.WeatherSelectionError):
            utils.choose_current_weather()
