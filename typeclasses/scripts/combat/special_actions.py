"""
Special actions are for different actions that players can take, either defined
by GM or otherwise called by specific commands. For GM-defined actions, they are
called by the @admin_combat command, and allow a table-top style of GMing where
a GM can specify for one or more players to be able to take a specific action
that'll cause a check during the characters' combat rounds, either for an 
individual or shared total, and GM the result.
"""

class ActionByGM(object):
    """
    An action the GM sets for the combat that players can choose to do.
    """
    def __init__(self, combat, name, stat="", skill="", difficulty=15):
        self.combat = combat
        self.name = name
        self.stat = stat
        self.skill = skill
        self.difficulty = difficulty
        self.recorded_actions = {}
        
    def __str__(self):
        return self.name
        
    def record_action(self, action):
        current_round = self.combat.ndb.rounds
        actions = self.recorded_actions.get(current_round, [])
        if action not in actions:
            actions.append(action)
            
    def make_checks(self, actions):
        """Rolls and records all actions."""
        for action in actions:
            self.record_action(action)
            action.do_roll(self.stat, self.skill, self.difficulty)
        
    @property
    def total(self):
        """Sums up all the rolls made for us"""
        actions = []
        for act_list in self.recorded_actions.values():
            actions.extend(act_list)
        return sum(action.roll_result for action in actions)
    