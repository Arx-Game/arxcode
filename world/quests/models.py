from datetime import datetime

from django.db import models


class QuestText(models.Model):
    ic_desc = models.TextField(blank=True)
    gm_note = models.TextField(blank=True)

    class Meta:
        abstract = True


class Quest(QuestText):
    """A To-Do list of accomplishments for a character to achieve something."""
    name = models.CharField(unique=True, max_length=255)
    entities = models.ManyToManyField(to="dominion.AssetOwner", through="QuestStatus", related_name="quests")
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, db_index=True, related_name="quests")

    def __str__(self):
        return self.name

class QuestStep(QuestText):
    """A task that contributes to the completion of a Quest."""
    quest = models.ForeignKey(to="Quest", related_name="steps", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    step_number = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.name


class QuestStatus(QuestText):
    "Records an entity's efforts and completion status of a Quest."
    quest = models.ForeignKey(to="Quest", related_name="statuses", on_delete=models.CASCADE)
    entity = models.ForeignKey(verbose_name="Character/Org", to="dominion.AssetOwner", related_name="statuses", on_delete=models.CASCADE)
    db_date_created = models.DateTimeField(auto_now_add=True)
    quest_completed = models.DateTimeField(verbose_name="Completed On", blank=True, null=True,
                                           help_text="Generated when all steps are marked complete.")

    class Meta:
        verbose_name_plural = "Quest Statuses"

    def __str__(self):
        return f"{self.entity} on: {self.quest}"


class QuestStepEffort(models.Model):
    """Any of the items that show evidence toward a QuestStep's completion."""
    status = models.ForeignKey(to="QuestStatus", related_name="efforts", on_delete=models.CASCADE)
    step = models.ForeignKey(to="QuestStep", related_name="efforts", on_delete=models.CASCADE)
    attempt_number = models.PositiveSmallIntegerField(blank=True, null=True)
    step_completed = models.DateTimeField(verbose_name="Marked Complete On", blank=True, null=True,
                                          help_text="Mark the date to complete this step of the quest.")
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
    quest_status = models.ForeignKey(to="QuestStatus", related_name="used_in_efforts", on_delete=models.CASCADE,
                                     blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.attempt_number == None:
            last_num = self.status.efforts.filter(step=self.step).exclude(id=self.id).count()
            self.attempt_number = last_num + 1
        super().save(*args, **kwargs)
        if self.step_completed and not self.status.quest_completed:
            successful_efforts = QuestStepEffort.objects.filter(status=self.status, step_completed=True)
            incomplete_steps = self.status.quest.steps.exclude(efforts__in=successful_efforts).distinct().count()
            if not incomplete_steps:
                self.status.quest_completed = datetime.now()  # You're killing me, Smalls
                self.status.save()

    def __str__(self):
        return f"Effort by {self.status.entity}: {self.step.quest} ({self.step.name})"
