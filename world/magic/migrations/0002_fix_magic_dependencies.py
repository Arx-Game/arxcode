from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    replaces = [
        ("magic", "0008_auto_20181211_0253"),
        ("magic", "0009_auto_20181211_1716"),
        ("magic", "0010_auto_20191228_1417"),
    ]
    dependencies = [
        ("magic", "0001_squashed_magic"),
        ("character", "0001_squashed_character"),
        ("dominion", "0001_squashed_dominion"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClueCollection",
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
                ("name", models.CharField(max_length=80)),
                ("gm_notes", models.TextField(blank=True, null=True)),
                (
                    "clues",
                    models.ManyToManyField(
                        related_name="magic_collections", to="character.Clue"
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="skillnode",
            name="discovered_by_revelations",
            field=models.ManyToManyField(
                blank=True,
                help_text="If we discover these revelations, the node is automatically discovered.",
                related_name="nodes",
                to="character.Revelation",
            ),
        ),
        migrations.AddField(
            model_name="spell",
            name="discovered_by_clues",
            field=models.ManyToManyField(
                blank=True,
                help_text="If we discover any of these clues, the spell is automatically learned.",
                related_name="spells",
                to="character.Clue",
            ),
        ),
        migrations.CreateModel(
            name="FamiliarAttunement",
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
                ("raw_attunement_level", models.FloatField(default=0.0)),
                (
                    "familiar",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bondmates",
                        to="dominion.Agent",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="workingparticipant",
            name="familiar",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="magic.FamiliarAttunement",
            ),
        ),
        migrations.AddField(
            model_name="familiarattunement",
            name="practitioner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="familiars",
                to="magic.Practitioner",
            ),
        ),
    ]
