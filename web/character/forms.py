"""
Forms for the Character app. Stuff based around the character sheet page
"""
from cloudinary.forms import (
    CloudinaryFileField,
    CloudinaryJsFileField,
    CloudinaryUnsignedJsFileField,
)
from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q

from web.character.models import (
    Photo,
    Flashback,
    RosterEntry,
    Clue,
    Revelation,
    SearchTag,
)
from server.utils.arx_utils import inform_staff
from world.dominion.plots.models import Plot


class PhotoModelChoiceField(forms.ModelChoiceField):
    """Field for choosing from different photos"""

    def label_from_instance(self, obj):
        """Labels a photo"""
        if obj.title:
            return obj.title
        return obj.image.public_id


class PortraitSelectForm(forms.Form):
    """Form for selecting a character sheet portrait"""

    select_portrait = PhotoModelChoiceField(queryset=None, empty_label="(No Portrait)")
    portrait_height = forms.IntegerField(initial=480)
    portrait_width = forms.IntegerField(initial=320)

    def __init__(self, object_id=None, *args, **kwargs):
        super(PortraitSelectForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields["select_portrait"].queryset = qset


class PhotoEditForm(forms.Form):
    """Form for selecting a photo to edit"""

    select_photo = PhotoModelChoiceField(
        queryset=None, empty_label="(No Image Selected)"
    )
    title = forms.CharField(max_length=200)
    alt_text = forms.CharField(max_length=200)

    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoEditForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields["select_photo"].queryset = qset


class PhotoDeleteForm(forms.Form):
    """Form for selecting a photo to delete"""

    select_photo = PhotoModelChoiceField(
        queryset=None, empty_label="(No Image Selected)"
    )

    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoDeleteForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields["select_photo"].queryset = qset


class PhotoForm(forms.ModelForm):
    """Form for uploading a Photo"""

    class Meta:
        """We set the image to be a CloudinaryFileField for the upload"""

        model = Photo
        fields = ["title", "alt_text", "image"]
        image = CloudinaryFileField(
            options={"use_filename": True, "unique_filename": False, "overwrite": False}
        )


class PhotoDirectForm(PhotoForm):
    """Form for uploading with javascript"""

    image = CloudinaryJsFileField()


class PhotoUnsignedDirectForm(PhotoForm):
    """Form for uploading when unsigned"""

    upload_preset_name = "Arx_Default_Unsigned"
    image = CloudinaryUnsignedJsFileField(upload_preset_name)


class FlashbackPostForm(forms.Form):
    """Form for adding a post to a flashback"""

    actions = forms.CharField(
        label="Post Text",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": "10"}),
    )

    def add_post(self, flashback, poster):
        """Adds the post, which does various in-game updates, like sending informs."""
        actions = self.cleaned_data["actions"]
        flashback.add_post(actions, poster)


class FlashbackCreateForm(forms.ModelForm):
    """Simple ModelForm for creating a new Flashback. We add the owner automatically."""

    invites = forms.ModelMultipleChoiceField(
        queryset=RosterEntry.objects.all(), required=False
    )

    class Meta:
        """Set our model and fields"""

        model = Flashback
        fields = ["title", "summary"]

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop("owner")
        super(FlashbackCreateForm, self).__init__(*args, **kwargs)
        self.fields["invites"].queryset = (
            RosterEntry.objects.filter(
                Q(roster__name="Active")
                | Q(roster__name="Available")
                | Q(roster__name="Gone")
                | Q(roster__name="Inactive")
                | Q(roster__name="Unavailable")
            )
            .exclude(roster__id=self.owner.id)
            .order_by("character__db_key")
        )

    def save(self, commit=True):
        """Saves the form as a new Flashback and adds our owner/date created fields"""
        from datetime import datetime

        obj = super(FlashbackCreateForm, self).save(commit=False)
        obj.db_date_created = datetime.now()
        obj.save()
        invites = self.cleaned_data.get("invites", [])
        obj.invite_roster(self.owner, owner=True)
        for friend in invites:
            obj.invite_roster(friend)
        return obj


class DisplayErrorsMixin(object):
    """Displays errors for the in-game display of a form"""

    def display_errors(self):
        """Returns a game-friendly errors string"""

        def format_name(field_name):
            """Formats field names for error display"""
            return "{w%s{n" % field_name.capitalize()

        msg = "Please correct the following errors:\n"
        msg += "\n".join(
            "%s: {r%s{n" % (format_name(field), ", ".join(errs))
            for field, errs in self.errors.items()
        )
        return msg


class PRPFormBase(DisplayErrorsMixin, forms.ModelForm):
    """Shared base class for PRP forms"""

    tag_names = forms.CharField(
        required=False,
        help_text="Separate each tag with a comma (ex: 'first tag, second')",
    )

    @property
    def gm_plots(self):
        """Plots our caller is gming"""
        return self.author.player.Dominion.plots_we_can_gm

    def __init__(self, *args, **kwargs):
        self.author = kwargs.pop("author")
        super(PRPFormBase, self).__init__(*args, **kwargs)
        self.fields["desc"].required = True
        self.fields["desc"].label = "Description"
        self.fields["name"].required = True

    def save(self, commit=True):
        obj = super(PRPFormBase, self).save(commit=commit)
        tag_names = self.cleaned_data.get("tag_names", "").split(",")
        for tag_name in tag_names:
            tag_name = tag_name.strip()
            try:
                search_tag = SearchTag.objects.get(name__iexact=tag_name)
            except SearchTag.DoesNotExist:
                search_tag = SearchTag.objects.create(name=tag_name)
            except SearchTag.MultipleObjectsReturned:
                search_tag = SearchTag.objects.filter(name__iexact=tag_name).first()
                inform_staff(
                    "Multiple '%s' tags exist; using #%s to tag %s."
                    % (tag_name, search_tag.id, obj)
                )
            obj.search_tags.add(search_tag)
        return obj


class ClueCreateForm(PRPFormBase):
    """Form for a prp GM making clues"""

    revelation = forms.ModelChoiceField(
        required=True, queryset=Revelation.objects.none()
    )

    class Meta:
        """sets model and fields"""

        model = Clue
        fields = [
            "name",
            "desc",
            "red_herring",
            "allow_investigation",
            "rating",
            "allow_sharing",
        ]

    def __init__(self, *args, **kwargs):
        super(ClueCreateForm, self).__init__(*args, **kwargs)
        self.fields["revelation"].queryset = Revelation.objects.filter(
            author=self.author
        )
        self.fields["rating"].validators = [MaxValueValidator(50), MinValueValidator(1)]

    def display(self):
        """Text display of form for in-game command"""
        revelation = self.data.get("revelation")
        if revelation:
            try:
                revelation = Revelation.objects.get(id=revelation)
            except Revelation.DoesNotExist:
                pass
        msg = "{wName{n: %s\n" % self.data.get("name")
        msg += "{wDesc{n: %s\n" % self.data.get("desc")
        msg += "{wRevelation:{n %s\n" % revelation
        if revelation:
            msg += "{wPlot:{n %s\n" % ", ".join(
                str(ob) for ob in revelation.plots.filter(id__in=self.gm_plots)
            )
        msg += "{wRating{n: %s\n" % self.data.get("rating")
        msg += "{wTags:{n %s\n" % self.data.get("tag_names")
        msg += "{wReal:{n %s\n" % ("Fake" if self.data.get("red_herring") else "True")
        msg += "{wCan Investigate:{n %s\n" % self.data.get("allow_investigation")
        msg += "{wCan Share:{n %s\n" % self.data.get("allow_sharing")
        return msg

    def save(self, commit=True):
        clue = super(ClueCreateForm, self).save(commit)
        clue.author = self.author
        clue.save()
        revelation = self.cleaned_data.get("revelation")
        clue.usage.create(revelation=revelation)
        clue.discoveries.create(character=self.author, discovery_method="author")
        inform_staff("Clue '%s' created for revelation '%s'." % (clue, revelation))
        return clue


class RevelationCreateForm(PRPFormBase):
    """Form for creating a revelation for a PRP"""

    plot = forms.ModelChoiceField(required=True, queryset=Plot.objects.none())
    plot_gm_notes = forms.CharField(required=False)

    class Meta:
        model = Revelation
        fields = ["name", "desc", "required_clue_value", "red_herring"]

    def __init__(self, *args, **kwargs):
        super(RevelationCreateForm, self).__init__(*args, **kwargs)
        self.fields["plot"].queryset = self.gm_plots
        self.fields["required_clue_value"].validators = [
            MaxValueValidator(10000),
            MinValueValidator(1),
        ]
        self.fields["required_clue_value"].label = "Rating"

    def display(self):
        """Text display of form for in-game command"""
        plot = self.data.get("plot")
        if plot:
            try:
                plot = Plot.objects.get(id=plot)
            except Plot.DoesNotExist:
                pass
        msg = "{wName{n: %s\n" % self.data.get("name")
        msg += "{wDesc{n: %s\n" % self.data.get("desc")
        msg += "{wPlot:{n %s\n" % plot
        msg += "{wRequired Clue Value{n: %s\n" % self.data.get("required_clue_value")
        msg += "{wTags:{n %s\n" % self.data.get("tag_names")
        msg += "{wReal:{n %s\n" % ("Fake" if self.data.get("red_herring") else "True")
        return msg

    def save(self, commit=True):
        revelation = super(RevelationCreateForm, self).save(commit)
        revelation.author = self.author
        revelation.save()
        plot = self.cleaned_data.get("plot")
        gm_notes = self.cleaned_data.get("plot_gm_notes", "")
        revelation.plot_involvement.create(plot=plot, gm_notes=gm_notes)
        revelation.discoveries.create(character=self.author, discovery_method="author")
        inform_staff("Revelation '%s' created for plot '%s'." % (revelation, plot))
        return revelation
