# -*- coding: utf-8 -*-
"""
Models for Petitions app
"""
from __future__ import unicode_literals

from django.db import models

from evennia.utils.idmapper.models import SharedMemoryModel

from server.utils.exceptions import PayError
from .exceptions import PetitionError
from world.dominion.models import Organization







class BrokeredSale(SharedMemoryModel):
    """A sale sitting on the broker, waiting for someone to buy it"""
    ACTION_POINTS = 0
    ECONOMIC = 1
    SOCIAL = 2
    MILITARY = 3
    CRAFTING_MATERIALS = 4
    SALE = 0
    PURCHASE = 1
    OFFERING_TYPES = ((ACTION_POINTS, "Action Points"), (ECONOMIC, "Economic Resources"), (SOCIAL, "Social Resources"),
                      (MILITARY, "Military Resources"), (CRAFTING_MATERIALS, "Crafting Materials"))
    RESOURCE_TYPES = ((ECONOMIC, "economic"), (SOCIAL, "social"), (MILITARY, "military"))
    BROKER_TYPES = ((PURCHASE, "Purchase"), (SALE, "Sale"))
    owner = models.ForeignKey("dominion.PlayerOrNpc", related_name="brokered_sales")
    sale_type = models.PositiveSmallIntegerField(default=ACTION_POINTS, choices=OFFERING_TYPES)
    amount = models.PositiveIntegerField(default=0)
    price = models.PositiveIntegerField(default=0)
    buyers = models.ManyToManyField("dominion.PlayerOrNpc", related_name="brokered_purchases",
                                    through="PurchasedAmount")
    crafting_material_type = models.ForeignKey("dominion.CraftingMaterialType", null=True, blank=True,
                                               on_delete=models.CASCADE)
    broker_type = models.PositiveSmallIntegerField(default=SALE, choices=BROKER_TYPES)

    @property
    def material_name(self):
        """Returns the name of what we're offering"""
        if self.crafting_material_type:
            return self.crafting_material_type.name
        return self.get_sale_type_display()

    @property
    def owner_character(self):
        """Character object of our owner"""
        return self.owner.player.char_ob

    def display(self, caller):
        """
        Gets a string display of the sale based on caller's privileges
        Args:
            caller: Character object, determine if it's our owner to show buyer information

        Returns:
            string display of the sale
        """
        msg = "{wID{n: %s\n" % self.id
        msg += "{wMaterial{n: %s {wAmount{n: %s {wPrice{n: %s\n" % (self.material_name, self.amount, self.price)
        amounts = self.purchased_amounts.all()
        if caller == self.owner_character and amounts:
            msg += "{wPurchase History:{n\n"
            msg += ", ".join(ob.display() for ob in amounts)
        return msg

    def make_purchase(self, buyer, amount):
        """
        Khajit has wares, if you have coin.
        Args:
            buyer (PlayerOrNpc): the buyer
            amount (int): How much they're buying

        Returns:
            the amount they paid

        Raises:
            PayError if they can't afford stuff
        """
        if amount > self.amount:
            raise PayError("You want to buy %s, but there is only %s for sale." % (amount, self.amount))
        cost = self.price * amount
        self.amount -= amount
        if self.broker_type == self.SALE:
            self.send_goods(buyer, amount)
            self.pay_owner(buyer, amount, cost)
        else:
            self.send_goods(self.owner, amount)
            self.pay_seller(buyer, amount, cost)
        if self.amount:
            self.save()
            self.record_sale(buyer, amount)
        else:
            self.delete()
        return cost

    def send_goods(self, buyer, amount):
        """
        Sends the results of a sale to buyer and records the purchase
        Args:
            buyer (PlayerOrNpc): person we send the goods to
            amount (int): How much we're sending
        """
        if self.sale_type == self.ACTION_POINTS:
            buyer.player.pay_action_points(-amount)
        elif self.sale_type == self.CRAFTING_MATERIALS:
            buyer.player.gain_materials(self.crafting_material_type, amount)
        else:  # resources
            resource_types = dict(self.RESOURCE_TYPES)
            resource = resource_types[self.sale_type]
            buyer.player.gain_resources(resource, amount)

    def record_sale(self, buyer, amount):
        """Records a sale"""
        record, _ = self.purchased_amounts.get_or_create(buyer=buyer)
        record.amount += amount
        record.save()

    def pay_owner(self, buyer, quantity, cost):
        """Pays our owner"""
        self.owner_character.pay_money(-cost)
        self.owner.player.inform("%s has bought %s %s for %s silver." % (buyer, quantity, self.material_name, cost),
                                 category="Broker Sale", append=True)

    def pay_seller(self, seller, quantity, cost):
        seller.player.char_ob.pay_money(-cost)
        self.owner.player.inform("%s has sold %s %s for %s silver." % (seller, quantity, self.material_name, cost),
                                 category="Broker Sale", append=True)

    def cancel(self):
        """Refund our owner and delete ourselves"""
        if self.broker_type == self.PURCHASE:
            self.owner_character.pay_money(-self.amount*self.price)
        else:
            self.send_goods(self.owner, self.amount)
        self.delete()

    def change_price(self, new_price):
        """Changes the price to new_price. If we have an existing sale by that price, merge with it."""
        if self.broker_type == self.PURCHASE:
            buyer = self.owner_character
            original_cost = new_price*self.amount
            new_cost = self.price*self.amount
            to_pay = original_cost-new_cost
            if to_pay > buyer.currency:
                raise PayError("You cannot afford to pay %s when you only have %s silver." % (to_pay, buyer.currency))
            self.owner_character.pay_money(to_pay)
        try:
            other_sale = self.owner.brokered_sales.get(sale_type=self.sale_type, price=new_price,
                                                       crafting_material_type=self.crafting_material_type,
                                                       broker_type=self.broker_type)
            other_sale.amount += self.amount
            other_sale.save()
            self.delete()
        except BrokeredSale.DoesNotExist:
            self.price = new_price
            self.save()


