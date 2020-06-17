from datetime import date
from django.db import models


class QuestText(models.Model):
    ic_desc = models.TextField(blank=True)
    gm_note = models.TextField(blank=True)

    class Meta:
        abstract = True


class Quest(QuestText):
    """A To-Do list of accomplishments for a character to achieve something."""
    name = models.CharField(unique=True, max_length=255, blank=False)
    entities = models.ManyToManyField(to="dominion.AssetOwner", through="QuestStatus", related_name="quests")
    search_tags = models.ManyToManyField("character.SearchTag", blank=True, db_index=True, related_name="quests")

    def __str__(self):
        return self.name


class QuestStep(QuestText):
    """A task that contributes to the completion of a Quest."""
    quest = models.ForeignKey(to="Quest", related_name="steps", on_delete=models.CASCADE, null=False, blank=False)
    name = models.CharField(max_length=255, blank=False)
    step_number = models.PositiveSmallIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name


class QuestStatus(QuestText):
    "Records an entity's efforts and completion status of a Quest."
    quest = models.ForeignKey(to="Quest", related_name="statuses", on_delete=models.CASCADE, blank=False)
    entity = models.ForeignKey(verbose_name="Character/Org", to="dominion.AssetOwner", related_name="statuses",
                               on_delete=models.CASCADE, blank=False)
    db_date_created = models.DateField(verbose_name="Started", auto_now_add=True)
    quest_completed = models.DateField(verbose_name="Completed", blank=True, null=True,
                                       help_text="Generated when all steps are marked complete.")

    class Meta:
        verbose_name_plural = "Quest Statuses"

    def __str__(self):
        return f"{self.entity} on: {self.quest}"


class QuestEffort(models.Model):
    """Any of the items that show evidence toward a QuestStep's completion."""
    status = models.ForeignKey(to="QuestStatus", verbose_name="Quester Status", related_name="efforts",
                               on_delete=models.CASCADE, blank=False)
    step = models.ForeignKey(to="QuestStep", verbose_name="Quest Step", related_name="efforts",
                             on_delete=models.CASCADE, blank=False)
    attempt_number = models.PositiveSmallIntegerField(verbose_name="Attempt #", blank=True, null=True,
                                                      help_text="Efforts can be reordered with this.")
    step_completed = models.BooleanField(verbose_name="Step Complete?", blank=True, default=False,
                                         help_text="Mark if this effort fulfills the Quest Step's requirements.")
    # behold! the field in which I grow mine fks, and see that there are many:
    event = models.ForeignKey(to="dominion.RPEvent", verbose_name="Event", related_name="used_in_efforts",
                              on_delete=models.CASCADE, blank=True, null=True)
    flashback = models.ForeignKey(to="character.Flashback", verbose_name="Flashback", related_name="used_in_efforts",
                                  on_delete=models.CASCADE, blank=True, null=True)
    clue = models.ForeignKey(to="character.ClueDiscovery", verbose_name="Clue disco", related_name="used_in_efforts",
                             on_delete=models.CASCADE, blank=True, null=True,
                             help_text="A character's discovery of a clue, not the clue itself.")
    org_clue = models.ForeignKey(to="dominion.ClueForOrg", verbose_name="Org Clue", related_name="used_in_efforts",
                                 on_delete=models.CASCADE, blank=True, null=True,
                                 help_text="An organization's possession of a clue, not the clue itself.")
    revelation = models.ForeignKey(to="character.RevelationDiscovery", verbose_name="Rev disco",
                                   related_name="used_in_efforts", on_delete=models.CASCADE, blank=True, null=True,
                                   help_text="A character's discovery of revelation, not the revelation itself.")
    action = models.ForeignKey(to="dominion.PlotAction", verbose_name="Action", related_name="used_in_efforts",
                               on_delete=models.CASCADE, blank=True, null=True)
    quest = models.ForeignKey(to="QuestStatus", verbose_name="Required Quest", related_name="used_in_efforts",
                              on_delete=models.CASCADE, blank=True, null=True,
                              help_text="Character's status/progress on another quest, not the quest itself.")

    def save(self, *args, **kwargs):
        if self.attempt_number == None:
            last_number = self.status.efforts.filter(step=self.step).exclude(id=self.id).count()
            self.attempt_number = last_number + 1
        super().save(*args, **kwargs)
        successful_efforts = QuestEffort.objects.filter(status=self.status, step_completed=True)
        incomplete_steps = self.step.quest.steps.exclude(efforts__in=successful_efforts).distinct().count()
        if not self.step_completed and self.status.quest_completed and incomplete_steps:
            self.status.quest_completed = None
            self.status.save()
        elif self.step_completed and not self.status.quest_completed and not incomplete_steps:
            self.status.quest_completed = date.today()
            self.status.save()

    def __str__(self):
        return f"Effort by {self.status.entity} (Quest #{self.step.quest_id} Step {self.step.step_number})"
