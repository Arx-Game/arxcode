from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    replaces = [
        # ("exploration", "0046_shardhavenpuzzle_name"),
        # ("exploration", "0047_auto_20181122_2250"),
        # ("exploration", "0048_shardhavenpuzzle_haven_types"),
        # ("exploration", "0049_auto_20181123_0105"),
        # ("exploration", "0050_auto_20181123_1233"),
        # ("exploration", "0051_auto_20181123_1244"),
        # ("exploration", "0052_auto_20181123_1307"),
        # ("exploration", "0053_auto_20181202_2019"),
        # ("exploration", "0054_auto_20191228_1417"),
    ]

    dependencies = [
        # ("dominion", "0032_auto_20180831_0557"),
        ("dominion", "0001_squashed_dominion"),
        ("magic", "0006_auto_20181202_2018"),
        ("magic", "0004_alchemicalmaterial_plural_name"),
        ("magic", "0002_auto_20181113_2246"),
        # ("character", "0025_storyemit_orgs"),
        # ("character", "0029_auto_20181111_2007"),
        ("character", "0001_squashed_character"),
        ("exploration", "0001_squashed_exploration"),
    ]

    operations = [
        migrations.AddField(
            model_name="shardhaven",
            name="discovered_by",
            field=models.ManyToManyField(
                blank=True,
                related_name="discovered_shardhavens",
                through="exploration.ShardhavenDiscovery",
                to="dominion.PlayerOrNpc",
            ),
        ),
        migrations.AddField(
            model_name="shardhaven",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shardhavens",
                to="dominion.MapLocation",
            ),
        ),
        migrations.AddField(
            model_name="shardhavendiscovery",
            name="player",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shardhaven_discoveries",
                to="dominion.PlayerOrNpc",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenlayoutsquare",
            name="tile",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="dominion.PlotRoom",
            ),
        ),
        migrations.AddField(
            model_name="monstercraftingdrop",
            name="material",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="monsters",
                to="dominion.CraftingMaterialType",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenpuzzlecraftingmaterial",
            name="material",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="dominion.CraftingMaterialType",
            ),
        ),
        migrations.AddField(
            model_name="monsteralchemicaldrop",
            name="material",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="monsters",
                to="magic.AlchemicalMaterial",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenalignmentchance",
            name="alignment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="magic.Alignment",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenaffinitychance",
            name="affinity",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="magic.Affinity",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenpuzzlematerial",
            name="material",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="magic.AlchemicalMaterial",
            ),
        ),
        migrations.AddField(
            model_name="shardhavenobstacleclue",
            name="clue",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="character.Clue"
            ),
        ),
        migrations.AddField(
            model_name="shardhavenclue",
            name="clue",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="related_shardhavens",
                to="character.Clue",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="shardhavenalignmentchance",
            unique_together=set([("haven", "alignment")]),
        ),
        migrations.AlterUniqueTogether(
            name="shardhavenaffinitychance",
            unique_together=set([("haven", "affinity")]),
        ),
    ]
