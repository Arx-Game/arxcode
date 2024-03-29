# Generated by Django 2.2.24 on 2021-09-06 14:57

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def populate_new_tables(apps, schema_editor):
    CheckRank = apps.get_model("stat_checks", "CheckRank")
    StatWeight = apps.get_model("stat_checks", "StatWeight")
    # weight for stat + skill in new system
    StatWeight.objects.create(stat_type=8, level=1, weight=10)
    # weight for stat alone
    StatWeight.objects.create(stat_type=9, level=1, weight=20)
    # ascending ranks in terms of difficulty/power
    CheckRank.objects.create(
        id=0,
        value=0,
        name="Laughably weak",
        description="Trivial things. Walking up stairs. Fighting a tiny kitten.",
    )
    CheckRank.objects.create(
        id=1,
        value=20,
        name="Weak",
        description="Very easy things. Fighting an unarmed and untrained serf.",
    )
    CheckRank.objects.create(
        id=2,
        value=40,
        name="Mediocre",
        description="Normal difficulty. Fighting an armed but unimpressive mook.",
    )
    CheckRank.objects.create(
        id=3,
        value=60,
        name="Above average",
        description="Slightly hard things. Fighting a trained guard.",
    )
    CheckRank.objects.create(
        id=4,
        value=80,
        name="Exceptional",
        description="Hard things. Fighting elite/veteran guards.",
    )
    CheckRank.objects.create(
        id=5,
        value=100,
        name="Extraordinary",
        description="Very difficult things. Fighting extraordinary warriors.",
    )
    CheckRank.objects.create(
        id=6,
        value=150,
        name="Legendary",
        description="The start of superhuman feats. Fighting a legendary warrior.",
    )
    CheckRank.objects.create(
        id=7,
        value=225,
        name="Boss I",
        description="Fighting most starting bosses is here",
    )
    CheckRank.objects.create(
        id=8, value=300, name="Boss II", description="Intermediate bosses"
    )
    CheckRank.objects.create(
        id=9, value=400, name="Boss III", description="Hard bosses"
    )
    CheckRank.objects.create(
        id=10,
        value=500,
        name="Herokiller I",
        description="Starting herokillers that would be impossible for ordinary "
        "people to defeat without some advantage. Gargantuans. "
        "Somewhat potent demons.",
    )
    CheckRank.objects.create(
        id=11,
        value=700,
        name="Herokiller II",
        description="Probably most advanced magic users would be here.",
    )
    CheckRank.objects.create(
        id=12,
        value=900,
        name="Herokiller III",
        description="Low-ranking demon nobility, young-adult dragons.",
    )
    CheckRank.objects.create(
        id=13,
        value=1100,
        name="Herokiller IV",
        description="Mid-rank demon nobility, very powerful mages.",
    )
    CheckRank.objects.create(
        id=14,
        value=1300,
        name="Herokiller V",
        description="High-ranking demon nobility.",
    )
    CheckRank.objects.create(
        id=15,
        value=1500,
        name="Epic I",
        description="Archmages, demon lords, adult dragons. This is probably about "
        "the theoretical max PCs might be able to one day achieve.",
    )
    CheckRank.objects.create(
        id=16,
        value=1700,
        name="Epic II",
        description="The less powerful Fractals, Metallics, etc.",
    )
    CheckRank.objects.create(
        id=17,
        value=1900,
        name="Epic III",
        description="More average among Fractals/Metallics/etc",
    )
    CheckRank.objects.create(
        id=18,
        value=2100,
        name="Epic IV",
        description="Above average Fractals/Metallics",
    )
    CheckRank.objects.create(
        id=19,
        value=2300,
        name="Epic V",
        description="Very strong even for Fractals/Metallics, which is saying a lot",
    )
    CheckRank.objects.create(
        id=20,
        value=2500,
        name="ArchEpic I",
        description="The most powerful beings that were once mortal.",
    )
    CheckRank.objects.create(
        id=21, value=2900, name="ArchEpic II", description="Weaker demigods, primordia"
    )
    CheckRank.objects.create(
        id=22,
        value=3300,
        name="ArchEpic III",
        description="Somewhat stronger demigods, primordia, Passions, etc",
    )
    CheckRank.objects.create(
        id=23, value=3700, name="ArchEpic IV", description="The Kindly Voices."
    )
    CheckRank.objects.create(
        id=24,
        value=4100,
        name="ArchEpic V",
        description="The most powerful beings that can enter the world, but "
        "not easily and at great cost.",
    )
    CheckRank.objects.create(
        id=25,
        value=4500,
        name="God I",
        description="Lesser gods/archfiends. Can not enter the world without "
        "things going very, very badly.",
    )
    CheckRank.objects.create(
        id=26, value=6000, name="God II", description="Intermediate gods."
    )
    CheckRank.objects.create(
        id=27, value=8000, name="God III", description="More powerful gods."
    )
    CheckRank.objects.create(
        id=28, value=11000, name="God IV", description="Elder gods."
    )
    CheckRank.objects.create(
        id=29,
        value=15000,
        name="God V",
        description="Let the Sleeper awaken and burn the world anew.",
    )
    CheckRank.objects.create(
        id=30,
        value=25000,
        name="God VI",
        description="This happens when gods eat one another. Run.",
    )
    # add DifficultyTables
    DifficultyTable = apps.get_model("stat_checks", "DifficultyTable")
    plus_8 = DifficultyTable.objects.create(value=8, name="Guaranteed Success")
    plus_7 = DifficultyTable.objects.create(value=7, name="Insultingly Trivial")
    plus_6 = DifficultyTable.objects.create(value=6, name="Very Trivial")
    plus_5 = DifficultyTable.objects.create(value=5, name="Trivial")
    plus_4 = DifficultyTable.objects.create(value=4, name="Very Easy")
    plus_3 = DifficultyTable.objects.create(value=3, name="Easy")
    plus_2 = DifficultyTable.objects.create(value=2, name="Moderate")
    plus_1 = DifficultyTable.objects.create(value=1, name="Slightly Challenging")
    plus_0 = DifficultyTable.objects.create(value=0, name="Challenging")
    neg_1 = DifficultyTable.objects.create(value=-1, name="Challenging + 1")
    neg_2 = DifficultyTable.objects.create(value=-2, name="Challenging + 2")
    neg_3 = DifficultyTable.objects.create(value=-3, name="Challenging + 3")
    neg_4 = DifficultyTable.objects.create(value=-4, name="Challenging + 4")
    neg_5 = DifficultyTable.objects.create(value=-5, name="Challenging + 5")
    neg_6 = DifficultyTable.objects.create(value=-6, name="Challenging + 6")
    neg_7 = DifficultyTable.objects.create(value=-7, name="Challenging + 7")
    neg_8 = DifficultyTable.objects.create(value=-8, name="Impossible")

    # now the long part - adding the difficulty ranges for each and every table
    Range = apps.get_model("stat_checks", "DifficultyTableResultRange")
    RollResult = apps.get_model("stat_checks", "RollResult")
    botch_2 = RollResult.objects.get(value=-260)
    botch_1 = RollResult.objects.get(value=-160)
    fails = RollResult.objects.get(name="fails")
    marginal_fail = RollResult.objects.get(name="marginally fails")
    marginal_success = RollResult.objects.get(name="marginally successful")
    success = RollResult.objects.get(name="successful")
    crit_1 = RollResult.objects.get(name="spectacularly successful")
    crit_2 = RollResult.objects.get(name="inhumanly successful")
    opposites = {
        # successes to failures
        marginal_success: marginal_fail,
        success: fails,
        crit_1: botch_1,
        crit_2: botch_2,
        # failures to successes
        marginal_fail: marginal_success,
        fails: success,
        botch_1: crit_1,
        botch_2: crit_2,
    }

    def create_inverse(range_list, diff):
        """Creates opposite range for inverse table"""
        range_list = reversed(range_list)
        value = 1
        prev_value = 101
        for range_obj in range_list:
            Range.objects.create(
                value=value, result=opposites[range_obj.result], difficulty_table=diff
            )
            # get the value of the next based on the range that's been covered
            value += prev_value - range_obj.value
            prev_value = range_obj.value

    # plus_8 is guaranteed to always succeed
    ranges = [
        Range.objects.create(difficulty_table=plus_8, result=marginal_success, value=1),
        Range.objects.create(difficulty_table=plus_8, result=success, value=2),
        Range.objects.create(difficulty_table=plus_8, result=crit_1, value=21),
        Range.objects.create(difficulty_table=plus_8, result=crit_2, value=61),
    ]
    create_inverse(ranges, neg_8)

    # plus_7 has an incredibly small chance of failure
    ranges = [
        Range.objects.create(difficulty_table=plus_7, result=marginal_fail, value=1),
        Range.objects.create(difficulty_table=plus_7, result=marginal_success, value=2),
        Range.objects.create(difficulty_table=plus_7, result=success, value=3),
        Range.objects.create(difficulty_table=plus_7, result=crit_1, value=61),
        Range.objects.create(difficulty_table=plus_7, result=crit_2, value=81),
    ]
    create_inverse(ranges, neg_7)

    # plus_6
    ranges = [
        Range.objects.create(difficulty_table=plus_6, result=fails, value=1),
        Range.objects.create(difficulty_table=plus_6, result=marginal_fail, value=2),
        Range.objects.create(difficulty_table=plus_6, result=marginal_success, value=3),
        Range.objects.create(difficulty_table=plus_6, result=success, value=10),
        Range.objects.create(difficulty_table=plus_6, result=crit_1, value=71),
        Range.objects.create(difficulty_table=plus_6, result=crit_2, value=91),
    ]
    create_inverse(ranges, neg_6)

    # plus 5
    ranges = [
        Range.objects.create(difficulty_table=plus_5, result=fails, value=1),
        Range.objects.create(difficulty_table=plus_5, result=marginal_fail, value=6),
        Range.objects.create(
            difficulty_table=plus_5, result=marginal_success, value=11
        ),
        Range.objects.create(difficulty_table=plus_5, result=success, value=21),
        Range.objects.create(difficulty_table=plus_5, result=crit_1, value=81),
        Range.objects.create(difficulty_table=plus_5, result=crit_2, value=96),
    ]
    create_inverse(ranges, neg_5)

    # plus 4
    ranges = [
        Range.objects.create(difficulty_table=plus_4, result=botch_1, value=1),
        Range.objects.create(difficulty_table=plus_4, result=fails, value=2),
        Range.objects.create(difficulty_table=plus_4, result=marginal_fail, value=9),
        Range.objects.create(
            difficulty_table=plus_4, result=marginal_success, value=19
        ),
        Range.objects.create(difficulty_table=plus_4, result=success, value=39),
        Range.objects.create(difficulty_table=plus_4, result=crit_1, value=92),
        Range.objects.create(difficulty_table=plus_4, result=crit_2, value=98),
    ]
    create_inverse(ranges, neg_4)

    # plus_3
    ranges = [
        Range.objects.create(difficulty_table=plus_3, result=botch_1, value=1),
        Range.objects.create(difficulty_table=plus_3, result=fails, value=3),
        Range.objects.create(difficulty_table=plus_3, result=marginal_fail, value=13),
        Range.objects.create(
            difficulty_table=plus_3, result=marginal_success, value=27
        ),
        Range.objects.create(difficulty_table=plus_3, result=success, value=41),
        Range.objects.create(difficulty_table=plus_3, result=crit_1, value=93),
        Range.objects.create(difficulty_table=plus_3, result=crit_2, value=99),
    ]
    create_inverse(ranges, neg_3)

    # plus_2
    ranges = [
        Range.objects.create(difficulty_table=plus_2, result=botch_2, value=1),
        Range.objects.create(difficulty_table=plus_2, result=botch_1, value=2),
        Range.objects.create(difficulty_table=plus_2, result=fails, value=4),
        Range.objects.create(difficulty_table=plus_2, result=marginal_fail, value=19),
        Range.objects.create(
            difficulty_table=plus_2, result=marginal_success, value=35
        ),
        Range.objects.create(difficulty_table=plus_2, result=success, value=45),
        Range.objects.create(difficulty_table=plus_2, result=crit_1, value=94),
        Range.objects.create(difficulty_table=plus_2, result=crit_2, value=99),
    ]
    create_inverse(ranges, neg_2)

    # plus_1
    ranges = [
        Range.objects.create(difficulty_table=plus_1, result=botch_2, value=1),
        Range.objects.create(difficulty_table=plus_1, result=botch_1, value=2),
        Range.objects.create(difficulty_table=plus_1, result=fails, value=5),
        Range.objects.create(difficulty_table=plus_1, result=marginal_fail, value=23),
        Range.objects.create(
            difficulty_table=plus_1, result=marginal_success, value=43
        ),
        Range.objects.create(difficulty_table=plus_1, result=success, value=51),
        Range.objects.create(difficulty_table=plus_1, result=crit_1, value=95),
        Range.objects.create(difficulty_table=plus_1, result=crit_2, value=99),
    ]
    create_inverse(ranges, neg_1)

    # plus_0, finally equal. Enter Thanos here saying something about balance
    ranges = [
        Range.objects.create(difficulty_table=plus_0, result=botch_2, value=1),
        Range.objects.create(difficulty_table=plus_0, result=botch_1, value=2),
        Range.objects.create(difficulty_table=plus_0, result=fails, value=6),
        Range.objects.create(difficulty_table=plus_0, result=marginal_fail, value=46),
        Range.objects.create(
            difficulty_table=plus_0, result=marginal_success, value=51
        ),
        Range.objects.create(difficulty_table=plus_0, result=success, value=56),
        Range.objects.create(difficulty_table=plus_0, result=crit_1, value=96),
        Range.objects.create(difficulty_table=plus_0, result=crit_2, value=100),
    ]
    # no inverse


