from django.db.models import QuerySet, F, Sum


class CraftMaterialsAmountQuerySet(QuerySet):
    def annotate_calculated_value(self):
        return self.annotate(calculated_value=F("type__value") * F("amount"))

    def total_value(self) -> int:
        return int(
            self.annotate_calculated_value().aggregate(
                total_value=Sum("calculated_value")
            )["total_value"]
            or 0
        )
