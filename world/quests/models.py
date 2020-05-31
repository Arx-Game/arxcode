from django.db import models


class QuestText(models.Model):
    ic_desc = models.TextField(blank=True)
    gm_note = models.TextField(blank=True)

    class Meta:
        abstract = True


class Quest(QuestText):
    """A To-Do list of smaller accomplishments for a character to achieve something."""
    name = models.CharField(unique=True, max_length=255)
    db_date_created = models.DateTimeField(auto_now_add=True)
    entities = models.ManyToManyField(to="dominion.AssetOwner", through="QuestStatus", related_name="quests")


class QuestStep(QuestText):
    """A task that contributes to the completion of a Quest."""
    quest = models.ForeignKey(to="Quest", related_name="quest_steps", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    step_number = models.PositiveSmallIntegerField(default=0)


class QuestStatus(models.Model):
    "Records an entity's efforts and completion status of a Quest."
    quest = models.ForeignKey(to="Quest", related_name="statuses", on_delete=models.CASCADE)
    entity = models.ForeignKey(verbose_name="Character/Org", to="dominion.AssetOwner", related_name="statuses", on_delete=models.CASCADE)
    quest_completed = models.DateTimeField(verbose_name="Completed On", blank=True, null=True,
                                           help_text="Generated when all steps are marked complete.")

    class Meta:
        verbose_name_plural = "Quest Statuses"


class QuestStepEffort(models.Model):
    """Any of the items that show evidence toward a QuestStep's completion."""
    status = models.ForeignKey(to="QuestStatus", related_name="efforts", on_delete=models.CASCADE)
    step = models.ForeignKey(to="QuestStep", related_name="efforts", on_delete=models.CASCADE)
    attempt_number = models.PositiveSmallIntegerField(default=0)  # auto-increment this but allow changes
    step_completed = models.DateTimeField(verbose_name="Marked Complete On", blank=True, null=True,
                                          help_text="Mark this date to complete this step of the quest.")
    # behold! the field in which I grow mine fks, and see that there are many:
    event = models.ForeignKey(to="dominion.RPEvent", related_name="used_in_efforts", on_delete=models.CASCADE,
                              blank=True, null=True)
    flashback = models.ForeignKey(to="character.Flashback", related_name="used_in_efforts", on_delete=models.CASCADE,
                                  blank=True, null=True)
    char_clue = models.ForeignKey(to="character.ClueDiscovery", related_name="used_in_efforts",
                                  on_delete=models.CASCADE, blank=True, null=True)
    org_clue = models.ForeignKey(to="dominion.ClueForOrg", related_name="used_in_efforts", on_delete=models.CASCADE,
                                 blank=True, null=True)
    revelation = models.ForeignKey(to="character.RevelationDiscovery", related_name="used_in_efforts",
                                   on_delete=models.CASCADE, blank=True, null=True)
    action = models.ForeignKey(to="dominion.PlotAction", related_name="used_in_efforts", on_delete=models.CASCADE,
                               blank=True, null=True)
    quest = models.ForeignKey(to="QuestStatus", related_name="used_in_efforts", on_delete=models.CASCADE, blank=True,
                              null=True)
