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


class QuestStep(QuestText):
    """A task that contributes to the completion of a Quest."""
    quest = models.ForeignKey(to="Quest", related_name="quest_steps", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    step_number = models.PositiveSmallIntegerField(default=0)


class EntityQuestStepProgress(models.Model):
    "Records a character's efforts and completion status of a QuestStep"
    quest_step = models.ForeignKey(to="QuestStep", related_name="quest_step_progresses", on_delete=models.CASCADE)
    entity = models.ForeignKey(to="AssetOwner", related_name="quest_step_progresses", on_delete=models.CASCADE)
    date_completed = models.DateTimeField(blank=True, null=True)


class QuestStepEffort(models.Model):
    """Any of the items that show evidence toward a QuestStep's completion."""
    attempt_number = models.PositiveSmallIntegerField(default=0)  # auto-increment this but allow changes
    effort_for = models.ForeignKey(to="EntityQuestStepProgress", related_name="efforts", on_delete=models.CASCADE)
    # behold! the field in which I grow mine fks, and see that there are many:
    # event  # This includes PRP
    # flashback
    # clue  # This includes vision, secret
    # revelation
    # action
    # quest  # the quest-completion of another quest, as a step. aka 'achievements' in eq2

