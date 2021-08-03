from evennia_extensions.character_extensions.constants import CHEST_KEY, ROOM_KEY
from evennia_extensions.character_extensions.storage_wrappers import (
    RosterEntryWrapper,
    CharacterSheetWrapper,
    CombatSettingsWrapper,
    MessengerSettingsWrapper,
)
from evennia_extensions.character_extensions.validators import (
    fealty_validator,
    race_validator,
)
from evennia_extensions.object_extensions.item_data_handler import ItemDataHandler
from evennia_extensions.object_extensions.storage_wrappers import DisplayNamesWrapper

from evennia_extensions.object_extensions.validators import get_character, get_int
from server.utils.exceptions import CommandError


class CharacterDataHandler(ItemDataHandler):
    longname = DisplayNamesWrapper(default_is_none=True)
    # some PC-only values contained in a RosterEntry
    action_points = RosterEntryWrapper()
    pose_count = RosterEntryWrapper()
    previous_pose_count = RosterEntryWrapper()
    portrait_height = RosterEntryWrapper()
    portrait_width = RosterEntryWrapper()
    dice_string = RosterEntryWrapper()
    briefmode = RosterEntryWrapper(attr_name="brief_mode")
    brief_mode = briefmode
    # characteristics that can be held by PCs or NPCs, on a CharacterSheet
    age = CharacterSheetWrapper(validator_func=get_int, allow_null=False)
    real_age = CharacterSheetWrapper(
        validator_func=get_int, allow_null=False, default_is_none=True
    )
    race = CharacterSheetWrapper(validator_func=race_validator)
    # validation handled by CharacterSheet itself for characteristic values
    breed = CharacterSheetWrapper(default_is_none=True)
    gender = CharacterSheetWrapper(default_is_none=True)
    hair_color = CharacterSheetWrapper(default_is_none=True)
    haircolor = hair_color  # alias for original attribute name
    eye_color = CharacterSheetWrapper(default_is_none=True)
    eyecolor = eye_color  # alias for original attribute name
    height = CharacterSheetWrapper(default_is_none=True)
    skin_tone = CharacterSheetWrapper(default_is_none=True)
    skintone = skin_tone  # alias for original attribute name
    concept = CharacterSheetWrapper()
    real_concept = CharacterSheetWrapper(default_is_none=True)
    marital_status = CharacterSheetWrapper()
    family = CharacterSheetWrapper()
    fealty = CharacterSheetWrapper(
        validator_func=fealty_validator, default_is_none=True
    )
    vocation = CharacterSheetWrapper(default_is_none=True)
    birthday = CharacterSheetWrapper(default_is_none=True)
    social_rank = CharacterSheetWrapper(validator_func=get_int, allow_null=False)
    quote = CharacterSheetWrapper(default_is_none=True)
    personality = CharacterSheetWrapper(default_is_none=True)
    background = CharacterSheetWrapper(default_is_none=True)
    obituary = CharacterSheetWrapper(default_is_none=True)
    additional_desc = CharacterSheetWrapper(default_is_none=True, deleted_value="")
    # combat settings and XP - these values can all be used by NPCs, not just PCs
    guarding = CombatSettingsWrapper(validator_func=get_character, default_is_none=True)
    xp = CombatSettingsWrapper(validator_func=get_int, allow_null=False)
    total_xp = CombatSettingsWrapper(validator_func=get_int, allow_null=False)
    combat_stance = CombatSettingsWrapper()
    autoattack = CombatSettingsWrapper()
    # messenger settings for the character
    custom_messenger = MessengerSettingsWrapper(
        validator_func=get_character, default_is_none=True
    )
    discreet_messenger = MessengerSettingsWrapper(
        validator_func=get_character, default_is_none=True
    )
    messenger_draft = MessengerSettingsWrapper(default_is_none=True, deleted_value="")

    def set_sheet_value(self, attr, value):
        """
        Helper to set our sheet values in character select. Done this way because
        it's much easier to search for this method than a setattr() call. This
        should be removed when character creation is redone to use forms/serializers.
        """
        setattr(self, attr, value)

    # ------------------------------------------------
    # methods for accessing room/chest keys held by the character

    def has_key_by_id(self, dbref):
        """Checks if we have a room/chest key by a given id"""
        return self.obj.held_keys.filter(keyed_object_id=dbref).exists()

    def remove_key_by_name(self, name):
        key_matches = self.obj.held_keys.filter(keyed_object__db_key__iexact=name)
        matched_objects = [obj.keyed_object for obj in key_matches]
        key_matches.delete()
        return matched_objects

    @property
    def all_keyed_objects(self):
        return [obj.keyed_object for obj in self.obj.held_keys.all()]

    def add_key(self, keyed_object, key_type):
        if not self.obj.held_keys.filter(keyed_object=keyed_object).exists():
            return self.obj.held_keys.create(
                keyed_object=keyed_object, key_type=key_type
            )

    def remove_key(self, keyed_object):
        return any(self.obj.held_keys.filter(keyed_object=keyed_object).delete())

    def add_chest_key(self, obj):
        return self.add_key(obj, CHEST_KEY)

    def add_room_key(self, obj):
        return self.add_key(obj, ROOM_KEY)

    def transfer_keys(self, target):
        target_keyed_objects = target.held_keys.values("keyed_object_id")
        missing_keys = self.obj.held_keys.exclude(
            keyed_object_id__in=target_keyed_objects
        )
        for key in missing_keys:
            target.held_keys.create(
                keyed_object=key.keyed_object, key_type=key.key_type
            )

    def check_value_allowed_for_race(
        self, characteristic_name: str, value: str
    ) -> bool:
        from evennia_extensions.character_extensions.models import CharacteristicValue

        char_values = CharacteristicValue.objects.filter(
            allowed_races__name__iexact=str(self.race)
        ).filter(characteristic__name__iexact=characteristic_name)
        if char_values.filter(value__iexact=value).exists():
            return True
        valid_values = ", ".join(
            char_value.value for char_value in char_values.all().order_by("value")
        )
        raise CommandError(
            f"That is not a valid value for {characteristic_name} for {self.race}. "
            f"Valid values: {valid_values}."
        )
