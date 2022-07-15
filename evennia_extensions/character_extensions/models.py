from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia_extensions.character_extensions.constants import (
    RACE_TYPE_CHOICES,
    SMALL_ANIMAL,
    KEY_CHOICES,
    CHEST_KEY,
    SINGLE,
    MARITAL_STATUS_CHOICES,
)
from server.utils.abstract_models import NameLookupModel
from server.utils.arx_utils import CachedProperty


class Characteristic(NameLookupModel):
    """
    A type of physical characteristic, such as eye color, hair color, skin tone, etc.
    The names of characteristics should be considered hardcoded constants, much like
    traits.
    """

    description = models.TextField(blank=True)


class CharacteristicValue(SharedMemoryModel):
    """
    This represents a value for characteristic, such as 'red' for hair color. Character sheets
    will then point to these for characteristics. Ideally characteristic/value pairs would form
    a composite primary key, but django does not support that.
    """

    characteristic = models.ForeignKey(
        Characteristic, on_delete=models.PROTECT, related_name="values"
    )
    value = models.CharField(max_length=80, db_index=True)

    class Meta:
        unique_together = ("value", "characteristic")
        ordering = ("characteristic", "value")

    def __str__(self):
        return f"{self.characteristic}: {self.value}"


class Race(SharedMemoryModel):
    """
    For our purposes, race refers to the type of creature that a character
    may be that shares characteristics that can be selected during character or
    retainer creation. For example, a type of elf may be allowed to take radically
    different hair and eye color than a human. For types of creatures where the
    differences won't really change beyond the name, we'll have a "breed"
    characteristic. For example, a small animal retainer might be of the 'bird'
    race with 'peregrine' as its chosen breed. Later on, we'll probably have
    ability kits that have a Many-to-Many relationship with Race for allowing
    specifying different starting abilities that inherent to that race, such as
    flight for avian races.
    """

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    allowed_characteristic_values = models.ManyToManyField(
        CharacteristicValue, related_name="allowed_races", blank=True
    )
    race_type = models.PositiveSmallIntegerField(
        choices=RACE_TYPE_CHOICES, default=SMALL_ANIMAL
    )

    def __str__(self):
        return self.name


class SheetValueWrapper:
    """
    Just a little wrapper to hide away details of getting different CharacterSheetValues
    and caching them on retrieval/saving them on set.
    """

    def __init__(self, name=None):
        self.characteristic_name = name

    def __set_name__(self, owner, name):
        if not self.characteristic_name:
            self.characteristic_name = name

    def __get__(self, instance, owner):
        """The getter will retrieve the string value of the characteristic"""
        if not instance:
            return self
        try:
            return instance.cached_values[self.characteristic_name].value
        except KeyError:
            return None

    def __set__(self, instance, value):
        """Sets a value for a characteristic on a character sheet"""
        if not value:
            self.delete_sheet_value(instance)
            return
        characteristic = Characteristic.objects.get(name=self.characteristic_name)
        try:
            new_value = CharacteristicValue.objects.get(
                value__iexact=value, characteristic=characteristic
            )
        except CharacteristicValue.DoesNotExist:
            valid_values = ", ".join(
                CharacteristicValue.objects.filter(
                    characteristic=characteristic
                ).values_list("value", flat=True)
            )
            raise ValidationError(
                f"{value} is not allowed for {self.characteristic_name}. "
                f"Valid values: {valid_values}"
            )
        if self.characteristic_name in instance.cached_values:
            sheet_value = instance.cached_values[self.characteristic_name]
            sheet_value.characteristic_value = new_value
            sheet_value.save()
        else:
            characteristic = Characteristic.objects.get(name=self.characteristic_name)
            sheet_value = instance.values.create(
                characteristic=characteristic,
                characteristic_value=new_value,
            )
            # add the sheet_value to our cache
            instance.cached_values[self.characteristic_name] = sheet_value

    def __delete__(self, instance):
        self.delete_sheet_value(instance)

    def delete_sheet_value(self, instance):
        """
        We can assume that the sheet_value is inside the instance cached_values if it
        exists. This will be a noop if it's not found.
        """
        if self.characteristic_name in instance.cached_values:
            sheet_value = instance.cached_values.pop(self.characteristic_name)
            sheet_value.delete()


class CharacterExtensionModel(SharedMemoryModel):
    """
    This represents a table with a one-to-one relationship with a Character,
    which is a proxy class for an Evennia ObjectDB model. They'll hold some
    additional data for the character in some semi-organized fashion based
    on usage or the nature of the data.
    """

    objectdb = models.OneToOneField(
        "objects.ObjectDB", on_delete=models.CASCADE, primary_key=True
    )

    class Meta:
        abstract = True


