from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    replaces = [
        # ("character", "0025_storyemit_orgs"),
        # ("character", "0026_playerinfoentry_playersiteentry"),
        # ("character", "0027_playerinfoentry_entry_date"),
        # ("character", "0028_playerinfoentry_author"),
        # ("character", "0029_auto_20181111_2007"),
        # ("character", "0030_auto_20180828_0040"),
        # ("character", "0031_auto_20181116_1219"),
        # ("character", "0032_theory_plots"),
        # ("character", "0033_goal_goalupdate"),
        # ("character", "0034_auto_20190508_1944"),
        # ("character", "0035_auto_20191228_1417"),
        # ("character", "0036_auto_20201115_1451"),
    ]
    dependencies = [
        ("character", "0001_squashed_character"),
        ("dominion", "0001_squashed_dominion"),
    ]

    operations = [
        migrations.CreateModel(
            name="RevelationPlotInvolvement",
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
                    "plot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revelation_involvement",
                        to="dominion.Plot",
                    ),
                ),
                (
                    "revelation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plot_involvement",
                        to="character.Revelation",
                    ),
                ),
                ("gm_notes", models.TextField(blank=True)),
            ],
            options={
                "abstract": False,
                "unique_together": {("revelation", "plot")},
            },
        ),
        migrations.AddField(
            model_name="flashback",
            name="beat",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="flashbacks",
                to="dominion.PlotUpdate",
            ),
        ),
        migrations.AddField(
            model_name="goalupdate",
            name="beat",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="goal_updates",
                to="dominion.PlotUpdate",
            ),
        ),
        migrations.AddField(
            model_name="storyemit",
            name="beat",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="emits",
                to="dominion.PlotUpdate",
            ),
        ),
        migrations.AddField(
            model_name="revelation",
            name="plots",
            field=models.ManyToManyField(
                blank=True,
                related_name="revelations",
                through="character.RevelationPlotInvolvement",
                to="dominion.Plot",
            ),
        ),
        migrations.CreateModel(
            name="CluePlotInvolvement",
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
                        related_name="plot_involvement",
                        to="character.Clue",
                    ),
                ),
                (
                    "plot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clue_involvement",
                        to="dominion.Plot",
                    ),
                ),
                ("gm_notes", models.TextField(blank=True)),
                (
                    "access",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "Neutral"), (1, "Hooked"), (2, "Granted")],
                        default=0,
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("clue", "plot")},
            },
        ),
        migrations.AddField(
            model_name="clue",
            name="plots",
            field=models.ManyToManyField(
                blank=True,
                related_name="clues",
                through="character.CluePlotInvolvement",
                to="dominion.Plot",
            ),
        ),
        migrations.AddField(
            model_name="goal",
            name="plot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="goals",
                to="dominion.Plot",
            ),
        ),
        migrations.AddField(
            model_name="theory",
            name="plots",
            field=models.ManyToManyField(
                blank=True, related_name="theories", to="dominion.Plot"
            ),
        ),
        migrations.AddField(
            model_name="storyemit",
            name="orgs",
            field=models.ManyToManyField(
                blank=True, related_name="emits", to="dominion.Organization"
            ),
        ),
    ]
