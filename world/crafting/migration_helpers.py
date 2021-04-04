def get_material_mapping(apps):
    return get_mapping_by_name(
        apps.get_model("dominion", "CraftingMaterialType"),
        apps.get_model("crafting", "CraftingMaterialType"),
    )


def get_mapping_by_name(old_model, new_model):
    """Gets a mapping between two models by name"""
    old_instances = old_model.objects.all().values_list("id", "name")
    new_instances = {val.name: val for val in new_model.objects.all()}
    mapping = {}
    for old_id, name in old_instances:
        # set a mapping of old ID to new ID by getting a match of names
        mapping[old_id] = new_instances[name]
    return mapping


def get_val(rdict, key, default, cls):
    try:
        return cls(rdict.get(key, default))
    except (TypeError, ValueError):
        return default


def parse_result(results):
    """
    Given a string, return a dictionary of the different
    key:value pairs separated by semicolons
    """
    if not results:
        return {}
    rlist = results.split(";")
    keyvalpairs = [pair.split(":") for pair in rlist]
    keydict = {
        pair[0].strip(): pair[1].strip() for pair in keyvalpairs if len(pair) == 2
    }
    return keydict


def get_crafting_mapping(apps):
    return get_mapping_by_name(
        apps.get_model("dominion", "CraftingRecipe"),
        apps.get_model("crafting", "CraftingRecipe"),
    )
