from django.db.models import QuerySet


class IntegerGameConstantQueryset(QuerySet):
    def get_amount_needed_to_heal_wound(self):
        return self.get(id="Amount Needed To Heal Wounds").value

    def get_max_wound_healing_per_day(self):
        return self.get(id="Max Wound Healing Per Day").value
