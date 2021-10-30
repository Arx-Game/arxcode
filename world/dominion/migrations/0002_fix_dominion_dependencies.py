from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    replaces = [
        # ("dominion", "0035_auto_20180831_0922"),
        # ("dominion", "0036_plotaction_working"),
        # ("dominion", "0037_auto_20181207_1202"),
        # ("dominion", "0038_auto_20181212_2111"),
        # ("dominion", "0039_prestigetier"),
        # ("dominion", "0040_auto_20181216_1510"),
        # ("dominion", "0041_prestigenomination"),
        # ("dominion", "0042_auto_20181216_1658"),
        # ("dominion", "0043_auto_20181230_1627"),
        # ("dominion", "0044_auto_20190225_2014"),
        # ("dominion", "0045_auto_20190415_2022"),
        # ("dominion", "0046_auto_20191228_1417"),
        # ("dominion", "0047_actionrequirement"),
        # ("dominion", "0048_auto_20200719_1248"),
    ]

    dependencies = [
        ("dominion", "0001_squashed_dominion"),
        # ("character", "0009_investigation_roll"),
        # ("character", "0005_auto_20170122_0008"),
        # ("character", "0019_auto_20171029_1416"),
        # ("character", "0004_auto_20161217_0654"),
        # ("character", "0015_auto_20170605_2252"),
        # ("character", "0022_auto_20171226_0208"),
        # ("character", "0035_auto_20191228_1417"),
        ("magic", "0001_squashed_magic"),
        # ("exploration", "0003_auto_20181105_1756"),
        ("exploration", "0001_squashed_exploration"),
        ("character", "0001_squashed_character"),
    ]

    operations = [
        migrations.AddField(
            model_name="plotroom",
            name="shardhaven_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tilesets",
                to="exploration.ShardhavenType",
            ),
        ),
        migrations.CreateModel(
            name="ClueForOrg",
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
                    "clue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="org_discoveries",
                        to="character.Clue",
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clue_discoveries",
                        to="dominion.Organization",
                    ),
                ),
                (
                    "revealed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clues_added_to_orgs",
                        to="character.RosterEntry",
                    ),
                ),
            ],
            options={
                "unique_together": {("clue", "org")},
            },
        ),
        migrations.AddField(
            model_name="organization",
            name="clues",
            field=models.ManyToManyField(
                blank=True,
                related_name="orgs",
                through="dominion.ClueForOrg",
                to="character.Clue",
            ),
        ),
        migrations.CreateModel(
            name="ActionRequirement",
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
                    "requirement_type",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "silver"),
                            (1, "military resources"),
                            (2, "economic resources"),
                            (3, "social resources"),
                            (4, "action points"),
                            (5, "clue"),
                            (6, "revelation"),
                            (7, "magic skill node"),
                            (8, "spell"),
                            (9, "military forces"),
                            (10, "item"),
                            (11, "Other Requirement/Event"),
                        ],
                        default=0,
                    ),
                ),
                (
                    "total_required_amount",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Amount for resources/AP"
                    ),
                ),
                (
                    "max_rate",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="If greater than 0, max amount that can be added per week",
                    ),
                ),
                (
                    "weekly_total",
                    models.PositiveIntegerField(
                        default=0, verbose_name="Amount added so far this week"
                    ),
                ),
                (
                    "requirement_text",
                    models.TextField(
                        blank=True,
                        verbose_name="Specifies what you want the player to add for military forces or an event",
                    ),
                ),
                (
                    "explanation",
                    models.TextField(
                        blank=True,
                        verbose_name="Explanation by fulfilling player of how the requirement is met",
                    ),
                ),
                (
                    "action",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requirements",
                        to="dominion.PlotAction",
                    ),
                ),
                (
                    "clue",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="character.Clue",
                    ),
                ),
                (
                    "fulfilled_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="For non-amount clues, who satisfied the requirement",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requirements_fulfilled",
                        to="dominion.PlayerOrNpc",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="objects.ObjectDB",
                    ),
                ),
                (
                    "revelation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="character.Revelation",
                    ),
                ),
                (
                    "rfr",
                    models.ForeignKey(
                        blank=True,
                        help_text="PlotUpdate that player specified to fill this requirement",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="dominion.PlotUpdate",
                    ),
                ),
                (
                    "skill_node",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="magic.SkillNode",
                    ),
                ),
                (
                    "spell",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="magic.Spell",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="rpevent",
            name="search_tags",
            field=models.ManyToManyField(
                blank=True, related_name="events", to="character.SearchTag"
            ),
        ),
        migrations.AddField(
            model_name="plot",
            name="search_tags",
            field=models.ManyToManyField(
                blank=True, related_name="plots", to="character.SearchTag"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="theories",
            field=models.ManyToManyField(
                blank=True, related_name="orgs", to="character.Theory"
            ),
        ),
        migrations.AddField(
            model_name="plot",
            name="required_clue",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="crises",
                to="character.Clue",
            ),
        ),
        migrations.AddField(
            model_name="plot",
            name="chapter",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="crises",
                to="character.Chapter",
            ),
        ),
        migrations.AddField(
            model_name="plotupdate",
            name="episode",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="plot_updates",
                to="character.Episode",
            ),
        ),
        migrations.AddField(
            model_name="plotupdate",
            name="search_tags",
            field=models.ManyToManyField(
                blank=True,
                related_name="plot_updates",
                to="character.SearchTag",
            ),
        ),
        migrations.AddField(
            model_name="plotaction",
            name="search_tags",
            field=models.ManyToManyField(
                blank=True, related_name="actions", to="character.SearchTag"
            ),
        ),
        migrations.AddField(
            model_name="plotaction",
            name="gemit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="actions",
                to="character.StoryEmit",
            ),
        ),
        migrations.AddField(
            model_name="plotaction",
            name="working",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="action",
                to="magic.Working",
            ),
        ),
    ]
