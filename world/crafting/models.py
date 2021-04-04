from django.db import models

from evennia.locks.lockhandler import LockHandler
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils import create
from server.utils.arx_utils import CachedProperty, CachedPropertiesMixin
from world.crafting.querysets import CraftMaterialsAmountQuerySet
from typing import Iterable


class CraftingRecipe(CachedPropertiesMixin, SharedMemoryModel):
    """
    For crafting, a recipe has a name, description, then materials. A lot of information
    is saved as a parsable text string in the 'result' text field. It'll
    take a form like: "baseval:0;scaling:1" and so on. baseval is a value
    the object has (for armor, say) for minimum quality level, while
    scaling is the increase per quality level to stats. "slot" and "slot limit"
    are used for wearable objects to denote the slot they're worn in and
    how many other objects may be worn in that slot, respectively.
    """

    name = models.CharField(unique=True, max_length=255)
    desc = models.TextField(blank=True)
    # organizations or players that know this recipe
    known_by = models.ManyToManyField(
        "dominion.AssetOwner", blank=True, related_name="crafting_recipes"
    )
    materials = models.ManyToManyField(
        "CraftingMaterialType", blank=True, through="RequiredMaterial"
    )
    difficulty = models.PositiveSmallIntegerField(default=0)
    additional_cost = models.PositiveIntegerField(default=0)
    # the ability/profession that is used in creating this
    ability = models.CharField(blank=True, max_length=80, db_index=True)
    skill = models.CharField(blank=True, max_length=80, db_index=True)
    # the type of object we're creating
    type = models.CharField(blank=True, max_length=80, db_index=True)
    # level in ability this recipe corresponds to. 1 through 6, usually
    level = models.PositiveSmallIntegerField(default=1)
    allow_adorn = models.BooleanField(default=True)
    lock_storage = models.TextField(
        "locks", blank=True, help_text="defined in setup_utils"
    )
    # values for items created by this recipe
    volume = models.IntegerField(
        default=0, help_text="The size of objects created by this recipe."
    )
    base_value = models.DecimalField(
        default=0.0,
        help_text="Value the recipe uses in different "
        "calculations for typeclass properties.",
        max_digits=6,
        decimal_places=2,
    )
    scaling = models.DecimalField(
        default=0.0,
        help_text="Adjusts calculated value based on item quality",
        max_digits=6,
        decimal_places=2,
    )
    # values for containers
    displayable = models.BooleanField(
        default=True, help_text="Used for furniture types"
    )
    display_by_line = models.BooleanField(
        default=True,
        help_text="If true, display inventory by line for container recipe",
    )
    # values for equipment
    slot = models.CharField(
        max_length=80, blank=True, help_text="Location where clothing/armor is worn"
    )
    slot_limit = models.PositiveSmallIntegerField(
        default=1, help_text="Max number that can be worn"
    )
    fashion_mult = models.DecimalField(
        null=True,
        blank=True,
        help_text="If defined, multiplier for modeling",
        max_digits=6,
        decimal_places=2,
    )
    armor_penalty = models.DecimalField(
        default=0.0,
        help_text="Value for armor impairing movement",
        max_digits=6,
        decimal_places=2,
    )
    weapon_skill = models.CharField(
        max_length=80,
        blank=True,
        help_text="Weapon skill used for weapons made by this recipe",
    )

    def __init__(self, *args, **kwargs):
        super(CraftingRecipe, self).__init__(*args, **kwargs)
        self.locks = LockHandler(self)

    def access(self, accessing_obj, access_type="learn", default=False):
        """
        Determines if another object has permission to access.
        accessing_obj - object trying to access this one
        access_type - type of access sought
        default - what to return if no lock of access_type was found
        """
        return self.locks.check(accessing_obj, access_type=access_type, default=default)

    def org_owners(self):
        return self.known_by.select_related("organization_owner").filter(
            organization_owner__isnull=False
        )

    org_owners: Iterable = CachedProperty(org_owners, "_org_owners")

    def can_be_learned_by(self, learner):
        """Returns True if learner can learn this recipe, False otherwise"""
        if not self.access(learner):
            return False
        # if we have no orgs that know this recipe, anyone can learn it normally
        if not self.org_owners:
            return True
        # check if they have granted access from any of the orgs that know it
        return any(ob.access(learner, access_type="recipe") for ob in self.org_owners)

    def display_reqs(self, dompc=None, full=False):
        """Returns string display for recipe"""
        msg = ""
        if full:
            msg += "{wName:{n %s\n" % self.name
            msg += "{wDescription:{n %s\n" % self.desc
        msg += "{wSilver:{n %s\n" % self.additional_cost

        material_msgs = []
        for material_requirement in self.required_materials.all():
            mat = material_requirement.type
            req_amt = material_requirement.amount
            mat_msg = f"{mat}: {req_amt}"
            if dompc:
                try:
                    pcmat = dompc.assets.owned_materials.get(type=mat)
                    amt = pcmat.amount
                except OwnedMaterial.DoesNotExist:
                    amt = 0
                mat_msg += f"({amt}/{req_amt})"
            material_msgs.append(mat_msg)
        if material_msgs:
            msg += "{wMaterials:{n %s\n" % ", ".join(material_msgs)
        return msg

    @CachedProperty
    def value(self):
        """Returns total cost of all materials used"""
        val = self.additional_cost
        val += RequiredMaterial.objects.filter(recipe=self).total_value()
        return val

    def __str__(self):
        return self.name

    @property
    def attack_type(self):
        if self.weapon_skill == "archery":
            return "ranged"
        return "melee"

    def create_obj(self, typec, key, loc, home, quality, crafter=None):
        if "{" in key and not key.endswith("{n"):
            key += "{n"
        obj = create.create_object(typeclass=typec, key=key, location=loc, home=home)
        CraftingRecord.objects.create(
            objectdb=obj, quality_level=quality, crafted_by=crafter, recipe=self
        )
        # will set color name and strip ansi from colorized name for key
        obj.name = key
        return obj


