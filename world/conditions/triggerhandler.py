"""
A class for caching triggers on individual objects to prevent queries on very frequent checks, like every
time a character moves through a room.
"""
_TRIGGER = None


class TriggerHandler(object):
    """
    Stores a cache of an ObjectDB's triggers.
    """

    def __init__(self, obj):
        self.obj = obj
        self._cache = {}

    def check_room_entry_triggers(self, target):
        global _TRIGGER
        if _TRIGGER is None:
            from world.conditions.models import EffectTrigger as _TRIGGER
        self.check_trigger(_TRIGGER.ON_OTHER_ENTRY, target)

    def check_health_change_triggers(self, amount):
        global _TRIGGER
        if _TRIGGER is None:
            from world.conditions.models import EffectTrigger as _TRIGGER
        if amount < 0:
            self.check_trigger(
                _TRIGGER.ON_TAKING_DAMAGE, self.obj, change_amount=amount
            )
        else:
            self.check_trigger(_TRIGGER.ON_BEING_HEALED, self.obj, change_amount=amount)

    def check_trigger(self, event_type, target, change_amount=0):
        """Checks triggers for a given event_type. Caches check."""
        if event_type not in self._cache:
            self.add_query_to_cache(event_type)
        triggered = False
        current_priority = None
        relevant_triggers = sorted(
            [ob for ob in self._cache[event_type] if ob and ob.pk],
            key=lambda x: x.priority,
            reverse=True,
        )
        for trigger in relevant_triggers:
            if triggered and trigger.priority < current_priority:
                break
            triggered = trigger.check_trigger_on_target(
                target, change_amount=change_amount
            )
            current_priority = trigger.priority

        if any([ob for ob in self._cache[event_type] if not ob or not ob.pk]):
            self.add_query_to_cache(event_type)

    def add_query_to_cache(self, event_type):
        """Caches a query for a triggering event."""
        self._cache[event_type] = list(
            self.obj.triggers.filter(trigger_event=event_type).order_by("-priority")
        )

    def add_trigger_to_cache(self, trigger):
        """
        When a trigger is saved, it'll check if it needs to be added to the triggerhandler cache. It might
        be added by the cache building that query, but if the query is already in there we'll check to make sure
        we're already there before appending.
        """
        if trigger.trigger_event not in self._cache:
            self.add_query_to_cache(trigger.trigger_event)
        elif trigger not in self._cache[trigger.trigger_event]:
            trig_list = self._cache[trigger.trigger_event]
            trig_list.append(trigger)
            trig_list.sort(key=lambda x: x.priority, reverse=True)
