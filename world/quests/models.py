from django.db import models

class Quest(models.Model):
    """Represents a To-Do list of smaller accomplishments for a character to achieve something."""
    name = models.CharField(unique=True, max_length=255)
    parent = models.ForeignKey("self", null=True, on_delete=models.SET_NULL, related_name="subquests")
    ic_desc = models.TextField(blank=True)
    ooc_desc = models.TextField(blank=True)


class QuestStep(models.Model):
    """A task that contributes to the completion of a Quest."""