class CraftingMaterialType(SharedMemoryModel):
    """
    Different types of crafting materials. Contraband doesn't show up on the
    market.
    """

    # the type of material we are
    name = models.CharField(max_length=80, db_index=True)
    desc = models.TextField(blank=True, null=True)
    # silver value per unit
    value = models.PositiveIntegerField(blank=0, default=0)
    category = models.CharField(blank=True, null=True, max_length=80, db_index=True)
    contraband = models.BooleanField(default=False)

    def __str__(self):
        return self.name or "Unknown"

    def create_instance(self, quantity):
        name_string = self.name
        if quantity > 1:
            name_string = f"{quantity} {self.name}"

        result = create.create_object(
            key=name_string,
            typeclass="world.dominion.dominion_typeclasses.CraftingMaterialObject",
        )
        result.item_data.material_type = self
        result.item_data.quantity = quantity
        return result


class CraftMaterialsAmount(SharedMemoryModel):
    """
    Abstract model that represents Crafting Materials being allocated/required in
    some amount.
    """

    type = models.ForeignKey(
        "CraftingMaterialType",
        on_delete=models.CASCADE,
    )
    amount = models.PositiveIntegerField(default=0)

    objects = CraftMaterialsAmountQuerySet.as_manager()

    class Meta:
        abstract = True

    def __str__(self):
        return "%s %s" % (self.amount, self.type)

    @property
    def value(self):
        """Returns value of materials they have"""
        return self.type.value * self.amount


class OwnedMaterial(CraftMaterialsAmount):
    """
    Materials owned by an AssetOwner (character or organization)
    """

    owner = models.ForeignKey(
        "dominion.AssetOwner",
        related_name="owned_materials",
        on_delete=models.CASCADE,
    )

    class Meta:
        """Define Django meta options"""

        verbose_name_plural = "Owned Materials"


class RequiredMaterial(CraftMaterialsAmount):
    """
    Materials used for a recipe
    """

    recipe = models.ForeignKey(
        "CraftingRecipe", related_name="required_materials", on_delete=models.CASCADE
    )

    class Meta:
        verbose_name_plural = "Required Materials"


class AdornedMaterial(CraftMaterialsAmount):
    """
    Materials adorned on an item
    """

    objectdb = models.ForeignKey(
        "objects.ObjectDB", related_name="adorned_materials", on_delete=models.CASCADE
    )


class CraftingRecord(SharedMemoryModel):
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="crafting_record",
    )
    recipe = models.ForeignKey(
        "CraftingRecipe",
        on_delete=models.CASCADE,
        related_name="crafting_records",
        null=True,
        blank=True,
    )
    quality_level = models.PositiveSmallIntegerField(default=0)
    crafted_by = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_crafts_records",
    )

    def set_refine_attempts(self, crafter, num_attempts):
        obj, _ = self.refine_attempts.get_or_create(crafter=crafter)
        obj.num_attempts = num_attempts
        obj.save()


