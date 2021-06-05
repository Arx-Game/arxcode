from django.db.models import (
    QuerySet,
    Max,
    Subquery,
    OuterRef,
    F,
    Value,
    Case,
    When,
    BooleanField,
    Prefetch,
    IntegerField,
    Q,
)

from world.conditions.constants import UNCONSCIOUS, REVIVE, RECOVERY
from world.stat_checks.constants import HEAL_AND_CURE_WOUND


class HealthStatusQuerySet(QuerySet):
    """QuerySet with methods for different queries"""

    def living(self):
        return self.select_related("character").filter(is_dead=False)

    def unconscious(self):
        return self.filter(consciousness=UNCONSCIOUS)

    def damaged_or_wounded(self):
        return self.filter(Q(damage__gt=0) | Q(wounds__isnull=False)).distinct()

    def annotate_highest_treatment(self, treatment_type, attr_name):
        """This annotates the queryset with the highest value for a given type of treatments"""
        from world.conditions.models import TreatmentAttempt

        subquery_queryset = (
            TreatmentAttempt.objects.filter(
                target=OuterRef("pk"),
                treatment_type=treatment_type,
                uses_remaining__gt=0,
            )
            .annotate(highest_value=Max("value", output_field=IntegerField(default=0)))
            .values("highest_value")[:1]
        )
        query_kwargs = {
            attr_name: Subquery(subquery_queryset, output_field=IntegerField(default=0))
        }
        return self.annotate(**query_kwargs)

    def annotate_recovery_treatment(self):
        return self.annotate_highest_treatment(
            RECOVERY, "cached_highest_recovery_treatment_roll"
        )

    def annotate_should_heal_wound(self):
        return self.annotate(
            cached_should_heal_wound=Case(
                When(
                    treatment_attempts__outcome__effect=HEAL_AND_CURE_WOUND,
                    then=Value(True),
                ),
                default=Value(False),
                output_field=BooleanField(default=False),
            )
        )

    def prefetch_wounds(self):
        return self.prefetch_related(Prefetch("wounds", to_attr="cached_wounds"))

    def get_recovery_queryset(self):
        return (
            self.living()
            .damaged_or_wounded()
            .annotate_recovery_treatment()
            .annotate_should_heal_wound()
            .prefetch_wounds()
        )

    def prefetch_revive_treatments(self):
        from world.conditions.models import TreatmentAttempt

        return self.prefetch_related(
            Prefetch(
                "treatment_attempts",
                queryset=TreatmentAttempt.objects.filter(treatment_type=REVIVE),
                to_attr="cached_revive_treatments",
            )
        )

    def get_revive_queryset(self):
        return self.living().unconscious().prefetch_revive_treatments()


class TreatmentAttemptQuerySet(QuerySet):
    def decrement_treatments(self, treatment_type):
        self.filter(treatment_type=treatment_type).update(
            uses_remaining=F("uses_remaining") - Value(1)
        )
        self.filter(treatment_type=treatment_type, uses_remaining__lte=0).delete()
