from .models import Alignment, Affinity, Practitioner
from world.dominion.models import CraftingRecipe, CraftingMaterialType
from server.utils.arx_utils import a_or_an
from evennia.utils import logger


_MAX_PRIMUM_TIER1 = 20
_MAX_PRIMUM_TIER2 = 10


class MagicMixins(object):

    @property
    def practitioner(self):
        if self.ndb.practitioner:
            return self.ndb.practitioner

        try:
            practitioner = Practitioner.objects.get(character=self)
            self.ndb.practitioner = practitioner
            return practitioner
        except Practitioner.DoesNotExist:
            pass

        return None

    @property
    def alignment(self):
        if self.practitioner:
            return self.practitioner.alignment

        if self.db.alignment:
            try:
                align_id = int(self.db.alignment)
                align = Alignment.objects.get(id=align_id)
                return align
            except ValueError:
                try:
                    align = Alignment.objects.get(name__iexact=self.db.alignment)
                    return align
                except Alignment.DoesNotExist:
                    pass
            except Alignment.DoesNotExist:
                pass

        return Alignment.PRIMAL

    @property
    def affinity(self):
        if self.practitioner:
            return self.practitioner.affinity

        if self.db.affinity:
            try:
                affinity_id = int(self.db.affinity)
                affinity = Affinity.objects.get(id=affinity_id)
                return affinity
            except ValueError:
                try:
                    affinity = Affinity.objects.get(name__iexact=self.db.affinity)
                    return affinity
                except Affinity.DoesNotExist:
                    pass
            except Affinity.DoesNotExist:
                pass

        return None

    def quality_level_from_primum(self, primum):
        if self.db.recipe:
            try:
                recipe_id = int(self.db.recipe)
            except ValueError:
                return None

            try:
                recipe = CraftingRecipe.objects.get(id=recipe_id)

                lower_name = recipe.name.lower()
                if "alaricite" in lower_name:
                    return primum / _MAX_PRIMUM_TIER1
                elif "diamondplate" in lower_name:
                    return primum / _MAX_PRIMUM_TIER2
                elif "star iron" in lower_name:
                    return primum / _MAX_PRIMUM_TIER1
                elif "iridescite" in lower_name:
                    return primum / _MAX_PRIMUM_TIER2
                elif "stygian" in lower_name:
                    return primum / _MAX_PRIMUM_TIER2
            except CraftingRecipe.DoesNotExist:
                pass

    @property
    def max_potential(self):
        if self.practitioner:
            return self.practitioner.potential

        if self.db.recipe:
            try:
                recipe_id = int(self.db.recipe)
            except ValueError:
                return None

            try:
                recipe = CraftingRecipe.objects.get(id=recipe_id)
                lower_name = recipe.name.lower()
            except CraftingRecipe.DoesNotExist:
                return self.potential
        else:
            return self.potential

        result = None
        if lower_name:
            if "alaricite" in lower_name:
                result = _MAX_PRIMUM_TIER1 * 11
            elif "diamondplate" in lower_name:
                result = _MAX_PRIMUM_TIER2 * 11
            elif "star iron" in lower_name:
                result = _MAX_PRIMUM_TIER1 * 11
            elif "iridescite" in lower_name:
                result = _MAX_PRIMUM_TIER2 * 11
            elif "stygian" in lower_name:
                result = _MAX_PRIMUM_TIER2 * 11

        if not result:
            return self.potential

        quantity = 1
        if self.db.quantity:
            try:
                quantity = int(self.db.quantity)
            except ValueError:
                pass

        result *= quantity
        return result

    @property
    def potential(self):
        if self.practitioner:
            return self.practitioner.potential

        if self.db.potential:
            try:
                potential_value = int(self.db.potential)
                return potential_value
            except ValueError:
                pass

        quality_level = 1
        if self.db.quality_level:
            try:
                quality_level = int(self.db.quality_level)
            except ValueError:
                return 0

        result = quality_level
        lower_name = None
        if self.db.recipe and quality_level > 0:
            try:
                recipe_id = int(self.db.recipe)
            except ValueError:
                return None

            try:
                recipe = CraftingRecipe.objects.get(id=recipe_id)

                lower_name = recipe.name.lower()
            except CraftingRecipe.DoesNotExist:
                pass

        if self.db.material_type:
            try:
                material_id = int(self.db.material_type)
            except ValueError:
                return None

            try:
                material = CraftingMaterialType.objects.get(id=material_id)
                lower_name = material.name.lower()
                quality_level = 1
            except CraftingMaterialType.DoesNotExist:
                pass

        if lower_name:
            if "alaricite" in lower_name:
                result = _MAX_PRIMUM_TIER1 * quality_level
            elif "diamondplate" in lower_name:
                result = _MAX_PRIMUM_TIER2 * quality_level
            elif "star iron" in lower_name:
                result = _MAX_PRIMUM_TIER1 * quality_level
            elif "iridescite" in lower_name:
                result = _MAX_PRIMUM_TIER2 * quality_level
            elif "stygian" in lower_name:
                result = _MAX_PRIMUM_TIER2 * quality_level

        quantity = 1
        if self.db.quantity:
            try:
                quantity = int(self.db.quantity)
            except ValueError:
                pass

        result *= quantity
        self.db.potential = result

        return result

    @property
    def primum(self):
        if self.practitioner:
            return self.practitioner.anima

        if self.db.primum:
            try:
                primum_value = int(self.db.primum)
                return primum_value
            except ValueError:
                pass

        return self.potential

    @property
    def valid_sacrifice(self):
        if self.practitioner:
            return False

        if self.is_typeclass("typeclasses.characters.Character"):
            return False

        return self.primum != 0

    def drain_primum(self, amount):
        if self.practitioner or self.is_typeclass('typeclasses.characters.Character'):
            logger.log_err("Tried to drain a Character of primum as though it were an Object!  Not good.")
            raise ValueError

        if self.primum == 0:
            logger.log_err("Tried to drain an object of primum when it has none.")

        self.db.primum = self.primum - amount
        if self.db.primum <= 0:
            self.location.msg("{} crumbles into dust.".format(self.name))
            self.location.msg_contents("{} crumbles into dust.".format(self.name))
            self.softdelete()
            return

        if self.db.quality_level:
            self.db.quality_level = self.quality_level_from_primum(self.db.primum)

    def infuse_primum(self, amount):
        if self.practitioner or self.is_typeclass('typeclasses.characters.Character'):
            logger.log_err("Tried to infuse a Character with primum as though it were an Object!  Not good.")
            raise ValueError

        self.db.primum = min(self.primum + amount, self.max_potential)
        if self.db.primum > self.potential:
            self.db.potential = self.db.primum

        if self.db.quality_level:
            self.db.quality_level = self.quality_level_from_primum(self.db.primum)

    @property
    def magic_description(self):
        if self.db.magic_desc_override:
            return self.db.magic_desc_override

        if not self.alignment:
            return None

        noun = "blob of formless magic"
        second_noun = None
        if self.affinity:
            if self.practitioner:
                affinity_value = self.practitioner.resonance_for_affinity(self.affinity)
            else:
                affinity_value = self.primum
                if self.potential != self.primum:
                    second_noun = self.affinity.description_for_value(self.potential)

            noun = self.affinity.description_for_value(affinity_value)

        adjective = self.alignment.adjective
        part = a_or_an(adjective)

        base_string = "{} {} {}".format(part.capitalize(), adjective, noun)
        if second_noun and (second_noun != noun):
            base_string = "Once {} {} {}, now only {} {}".format(part, adjective, second_noun,
                                                                 a_or_an(noun), noun)

        magic_desc_short = None
        if self.practitioner:
            magic_desc_short = self.practitioner.magic_desc_short

        if not magic_desc_short:
            magic_desc_short = self.db.magic_desc_short

        if magic_desc_short:
            base_string += ", {}.".format(magic_desc_short)
        else:
            base_string += "."

        return base_string

    @property
    def magic_description_advanced(self):

        result = None

        if self.practitioner:
            result = self.practitioner.magic_description_advanced

        if not result:
            result = self.db.magic_desc_detail

        return result

    @property
    def magic_word(self):
        return self.db.magic_word or "Default Magicword"

    def msg_magic(self, text, strength=10, guaranteed=False, mundane=False):
        practitioner = self.practitioner

        admin = False
        if hasattr(self, "account") and self.account:
            admin = self.account.check_permstring("admin")
        see_all = self.tags.get("see_all", category="magic") or admin

        if not practitioner and (mundane or see_all or guaranteed):
            # If we don't have a practitioner record we want to still show the
            # effect with their magicword, so they can see that something legitimately
            # came from the magic system.

            self.msg(text, options={'is_pose': True, 'is_magic': True})
            return

        if practitioner:
            if guaranteed or mundane:
                practitioner.notify_magic(text)
            else:
                practitioner.check_perceive_magic(text, strength=strength)
            return

    def msg_contents_magic(self, text, strength=10, guaranteed=False, mundane=False):
        for obj in self.contents:
            if hasattr(obj, 'msg_magic'):
                obj.msg_magic(text, strength=strength, guaranteed=guaranteed, mundane=mundane)