class TranslatedDescription(SharedMemoryModel):
    """Stores a value in another language that is on an item."""

    objectdb = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="translations"
    )
    language = models.CharField(max_length=80)
    description = models.TextField()


class MaterialComposition(SharedMemoryModel):
    """Used for typeclasses that represent a material in-game"""

    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="material_composition",
    )
    material_type = models.ForeignKey("CraftingMaterialType", on_delete=models.CASCADE)


class RefineAttempt(SharedMemoryModel):
    """Stores attempts to refine a crafted item and improve its quality"""

    record = models.ForeignKey(
        "CraftingRecord", on_delete=models.CASCADE, related_name="refine_attempts"
    )
    crafter = models.ForeignKey(
        "objects.ObjectDB", on_delete=models.CASCADE, related_name="refine_attempts"
    )
    num_attempts = models.PositiveIntegerField(default=1)


class EquippedStatus(SharedMemoryModel):
    UNEQUIPPED, WORN, WIELDED = range(3)
    STATUS_CHOICES = (
        (UNEQUIPPED, "unequipped"),
        (WORN, "worn"),
        (WIELDED, "wielded"),
    )
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="equipped_status",
    )
    status = models.PositiveSmallIntegerField(
        default=UNEQUIPPED, choices=STATUS_CHOICES
    )
    worn_time = models.FloatField(default=0.0)
    ready_phrase = models.TextField(blank=True)

    @property
    def currently_worn(self):
        return self.status == self.WORN

    @currently_worn.setter
    def currently_worn(self, value):
        if not value:
            self.status = self.UNEQUIPPED
        else:
            self.status = self.WORN

    @property
    def currently_wielded(self):
        return self.status == self.WIELDED

    @currently_wielded.setter
    def currently_wielded(self, value):
        if not value:
            self.status = self.UNEQUIPPED
        else:
            self.status = self.WIELDED


class ArmorOverride(SharedMemoryModel):
    """
    Allows an item to have a value that overrides its normal value
    from recipe/quality level. Any value that is not null will override.
    Consequently, all the fields are nullable.
    """

    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="armor_override",
    )
    armor_penalty = models.DecimalField(
        null=True,
        blank=True,
        max_digits=6,
        decimal_places=2,
    )
    armor_resilience = models.DecimalField(
        null=True,
        blank=True,
        max_digits=6,
        decimal_places=2,
    )
    slot_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    slot = models.CharField(null=True, blank=True, max_length=80)


class MaskedDescription(SharedMemoryModel):
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="masked_description",
    )
    description = models.TextField()


class PlaceOccupation(SharedMemoryModel):
    character = models.OneToOneField(
        "objects.ObjectDB",
        related_name="place_occupation",
        on_delete=models.CASCADE,
    )
    place = models.ForeignKey(
        "objects.ObjectDB",
        related_name="occupying_characters",
        on_delete=models.CASCADE,
    )


class PlaceSpotsOverride(SharedMemoryModel):
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="place_spots_override",
    )
    max_spots = models.PositiveSmallIntegerField(default=1)


class WeaponOverride(SharedMemoryModel):
    objectdb = models.OneToOneField(
        "objects.ObjectDB",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="weapon_override",
    )
    attack_skill = models.CharField(null=True, blank=True, max_length=80)
    attack_stat = models.CharField(null=True, blank=True, max_length=80)
    damage_stat = models.CharField(null=True, blank=True, max_length=80)
    damage_bonus = models.PositiveSmallIntegerField(null=True, blank=True)
    attack_type = models.CharField(null=True, blank=True, max_length=80)
    can_be_parried = models.BooleanField(null=True, blank=True)
    can_be_blocked = models.BooleanField(null=True, blank=True)
    can_be_dodged = models.BooleanField(null=True, blank=True)
    can_be_countered = models.BooleanField(null=True, blank=True)
    can_parry = models.BooleanField(null=True, blank=True)
    can_riposte = models.BooleanField(null=True, blank=True)
    difficulty_mod = models.SmallIntegerField(null=True, blank=True)
    flat_damage_bonus = models.SmallIntegerField(null=True, blank=True)
