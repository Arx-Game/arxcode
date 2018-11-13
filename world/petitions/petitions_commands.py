"""
Commands for petitions app
"""
from django.db.models import Q

from server.utils.arx_utils import ArxCommand
from server.utils.exceptions import PayError, CommandError
from server.utils.prettytable import PrettyTable
from world.petitions.forms import PetitionForm
from world.petitions.exceptions import PetitionError
from world.petitions.models import BrokeredSale, Petition


class CmdPetition(ArxCommand):
    """
    Creates a petition to an org or the market as a whole

    Usage:
    -Viewing:
        petition [<# to view>]
        petition[/old][/onlyorgs] [org name]
        petition/search <keyword>[=<org name>]
    -Org admin options
        petition/assign <#>=<member>
        petition/remove <#>=<member>
        petition/close <#>=<message sent to petitioner>
        petition/reopen <#>
    -Creation/Submission:
        petition/create [<topic>][=<description>]
        petition/topic <topic>
        petition/desc <description>
        petition/org <organization>
        petition/submit
        petition/cancel
    -Owner/Editing:
        petition/editdesc <#>=<new desc>
        petition/edittopic <#>=<new topic>
    -Anyone with access:
        petition/signup <#>
        petition/leave <#>
        petition/ic_note <#>=<ic note>
        petition/ooc_note <#>=<ooc note>

    Create a petition that is either submitted to an organization or
    posted in the market for signups.
    """
    key = "petition"
    help_category = "Social"
    aliases = ["petitions"]
    list_switches = ("old", "search", "onlyorgs")
    anyone_switches = ("signup", "leave", "ic_note", "ooc_note")
    org_admin_switches = ("assign", "remove")
    admin_switches = org_admin_switches + ("close", "reopen")
    creation_switches = ("create", "topic", "desc", "org", "submit", "cancel")
    owner_switches = ("editdesc", "edittopic")

    class PetitionCommandError(CommandError):
        """Exception class for Petition Command"""
        pass

    def func(self):
        """Executes petition command"""
        try:
            if self.check_switches(self.list_switches) or (not self.switches and not self.args.isdigit()):
                return self.list_petitions()
            elif not self.switches and self.args.isdigit():
                return self.display_petition()
            elif self.check_switches(self.anyone_switches):
                return self.do_any_access_switches()
            elif self.check_switches(self.admin_switches):
                return self.do_admin_switches()
            elif self.check_switches(self.creation_switches):
                return self.do_creation_switches()
            elif self.check_switches(self.owner_switches):
                return self.do_owner_switches()
            raise self.PetitionCommandError("Invalid switch.")
        except (self.PetitionCommandError, PetitionError) as err:
            self.msg(err)

    def list_petitions(self):
        """Lists petitions for org/player"""
        if ("search" in self.switches and self.rhs) or (self.args and "search" not in self.switches):
            if self.rhs:
                org = self.get_org_from_args(self.rhs)
            else:
                org = self.get_org_from_args(self.lhs)
            if not org.access(self.caller, "view_petition"):
                raise self.PetitionCommandError("You do not have access to view petitions for %s." % org)
            qs = org.petitions.all()
        else:
            from world.dominion.models import Organization
            orgs = Organization.objects.filter(members__deguilded=False).filter(members__player=self.caller.dompc)
            orgs = [org for org in orgs if org.access(self.caller, "view_petition")]
            query = Q(organization__in=orgs)
            if "onlyorgs" not in self.switches:
                query = query | Q(organization__isnull=True) | Q(dompcs=self.caller.dompc)
            qs = Petition.objects.filter(query)
        if "old" in self.switches:
            qs = qs.filter(closed=True)
        else:
            qs = qs.filter(closed=False)
        if "search" in self.switches:
            qs = qs.filter(Q(topic__icontains=self.lhs) | Q(description__icontains=self.lhs))
        signed_up = list(self.caller.dompc.petitions.filter(petitionparticipation__signed_up=True))
        table = PrettyTable(["ID", "Owner", "Topic", "Org", "On"])
        for ob in qs.distinct():
            signed_str = "X" if ob in signed_up else ""
            table.add_row([ob.id, str(ob.owner), ob.topic[:30], str(ob.organization), signed_str])
        self.msg(str(table))
        self.display_petition_form()

    def display_petition(self):
        """Displays detail about a petition"""
        petition = self.get_petition()
        self.msg(petition.display())
        petition.mark_posts_read(self.caller.dompc)

    def do_any_access_switches(self):
        """Commands that anyone who can see the petition can do"""
        petition = self.get_petition()
        if "signup" in self.switches:
            petition.signup(self.caller.dompc)
            self.msg("You have signed up for this petition.")
        elif "leave" in self.switches:
            petition.leave(self.caller.dompc)
            self.msg("You are no longer signed up for this petition.")
        else:
            if not self.rhs:
                raise self.PetitionCommandError("You must have a message.")
            if "ic_note" in self.switches:
                in_character = True
                msg = "You have posted a message to the petition."
            else:  # "ooc_note" in self.switches
                in_character = False
                msg = "You made an ooc note to the petition."
            petition.add_post(self.caller.dompc, self.rhs, in_character)
            self.msg(msg)

    def do_admin_switches(self):
        """Assign/remove petition from the petition, open or close it"""
        petition = self.get_petition()
        if self.check_switches(self.org_admin_switches):
            from django.core.exceptions import ObjectDoesNotExist
            if not petition.check_org_access(self.caller.player_ob, "admin_petition"):
                raise self.PetitionCommandError("You don't have admin_petition access to that petition.")
            player = self.caller.player.search(self.rhs)
            if not player:
                return
            target = player.Dominion
            verb = "assign" if "assign" in self.switches else "remove"
            try:
                member = target.memberships.get(organization=petition.organization)
                if member.deguilded and verb == "assign":
                    raise ObjectDoesNotExist
            except ObjectDoesNotExist:
                raise self.PetitionCommandError("You can only %s members of your organization." % verb)
            first_person = target == self.caller.dompc
            if "assign" in self.switches:
                petition.signup(target, first_person=first_person)
                self.msg("You have assigned %s to the petition." % target)
            else:  # remove them
                petition.leave(target, first_person=first_person)
                self.msg("You have removed %s from the petition." % target)
            return
        if self.caller.dompc != petition.owner and not petition.check_org_access(self.caller.player, "admin_petition"):
            raise self.PetitionCommandError("You are not allowed to do that.")
        if "close" in self.switches:
            if petition.closed:
                raise self.PetitionCommandError("It is already closed.")
            petition.closed = True
            self.msg("You have closed the petition.")
        else:  # reopen it
            if not petition.closed:
                raise self.PetitionCommandError("It is already open.")
            petition.closed = False
            self.msg("You have reopened the petition.")
        petition.save()

    def do_creation_switches(self):
        """Handles creation of a new petition"""
        form = self.caller.db.petition_form
        if "submit" in self.switches:
            if not form:
                raise self.PetitionCommandError("You must create a form first.")
            form = PetitionForm(form, owner=self.caller.dompc)
            if not form.is_valid():
                raise self.PetitionCommandError(form.display_errors())
            petition = form.save()
            self.msg("Successfully created petition %s." % petition.id)
            self.caller.attributes.remove("petition_form")
        else:
            if "create" in self.switches:
                if form:
                    self.display_petition_form()
                    raise self.PetitionCommandError("You already are creating a petition.")
                self.caller.db.petition_form = {'topic': self.lhs or None, 'description': self.rhs}
            elif form is None:
                raise self.PetitionCommandError("You must use /create first.")
            elif "topic" in self.switches:
                form['topic'] = self.args
            elif "desc" in self.switches:
                form['description'] = self.args
            elif "org" in self.switches:
                from world.dominion.models import Organization
                if not self.args:
                    form['organization'] = None
                else:
                    try:
                        form['organization'] = Organization.objects.get(name__iexact=self.args).id
                    except (Organization.DoesNotExist, ValueError, TypeError):
                        raise self.PetitionCommandError("No organization by that name.")
            elif "cancel" in self.switches:
                self.caller.attributes.remove("petition_form")
                self.msg("Petition form cancelled.")
            self.display_petition_form()

    def do_owner_switches(self):
        """Owner edit commands"""
        petition = self.get_petition()
        if self.caller.dompc != petition.owner:
            raise self.PetitionCommandError("You must be the owner of the petition to do that.")
        if not self.rhs:
            raise self.PetitionCommandError("You must enter text for the description or topic.")
        if "editdesc" in self.switches:
            petition.description = self.rhs
            self.msg("New description: %s" % self.rhs)
        else:  # edit topic
            if len(self.rhs) > 120:
                raise self.PetitionCommandError("Topic is too long.")
            petition.topic = self.rhs
            self.msg("New topic: %s" % self.rhs)
        petition.save()

    def get_org_from_args(self, args):
        """Gets an organization"""
        from world.dominion.models import Organization
        try:
            return Organization.objects.get(name__iexact=args)
        except Organization.DoesNotExist:
            raise self.PetitionCommandError("No organization by the name %s." % args)

    def get_petition(self):
        """Gets a petition"""
        from world.petitions.models import Petition
        try:
            petition = Petition.objects.get(id=self.lhs)
        except (Petition.DoesNotExist, ValueError):
            raise self.PetitionCommandError("No petition by that ID number.")
        else:
            if not petition.check_view_access(self.caller.dompc):
                raise self.PetitionCommandError("You are not allowed to access that petition.")
            return petition

    def display_petition_form(self):
        """Displays petition information"""
        form = self.caller.db.petition_form
        if not form:
            return
        self.msg(PetitionForm(form, owner=self.caller.dompc).display())