class CharacterSheet(CharacterExtensionModel):
    age = models.PositiveSmallIntegerField(default=18)
    real_age = models.PositiveSmallIntegerField(null=True, blank=True)
    characteristics = models.ManyToManyField(
        Characteristic, related_name="character_sheets", through="CharacterSheetValue"
    )
    race = models.ForeignKey(
        Race,
        null=True,
        on_delete=models.SET_NULL,
        related_name="character_sheets",
        blank=True,
    )
    breed = SheetValueWrapper()
    gender = SheetValueWrapper()
    eye_color = SheetValueWrapper(name="eye color")
    hair_color = SheetValueWrapper(name="hair color")
    height = SheetValueWrapper()
    skin_tone = SheetValueWrapper(name="skin tone")
    concept = models.CharField(max_length=255, blank=True)
    real_concept = models.CharField(max_length=255, blank=True)
    marital_status = models.CharField(
        max_length=30, choices=MARITAL_STATUS_CHOICES, default=SINGLE
    )
    # turn family into a model later
    family = models.CharField(max_length=255, blank=True)
    fealty = models.ForeignKey(
        "dominion.Fealty",
        related_name="character_sheets",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # turn vocation into a model later
    vocation = models.CharField(max_length=255, blank=True)
    # Maybe turn this into an actual DateField one day
    birthday = models.CharField(max_length=255, blank=True)
    social_rank = models.PositiveSmallIntegerField(default=10)
    quote = models.TextField(blank=True)
    personality = models.TextField(blank=True)
    background = models.TextField(blank=True)
    obituary = models.TextField(blank=True)
    additional_desc = models.TextField(blank=True)
    religion = models.ForeignKey(
        "prayer.Religion",
        related_name="character_sheets",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    @CachedProperty
    def cached_values(self):
        return {ob.characteristic.name.lower(): ob for ob in self.values.all()}


class CharacterSheetValue(SharedMemoryModel):
    """
    Values for different characteristics for a CharacterSheet, such as hair_color,
    eye_color, etc. It's slightly denormalized - we have a characteristic even though
    that would be part of the characteristic_value. The reason for that is so
    that we can have a unique_together constraint that ensures that we only have one
    value per characteristic: that we don't have a character with a value for height
    as both 'short' and 'tall', for example. We'll need to validate that characteristic
    and characteristic_value.characteristic are always the same.
    """

    character_sheet = models.ForeignKey(
        CharacterSheet, on_delete=models.CASCADE, related_name="values"
    )
    # It sure would be swell if django supported composite primary keys. Since it doesn't,
    # we'll instead have FKs to both models and need to get the value from the latter
    characteristic = models.ForeignKey(
        Characteristic, related_name="sheet_values", on_delete=models.CASCADE
    )
    characteristic_value = models.ForeignKey(
        CharacteristicValue,
        related_name="sheet_values",
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("character_sheet", "characteristic")

    @property
    def value(self):
        return self.characteristic_value.value

    def __str__(self):
        return str(self.characteristic_value)

    def save(self, *args, **kwargs):
        """
        Sets denormalized characteristic FK so that we can check the uniqueness
        constraint on save.
        """
        try:
            # catch AttributeError so IntegrityError is allowed to propagate
            self.characteristic = self.characteristic_value.characteristic
        except AttributeError:
            pass
        super().save(*args, **kwargs)


class HeldKey(SharedMemoryModel):
    """A key held by a character for a chest or room"""

    keyed_object = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="distributed_keys"
    )
    character = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="held_keys"
    )
    key_type = models.PositiveSmallIntegerField(choices=KEY_CHOICES, default=CHEST_KEY)

    def __str__(self):
        return self.keyed_object.db_key


class CharacterCombatSettings(CharacterExtensionModel):
    guarding = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guarded_by_sheets",
    )
    # move xp and total_xp into Traits app eventually
    xp = models.PositiveSmallIntegerField(default=0)
    total_xp = models.PositiveSmallIntegerField(default=0)
    # convert to FK eventually to a CombatStance model
    combat_stance = models.CharField(max_length=255, blank=True)
    autoattack = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.guarding and self.guarding == self.objectdb:
            raise ValueError("CharacterCombatSettings cannot be set to guard itself.")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Character Combat Settings"


class CharacterMessengerSettings(CharacterExtensionModel):
    custom_messenger = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        blank=True,
    )
    discreet_messenger = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        blank=True,
    )
    messenger_draft = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Character Messenger Settings"


class CharacterTitle(SharedMemoryModel):
    """Titles a character might have. Maybe eventually have them merged with
    honorifics in some way."""

    character = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="character_titles"
    )
    title = models.TextField(blank=True)

    def __str__(self):
        return self.title
