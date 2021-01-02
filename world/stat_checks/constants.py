DEATH_SAVE = "death save"
UNCON_SAVE = "unconsciousness save"
PERMANENT_WOUND_SAVE = "permanent wound save"
RECOVERY_CHECK = "recovery check"
RECOVERY_TREATMENT = "recovery treatment"
REVIVE_TREATMENT = "revive treatment"

(
    NONE,
    DEATH,
    UNCONSCIOUSNESS,
    SERIOUS_WOUND,
    PERMANENT_WOUND,
    HEAL,
    HEAL_AND_CURE_WOUND,
    HEAL_UNCON_HEALTH,
    AUTO_WAKE,
) = range(9)

HEAL_EFFECTS = (HEAL, HEAL_AND_CURE_WOUND)
REVIVE_EFFECTS = (HEAL_UNCON_HEALTH, AUTO_WAKE)
