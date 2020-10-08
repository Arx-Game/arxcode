# Generated by Django 2.2.16 on 2020-09-15 19:38

from django.db import migrations, models
import django.db.models.deletion


def add_defaults(apps, schema_editor):
    DifficultyRating = apps.get_model("stat_checks", "DifficultyRating")
    DifficultyRating.objects.create(name="easy", value=25)
    DifficultyRating.objects.create(name="normal", value=50)
    DifficultyRating.objects.create(name="hard", value=75)
    DifficultyRating.objects.create(name="daunting", value=95)
    StatWeight = apps.get_model("stat_checks", "StatWeight")
    # skill
    StatWeight.objects.create(stat_type=0, level=1, weight=4)
    StatWeight.objects.create(stat_type=0, level=2, weight=5)
    StatWeight.objects.create(stat_type=0, level=3, weight=6)
    StatWeight.objects.create(stat_type=0, level=4, weight=7)
    StatWeight.objects.create(stat_type=0, level=5, weight=8)
    StatWeight.objects.create(stat_type=0, level=6, weight=10)
    # other
    StatWeight.objects.create(stat_type=1, level=1, weight=1)
    StatWeight.objects.create(stat_type=3, level=1, weight=1)
    # stat only
    StatWeight.objects.create(stat_type=4, level=1, weight=5)
    StatWeight.objects.create(stat_type=4, level=2, weight=6)
    StatWeight.objects.create(stat_type=4, level=3, weight=7)
    StatWeight.objects.create(stat_type=4, level=4, weight=8)
    StatWeight.objects.create(stat_type=4, level=5, weight=10)
    StatWeight.objects.create(stat_type=4, level=6, weight=15)
    StatWeight.objects.create(stat_type=5, level=0, weight=75)
    StatWeight.objects.create(stat_type=5, level=1, weight=25)
    StatWeight.objects.create(stat_type=6, level=1, weight=100)
    RollResult = apps.get_model("stat_checks", "RollResult")
    RollResult.objects.create(
        name="marginally successful",
        value=0,
        template="{{character}} is |240{{result}}|n.",
    )
    RollResult.objects.create(
        name="successful", value=16, template="{{character}} is |g{{result}}|n."
    )
    RollResult.objects.create(
        name="spectacularly successful",
        value=51,
        template="|542{% if crit %}{{ crit|title }}! {% endif %}{{character}} is {{result}}|n.",
    )
    RollResult.objects.create(
        name="inhumanly successful",
        value=151,
        template="|542{% if crit %}{{ crit|title }}! {% endif %}{{character}} is "
        "{{result}} in a way that defies expectations.|n",
    )
    RollResult.objects.create(
        name="marginally fails", value=-15, template="{{character}} |512{{result}}|n."
    )
    RollResult.objects.create(
        name="fails", value=-60, template="{{character}} |r{{result}}|n."
    )
    RollResult.objects.create(
        name="catastrophically fails",
        value=-160,
        template="{% if botch %}{{ botch|title }}! {% endif %}{{character}} |505{{result}}|n.",
    )
    RollResult.objects.create(
        name="simply outclassed",
        value=-260,
        template="|505{% if botch %}{{ botch|title }}! {% endif %}{{character}} is {{result}}. "
        "This is monumentally beyond them and the result is ruinous.|n.",
    )
    NaturalRollType = apps.get_model("stat_checks", "NaturalRollType")
    NaturalRollType.objects.create(name="critical success", value=96, result_shift=1)
    NaturalRollType.objects.create(name="botch", value=5, value_type=1, result_shift=-1)
    DamageRating = apps.get_model("stat_checks", "DamageRating")
    DamageRating.objects.create(name="bruise", value=1, max_value=10, armor_cap=90)
    DamageRating.objects.create(name="light", value=5, max_value=20, armor_cap=80)
    DamageRating.objects.create(name="medium", value=20, max_value=40, armor_cap=60)
    DamageRating.objects.create(name="heavy", value=40, max_value=80, armor_cap=40)
    DamageRating.objects.create(name="severe", value=70, max_value=110, armor_cap=25)
    DamageRating.objects.create(name="extreme", value=100, max_value=200, armor_cap=10)
    DamageRating.objects.create(name="nuke", value=200, max_value=350, armor_cap=5)


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DifficultyRating",
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
                ("name", models.CharField(max_length=150, unique=True)),
                (
                    "value",
                    models.SmallIntegerField(
                        unique=True,
                        verbose_name="minimum value for this difficulty range/rating",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="NaturalRollType",
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
                ("name", models.CharField(max_length=150, unique=True)),
                (
                    "value",
                    models.SmallIntegerField(
                        unique=True,
                        verbose_name="minimum value for this difficulty range/rating",
                    ),
                ),
                (
                    "value_type",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "lower bound"), (1, "upper bound")],
                        default=0,
                        help_text="If this is a lower bound, then rolls higher than value are of this type. If it's an upper bound, then rolls lower than it are of this type. It finds the closest boundary for the roll. So for example, you could have 'crit' of value 95, and then a higher crit called 'super crit' with a lower bound of 98, for 98-100 rolls.",
                        verbose_name="The type of boundary for value",
                    ),
                ),
                (
                    "result_shift",
                    models.SmallIntegerField(
                        default=0,
                        help_text="The number of levels to shift the result by, whether up or down. 1"
                        " for a crit would shift the result up by 1, such that a normal "
                        "success turns into the level above normal. Use negative numbers "
                        "for a botch/fumble (which should have an upper bound value "
                        "type).",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="RollResult",
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
                ("name", models.CharField(max_length=150, unique=True)),
                (
                    "value",
                    models.SmallIntegerField(
                        unique=True,
                        verbose_name="minimum value for this difficulty range/rating",
                    ),
                ),
                (
                    "template",
                    models.TextField(
                        help_text="A jinja2 template string that will be output with the message for this result. 'character' is the context variable for the roller: eg: '{{character}} fumbles.'"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="StatWeight",
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
                (
                    "stat_type",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "skill"),
                            (1, "stat"),
                            (2, "ability"),
                            (3, "knack"),
                            (4, "stat with no skill"),
                            (5, "health for stamina"),
                            (6, "health for boss rating"),
                        ],
                        default=0,
                    ),
                ),
                (
                    "level",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Set the level for the minimum rating in the stat for this weight to be used. With the default of 0 and no other weights set for this type, all levels of the type of stat (stat, skill, etc) will add a linear amount rather than curving.",
                        verbose_name="minimum level of stat for this weight",
                    ),
                ),
                (
                    "weight",
                    models.SmallIntegerField(
                        default=1,
                        help_text="This is the multiplier for how much to add to a roll for a stat/skill of at least this level, until it encounters a higher level value you assign. For example, a StatWeight(stat_type=STAT, level=0, weight=1) would give +1 for each level of the stat. If you added a StatWeight(stat_type=STAT, level=6, weight=10), then if they have a stat of 7 they would get 5 + 20.",
                        verbose_name="weight for this level of the stat",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DamageRating",
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
                ("name", models.CharField(max_length=150, unique=True)),
                ("value", models.SmallIntegerField(verbose_name="minimum damage")),
                ("max_value", models.SmallIntegerField(verbose_name="maximum damage")),
                (
                    "armor_cap",
                    models.SmallIntegerField(
                        help_text="Percent of damage armor can prevent. 100 means armor can completely negate the attack."
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.RunPython(add_defaults, migrations.RunPython.noop),
    ]
