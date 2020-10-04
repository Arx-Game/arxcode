"""
Input functions

Input functions are always called from the client (they handle server
input, hence the name).

This module is loaded by being included in the
`settings.INPUT_FUNC_MODULES` tuple.

All *global functions* included in this module are considered
input-handler functions and can be called by the client to handle
input.

An input function must have the following call signature:

    cmdname(session, *args, **kwargs)

Where session will be the active session and *args, **kwargs are extra
incoming arguments and keyword properties.

A special command is the "default" command, which is will be called
when no other cmdname matches. It also receives the non-found cmdname
as argument.

    default(session, cmdname, *args, **kwargs)

"""

from evennia.commands.cmdhandler import cmdhandler
from evennia.server.inputfuncs import _IDLE_COMMAND

# All global functions are inputfuncs available to process inputs


def json(session, *args, **kwargs):
    """
    Main cmd input from the client. This mimics the way text is handled to work
    with legacy string implementation.
    Args:
        cmd (str): First arg is used as text-command input. Other
            arguments are ignored.
    Kwargs:
        opts (dict): Holds all of the switch/arg/param in json format.
    """

    cmd = args[0] if args else None

    # explicitly check for None since cmd can be an empty string, which is
    # also valid
    if cmd is None:
        return
    # this is treated as a command input
    # handle the 'idle' command
    if cmd.strip() in _IDLE_COMMAND:
        session.update_session_counters(idle=True)
        return
    if session.player:
        # nick replacement
        puppet = session.puppet
        if puppet:
            cmd = puppet.nicks.nickreplace(
                cmd, categories=("inputline", "channel"), include_player=True
            )
        else:
            cmd = session.player.nicks.nickreplace(
                cmd, categories=("inputline", "channel"), include_player=False
            )

    kwargs["json"] = True
    cmdhandler(session, cmd, callertype="session", session=session, **kwargs)
    session.update_session_counters()
