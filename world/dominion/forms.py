"""
Forms for Dominion
"""
from django import forms
from django.db.models import Q

from typeclasses.rooms import ArxRoom
from world.dominion.models import RPEvent, Organization, PlayerOrNpc, PlotRoom, Plot


class RPEventCommentForm(forms.Form):
    """Form for commenting on an existing RPEvent"""
    journal_text = forms.CharField(widget=forms.Textarea)
    private = forms.BooleanField(initial=False, required=False)

    def post_comment(self, char, event):
        """Posts a comment for an RPEvent"""
        msg = self.cleaned_data['journal_text']
        white = not self.cleaned_data['private']
        char.messages.add_event_journal(event, msg, white=white)


class RPEventCreateForm(forms.ModelForm):
    """Form for creating a RPEvent. We'll actually try using it in commands for validation"""
    player_queryset = PlayerOrNpc.objects.filter(Q(player__roster__roster__name="Active") |
                                                 Q(player__is_staff=True)).distinct().order_by('player__username')
    org_queryset = Organization.objects.filter(members__isnull=False).distinct().order_by('name')
    room_name = forms.CharField(required=False, help_text="Location")
    hosts = forms.ModelMultipleChoiceField(queryset=player_queryset, required=False)
    invites = forms.ModelMultipleChoiceField(queryset=player_queryset, required=False)
    gms = forms.ModelMultipleChoiceField(queryset=player_queryset, required=False)
    org_invites = forms.ModelMultipleChoiceField(queryset=org_queryset, required=False)
    location = forms.ModelChoiceField(queryset=ArxRoom.objects.all(), widget=forms.HiddenInput(), required=False)
    plot = forms.ModelChoiceField(queryset=Plot.objects.none(), required=False)

    class Meta:
        """Meta options for setting up the form"""
        model = RPEvent
        fields = ['name', 'desc', 'date', 'room_desc', 'location', 'plotroom', 'celebration_tier', 'risk',
                  'public_event']

    def __init__(self, *args, **kwargs):
        self.owner = kwargs.pop('owner')
        super(RPEventCreateForm, self).__init__(*args, **kwargs)
        self.fields['desc'].required = True
        self.fields['date'].required = True
        self.fields['plot'].queryset = self.owner.plots_we_can_gm
        if not self.owner.player.is_staff:
            current_orgs = [ob.id for ob in self.owner.current_orgs]
            self.fields['org_invites'].queryset = self.org_queryset.filter(Q(secret=False) | Q(id__in=current_orgs))

    @property
    def cost(self):
        """Returns the amount of money needed for validation"""
        try:
            return dict(RPEvent.LARGESSE_VALUES)[int(self.data.get('celebration_tier', 0))][0]
        except (KeyError, TypeError, ValueError):
            self.add_error('celebration_tier', "Invalid largesse value.")

    def clean(self):
        """Validates that we can pay for things. Any special validation should be here"""
        cleaned_data = super(RPEventCreateForm, self).clean()
        self.check_risk()
        self.check_costs()
        self.check_location_or_plotroom()
        return cleaned_data

    def clean_date(self):
        """Validates our date. ValiDATES, get it? Get it?"""
        from datetime import datetime
        date = self.cleaned_data['date']
        if date < datetime.now():
            self.add_error("date", "You cannot add a date for the past.")
        return date

    def clean_location(self):
        """Use room name if we don't have a location defined"""
        location = self.cleaned_data.get('location')
        if location:
            return location
        room_name = self.data.get('room_name')
        if room_name:
            try:
                try:
                    room = ArxRoom.objects.get(db_key__icontains=room_name)
                except ArxRoom.MultipleObjectsReturned:
                    room = ArxRoom.objects.get(db_key__iexact=room_name)
            except ArxRoom.DoesNotExist:
                self.add_error('room_name', "No unique match for a room by that name.")
            else:
                return room

    def check_costs(self):
        """Checks if we can pay, if not, adds an error"""
        if self.cost > self.owner.player.char_ob.currency:
            self.add_error('celebration_tier', "You cannot afford to pay the cost of %s." % self.cost)

    def check_risk(self):
        """Checks that our risk field is acceptable"""
        gms = self.cleaned_data.get('gms', [])
        risk = self.cleaned_data.get('risk', RPEvent.NORMAL_RISK)
        if not any(gm for gm in gms if gm.player.is_staff or gm.player.check_permstring("builders")):
            if risk != RPEvent.NORMAL_RISK:
                self.add_error('risk', "Risk cannot be altered without a staff member as GM. Set to: %r" % risk)

    def check_location_or_plotroom(self):
        """Checks to make sure either a location or plotroom is defined."""
        location = self.cleaned_data.get('location')
        plotroom = self.cleaned_data.get('plotroom')
        if not (location or plotroom):
            self.add_error('plotroom', "You must give either a location or a plot room.")
        elif all((location, plotroom)):
            self.add_error('plotroom', "Please only specify location or plot room, not both.")

    def save(self, commit=True):
        """Saves the instance and adds the form's owner as the owner of the petition"""
        event = super(RPEventCreateForm, self).save(commit)
        event.add_host(self.owner, main_host=True)
        hosts = self.cleaned_data.get('hosts', [])
        for host in hosts:
            # prevent owner from being downgraded to normal host if they were added
            if host != self.owner:
                event.add_host(host)
        gms = self.cleaned_data.get('gms', [])
        for gm in gms:
            event.add_gm(gm)
        invites = self.cleaned_data.get('invites', [])
        for pc_invite in invites:
            if pc_invite not in hosts and pc_invite not in gms:
                event.add_guest(pc_invite)
        for org in self.cleaned_data.get('org_invites', []):
            event.invite_org(org)
        plot = self.cleaned_data.get('plot', None)
        if plot:
            # we create a blank PlotUpdate so that this is tagged to the Plot, but nothing has happened yet
            event.beat = plot.updates.create()
            event.save()
        self.pay_costs()
        self.post_event(event)
        return event

    def pay_costs(self):
        """Pays the costs of the event"""
        cost = self.cost
        if cost:
            self.owner.player.char_ob.pay_money(cost)
            self.owner.player.msg("You pay %s coins for the event." % cost)

    def post_event(self, event):
        """Makes a post of this event"""
        from evennia.scripts.models import ScriptDB
        if event.public_event:
            event_manager = ScriptDB.objects.get(db_key="Event Manager")
            event_manager.post_event(event, self.owner.player, self.display())

    def display(self):
        """Returns a game-friend display string"""
        msg = "{wName:{n %s\n" % self.data.get('name')
        plot = self.data.get('plot')
        if plot:
            plot = Plot.objects.get(id=plot)
            msg += "{wPlot:{n %s\n" % plot
        msg += "{wMain Host:{n %s\n" % self.owner
        hosts = PlayerOrNpc.objects.filter(id__in=self.data.get('hosts', []))
        if hosts:
            msg += "{wOther Hosts:{n %s\n" % ", ".join(str(ob) for ob in hosts)
        msg += "{wPublic:{n %s\n" % ("Public" if self.data.get('public_event', True) else "Private")
        msg += "{wDescription:{n %s\n" % self.data.get('desc')
        msg += "{wDate:{n %s\n" % self.data.get('date')
        location = self.data.get('location')
        if location:
            location = ArxRoom.objects.get(id=location)
        msg += "{wLocation:{n %s\n" % location
        plotroom = self.data.get('plotroom')
        if plotroom:
            plotroom = PlotRoom.objects.get(id=plotroom)
            msg += "{wPlotroom:{n %s\n" % plotroom
        msg += "{wLargesse:{n %s\n" % dict(RPEvent.LARGESSE_CHOICES).get(self.data.get('celebration_tier', 0))
        gms = PlayerOrNpc.objects.filter(id__in=self.data.get('gms', []))
        if gms:
            msg += "{wGMs:{n %s\n" % ", ".join(str(ob) for ob in gms)
            msg += "{wRisk:{n %s\n" % dict(RPEvent.RISK_CHOICES).get(self.data.get('risk', RPEvent.NORMAL_RISK))
        orgs = PlayerOrNpc.objects.filter(id__in=self.data.get('orgs', []))
        if orgs:
            msg += "{wOrg invitations:{n %s\n" % ", ".join(str(org) for org in self.orgs)
        invites = PlayerOrNpc.objects.filter(id__in=self.data.get('invites', []))
        if invites:
            msg += "{wInvitations:{n %s\n" % ", ".join(str(ob) for ob in invites)
        actions = self.data.get('actions', [])
        if actions:
            msg += "{wRelated Actions:{n %s\n" % ", ".join(str(ob) for ob in actions)
        return msg

    def display_errors(self):
        """Returns a game-friendly errors string"""
        def format_name(field_name):
            """Formats field names for error display"""
            if field_name == "celebration_tier":
                return "{wLargesse{n"
            return "{w%s{n" % field_name.capitalize()
        msg = "Please correct the following errors:\n"
        msg += "\n".join("%s: {r%s{n" % (format_name(field), ", ".join(errs)) for field, errs in self.errors.items())
        return msg
