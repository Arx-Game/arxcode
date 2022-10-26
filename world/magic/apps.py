from django.apps import AppConfig


class MagicConfig(AppConfig):

    name = "world.magic"

    def ready(self):
        from world.magic.effects import register_effects
        from world.magic.consequences import register_consequences

        register_effects()
        register_consequences()