class CmdBroker(ArxCommand):
    """
    Buy or sell AP/Resources in the market

    Usage:
        broker/search <type>
        broker/buy <ID #>=<amount>
        broker/sell <type>=<amount>,<price>
        broker/cancel <ID #>
        broker/reprice <ID #>=<new price>

    Allows you to automatically buy or sell crafting materials or
    more abstract things such as influence with npcs (resources)
    or time (action points). To sell or buy action points, specify
    'action points' or 'ap' as the type. To sell or buy resources,
    specify the type of resource (economic, social, or military).
    It costs three times as much action points as the amount you
    put on the broker. All prices are per-unit. Note that cancelling
    action points for sale will not refund the full amount.

    When searching, you can specify the name of a seller, a type
    of crafting material or resource (umbra, economic, etc), ap,
    or categories such as 'resources' or 'materials'.
    """
    key = "broker"
    help_category = "Market"

    class BrokerError(Exception):
        """Errors when using the broker"""
        pass

    def func(self):
        """Executes broker command"""
        try:
            if not self.args or "search" in self.switches:
                return self.broker_display()
            if not self.switches:
                return self.display_sale_detail()
            if "buy" in self.switches:
                return self.make_purchase()
            if "sell" in self.switches:
                return self.make_sale_offer()
            if "cancel" in self.switches:
                return self.cancel_sale()
            if "reprice" in self.switches:
                return self.change_sale_price()
            raise self.BrokerError("Invalid switch.")
        except (self.BrokerError, PayError) as err:
            self.msg(err)

    def get_sale_type(self):
        """Gets the constant based on types of args players might enter"""
        args = self.lhs.lower()
        if args in ("ap", "action points", "action_points"):
            return BrokeredSale.ACTION_POINTS
        elif "economic" in args:
            return BrokeredSale.ECONOMIC
        elif "social" in args:
            return BrokeredSale.SOCIAL
        elif "military" in args:
            return BrokeredSale.MILITARY
        else:
            return BrokeredSale.CRAFTING_MATERIALS

    def broker_display(self):
        """Displays items for sale on the broker"""

        qs = BrokeredSale.objects.filter(amount__gte=1)
        if "search" in self.switches and self.args:

            sale_type = self.get_sale_type()
            if sale_type in (BrokeredSale.ACTION_POINTS, BrokeredSale.ECONOMIC,
                             BrokeredSale.SOCIAL, BrokeredSale.MILITARY):
                query = Q(sale_type=sale_type)
            else:
                if set(self.args.lower().split()) & {"materials", "mats", "crafting"}:
                    query = Q(sale_type=BrokeredSale.CRAFTING_MATERIALS)
                elif "resource" in self.args.lower():
                    query = Q(sale_type__in=(BrokeredSale.ECONOMIC, BrokeredSale.SOCIAL, BrokeredSale.MILITARY))
                else:
                    query = (Q(crafting_material_type__name__icontains=self.args) |
                             Q(owner__player__username__iexact=self.args))
            qs = qs.filter(query)

        table = PrettyTable(["ID", "Seller", "Type", "Price", "Amount"])
        for deal in qs:
            table.add_row([deal.id, str(deal.owner), str(deal.material_name), deal.price, deal.amount])
        self.msg(str(table))

    def display_sale_detail(self):
        """Displays information about a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        self.msg(sale.display(self.caller))

    def make_purchase(self):
        """Buys some amount from a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        amount = self.get_amount(self.rhs)
        dompc = self.caller.player_ob.Dominion
        if sale.owner == dompc:
            raise self.BrokerError("You can't buy from yourself. Cancel it instead.")
        try:
            if sale.owner.player.roster.current_account == self.caller.roster.current_account:
                raise self.BrokerError("You can't buy from an alt.")
        except AttributeError:
            pass
        cost = sale.make_purchase(dompc, amount)
        self.msg("You have bought %s %s from %s for %s silver." % (amount, sale.material_name, sale.owner, cost))

    def get_amount(self, args, noun="amount"):
        """Gets a positive number to use for a transaction, or raises a BrokerError"""
        try:
            amount = int(args)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise self.BrokerError("You must provide a positive number as the %s." % noun)
        return amount

    def make_sale_offer(self):
        """Create a new sale"""
        if len(self.rhslist) != 2:
            raise self.BrokerError("You must ask for both an amount and a price.")
        amount = self.get_amount(self.rhslist[0])
        price = self.get_amount(self.rhslist[1], "price")
        sale_type = self.get_sale_type()
        material_type = None
        resource_types = dict(BrokeredSale.RESOURCE_TYPES)
        if sale_type == BrokeredSale.ACTION_POINTS:
            from evennia.server.models import ServerConfig
            disabled = ServerConfig.objects.conf(key="DISABLE_AP_TRANSFER")
            if disabled:
                raise self.BrokerError("Action Point sales are temporarily disabled.")
            if amount % 3:
                raise self.BrokerError("Action Points must be a factor of 3, since it's divided by 3 when put on sale.")
            if not self.caller.player_ob.pay_action_points(amount):
                raise self.BrokerError("You do not have enough action points to put on sale.")
            amount /= 3
        elif sale_type in resource_types:
            resource = resource_types[sale_type]
            if not self.caller.player_ob.pay_resources(resource, amount):
                raise self.BrokerError("You do not have enough %s resources to put on sale." % resource)
        else:
            from world.dominion.models import CraftingMaterialType
            try:
                material_type = CraftingMaterialType.objects.get(name__iexact=self.lhs)
            except CraftingMaterialType.DoesNotExist:
                raise self.BrokerError("Could not find a material by the name '%s'." % self.lhs)
            if "nosell" in (material_type.acquisition_modifiers or ""):
                raise self.BrokerError("You can't put contraband on the broker! Seriously, how are you still alive?")
            if not self.caller.player_ob.pay_materials(material_type, amount):
                raise self.BrokerError("You don't have enough %s to put on sale." % material_type)
        dompc = self.caller.player_ob.Dominion
        sale, created = dompc.brokered_sales.get_or_create(price=price, sale_type=sale_type,
                                                           crafting_material_type=material_type)
        sale.amount += amount
        sale.save()
        if created:
            self.msg("Created a new sale of %s %s for %s silver." % (amount, sale.material_name, price))
        else:
            self.msg("Added %s to the existing sale of %s for %s silver." % (amount, sale.material_name, price))

    def find_brokered_sale_by_id(self, args):
        """Tries to find a brokered sale with ID that matches args or raises BrokerError"""
        try:
            return BrokeredSale.objects.get(id=args)
        except (BrokeredSale.DoesNotExist, ValueError, TypeError):
            raise self.BrokerError("Could not find a sale on the broker by the ID %s." % args)

    def cancel_sale(self):
        """Cancels a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        if sale.owner != self.caller.player_ob.Dominion:
            raise self.BrokerError("You can only cancel your own sales.")
        sale.cancel()
        self.msg("You have cancelled the sale.")

    def change_sale_price(self):
        """Changes the price of a sale"""
        sale = self.find_brokered_sale_by_id(self.lhs)
        if sale.owner != self.caller.player_ob.Dominion:
            raise self.BrokerError("You can only change the price of your own sales.")
        price = self.get_amount(self.rhs, "price")
        if price == sale.price:
            raise self.BrokerError("The new price must be different from the current price.")
        sale.change_price(price)
        self.msg("You have changed the price to %s." % price)
