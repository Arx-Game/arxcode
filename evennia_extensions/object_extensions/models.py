"""
This is an app for providing storage for additional data we attach to
Evennia objects. Most tables here will have a one-to-one relationship
with Evennia's ObjectDB model.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class Dimensions(SharedMemoryModel):
    """
    Model for storing data about the physical dimensions of an object -
    its size, weight, and capacity for storing other objects. Fields, except
    for quantity, are nullable: any null field will be ignored in favor of
    defaults that are hardcoded into typeclasses. An object may set a single
    one of these fields, but all the rest would then be null and use their
    typeclass default values.
    """

    objectdb = models.OneToOneField(
        to="objects.ObjectDB", on_delete=models.CASCADE, primary_key=True
    )
    size = models.PositiveIntegerField(
        null=True,
        help_text="The amount of space this object takes up inside a container.",
    )
    weight = models.PositiveIntegerField(
        null=True, help_text="How heavy this object is."
    )
    capacity = models.PositiveIntegerField(null=True)
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="How many copies of this item there are, for stackable objects.",
    )
    is_locked = models.BooleanField(
        default=False, help_text="If this is a container or exit, whether it's locked."
    )

    class Meta:
        verbose_name_plural = "Dimensions"


class Permanence(SharedMemoryModel):
    """
    Model for storing values of when an object was changed/moved/deleted.
    """

    objectdb = models.OneToOneField(
        to="objects.ObjectDB", on_delete=models.CASCADE, primary_key=True
    )
    put_time = models.PositiveIntegerField(
        default=0,
        help_text="time.time() value of when an object was moved, used for sorting. "
        "We use integer time value here rather than datetime to prevent "
        "errors from null.",
    )
    deleted_time = models.DateTimeField(
        null=True,
        help_text="If set, this timestamp means an object is marked for deletion.",
        blank=True,
    )
    pre_offgrid_location = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.SET_NULL,
        related_name="offgrid_objects",
        help_text="Last location before an object was moved off-grid",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Permanence"


class DisplayNames(SharedMemoryModel):
    """
    Model for storing values of different display names for an object - such
    as a color-formatted version of the name, a name with titles, or a fake name
    from a mask. As with others, these are deliberately nullable because the
    wrappers explicitly check for a null value to see if an individual field
    should be ignored.
    """

    objectdb = models.OneToOneField(
        to="objects.ObjectDB",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="display_names",
    )
    false_name = models.CharField(null=True, blank=True, max_length=255)
    colored_name = models.TextField(null=True, blank=True)
    longname = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Display Names"


class Descriptions(SharedMemoryModel):
    """
    Model for displaying the description of an object. It defines a permanent
    description and a temporary description, the latter of which is used
    for things like masks or illusions.
    """
    permanent_description = models.TextField(blank=True)
    temporary_description = models.TextField(blank=True)
    objectdb = models.OneToOneField(
        to="objects.ObjectDB",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="descriptions",
    )
