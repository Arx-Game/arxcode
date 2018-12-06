from django.apps import AppConfig


class MagicConfig(AppConfig):

    name = 'world.magic'

    def ready(self):
        from .effects import register_effects
        from .consequences import register_consequences
        register_effects()
        register_consequences()
