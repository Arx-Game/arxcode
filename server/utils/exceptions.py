"""
Exceptions for Arx!
"""


class WalrusJudgement(Exception):
    WALRUSFACTS = [
        "Walruses hook their tusks on ice to rest in water.",
        "Walruses employ a tusk-based hierarchy; the bigger the better.",
        "Breaking a tusk usually means a walrus drops in social status.",
        "A mama walrus carries her calf for 16 months before giving birth.",
        "Walrus calves are born weighing between 100 to 170 pounds.",
        "Young walruses stay with their mother for about 5 years.",
        "A prehistoric walrus species had upper AND lower tusks, wow!",
        "The walrus' genus name (Odobenus) means 'Tooth-Walking Sea Horse'.",
        "The layer of blubber on a walrus is 6 inches thick.",
        "Walrus mouths create a high-suction vacuum powerful enough to crack clamshells.",
        "On land, walruses may sleep for 19 hours straight.",
        "Walruses sometimes stay awake at sea for three and a half straight days.",
        "Walrus tusks can grow over 3 feet in length.",
        "Walruses have 450 sensitive whiskers called vibrissae.",
        "Walruses can live to around 40 years old.",
    ]

    def __init__(self, *args, **kwargs):
        from random import choice

        super(WalrusJudgement, self).__init__(
            "Did you know? " + choice(self.WALRUSFACTS)
        )


class CommandError(Exception):
    pass


class PayError(CommandError):
    pass


class ActionSubmissionError(CommandError):
    pass
