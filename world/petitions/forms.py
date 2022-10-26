"""
Forms for petitions app
"""
from django.forms import ModelForm
from world.petitions.models import Petition


class PetitionForm(ModelForm):
    """Form for creating a Petition. We'll actually try using it in commands for validation"""

    class Meta:
        """Meta options for setting up the form"""

        model = Petition
        fields = ["organization", "topic", "description"]

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop("owner")
        super(PetitionForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        """Saves the instance and adds the form's owner as the owner of the petition"""
        petition = super(PetitionForm, self).save(commit)
        petition.petitionparticipation_set.create(dompc=self.owner, is_owner=True)
        org = self.cleaned_data.get("organization")
        if org:
            org.inform(
                "A new petition has been made by %s.  Type 'petition %s' to read it."
                % (self.owner, petition.id),
                category="Petitions",
            )
        return petition

    def display(self):
        """Returns a game-friend display string"""
        from world.dominion.models import Organization

        msg = "{wPetition Being Created:\n"
        msg += "{wTopic:{n %s\n" % self.data.get("topic")
        msg += "{wDescription:{n %s\n" % self.data.get("description")
        org = self.data.get("organization")
        if org:
            msg += "{wOrganization:{n %s\n" % Organization.objects.get(
                id=self.data["organization"]
            )
        return msg

    def display_errors(self):
        """Returns a game-friendly errors string"""
        msg = "Please correct the following errors:\n"
        msg += "\n".join(
            "%s: %s" % (field, ", ".join(str(err.args[0]) for err in errs))
            for field, errs in self.errors.as_data().items()
        )
        return msg
