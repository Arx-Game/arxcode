"""
Handler for Messengers
"""
from world.crafting.models import CraftingMaterialType, OwnedMaterial
from world.msgs.handler_mixins.msg_utils import (
    get_initial_queryset,
    lazy_import_from_str,
)
from world.msgs.handler_mixins.handler_base import MsgHandlerBase
from world.msgs.managers import (
    q_msgtag,
    PRESERVE_TAG,
    MESSENGER_TAG,
    reload_model_as_proxy,
)
from server.utils.arx_utils import get_date, create_arx_message, inform_staff


class MessengerHandler(MsgHandlerBase):
    def __init__(self, obj=None):
        """
        We'll be doing a series of delayed calls to set up the various
        attributes in the MessageHandler, since we can't have ObjectDB
        refer to Msg during the loading-up process.
        """
        super(MessengerHandler, self).__init__(obj)
        self._messenger_history = None

    @property
    def messenger_history(self):
        if self._messenger_history is None:
            self.build_messenger_history()
        return self._messenger_history

    @messenger_history.setter
    def messenger_history(self, value):
        self._messenger_history = value

    @property
    def messenger_draft(self):
        return self.obj.item_data.messenger_draft

    @messenger_draft.setter
    def messenger_draft(self, val):
        if not val:
            del self.obj.item_data.messenger_draft
        else:
            self.obj.item_data.messenger_draft = val
            self.msg("Saved message. To see it, type 'message/proof'.")

    def create_messenger_header(self, icdate):
        header = "date:%s" % icdate
        name = self.spoofed_name
        if name:
            header += ";spoofed_name:%s" % name
        return header

    @property
    def messenger_qs(self):
        return get_initial_queryset("Messenger").about_character(self.obj)

    def build_messenger_history(self):
        """
        Returns a list of all messengers this character has received. Does not include pending.
        """
        pending_ids = [
            tup[0].id
            for tup in self.pending_messengers
            if tup and tup[0] and hasattr(tup[0], "id")
        ]
        self._messenger_history = list(self.messenger_qs.exclude(id__in=pending_ids))
        return self._messenger_history

    def preserve_messenger(self, msg):
        pres_count = self.messenger_qs.filter(q_msgtag(PRESERVE_TAG)).count()
        if pres_count >= 200:
            self.msg("You are preserving the maximum amount of messages allowed.")
            return
        if msg.preserved:
            self.msg("That message is already being preserved.")
            return
        msg.preserve()
        self.msg("This message will no longer be automatically deleted.")
        return True

    def create_messenger(self, msg, date=""):
        """
        Here we create the msg object and return it to the command to handle.
        They'll attach the msg object to each receiver as an attribute, who
        can then call receive_messenger on the stored msg.
        """
        cls = lazy_import_from_str("Messenger")
        if not date:
            date = get_date()
        header = self.create_messenger_header(date)
        msg = create_arx_message(
            self.obj, msg, receivers=None, header=header, cls=cls, tags=MESSENGER_TAG
        )
        return msg

    def del_messenger(self, msg):
        if msg in self.messenger_history:
            self.messenger_history.remove(msg)
        self.obj.receiver_object_set.remove(msg)
        # only delete the messenger if no one else has a copy
        if not msg.receivers:
            msg.delete()

    @property
    def spoofed_name(self):
        return self.obj.db.spoofed_messenger_name

    @spoofed_name.setter
    def spoofed_name(self, name):
        """Setter for spoofed name. If no name is specified, remove it."""
        if not name:
            self.obj.attributes.remove("spoofed_messenger_name")
            self.obj.msg("You will no longer send messengers with a fake name.")
            return
        self.obj.db.spoofed_messenger_name = name
        self.obj.msg("You will now send messengers by the name %s" % name)

    @property
    def discreet_messenger(self):
        return self.obj.item_data.discreet_messenger

    @discreet_messenger.setter
    def discreet_messenger(self, val):
        if not val:
            del self.obj.item_data.discreet_messenger
            self.obj.msg("You will not receive messages discreetly.")
            return
        self.obj.item_data.discreet_messenger = val
        self.obj.msg(
            "%s will now deliver messages to you discreetly if they are in the same room."
            % val
        )

    @property
    def pending_messengers(self):
        if self.obj.db.pending_messengers is None:
            self.obj.db.pending_messengers = []
        return self.obj.db.pending_messengers

    @pending_messengers.setter
    def pending_messengers(self, val):
        self.obj.db.pending_messengers = val

    def unpack_oldest_pending_messenger(self, msgtuple):
        """
        A pending messenger is a tuple of several different values. We'll return values for any that we have, and
        defaults for everything else.
        Args:
            msgtuple: An iterable of values that we'll unpack.

        Returns:
            A string representing the messenger name, the Messenger object itself, any delivered object, silver,
            a tuple of crafting materials and their amount, and who this was forwarded by, if anyone.
        """
        messenger_name = "A messenger"
        msg = None
        delivered_object = None
        money = None
        mats = None
        forwarded_by = None
        try:
            import numbers

            msg = msgtuple[0]
            if msg and hasattr(msg, "id") and msg.id:
                # Very important: The Msg object is unpickled in Attributes as a Msg. It MUST be reloaded as its proxy
                msg = reload_model_as_proxy(msg)
            delivered_object = msgtuple[1]
            money_tuple = msgtuple[2]
            # check if the messenger is of old format, pre-conversion. Possible to sit in database for a long time
            if isinstance(money_tuple, numbers.Real):
                money = money_tuple
            elif money_tuple:
                money = money_tuple[0]
                if len(money_tuple) > 1:
                    mats = money_tuple[1]
                    try:
                        mats = (CraftingMaterialType.objects.get(id=mats[0]), mats[1])
                    except (CraftingMaterialType.DoesNotExist, TypeError, ValueError):
                        mats = None
            messenger_name = msgtuple[3] or "A messenger"
            forwarded_by = msgtuple[4]
        except IndexError:
            pass
        except (TypeError, AttributeError):
            import traceback

            traceback.print_exc()
            self.msg(
                "The message object was in the wrong format or deleted, possibly a result of a database error."
            )
            inform_staff("%s received a buggy messenger." % self.obj)
            return
        return msg, delivered_object, money, mats, messenger_name, forwarded_by

    def handle_delivery(self, obj, money, mats):
        """
        Handles the delivery of stuff from a Messenger to our character

            Args:
                obj (ObjectDB): Delivered object, of any typeclass
                money (float): Amount of silver
                mats (tuple): Tuple of CraftingMaterialType and amount
        """
        if obj:
            obj.move_to(self.obj, quiet=True)
            self.msg("{gYou also have received a delivery!")
            self.msg("{wYou receive{n %s." % obj)
            obj.tags.remove("in transit")
        if money and money > 0:
            self.obj.currency += money
            self.msg("{wYou receive %s silver coins.{n" % money)
        if mats:
            material, amt = mats
            dompc = self.obj.player_ob.Dominion
            try:
                mat = dompc.assets.owned_materials.get(type=material)
                mat.amount += amt
                mat.save()
            except OwnedMaterial.DoesNotExist:
                dompc.assets.owned_materials.create(type=material, amount=amt)
            self.msg("{wYou receive %s %s.{n" % (amt, material))

    def notify_of_messenger_arrival(self, messenger_name):
        """
        Let the character know they've received a messenger. If they have a discreet servant, only they're informed,
        otherwise the room will know.
        Args:
            messenger_name: Name of the messenger that is used.
        """
        discreet = self.discreet_messenger
        try:
            if discreet.location == self.obj.location:
                self.msg(
                    "%s has discreetly informed you of a message delivered by %s."
                    % (discreet, messenger_name)
                )
            else:
                discreet = None
        except AttributeError:
            discreet = None
        if not discreet:
            ignore = [
                ob
                for ob in self.obj.location.contents
                if ob.db.ignore_messenger_deliveries and ob != self.obj
            ]
            self.obj.location.msg_contents(
                "%s arrives, delivering a message to {c%s{n before departing."
                % (messenger_name, self.obj.name),
                exclude=ignore,
            )

    def get_packed_messenger(self):
        pending = self.pending_messengers
        if isinstance(pending, str):
            self.msg(
                "Your pending_messengers attribute was corrupted in the database conversion. "
                "Sorry! Ask a GM to see if they can find which messages were yours."
            )
            self.obj.db.pending_messengers = []
            return
        if not pending:
            self.msg("You have no messengers waiting to be received.")
            return
        return pending.pop()

    def receive_pending_messenger(self):
        packed = self.get_packed_messenger()
        if not packed:
            return
        # get msg object and any delivered obj
        (
            msg,
            obj,
            money,
            mats,
            messenger_name,
            forwarded_by,
        ) = self.unpack_oldest_pending_messenger(packed)
        # adds it to our list of old messages
        if msg and hasattr(msg, "id") and msg.id:
            self.add_messenger_to_history(msg)
            self.display_messenger(msg)
        else:
            from evennia.utils.logger import log_err

            self.msg("Error: The msg object no longer exists.")
            log_err(
                "%s has tried to receive a messenger that no longer exists." % self.obj
            )
        self.notify_of_messenger_arrival(messenger_name)
        # handle anything delivered
        self.handle_delivery(obj, money, mats)
        if forwarded_by:
            self.msg("{yThis message was forwarded by {c%s{n." % forwarded_by)

    def display_messenger(self, msg):
        if not msg:
            self.msg(
                "It appears this messenger was deleted already. If this appears to be an error, "
                "inform staff please."
            )
            return
        name = self.get_sender_name(msg)
        mssg = "{wSent by:{n %s\n" % name
        mssg += self.disp_entry(msg)
        self.msg(mssg, options={"box": True})

    def add_messenger_to_history(self, msg):
        """marks us as having received the message"""
        if not msg or not msg.pk:
            self.obj.msg("This messenger appears to have been deleted.")
            return
        self.obj.receiver_object_set.add(msg)
        # remove the pending message from the associated player
        player_ob = self.obj.player_ob
        player_ob.receiver_account_set.remove(msg)
        # add msg to our messenger history
        if msg not in self.messenger_history:
            self.messenger_history.insert(0, msg)
        # delete our oldest messenger that isn't marked to preserve
        self.delete_oldest_unpreserved_messenger()
        return msg

    def delete_oldest_unpreserved_messenger(self):
        qs = self.messenger_qs.exclude(q_msgtag(PRESERVE_TAG)).order_by(
            "db_date_created"
        )
        if qs.count() > 30:
            self.del_messenger(qs.first())

    def messenger_notification(self, num_times=1, force=False):
        from twisted.internet import reactor

        if self.pending_messengers:
            # send messages to our player object so even an @ooc player will see them
            player = self.obj.player_ob
            if not player or not player.is_connected:
                return
            if force or not player.db.ignore_messenger_notifications:
                player.msg(
                    "{mYou have %s messengers waiting.{n" % len(self.pending_messengers)
                )
                self.msg("(To receive a messenger, type 'receive messenger')")
                num_times -= 1
                if num_times > 0:
                    reactor.callLater(600, self.messenger_notification, num_times)
                else:
                    # after the first one, we only tell them once an hour
                    reactor.callLater(3600, self.messenger_notification, num_times)

    def send_draft_message(self):
        """
        Creates and sends a messenger with a copy of the message that our character has drafted up.
        """
        if not self.messenger_draft:
            self.msg("You have no draft message stored.")
            return
        targs, msg = self.messenger_draft
        msg = self.create_messenger(msg)
        packed = self.pack_messenger_for_delivery(msg)
        self.send_packed_messenger_to_receivers(packed, targs)
        self.messenger_draft = None

    def create_and_send_messenger(
        self, text, receivers, delivery=None, money=None, mats=None
    ):
        """
        Creates a new messenger and sends it off to our receivers
        Args:
            text: Message text to send
            receivers: List of characters to deliver to.
            delivery: Any object to deliver
            money: Money to send to each receiver
            mats: Tuple of materials to send to each receiver
        """
        messenger = self.create_messenger(text)
        self.prep_deliveries(receivers, delivery, money, mats)
        packed = self.pack_messenger_for_delivery(
            messenger, delivery=delivery, money=money, mats=mats
        )
        self.send_packed_messenger_to_receivers(packed, receivers)

    def prep_deliveries(self, receivers, delivery=None, money=None, mats=None):
        """
        Handle deliveries
        Args:
            receivers:
            delivery:
            money:
            mats:
        """
        # make delivery object unavailable while in transit, if we have one
        num = len(receivers)
        if delivery:
            delivery.location = None
            # call removal hooks
            delivery.at_after_move(self.obj)
            delivery.tags.add("in transit")
        if money:
            total = money * num
            self.obj.pay_money(total)
        if mats:
            amt = mats[1] * num
            pmats = self.obj.player.Dominion.assets.owned_materials
            pmat = pmats.get(type=mats[0])
            if pmat.amount < amt:
                raise ValueError(
                    "Attempted to send more materials than you have available."
                )
            pmat.amount -= amt
            pmat.save()

    def forward_messenger(self, receivers, messenger):
        """
        Forwards a messenger to the list of receivers
        Args:
            receivers: List of Characters for our forwarded Messenger
            messenger: Messenger object to be forwarded
        """
        packed = self.pack_messenger_for_delivery(
            messenger, delivery=None, money=None, mats=None, forwarder=self.obj
        )
        self.send_packed_messenger_to_receivers(packed, receivers)

    def send_packed_messenger_to_receivers(self, packed, receivers):
        """
        Sends our packed messenger off to our receivers. The first receiver gets any deliveries,
        then it's stripped out for the rest of them.
        Args:
            packed: tuple of packed data - the messenger, deliveries, and notifications
            receivers: List of Characters
        """
        # only the first receiver gets the whole package
        receivers[0].messages.add_packed_pending_messenger(packed)
        # now send the stripped version to remaining receivers
        stripped = self.strip_deliveries_from_packed(packed)
        for targ in receivers[1:]:
            targ.messages.add_packed_pending_messenger(stripped)
        # Show what we sent. Use initial package to show what was delivered
        self.display_sent_messenger_report(packed, receivers)
        # Mark player as having done something that is RP, so they're not inactive
        self.obj.posecount += 1

    @property
    def no_messenger_preview(self):
        return self.obj.player_ob.db.nomessengerpreview

    def display_sent_messenger_report(self, packed_messenger, receivers):
        """
        Gives feedback to our character after they've sent off messenger
        Args:
            packed_messenger: This is a tuple of a messenger with any deliveries. If we have multiple receivers,
                any delivery is only sent to the first receiver.
            receivers: List of Character receivers.
        """
        m_name = self.custom_messenger
        names = ", ".join(ob.key for ob in receivers)
        messenger = packed_messenger[0]
        delivery = packed_messenger[1]
        money = packed_messenger[2][0]
        mats = packed_messenger[2][1]
        if self.no_messenger_preview:
            self.msg("You dispatch %s to {c%s{n." % (m_name or "a messenger", names))
        else:
            self.msg(
                "You dispatch %s to {c%s{n with the following message:\n\n'%s'\n"
                % (m_name or "a messenger", names, messenger.db_message)
            )
        deliver_str = m_name or "Your messenger"
        if delivery:
            self.msg("%s will also deliver %s." % (deliver_str, delivery))
        if money:
            self.msg("%s will also deliver %s silver." % (deliver_str, money))
        if mats:
            mat = CraftingMaterialType.objects.get(id=mats[0])
            self.msg("%s will also deliver %s %s." % (deliver_str, mats[1], mat))

    def pack_messenger_for_delivery(
        self, messenger, delivery=None, money=None, mats=None, forwarder=None
    ):
        """
        Gets a list that will be used for serializing into a receiver's list of pending messengers.
        Args:
            messenger: Messenger object that is being sent
            delivery: Object to be delivered, if any
            money: Silver to be sent, if any
            mats: Tuple of ID of CraftingMaterialType and integer amount, if any
            forwarder: Character object who forwarded the mail, if any

        Returns:
            Tuple of the above values with also the name of our custom messenger, if any
        """
        return [messenger, delivery, (money, mats), self.custom_messenger, forwarder]

    @staticmethod
    def strip_deliveries_from_packed(packed):
        """
        Gets a packed messenger/delivery object and strips out any object delivery from it, which is only
        given to the first receiver.
        Args:
            packed: A packed messenger list

        Returns:
            A new list without an object delivery.
        """
        packed = list(packed)
        packed[1] = None
        return packed

    @property
    def custom_messenger(self):
        return self.obj.item_data.custom_messenger

    @custom_messenger.setter
    def custom_messenger(self, val):
        if not val:
            del self.obj.item_data.custom_messenger
            self.msg(
                "You will no longer have a custom messenger deliver messages for you."
            )
            return
        self.obj.item_data.custom_messenger = val
        self.msg("You will now have %s act as your messenger." % val)

    def add_packed_pending_messenger(self, packed_messenger):
        """
        Adds a tuple of a messenger with deliveries and other flags to our list of pending messengers.
        Args:
            packed_messenger: tuple of Messenger, delivery object, money, materials, and forwarding character.
        """
        # cast to new list so that different Attributes don't share a reference to the same list
        self.pending_messengers.insert(0, list(packed_messenger))
        packed_messenger[0].add_receiver(self.obj)
        self.messenger_notification(2)
