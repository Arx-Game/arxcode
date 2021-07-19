from django.core.exceptions import ObjectDoesNotExist
from django.db import migrations, models
import django.db.models.deletion
from server.utils.progress_bar import ProgressBar


def change_bonus_max_hp_attribute_to_trait(apps, schema_editor):
    """Forgot to convert bonus_max_hp before"""
    Attribute = apps.get_model("typeclasses", "Attribute")
    Trait = apps.get_model("traits", "Trait")
    CharacterTraitValue = apps.get_model("traits", "CharacterTraitValue")
    qs = Attribute.objects.filter(db_key="bonus_max_hp")
    trait = Trait.objects.get(name="bonus_max_hp")
    num = 0
    total = len(qs)
    if total:
        print(f"\nConverting {total} bonus_max_hp attributes")
    for ob in qs:
        num += 1
        progress = num / total
        print(ProgressBar(progress, "Progress: "), end="\r", flush=True)
        try:
            objdb = ob.objectdb_set.all()[0]
            value = int(ob.db_value)
            CharacterTraitValue.objects.update_or_create(
                character=objdb, trait=trait, defaults=dict(value=value)
            )
            ob.delete()
        except (AttributeError, ValueError, TypeError, IndexError, KeyError) as err:
            ob.delete()
            continue


def convert_skill_history(apps, schema_editor):
    """Converts the skill_history attribute to TraitPurchase objects"""
    Attribute = apps.get_model("typeclasses", "Attribute")
    Trait = apps.get_model("traits", "Trait")
    TraitPurchase = apps.get_model("traits", "TraitPurchase")
    qs = Attribute.objects.filter(db_key="skill_history")
    total = len(qs)
    num = 0
    if total:
        print(f"\nConverting {total} skill_history attributes")
    for ob in qs:
        num += 1
        progress = num / total
        print(ProgressBar(progress, "Progress: "), end="\r", flush=True)
        try:
            objdb = ob.objectdb_set.all()[0]
            try:
                for skill_name, cost_list in ob.db_value.items():
                    trait = Trait.objects.get(name__iexact=skill_name)
                    cost_list = list(cost_list)
                    for cost in cost_list:
                        TraitPurchase.objects.create(
                            cost=int(cost), character=objdb, trait=trait
                        )
            except (ObjectDoesNotExist, TypeError, ValueError):
                continue
            ob.delete()
        except (AttributeError, ValueError, TypeError, IndexError, KeyError) as err:
            ob.delete()
            continue


class Migration(migrations.Migration):

    dependencies = [
        ("traits", "0002_auto_20201108_1757"),
        ("stat_checks", "0003_auto_20201227_1710"),
    ]

    operations = [
        migrations.CreateModel(
            name="TraitPurchase",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cost", models.SmallIntegerField(default=0)),
                ("date_bought", models.DateTimeField(auto_now_add=True)),
                (
                    "character",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trait_purchases",
                        to="objects.ObjectDB",
                    ),
                ),
                (
                    "trait",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="purchases",
                        to="traits.Trait",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.RunPython(
            change_bonus_max_hp_attribute_to_trait,
            migrations.RunPython.noop,
            elidable=True,
        ),
        migrations.RunPython(
            convert_skill_history,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
