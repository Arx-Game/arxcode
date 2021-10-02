PC_RACE, NPC_RACE, SMALL_ANIMAL, LARGE_ANIMAL, MONSTER = range(5)

RACE_TYPE_CHOICES = (
    (PC_RACE, "Allowed Player Character Race"),
    (NPC_RACE, "NPC Only Race"),
    (SMALL_ANIMAL, "Small Animal"),
    (LARGE_ANIMAL, "Large Animal"),
    (MONSTER, "Monster"),
)

CHEST_KEY, ROOM_KEY = range(2)

KEY_CHOICES = ((CHEST_KEY, "chest key"), (ROOM_KEY, "room key"))

SINGLE, MARRIED, WIDOWED, DIVORCED = "single", "married", "widowed", "divorced"

MARITAL_STATUS_CHOICES = (
    (SINGLE, "Single"),
    (MARRIED, "Married"),
    (WIDOWED, "Widowed"),
    (DIVORCED, "Divorced"),
)
