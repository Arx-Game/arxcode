"""
Forms for the Character app. Stuff based around the character sheet page
"""
from cloudinary.forms import CloudinaryFileField, CloudinaryJsFileField, CloudinaryUnsignedJsFileField
from django import forms
from django.db.models import Q

from .models import Photo, Flashback, RosterEntry


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
        self.fields['select_portrait'].queryset = qset


class PhotoEditForm(forms.Form):
    """Form for selecting a photo to edit"""
    select_photo = PhotoModelChoiceField(queryset=None, empty_label="(No Image Selected)")
    title = forms.CharField(max_length=200)
    alt_text = forms.CharField(max_length=200)
    
    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoEditForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields['select_photo'].queryset = qset


class PhotoDeleteForm(forms.Form):
    """Form for selecting a photo to delete"""
    select_photo = PhotoModelChoiceField(queryset=None, empty_label="(No Image Selected)")

    def __init__(self, object_id=None, *args, **kwargs):
        super(PhotoDeleteForm, self).__init__(*args, **kwargs)
        if not object_id:
            qset = Photo.objects.none()
        else:
            qset = Photo.objects.filter(owner__id=object_id)
        self.fields['select_photo'].queryset = qset


class PhotoForm(forms.ModelForm):
    """Form for uploading a Photo"""
    class Meta:
        """We set the image to be a CloudinaryFileField for the upload"""
        model = Photo
        fields = ['title', 'alt_text', 'image']
        image = CloudinaryFileField(options={'use_filename': True,
                                             'unique_filename': False,
                                             'overwrite': False})


class PhotoDirectForm(PhotoForm):
    """Form for uploading with javascript"""
    image = CloudinaryJsFileField()


class PhotoUnsignedDirectForm(PhotoForm):
    """Form for uploading when unsigned"""
    upload_preset_name = "Arx_Default_Unsigned"
    image = CloudinaryUnsignedJsFileField(upload_preset_name)


class FlashbackPostForm(forms.Form):
    """Form for adding a post to a flashback"""
    actions = forms.CharField(label="Post Text", widget=forms.Textarea(attrs={'class': "form-control", 'rows': "10"}),)

    def add_post(self, flashback, poster):
        """Adds the post, which does various in-game updates, like sending informs."""
        actions = self.cleaned_data['actions']
        flashback.add_post(actions, poster)


class FlashbackCreateForm(forms.ModelForm):
    """Simple ModelForm for creating a new Flashback. We add the owner automatically."""
    class Meta:
        """Set our model and fields"""
        model = Flashback
        fields = ['title', 'summary', 'allowed']

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner')
        super(FlashbackCreateForm, self).__init__(*args, **kwargs)
        self.fields['allowed'].queryset = RosterEntry.objects.filter(Q(roster__name="Active") |
                                                                     Q(roster__name="Available") |
                                                                     Q(roster__name="Gone") |
                                                                     Q(roster__name="Inactive") |
                                                                     Q(roster__name="Unavailable")
                                                                     ).order_by('character__db_key')

    def save(self, commit=True):
        """Saves the form as a new Flashback and adds our owner/date created fields"""
        from datetime import datetime
        obj = super(FlashbackCreateForm, self).save(commit=False)
        obj.owner = self.owner
        obj.db_date_created = datetime.now()
        obj.save()
        return obj
