"""
Commands that are available from the connect screen.
"""
from django.conf import settings
from evennia.accounts.models import AccountDB
from evennia.server.models import ServerConfig

from evennia.utils import create, utils, ansi
from commands.base import ArxCommand
from dns.resolver import query, NXDOMAIN


MULTISESSION_MODE = settings.MULTISESSION_MODE
CONNECTION_SCREEN_MODULE = settings.CONNECTION_SCREEN_MODULE
CONNECTION_SCREEN = ""
try:
    CONNECTION_SCREEN = ansi.parse_ansi(utils.string_from_module(CONNECTION_SCREEN_MODULE))
except (AttributeError, TypeError, ValueError):
    pass
if not CONNECTION_SCREEN:
    CONNECTION_SCREEN = "\nEvennia: Error in CONNECTION_SCREEN MODULE (randomly picked connection screen " \
                        "variable is not a string). \nEnter 'help' for aid."

GUEST = "typeclasses.guest.Guest"


class CmdGuestConnect(ArxCommand):
    """
    Logs in a guest character to the game.

    Will search for available already created guests to
    see if any are not currently logged in. If one is available,
    log in the player as that guest. If none are available,
    create a new guest account.
    """
    key = "guest"

    def dc_session(self, msg):
        session = self.caller
        session.msg(msg)
        session.sessionhandler.disconnect(session, "Good bye! Disconnecting.")

    def func(self):
        """
        Guest is a child of Player typeclass.
        """
        session = self.caller
        num_guests = 1
        playerlist = AccountDB.objects.typeclass_search(GUEST)
        guest = None
        bans = ServerConfig.objects.conf("server_bans")
        addr = session.address
        if bans and (any(tup[2].match(session.address) for tup in bans if tup[2])):
            # this is a banned IP or name!
            string = "{rYou have been banned and cannot continue from here." \
                     "\nIf you feel this ban is in error, please email an admin.{x"
            self.dc_session(string)
            return
        try:
            check_vpn = settings.CHECK_VPN
        except AttributeError:
            check_vpn = False
        if check_vpn:
            # check if IP is in our whitelist
            white_list = ServerConfig.objects.conf("white_list") or []
            if addr not in white_list:
                qname = addr[::-1] + "." + str(settings.TELNET_PORTS[0]) + "." + settings.TELNET_INTERFACES[0][::-1]
                try:
                    query(qname)
                    msg = "Guest connections from TOR are not permitted, sorry."
                    self.dc_session(msg)
                    return
                except NXDOMAIN:
                    # not inside TOR
                    pass
                import json
                from urllib2 import urlopen
                api_key = getattr(settings, 'HOST_BLOCKER_API_KEY', "")
                request = "http://tools.xioax.com/networking/v2/json/%s/%s" % (addr, api_key)
                try:
                    data = json.load(urlopen(request))
                    print("Returned from xiaox: %s" % str(data))
                    if data['host-ip']:
                        self.dc_session("Guest connections from VPNs are not permitted, sorry.")
                        return
                    # the address was safe, add it to our white_list
                    white_list.append(addr)
                    ServerConfig.objects.conf('white_list', white_list)
                except Exception as err:
                    import traceback
                    traceback.print_exc()
                    print('Error code on trying to check VPN:', err)
        for pc in playerlist:
            if pc.is_guest():
                # add session check just to be absolutely sure we don't connect to a guest in-use
                if pc.is_connected or pc.sessions.all():
                    num_guests += 1
                else:
                    guest = pc
                    break
        # create a new guest account        
        if not guest:
            session.msg("All guests in use, creating a new one.")
            key = "Guest" + str(num_guests)
            playerlist = [ob.key for ob in playerlist]
            while key in playerlist:
                num_guests += 1
                key = "Guest" + str(num_guests)
                # maximum loop check just in case
                if num_guests > 5000:
                    break
            guest = create.create_account(key, "guest@guest.com", "DefaultGuestPassword",
                                          typeclass=GUEST,
                                          is_superuser=False,
                                          locks=None, permissions="Guests", report_to=session)
        # now connect the player to the guest account
        session.msg("Logging in as %s" % guest.key)
        session.sessionhandler.login(session, guest)


class CmdUnconnectedHelp(ArxCommand):
    """
    This is an unconnected version of the help command,
    for simplicity. It shows a pane of info.
    """
    key = "help"
    aliases = ["h", "?"]
    locks = "cmd:all()"

    def func(self):
        """Shows help"""

        string = \
            """
You are not yet logged into the game. Commands available at this point:
  {wconnect, guest, look, help, quit{n

To login to the system, you need to do one of the following:

{w1){n If you have no previous account, you must log in as a guest.

     {wguest{n

     Guests automatically are placed in a guest channel where you can
     ask for help by typing {wguest <message>{n. You can then apply
     to play an existing character on the {w@roster{n, or create a
     new character with the {w@charcreate{n command. If your application
     is approved, an email will be sent to you with your password.

{w2){n If you have an account already, use the 'connect' command:

     {wconnect Anna c67jHL8p{n

     if your password was c67jHL8p. If you just created or applied
     for a character, your password is sent to the email you used
     to apply.

   This should log you in. Run {whelp{n again once you're logged in
   to get more aid. Hope you enjoy your stay!

You can use the {wlook{n command if you want to see the connect screen again.
"""
        self.caller.msg(string)
