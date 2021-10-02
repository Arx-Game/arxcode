from evennia_extensions.object_extensions.storage_wrappers import StorageWrapper


class RosterEntryWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.roster

    def create_new_storage(self, instance):
        raise AttributeError("This object does not have a RosterEntry to store that.")


class CharacterSheetWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.charactersheet

    def create_new_storage(self, instance):
        from evennia_extensions.character_extensions.models import CharacterSheet

        return CharacterSheet.objects.create(objectdb=instance.obj)


class CombatSettingsWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.charactercombatsettings

    def create_new_storage(self, instance):
        from evennia_extensions.character_extensions.models import (
            CharacterCombatSettings,
        )

        return CharacterCombatSettings.objects.create(objectdb=instance.obj)


class MessengerSettingsWrapper(StorageWrapper):
    def get_storage(self, instance):
        return instance.obj.charactermessengersettings

    def create_new_storage(self, instance):
        from evennia_extensions.character_extensions.models import (
            CharacterMessengerSettings,
        )

        return CharacterMessengerSettings.objects.create(objectdb=instance.obj)