class PurchasedAmount(SharedMemoryModel):
    """Details of a purchase by a player"""
    deal = models.ForeignKey('BrokeredSale', related_name="purchased_amounts")
    buyer = models.ForeignKey('dominion.PlayerOrNpc', related_name="purchased_amounts")
    amount = models.PositiveIntegerField(default=0)

    def display(self):
        """Gets string display of the amount purchased and by whom"""
        return "{} bought {}".format(self.buyer, self.amount)

class PetitionSettings(SharedMemoryModel):
    owner = models.ForeignKey("dominion.PlayerOrNpc", related_name="petition_settings")
    inform=models.BooleanField(default=True)
    ignore_general=models.BooleanField(default=False)
    ignored_organizations=models.ManyToManyField(Organization)
    
    def cleanup(self):
        ignore_general=False
        inform=True
        ignored_organizations.clear()
        try:
            participations=self.owner.petitionparticipation_set.all()
            for petition_participation in participations:
                petition_participation.subscribed=False
                petition_participation.unread_posts=True
                petition_participation.signed_up=False
                if (petition_participation.is_owner):
                    petition_participation.petition.closed=True
                petition_participation.save()
        except:
            pass
    

    
class Petition(SharedMemoryModel):
    """A request for assistance made openly or to an organization"""
    dompcs = models.ManyToManyField('dominion.PlayerOrNpc', related_name="petitions", through="PetitionParticipation")
    organization = models.ForeignKey('dominion.Organization', related_name="petitions", blank=True, null=True,
                                     on_delete=models.CASCADE)
    closed = models.BooleanField(default=False)
    waiting=models.BooleanField(default=True)
    topic = models.CharField("Short summary of the petition", max_length=120)
    description = models.TextField("Description of the petition.")
    date_created = models.DateField(auto_now_add=True)
    date_updated = models.DateField(auto_now=True)

    @property
    def owner(self):
        """Gets first owner, if any"""
        try:
            return self.petitionparticipation_set.filter(is_owner=True).first().dompc
        except AttributeError:
            pass

    @property
    def is_public(self):
        """Whether anyone can see us"""
        return not self.organization

    def check_view_access(self, dompc):
        """Whether the petition can be seen"""
        if self.is_public:
            return True
        if dompc == self.owner:
            return True
        return self.check_org_access(dompc.player, access_type="view_petition")

    def check_org_access(self, player, access_type):
        """Checks if the player has access to the org"""
        try:
            return self.organization.access(player, access_type)
        except AttributeError:
            return False

    def display(self):
        """String display of the petition"""
        owner = self.owner
        participants = self.petitionparticipation_set.filter(signed_up=True)
        msg = "ID: %s  Topic: %s\n" % (self.id, self.topic)
        msg += "Owner: %s" % owner
        if self.organization:
            msg += "  Organization: %s" % self.organization
        msg += "\nDescription: %s\n" % self.description
        msg += "\nSignups: %s" % ", ".join(str(ob) for ob in participants)
        ic_posts = self.posts.filter(in_character=True)
        ooc_posts = self.posts.filter(in_character=False)
        if ic_posts:
            msg += "\nMessages For this Petition:\n"
            msg += "\n".join(post.display() for post in ic_posts)
        if ooc_posts:
            msg += "\nOOC Notes:\n"
            msg += "\n".join(post.display() for post in ooc_posts)
        return msg

    def signup(self, dompc, first_person=True):
        """Signs up a dompc for this"""
        if self.petitionparticipation_set.filter(dompc=dompc, signed_up=True).exists():
            if first_person:
                raise PetitionError("You have already signed up for this.")
            else:
                raise PetitionError("%s has already signed up for this." % dompc)
        part, _ = self.petitionparticipation_set.get_or_create(dompc=dompc)
        part.signed_up = True
        part.subscribed=True
        part.save()

    def leave(self, dompc, first_person=True):
        """Leaves a petition"""
        try:
            part = self.petitionparticipation_set.get(dompc=dompc, signed_up=True)
        except PetitionParticipation.DoesNotExist:
            if first_person:
                raise PetitionError("You are not signed up for that petition.")
            else:
                raise PetitionError("%s is not signed up for that petition." % dompc)
        part.signed_up = False
        part.save()

    def add_post(self, dompc, text, in_character):
        """Make a new post"""
        self.posts.create(in_character=in_character, dompc=dompc, text=text)
        part = self.petitionparticipation_set.get(dompc=dompc)
        part.subscribed=True
        for participant in self.petitionparticipation_set.filter(unread_posts=False).exclude(dompc=dompc):
            participant.unread_posts = True
            participant.save()
            if participant.subscribed:
                participant.player.msg("{wA new message has been posted to petition %s.{n" % self.id)
                participant.player.inform("{wA new message has been posted to petition %s:{n|/|/%s" % (self.id,text),category="Petition", append=True)

    def mark_posts_read(self, dompc):
        """If dompc is a participant, mark their posts read"""
        try:
            participant = self.petitionparticipation_set.get(dompc=dompc)
            participant.unread_posts = False
            participant.save()
        except PetitionParticipation.DoesNotExist:
            pass
    def mark_posts_unread(self, dompc):
        """If dompc is a participant, mark their posts read"""
        try:
            participants = self.petitionparticipation_set.all().exclude(dompc=dompc)
            for participant in participants:
                    participant.unread_posts = True
                    participant.save()
        except PetitionParticipation.DoesNotExist:
            pass


class PetitionParticipation(SharedMemoryModel):
    """A model showing how someone participated in a petition"""
    petition = models.ForeignKey('Petition')
    dompc = models.ForeignKey('dominion.PlayerOrNpc')
    is_owner = models.BooleanField(default=False)
    signed_up = models.BooleanField(default=False)
    unread_posts = models.BooleanField(default=False)
    subscribed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('petition', 'dompc')

    def __str__(self):
        return str(self.dompc)

    @property
    def player(self):
        return self.dompc.player


class PetitionPost(SharedMemoryModel):
    """A model of a message attached to a given petition."""
    petition = models.ForeignKey('petitions.Petition', related_name="posts")
    dompc = models.ForeignKey('dominion.PlayerOrNpc', blank=True, null=True)
    in_character = models.BooleanField(default=True)
    text = models.TextField(blank=True)

    def display(self):
        """Display of the post"""
        if self.in_character:
            msg = "{wWritten By:{n %s\n" % self.dompc
        else:
            msg = "{wOOC Note by:{n%s\n" % self.dompc
        msg += self.text + "\n"
        return msg