class Migration(migrations.Migration):

    dependencies = [
        ("stat_checks", "0003_auto_20201227_1710"),
    ]

    operations = [
        migrations.CreateModel(
            name="CheckRank",
            fields=[
                ("name", models.CharField(max_length=150, unique=True)),
                (
                    "id",
                    models.SmallIntegerField(
                        help_text="The rank number itself (rank 1, rank 2, etc).",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("description", models.TextField()),
                (
                    "value",
                    models.SmallIntegerField(
                        verbose_name="minimum check value for this rank", unique=True
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="DifficultyTable",
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
        migrations.AddField(
            model_name="statcheck",
            name="public",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="statcombination",
            name="combined_into",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="child_combinations",
                to="stat_checks.StatCombination",
            ),
        ),
        migrations.AlterField(
            model_name="statweight",
            name="stat_type",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "skill"),
                    (1, "stat"),
                    (2, "ability"),
                    (3, "knack"),
                    (4, "stat with no skill"),
                    (5, "health for stamina"),
                    (6, "health for boss rating"),
                    (7, "miscellaneous values (armor class, etc)"),
                    (8, "trait in new check system"),
                    (9, "trait as a lone value in new check system"),
                ],
                default=0,
            ),
        ),
        migrations.CreateModel(
            name="DifficultyTableResultRange",
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
                    "value",
                    models.IntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MaxValueValidator(100),
                            django.core.validators.MinValueValidator(1),
                        ],
                    ),
                ),
                (
                    "difficulty_table",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result_ranges",
                        to="stat_checks.DifficultyTable",
                    ),
                ),
                (
                    "result",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result_ranges",
                        to="stat_checks.RollResult",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Difficulty Table Result Ranges",
                "unique_together": {
                    ("difficulty_table", "value"),
                    ("difficulty_table", "result"),
                },
            },
        ),
        migrations.AddField(
            model_name="difficultytable",
            name="roll_results",
            field=models.ManyToManyField(
                related_name="difficulty_tables",
                through="stat_checks.DifficultyTableResultRange",
                to="stat_checks.RollResult",
            ),
        ),
        migrations.RunPython(
            populate_new_tables, migrations.RunPython.noop, elidable=False
        ),
    ]
