from django.contrib import admin
from .models import *


class AffinityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "opposed")


class AlchemicalMaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "alignment", "affinity")


class PractitionerAffinityInline(admin.TabularInline):
    model = PractitionerAlignment
    extra = 0
    raw_id_fields = ("practitioner",)


class PractitionerAttunementInline(admin.TabularInline):
    model = Attunement
    extra = 0
    raw_id_fields = ("practitioner", "obj")


class PractitionerFamiliarInline(admin.TabularInline):
    model = FamiliarAttunement
    extra = 0
    raw_id_fields = ("practitioner", "familiar")


class PractitionerAdmin(admin.ModelAdmin):
    list_display = ("id", "character", "potential", "anima")
    raw_id_fields = ("character",)
    inlines = (
        PractitionerAffinityInline,
        PractitionerAttunementInline,
        PractitionerFamiliarInline,
    )


class PractitionerSkillNodeResonanceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "practitioner",
        "node",
        "raw_resonance",
        "learned_by",
        "learned_notes",
    )
    raw_id_fields = ("practitioner", "node")


class EffectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "affinity", "weave_usable")


class SpellEffectInline(admin.TabularInline):
    model = SpellEffect
    extra = 0
    raw_id_fields = ("effect",)


class SkillNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent_node", "affinity", "affinity_default")
    list_filter = (
        "affinity",
        "affinity_default",
    )
    exclude = ("spells", "effects")
    raw_id_fields = ("parent_node",)
    filter_horizontal = ("discovered_by_revelations",)


class SpellAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "node", "alignment", "affinity")
    list_filter = ("alignment", "affinity")
    raw_id_fields = ("node", "discovered_by_clues")
    inlines = (SpellEffectInline,)


class PractitionerSpellAdmin(admin.ModelAdmin):
    list_display = ("id", "practitioner", "spell", "learned_by", "learned_notes")
    raw_id_fields = ("practitioner", "spell")


class PractitionerEffectAdmin(admin.ModelAdmin):
    raw_id_fields = ("practitioner", "effect")


class WorkingParticipantInline(admin.StackedInline):
    model = WorkingParticipant
    raw_id_fields = ("practitioner", "tool", "familiar")
    readonly_fields = ("drained",)
    extra = 0


class WorkingAdmin(admin.ModelAdmin):
    list_display = ("id", "lead", "spell", "weave_effect", "finalized", "template")
    list_filter = ("template", "finalized")
    raw_id_fields = ("lead", "spell", "weave_effect")
    inlines = (WorkingParticipantInline,)


class ConditionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "effects_list")
    raw_id_fields = ("effects", "node")


class PractitionerConditionAdmin(admin.ModelAdmin):
    list_display = ("id", "practitioner", "condition", "gm_notes")
    raw_id_fields = ("practitioner", "condition")


admin.site.register(Affinity, AffinityAdmin)
admin.site.register(AlchemicalMaterial, AlchemicalMaterialAdmin)
admin.site.register(Practitioner, PractitionerAdmin)
admin.site.register(Effect, EffectAdmin)
admin.site.register(SkillNode, SkillNodeAdmin)
admin.site.register(SkillNodeResonance, PractitionerSkillNodeResonanceAdmin)
admin.site.register(Spell, SpellAdmin)
admin.site.register(PractitionerSpell, PractitionerSpellAdmin)
admin.site.register(PractitionerEffect, PractitionerEffectAdmin)
admin.site.register(Working, WorkingAdmin)
admin.site.register(Condition, ConditionAdmin)
admin.site.register(PractitionerCondition, PractitionerConditionAdmin)
