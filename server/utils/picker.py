import random


class WeightedPicker(object):
    def __init__(self):
        self.choices = []

    def add_option(self, option, weight):
        """
        Adds a option to this weighted picker.
        :param option: The option to add to the picker, any valid Python object.
        :param weight: An integer value to use as the weight for this option.
        """
        try:
            weight = int(weight)
        except ValueError:
            raise ValueError("Weight must be an integer value.")

        self.choices.append((option, weight))

    def pick(self):
        """
        Picks an option from those given to this WeightedPicker.
        """

        pickerdict = {}
        current_value = 0

        if len(self.choices) == 0:
            return None

        if len(self.choices) == 1:
            return self.choices[0][0]

        for option in self.choices:
            pickerdict[current_value] = option[0]
            current_value += option[1]

        picker = random.randint(0, current_value)
        last_value = 0
        result = None
        sorted_keys = sorted(pickerdict.keys())

        found = False
        for key in sorted_keys:
            if key >= picker:
                result = pickerdict[last_value]
                found = True
                continue
            last_value = key

        if not found:
            result = pickerdict[sorted_keys[-1]]

        return result
