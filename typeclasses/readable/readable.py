"""
Readable/Writable objects
"""

from typeclasses.objects import Object
from evennia import CmdSet
from server.utils.arx_utils import ArxCommand
from world.templates.mixins import TemplateMixins


class Readable(Object):
    """
    Class for objects that can be written/named
    """

    def at_object_creation(self):
        """
        Run at Place creation.
        """
        self.db.written = False
        self.desc = "Nothing has been written on this yet. '{whelp write{n'"
        self.db.num_instances = 1
        self.db.can_stack = True
        self.db.do_not_format_desc = True
        self.db.destroyable = True
        self.at_init()
        
    def at_after_move(self, source_location):
        if self.db.num_instances > 1 and not self.db.written:
            self.setup_multiname()
        location = self.location
        # first, remove ourself from the source location's places, if it exists
        if source_location and source_location.is_room:
            if source_location.db.places and self in source_location.db.places:
                source_location.db.places.remove(self)
        # if location is a room, add cmdset
        if location and location.is_character:
            if self.db.written:
                self.cmdset.add_default(SignCmdSet, permanent=True)
            else:
                self.cmdset.add_default(WriteCmdSet, permanent=True)  
        else:
            self.cmdset.delete_default()

    def return_appearance(self, *args, **kwargs):
        msg = Object.return_appearance(self, *args, **kwargs)
        if self.db.signed and not self.db.can_stack:
            sigs = ", ".join(str(ob) for ob in self.db.signed)
            msg += "\nSigned by: %s" % sigs
        return msg

    # noinspection PyAttributeOutsideInit
    def setup_multiname(self):
        if self.db.num_instances > 1:
            self.key = "%s books" % self.db.num_instances
            self.save()
        else:
            self.key = "a book"

    def set_num(self, value):
        self.db.num_instances = value
        self.setup_multiname()


class WriteCmdSet(CmdSet):
    key = "WriteCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        """Init the cmdset"""
        self.add(CmdWrite())


class SignCmdSet(CmdSet):
    key = "SignCmd"
    priority = 0
    duplicates = True

    def at_cmdset_creation(self):
        self.add(CmdSign())


class CmdSign(ArxCommand):
    """
    Signs a document

    Usage:
        sign

    Places your signature on a document.
    """
    key = "sign"
    locks = "cmd:all()"

    def func(self):
        caller = self.caller
        obj = self.obj
        sigs = obj.db.signed or []
        if caller in sigs:
            caller.msg("You already signed this document.")
            return
        sigs.append(caller)
        caller.msg("You sign your name on %s." % obj.name)
        obj.db.signed = sigs
        return


class CmdWrite(ArxCommand, TemplateMixins):
    """
    Write upon a scroll/book/letter.
    
    Usage:
        write <description>
        write/title <title>
        write/proof
        write/translated_text <language>=<text>
        write/finish

    Writes upon a given scroll/letter/book or other object
    to give it a description set to the body of the text you
    write and set its name to the title you specify. For example,
    to rename 'a scroll' into 'Furen's Book of Wisdom', use
    'write/title Furen's Book of Wisdom'. To write in other languages,
    use /translated_text to show what the material actually says. 
    Check your changes with /proof, and then finalize changes with /finish. 
    Once set, no further changes can be made.
    """
    key = "write"
    locks = "cmd:all()"

    def display(self):
        obj = self.obj
        title = obj.ndb.title or obj.name
        desc = obj.ndb.desc or obj.desc
        msg = "{wName:{n %s\n" % title
        msg += "{wDesc:{n\n%s" % desc
        transtext = obj.ndb.transtext or {}
        for lang in transtext:
            msg += "\n{wWritten in {c%s:{n\n%s\n" % (lang.capitalize(), transtext[lang])
        return msg
        
    def func(self):
        """Look for object in inventory that matches args to wear"""
        caller = self.caller
        obj = self.obj

        if not self.args and not self.switches:
            self.switches.append("proof")
        if not self.switches or 'desc' in self.switches:
            if not self.can_apply_templates(caller, self.args):
                return
            obj.ndb.desc = self.args
            caller.msg("Desc set to:\n%s" % self.args)
            return
        if "title" in self.switches:
            obj.ndb.title = self.args
            caller.msg("Name set to: %s" % self.args)
            return
        if "translated_text" in self.switches:
            transtext = obj.ndb.transtext or {}
            if not self.rhs:
                self.msg("Must have text.")
            lhs = self.lhs.lower()
            if lhs not in self.caller.languages.known_languages:
                self.msg("You cannot speak that language.")
                return
            transtext[lhs] = self.rhs
            obj.ndb.transtext = transtext
            self.msg(self.display())
            return
        if "proof" in self.switches:
            msg = self.display()
            caller.msg(msg, options={'box': True})
            return
        if "finish" in self.switches:
            name = obj.ndb.title
            desc = obj.ndb.desc
            if not name:
                caller.msg("Still needs a title set.")
                return
            if not desc:
                caller.msg("Still needs a description set.")
                return
            if obj.db.num_instances > 1:
                from evennia.utils.create import create_object
                remain = obj.db.num_instances - 1
                newobj = create_object(typeclass="typeclasses.readable.readable.Readable",
                                       key='book', location=caller, home=caller)
                newobj.set_num(remain)
            obj.db.num_instances = 1
            obj.name = name
            obj.desc = desc
            if obj.ndb.transtext:
                obj.db.translation = obj.ndb.transtext
            obj.save()
            
            self.apply_templates_to(obj)

            caller.msg("You have written on %s." % obj.name)
            obj.attributes.remove("quality_level")
            obj.attributes.remove("can_stack")
            obj.db.author = caller
            obj.db.written = True
            obj.cmdset.delete_default()
            obj.cmdset.add_default(SignCmdSet, permanent=True)
            obj.aliases.add("book")

            return
        caller.msg("Unrecognized syntax for write.")
