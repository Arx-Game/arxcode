# Generated by Django 2.2.20 on 2021-06-07 22:53

from django.db import migrations, models
import django.db.models.deletion
from django.core.exceptions import ObjectDoesNotExist


def convert_prelogout_location(apps, schema_editor):
    Attribute = apps.get_model("typeclasses", "Attribute")
    Permanence = apps.get_model("object_extensions", "Permanence")
    ObjectDB = apps.get_model("objects", "ObjectDB")

    # set deleted objects
    qs = Attribute.objects.filter(db_key="prelogout_location")
    locations = {}
    for attr in qs:
        try:
            objdb = attr.objectdb_set.all()[0]
            location_id = attr.db_value[-1]
            if location_id in locations:
                location = locations[location_id]
            else:
                location = ObjectDB.objects.get(id=location_id)
                locations[location_id] = location
            Permanence.objects.get_or_create(
                objectdb=objdb, defaults=dict(pre_offgrid_location=location)
            )
        except (TypeError, ValueError, IndexError, KeyError, ObjectDoesNotExist) as err:
            print(f"Failed to convert {attr.id}: {err}")
    qs.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("object_extensions", "0003_dimensions_is_locked"),
    ]

    operations = [
        migrations.AddField(
            model_name="permanence",
            name="pre_offgrid_location",
            field=models.ForeignKey(
                blank=True,
                help_text="Last location before an object was moved off-grid",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="offgrid_objects",
                to="objects.ObjectDB",
            ),
        ),
        migrations.RunPython(
            convert_prelogout_location, migrations.RunPython.noop, elidable=True
        ),
    ]
