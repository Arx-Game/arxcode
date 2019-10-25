"""
Guest (OOC) commands. These are stored on the Player object
and self.caller is thus always a Player, not an Object/Character.

These commands will be used to implement a character creation
setup based on look and entered prompts.

To-Do list - have character creator prompt for email address at the
start of character creation to save the character-in progress. Iteratively
create the character on the roster, filling in incomplete fields by the player
jumping around to them.

"""
import copy
import traceback

from django.conf import settings
from evennia import syscmdkeys
from evennia.accounts.models import AccountDB
from evennia.utils import utils, create, search
from six import string_types
from unidecode import unidecode

from commands.base import ArxPlayerCommand
from server.utils.arx_utils import inform_staff, check_break
from world.stats_and_skills import (get_partial_match, get_skill_cost,
                                    CRAFTING_ABILITIES, VALID_SKILLS,
                                    VALID_STATS, )

# limit symbol import for API
__all__ = ("CmdGuestLook", "CmdGuestCharCreate", "CmdGuestPrompt", "CmdGuestAddInput", "census_of_fealty",
           "setup_voc")
CMD_NOINPUT = syscmdkeys.CMD_NOINPUT
CMD_NOMATCH = syscmdkeys.CMD_NOMATCH
_vocations_ = ("noble", "courtier", "charlatan", "soldier", "knight", "priest", "merchant",
               "criminal", "artisan", "scholar", "lawyer", "steward", "commoner",
               "jeweler", "tailor", "weaponsmith", "armorsmith", "leatherworker",
               "apothecary", "carpenter")
_stage3_fields_ = ("concept", "gender", "age", "fealty", "family", "religion", "desc", "personality", "background",
                   "marital_status", "quote", "birthday", "social_rank", "skintone", "eyecolor", "haircolor", "height")
_valid_fealty_ = ("Crownsworn", "Grayson", "Redrain", "Thrax", "Valardin", "Velenosa")
_stage3_optional_ = ("real_concept", "real_age")
# Minimum and maximum ages players can set for starting characters
_min_age_ = 18
_max_age_ = 65
# We have 12 stats. no more than two at 5. tuple is in the following order:
# (strength,dexterity,stamina,charm,command,composure,intellect,perception,wits,mana,luck,willpower)
_voc_start_stats_ = {"noble":          (3, 3, 3,  4, 5, 4,  3, 3, 2,  2, 2, 2),
                     "courtier":       (2, 2, 2,  5, 4, 5,  3, 3, 4,  2, 2, 2),
                     "charlatan":      (2, 2, 2,  4, 3, 5,  3, 4, 4,  3, 3, 1),
                     "soldier":        (5, 4, 5,  2, 3, 4,  2, 2, 3,  2, 2, 2),
                     "knight":         (4, 4, 4,  3, 4, 4,  2, 2, 3,  2, 2, 2),
                     "priest":         (2, 2, 2,  4, 5, 4,  3, 3, 2,  3, 3, 3),
                     "merchant":       (2, 2, 2,  4, 3, 4,  3, 4, 3,  2, 3, 4),
                     "criminal":       (4, 4, 4,  3, 3, 3,  3, 3, 3,  2, 2, 2),
                     "tailor":         (2, 2, 2,  3, 3, 3,  4, 4, 4,  3, 3, 3),
                     "artisan":        (2, 2, 2,  3, 3, 3,  4, 4, 4,  3, 3, 3),
                     "weaponsmith":    (4, 4, 4,  3, 3, 3,  2, 2, 2,  3, 3, 3),
                     "armorsmith":     (4, 4, 4,  3, 3, 3,  2, 2, 2,  3, 3, 3),
                     "leatherworker":  (4, 4, 4,  3, 3, 3,  2, 2, 2,  3, 3, 3),
                     "apothecary":     (2, 2, 2,  3, 3, 3,  4, 4, 4,  3, 3, 3),
                     "carpenter":      (4, 4, 4,  3, 3, 3,  2, 2, 2,  3, 3, 3),
                     "jeweler":        (2, 2, 2,  3, 3, 3,  4, 4, 4,  3, 3, 3),
                     "scholar":        (2, 2, 2,  3, 3, 3,  5, 5, 4,  2, 2, 3),
                     "lawyer":         (2, 2, 2,  3, 3, 3,  5, 5, 4,  2, 2, 3),
                     "steward":        (3, 3, 3,  3, 3, 3,  4, 4, 4,  2, 2, 2),
                     "commoner":       (4, 3, 4,  3, 2, 3,  2, 3, 4,  2, 4, 2)}
# 20 points for skills
_voc_start_skills_ = {"noble": {"diplomacy": 3, "leadership": 3, "etiquette": 2,
                                "law": 1, "ride": 1,
                                "manipulation": 1, "empathy": 1, "war": 1},
                      "courtier": {"diplomacy": 1, "etiquette": 3, "manipulation": 2,
                                   "empathy": 2, "seduction": 3, "propaganda": 1},
                      "charlatan": {"legerdemain": 3, "manipulation": 3, "empathy": 1,
                                    "streetwise": 3, "occult": 1},
                      "soldier": {"medium wpn": 3, "brawl": 1, "dodge": 1,
                                  "archery": 1, "survival": 1},
                      "knight": {"medium wpn": 3, "dodge": 1, "war": 1, "etiquette": 1,
                                 "ride": 2, "leadership": 1},
                      "lawyer": {"law": 4, "etiquette": 1, "empathy": 2, "manipulation": 2,
                                 "teaching": 1, "investigation": 1, "linguistics": 1},
                      "priest": {"theology": 3, "occult": 2, "medicine": 3,
                                 "empathy": 1, "leadership": 1, "propaganda": 2},
                      "merchant": {"economics": 3, "streetwise": 2, "manipulation": 1,
                                   "haggling": 4, },
                      "criminal": {"stealth": 1, "streetwise": 2,
                                   "small wpn": 2, "brawl": 2, "dodge": 1, "legerdemain": 1},
                      "artisan": {"smithing": 2, "alchemy": 2, "sewing": 2, "tanning": 2, "haggling": 1,
                                  "propaganda": 1, "streetwise": 1, "teaching": 1, "woodworking": 2,
                                  "etiquette": 1},
                      "tailor": {"sewing": 4, "teaching": 2, "haggling": 1},
                      "weaponsmith": {"smithing": 4, "brawl": 1, "haggling": 1},
                      "armorsmith": {"smithing": 4, "brawl": 1, "haggling": 1},
                      "leatherworker": {"tanning": 4, "brawl": 1, "haggling": 1},
                      "apothecary": {"alchemy": 4, "teaching": 2, "haggling": 1},
                      "carpenter": {"woodworking": 4, "brawl": 1, "haggling": 1},
                      "jeweler": {"smithing": 4, "teaching": 2, "haggling": 1},
                      "scholar": {"medicine": 3, "occult": 2, "agriculture": 1, "economics": 1,
                                  "teaching": 3, "theology": 1, "law": 1, "etiquette": 1},
                      "steward": {"stewardship": 4, "economics": 1, "etiquette": 2, "law": 2,
                                  "agriculture": 2},
                      "commoner": {"streetwise": 2, "stealth": 1, "brawl": 1, "athletics": 1, "survival": 2,
                                   "investigation": 1, "dodge": 1, "occult": 1, "haggling": 1}}


def setup_voc(char, args):
    """Sets skills/stats for vocation template"""
    char.attributes.add("skill_points", get_bonus_skill_points())
    char.attributes.add("stat_points", 0)
    skills = _voc_start_skills_[args]
    stat_tup = _voc_start_stats_[args]
    x = 0
    for stat in VALID_STATS:
        char.attributes.add(stat, stat_tup[x])
        x += 1
    char.attributes.add("skills", copy.deepcopy(skills))
    char.db.abilities = {}
    # if their vocation is a crafter, give them a starting rank of 2
    if args in CRAFTING_ABILITIES:
        char.db.abilities = {args: 3}


def get_total_skill_points():
    return SKILL_POINTS + get_bonus_skill_points()


def get_bonus_skill_points():
    from evennia.server.models import ServerConfig
    return ServerConfig.objects.conf("CHARGEN_BONUS_SKILL_POINTS", default=0)


STAT_POINTS = 12
SKILL_POINTS = 20
CONCEPT_MAX_LEN = 30
DESC_MIN_LEN = 300
DESC_MAX_LEN = 1400

XP_BONUS_BY_SRANK = {2: 0,
                     3: 20,
                     4: 40,
                     5: 60,
                     6: 80,
                     7: 120,
                     8: 160,
                     9: 200,
                     }

XP_BONUS_BY_POP = 1


def census_of_fealty():
    """Returns dict of fealty name to number of active players"""
    fealties = {"Valardin": 0, "Velenosa": 0, "Grayson": 0, "Crownsworn": 0, "Thrax": 0, "Redrain": 0}
    from typeclasses.characters import Character
    for char in Character.objects.filter(roster__roster__name="Active"):
        fealty = (char.db.fealty or "").capitalize()
        if fealty in fealties:
            fealties[fealty] += 1
    from collections import OrderedDict
    # return an OrderedDict of lowest to highest population of fealites
    return OrderedDict(sorted(fealties.items(), key=lambda k: k[1]))


def award_bonus_by_fealty(fealty):
    """Awards bonus xp based on fealty population - less populated gets a bonus"""
    census = census_of_fealty()
    max_pop = census[census.keys()[-1]]
    try:
        fealty = fealty.capitalize()
        bonus = XP_BONUS_BY_POP * (max_pop - census[fealty])
    except (KeyError, AttributeError):
        bonus = 0
    return bonus


def award_bonus_by_age(age):
    """Awards bonus xp for older characters"""
    try:
        bonus = (age - 15)/4
        if age > 20:
            bonus += (age - 20)
        if age > 30:
            bonus += (age - 30)
        if age > 40:
            bonus += (age - 40)
        if age > 50:
            bonus += (age - 50)
        if age > 60:
            bonus += (age - 60)
    except (TypeError, ValueError):
        bonus = 0
    return bonus


STAGE0 = \
       """
Welcome to {cArx{n, a text based fantasy roleplaying game, similar in design
to many other MUSH based games. Arx is a game of intrigue and adventure,
politics and deeply woven stories, allowing players to enter the ongoing
stories with either a character from a roster of pre-generated characters
that have been a part of the story so far, or to create your own with help
and guidance to best fit into the stories we are creating here.

If you'd like to read about the current stories, or background lore and
completed roleplay, please access our help files with '{whelp{n' to browse
the different subjects. To see a list of commands available to you, use the
'{whelp{n' command. To look at the roster of available characters, use
'{w@roster{n' and '{w@sheet{n'.

To submit an application for a character on the roster that you would like
to play, you will need to supply an email address with {w@add/email <email>{n.
Then enter '{w@roster/apply{n {c<character name>{n {w={n {c<application>{n'.
Your application should contain the reason you'd like to play the character
and what you perceive as their goals and motivations and what direction you
will take their roleplay. Tell us your take on the character. How would you RP
them in a way that contributes to a positive environment and creates
collaborative, fun RP for other people?

To create a new, original character, or to resume a previous session you
were disconnected from, use '{w@charcreate {c<email>{n'. To view a board
of wanted character concepts, use '{w@bb wanted concepts{n'.

The guest channel exists to help new players with
the process of requesting or generating their characters - to speak in it,
please type '{wguest {c<message>{n'.
       """
STAGE1 = \
       """
To start with, choose a unique name for your character that consists of a
single word of only letters - no spaces, numbers, or special characters.

Although characters will typically have both family names, and some may have
titles, every character has a unique first name as an identifier for game
commands. For example, Prince Donrai Thrax would be known by his full name,
but commands such as 'look' would be executed by 'look donrai'.

To choose a name, please use {w'@add/name {c<name>'{n. Names may only consist
of letters, and should generally be between 4-12 characters in length.
       """
STAGE2 = \
       """
A vocation describes your character's occupation. A number of sample
vocations have been prepared, but you are not limited to them. You may
choose either one of the sample vocations, or create your own with
{w'@add/newvocation {c<name>'{n. To select any of the given vocations, use
{w'@add/vocation {c<name>'{n

To get more information about the listed vocations, type {w'help {c<name>'{n for
any. Each sample vocation has a pre-generated list of stats and skills,
which can be modified in a following step. Creating a new vocation will
require you to set them manually.
       """
STAGE3 = \
       """
In this step, you'll create all the details of your character's starting
story. This will let you define who they are now, what their previous
history was, and the overall character concept by defining fields on your
character {w+sheet{n. If any of the fields at all confuse you, please use
the '{whelp{n' command for greater detail.

In order to give detail about your character, you use the '{w@add{n' command
to define a field. For example, the concept field. Your character concept is
an extremely brief two or three word character concept, the most basic
pitch possible for your character. So someone wishing to play a knight
struggling with cynicism and his own past might use the '{w@add{n' command to
'{w@add/concept{n Embittered Knight'. Then they can use the '{w@add{n'
command to define why that concept is accurate for him and just what makes
the character tick by completing the other fields below.

Characters who start at a lower social rank will receive bonus xp after
character creation which they can use in any manner they choose.

To add a field '{w@add/{c<field> <value>{n' For example, '{w@add/age{n 21'
would set the character's age to 21.

If you would prefer to fill in character stats first, you may temporarily
skip this stage with '{w@add/skip{n', though the mandatory fields must be
filled in with the appropriate '{w@add{n' commands before you are able to
submit your character.
       """
STAGE4 = \
       """
You may now adjust the starting skills and stats of your character if you
wish, or submit your character for approval if you're satisfied with how
everything looks. To add or remove skills or stats, use '{wadd/stat{n' or
'{wadd/skill{n', in a format like: '{wadd/stat strength=+1{n'.
{wadd/stat luck=+1{n, {wadd/stat mana=-1{n, {wadd/skill dexterity=+1{n, etc.

To see a list of skills, enter '{whelp skills{n', with a help file of each
under '{whelp {c<skill name>{n'. Stats cost 1 point regardless of their
current rank, while skills cost 1 point per rank for non-combat skills, and
2 points per rank for combat skills. So to raise melee from 4 to 5 would
cost 10 skill points.

If you have selected one of the pre-defined vocations for a character
rather than creating a new one, all stats/skills will already be assigned,
though you may move points around as you wish. Characters of lower social
rank will still receive a bonus to XP after character creation regardless
of their chosen vocation, however.

When you are finished, use {g'add/submit {w<application>'{n to submit your
finished character. Before submission, you can still add or change fields
such as your desc, haircolor, eyecolor, etc. In place of <application>,
please tell us why you'd like to claim this character. For example:
'{w@add/submit She's awesome, and I'm awesome, so this is the
character I think I should play.{n
       """
STAGE5 = \
       """
Thank you for submitting your character. If you provided an email, then
you should receive an email response after GMs review your application.
If you didn't submit an email, GMs will send you a page/tell after they've
finished reviewing your application, providing you with the character's
password if you are approved. To log in to an approved character,
reconnect to ArxMUSH and enter '{wconnect {c<name> <password>{n' with the
name you chose for the character and the password you will be provided.
       """


def stage_title(stage):
    """Helper function for setting the title bar of a stage"""
    stage_txt = ("Name", "Vocation", "Character Design and Details",
                 "Stats and Skills", "All Done: Thank You!")
    stage_cmd = ("{w@add/name <character name>{n", "{w@add/vocation <character's vocation>{n",
                 "{w@add/<field name> <value>", "{w@add/<stat or skill> <stat or skill name>=<+ or -><new value>{n",
                 "{w@add/submit <application notes>")
    msg = "{wStep %s: %s" % (stage, stage_txt[stage - 1])
    msg += "\n%s" % (stage_cmd[stage - 1])
    return msg


class CmdGuestPrompt(ArxPlayerCommand):
    """
    This is activated when the text entered by the guest doesn't
    match the other existing commands. If  the tutorial is expecting
    input, based on guest.db.prompt, then we process the result with
    the arguments. If not, then it's a normal mismatch and we should
    provide a guest-specific help text.
    """
    key = CMD_NOMATCH
    locks = "cmd:all()"
    auto_help = False

    def func(self):
        """"Execute the command"""
        caller = self.caller
        caller.msg(utils.fill("%rInvalid command. To see a list of valid commands, " +
                              "please type '{whelp{n'. To ask for assistance, please " +
                              "type '{wguest{n <message>'. To see the current menu, " +
                              "please type '{wlook{n'. To add a field to a character you " +
                              "are creating, please use the '{w@add{n' command."))
        return


class CmdGuestLook(ArxPlayerCommand):
    """
    ooc look

    Usage:
      look

    Look in the ooc state.
    """

    # This command will be used for the character creation
    # tutorial. The initial state will be our beginning help
    # window to guide the player through the process, step by
    # step.

    key = "look"
    aliases = ["l", "ls"]
    locks = "cmd:all()"
    help_category = "General"

    def func(self):
        """"implement the ooc look command"""
        caller = self.caller
        stage = caller.db.tutorial_stage
        if not stage:
            stage = 0
            caller.db.tutorial_stage = 0
        char = caller.db.char
        if stage == 0:
            caller.msg(STAGE0)
            return
        if stage == 1:
            caller.msg(stage_title(stage))
            if not caller.ndb.seen_stage1_intro:
                caller.msg(STAGE1)
                caller.ndb.seen_stage1_intro = True
            else:
                caller.msg("To choose a name, please use {w'@add/name <name>'{n. Names may only consist " +
                           "of letters, and should generally be between 4-12 characters in length.")
            return
        if stage == 2:
            caller.msg(stage_title(stage))
            if not caller.ndb.seen_stage2_intro:
                caller.msg(STAGE2)
                caller.ndb.seen_stage2_intro = True
            vocs = [item.capitalize() for item in _vocations_]
            vocs = ", ".join(vocs)
            caller.msg("Sample vocations: {w%s{n" % vocs)
            caller.msg("Please {w@add/vocation{n one of the above vocations, for example:\n" +
                       "{w@add/vocation soldier{n\n" +
                       "Or create a new one with {w@add/newvocation{n, for example:\n" +
                       "{w@add/newvocation farmer{n\n")
            caller.msg("To see the progress of your character, type '{w@sheet{n'.")
            return
        if stage == 3:
            caller.msg(stage_title(stage))
            if not caller.ndb.seen_stage3_intro:
                caller.msg(STAGE3)
                caller.ndb.seen_stage3_intro = True
            unfinished = char.db.unfinished_values
            if not unfinished:
                def_txt = ", ".join(list(_stage3_fields_))
                caller.msg("Your @sheet has completed: {w%s{n" % def_txt)
                def_txt = ", ".join(list(_stage3_optional_))
                caller.msg("Optional fields that can be changed with @add if you wish: {w%s{n" % def_txt)
                caller.db.tutorial_stage = 4
                char.player_ob.db.tutorial_stage = caller.db.tutorial_stage
                caller.execute_cmd("look")
                return
            caller.msg("\nTo add a field, '{w@add/<field> <value>'{n. For example,\n" +
                       "{w@add/concept Surly Assassin{n would add your character's concept.\n")
            def_txt = set(_stage3_fields_) - set(unfinished)
            def_txt = ", ".join(list(def_txt))
            if def_txt:
                caller.msg("Your @sheet has completed: {w%s{n" % def_txt)
            unfinished = ", ".join(list(unfinished))
            optional = ", ".join(list(_stage3_optional_))
            caller.msg("%s still needs to '{w@add{n' the following fields: {w%s{n" % (char.key.capitalize(),
                                                                                      unfinished))
            caller.msg("%s can also add these optional fields: {w%s{n" % (char.key.capitalize(), optional))
            mssg = "For clarification on any field and an explanation for just what a field means,"
            mssg += " type '{whelp character{n' for a list of the fields, and '{whelp <field name>{n'"
            mssg += " for a detailed explanation on what a field means for your character."
            caller.msg(mssg)
            return
        if stage == 4:
            caller.msg(stage_title(stage))
            if char.db.skills is None:
                char.db.skills = {}
            if char.db.abilities is None:
                char.db.abilities = {}
            if not caller.ndb.seen_stage4_intro:
                caller.msg(STAGE4)
                caller.ndb.seen_stage4_intro = True
                caller.msg("To see the progress of your character, type '{w@sheet{n'.")
            if char:
                skill_pts = char.db.skill_points
                stat_pts = char.db.stat_points
                if not skill_pts:
                    skill_pts = 0
                if not stat_pts:
                    stat_pts = 0
                caller.msg("\nYou have {w%s{n stat points and {w%s{n skill points to spend." % (stat_pts, skill_pts))
                stat_str = "{wCurrent stats:{n "
                for stat in VALID_STATS:
                    val = char.attributes.get(stat)
                    if not val:
                        val = 0
                    stat_str += "{c" + stat + "{n: {w" + str(val) + "{n\t"
                caller.msg(stat_str)
                skill_str = "{wCurrent skills:{n "
                for skill in sorted(char.db.skills):
                    skill_str += " {c" + skill + "{n: {w" + str(char.db.skills[skill]) + "{n\t"
                caller.msg(skill_str)
                caller.msg("""
To see a list of skills, enter '{whelp skills{n', with a description of each
under '{whelp {c<skill name>{n'. Stats cost 1 point regardless of their current
rank, while skills cost 1 point per rank for non-combat skills, and 2
points per rank for combat skills. So to raise melee from 4 to 5 would
cost 10 skill points.""")
                caller.msg("Please use {w@add/stat{n or {w@add/skill{n to change any stat or skill, " +
                           "or {w@add/submit <any notes you wish to add about your application>{n " +
                           "to finish.")
                caller.msg("Examples: '{w@add/stat strength=+1{n', {w@add/skill dodge=-1{n'")
            return
        if stage == 5:
            caller.msg(stage_title(stage))
            caller.msg(STAGE5)
            return


class CmdGuestCharCreate(ArxPlayerCommand):
    """
    Starts or resumes the character creation process

    Usage:
      @charcreate <email address>

    Starts or resumes the character creation process corresponding
    with the given email. The email address you provide is very
    important - it will be used for sending you your password if
    your application is approved, and if you decide to quit during
    the character creation process, you can resume it by using the
    same email address the next time you log in.
    """
    key = "@charcreate"
    locks = "cmd:all()"
    help_category = "General"

    def func(self):
        """"create the new character"""
        player = self.caller
        new_character = None
        # see if we've already defined email with @add/email
        email = player.ndb.email or self.lhs.lower()
        if not utils.validate_email_address(email):
            self.msg("\n{w@charcreate{n expects an email address to be entered with it. " +
                     "This allows you to resume a previous unfinished character by " +
                     "entering the same email address, and for your character to be " +
                     "approved while offline, with the password emailed to the address " +
                     "provided.")
            return
        if check_break(player, checking_character_creation=True):
            self.msg("Staff are currently on break, and making original characters has been disabled until the "
                     "break ends. You can still apply to play roster characters until that time, or wait until "
                     "the break is over.")
            return
        # we check email address to see if it matches an existing unfinished character
        from web.character.models import RosterEntry
        try:
            try:
                entry = RosterEntry.objects.get(roster__name="Incomplete",
                                                player__email=email)
                self.msg("{wFound an unfinished character with the provided email address. "
                         "Resuming that session.{n")
            except RosterEntry.MultipleObjectsReturned:
                entries = RosterEntry.objects.filter(roster__name="Incomplete",
                                                     player__email=email).order_by('player__date_joined')
                if not self.rhs:
                    self.msg("Found %s incomplete characters with that email address." % entries.count())
                    self.msg("Please @charcreate <email>=<number> to selection one, where <number> is "
                             "a number from 1 to %s, where 1 is the oldest character." % entries.count())
                    return
                try:
                    index = int(self.rhs) - 1
                    entry = entries[index]
                except (ValueError, TypeError, IndexError):
                    self.msg("Please select a number from 1 to "
                             "%s, where 1 is the oldest character." % entries.count())
                    return
                self.msg("Choosing entry number %s out of the ones for that email." % index)
            new_character = entry.character
            stage = new_character.player_ob.db.tutorial_stage
            if not stage:
                stage = 1
            player.db.char = new_character
            player.db.tutorial_stage = stage
            player.ndb.email = email
            player.execute_cmd("look")
            return
        except RosterEntry.DoesNotExist:
            self.msg("No existing incomplete character found with that email.")
        if not new_character:
            # create the character
            try:
                from evennia.objects.models import ObjectDB

                default_home = ObjectDB.objects.get_id(settings.DEFAULT_HOME)
                typeclass = settings.BASE_CHARACTER_TYPECLASS
                permissions = settings.PERMISSION_ACCOUNT_DEFAULT
                # Some placeholder values for utils.create, will be overwritten later
                playername = email+'_player'
                # Make sure the playername is unique
                num_tries = 0
                while search.search_account(playername):
                    num_tries += 1
                    playername += str(num_tries)
                password = email+'_default_password'
                new_player = create.create_account(playername, email, password, permissions=permissions)
                new_character = create.create_object(typeclass, key=email,
                                                     location=default_home,
                                                     home=default_home,
                                                     permissions=permissions)
                # only allow creator (and immortals) to puppet this char
                new_character.locks.add("puppet:id(%i) or pid(%i) or perm(Immortals) or pperm(Immortals)" %
                                        (new_character.id, new_player.id))
                # noinspection PyProtectedMember
                new_player.db._playable_characters.append(new_character)
                new_player.db._last_puppet = new_character
                # this is redundant, but shows up a few times in code, so just setting both
                new_player.email = email
                new_player.save()
                new_character.desc = "Description to be set later."
                new_character.db.unfinished_values = set(_stage3_fields_)
                # so they don't show up in Arx City Center during character creation
                new_character.db.prelogout_location = new_character.location
                new_character.location = None
                new_character.save()
                try:
                    from web.character.models import Roster
                    incom = Roster.objects.incomplete
                    incom.entries.create(character=new_character, player=new_player)
                except Exception as err:
                    print("Error in adding character to roster for guest: %s" % err)
                    traceback.print_exc()
            except Exception as err:
                print("Error in creating a character/player combination for guest: %s" % err)
                player.msg("Something went wrong during the character/player startup process." +
                           " Please tell an admin to look into it.")
                traceback.print_exc()
                return
            player.db.char = new_character
            player.db.tutorial_stage = 1
            player.msg("Email address set to %s." % email)
            player.ndb.email = email
            intro = """
Welcome to character creation. The character creation process will be
a series of prompts asking you to enter values, for which you will use
the 'add' command. The '{w@add{n' command is executed by adding a '/' after
it with the name of the field you wish to modify, followed by an argument.
For example, to set your character's {cname{n, you might enter
        {w@add/name Alarice{n
for a character named Alarice.
        """
            player.msg(intro)
            player.execute_cmd("look")


class CmdGuestAddInput(ArxPlayerCommand):
    """
    Adding input into the character creator

    Usage:
      @add/<switches> <text input>

    Fills in a field at a given prompt with all input following '@add'.
    Old fields can be filled out with various switches. For example, to
    add your email address, you might enter:
        @add/email leona.manly@teemocorps.net
    """

    key = "@add"
    aliases = ["add", "+add"]
    locks = "cmd:all()"
    help_category = "General"

    @staticmethod
    def do_stage_1(caller, args):
        """Sets the name for the character in stage 1"""
        char = caller.db.char
        if not args:
            caller.msg("Enter a unique first name for your character with the '{w@add/name{n' command.\n" +
                       "Ex: {w@add/name Robert{n")
            return
        # check to see if name is taken
        # sanity checks
        playername = args.lower()
        if not playername.isalpha() or not (0 < len(playername) <= 30):
            # this echoes the restrictions made by django's auth
            # module (except not allowing spaces, for convenience of
            # logging in).
            string = "\n\r Playername can max be 30 characters or fewer."
            string += " Only letters, no numbers or special characters."
            caller.msg(string)
            return
        # strip excessive spaces in playername
        if AccountDB.objects.filter(username__iexact=playername).exclude(id=char.player_ob.id):
            # player already exists (we also ignore capitalization here)
            caller.msg("Sorry, there is already a player with the name '%s'." % playername)
            return
        # everything's fine, username is unique and valid
        char.player_ob.key = playername
        char.name = playername.capitalize()
        if caller.db.tutorial_stage == 1:
            caller.db.tutorial_stage += 1
            char.player_ob.db.tutorial_stage = caller.db.tutorial_stage
        caller.msg("{cName{n set to {w%s{n." % char.key)
        char.save()
        caller.execute_cmd("look")

    @staticmethod
    def do_stage_2(caller, args, switches):
        """Sets the vocation of the character in stage 2"""
        char = caller.db.char
        if not args:
            caller.msg("Enter your vocation with '{w@add/vocation <vocation name>{n'. You may either choose one " +
                       "of the vocations provided, or create one of your own with '{w@add/newvocation <vocation>{n.")
            return
        args = args.lower().strip()

        def remove_all_skills():
            """helper function to wipe skills in case we have a previous vocation set"""
            char.attributes.add("skills", {})
            char.attributes.add("abilities", {})

        if 'newvocation' in switches:
            if args in _vocations_:
                caller.msg("Selected one of the default vocations. Please use 'vocation' rather than 'newvocation.")
                return
            char.db.vocation = args
            # set up default stats/skills for a new vocation here
            remove_all_skills()
            for stat in VALID_STATS:
                char.attributes.add(stat, 2)
            char.attributes.add("skill_points", get_total_skill_points())
            char.attributes.add("stat_points", STAT_POINTS)
        elif 'vocation' in switches:
            if args not in _vocations_:
                caller.msg("Argument does not match any of the sample vocations. If you meant to create a new " +
                           "vocation, please use the '{w@add/newvocation{n' command.")
                return
            char.db.vocation = args
            # setup voc will wipe any previous skills, replace em
            setup_voc(char, args)
        caller.msg("\n{cVocation{n set to {w%s{n." % args)
        if caller.db.tutorial_stage == 2:
            caller.db.tutorial_stage += 1
            char.player_ob.db.tutorial_stage = caller.db.tutorial_stage
        caller.execute_cmd("look")
        return

    @staticmethod
    def do_stage_3(caller, args, switches):
        """Sets background attributes for the character in stage 3 - fleshing them out"""
        char = caller.db.char
        if not args:
            caller.msg("{w@add/<field>{n must have a value after a space. Examples:\n" +
                       "{w@add/gender{n, ex: {w@add/gender female{n\n" +
                       "{w@add/age{n, ex: {w@add/age 25{n\n" +
                       "{w@add/fealty{n, ex: {w@add/fealty Velenosa{n\n" +
                       "{w@add/family{n, ex: {w@add/family Whisper{n\n" +
                       "{w@add/religion{n, ex: {w@add/religion Pantheon{n\n" +
                       "{w@add/desc{n, ex: {w@add/desc A severe girl with blue eyes...{n\n" +
                       "{w@add/concept{n, ex: {w@add/concept Humorless Handmaiden{n\n" +
                       "{w@add/background{n, ex: {w@add/background She was of humble birth..." +
                       "{w@add/social_rank{n, ex: {w@add/social_rank 8")
            return
        # if switches is a list, convert it to a string
        if not isinstance(switches, string_types):
            switches = switches[0]
        if switches not in list(_stage3_fields_) + list(_stage3_optional_):
            caller.msg("{w@add/<switch>{n must be one of the following: %s" % (list(_stage3_fields_) +
                                                                               list(_stage3_optional_)))
            return
        if 'age' == switches:
            if not args.isdigit():
                caller.msg('Age must be given a number.')
                return
            args = int(args)
            if not (_min_age_ <= args <= _max_age_):
                caller.msg("Age must be between %s and %s." % (_min_age_, _max_age_))
                return
            bonus = award_bonus_by_age(args)
            msg = "For having the age of %s, you will receive %s " % (args, bonus)
            msg += "bonus xp after character creation."
            caller.msg(msg)
        if 'birthday' in switches:
            arglist = args.split("/")
            arglist = [x for x in arglist if x.isdigit()]
            if not arglist or len(arglist) != 2:
                caller.msg("Birthday should be in the form of month/day, eg: 5/27")
                return
            if not 0 < int(arglist[0]) < 13:
                caller.msg("The month of a character's birth must be between 1 to 12.")
                return
            if not 0 < int(arglist[1]) < 31:
                caller.msg("The day of a character's birth must be between 1 to 30.")
                return
        if 'fealty' in switches:
            args = args.capitalize()
            if args not in _valid_fealty_:
                fealties = ", ".join(_valid_fealty_)
                caller.msg("The argument for fealty must be one of the following: {w%s{n"
                           % fealties)
                return
            bonus = award_bonus_by_fealty(args)
            msg = "For having the fealty of %s, you will receive %s " % (args, bonus)
            msg += "bonus xp after character creation."
            caller.msg(msg)
        if 'social_rank' in switches:
            args = args.strip()
            if not args.isdigit():
                caller.msg("Social rank must be a number.")
                return
            args = int(args)
            if args < 2 or args > 9:
                caller.msg("Social rank must be between 2 and 9.")
                return
            bonus = XP_BONUS_BY_SRANK.get(args, 0)
            caller.msg("For starting at a social rank of " +
                       "%s, you will receive %s bonus experience after character creation." % (args, bonus))
        if 'personality' in switches:
            if not (DESC_MAX_LEN > len(args) > DESC_MIN_LEN):
                caller.msg("Personality length must be between %s and %s characters." % (DESC_MIN_LEN, DESC_MAX_LEN))
                caller.msg("Current length was: %s" % len(args))
                return
        if 'desc' in switches:
            # desc is no longer an attribute, so it is a special case
            if not (DESC_MAX_LEN > len(args) > DESC_MIN_LEN):
                caller.msg("Description length must be between %s and %s characters." % (DESC_MIN_LEN, DESC_MAX_LEN))
                caller.msg("Current length was: %s" % len(args))
                return
            char.desc = args
            char.save()
        else:
            char.attributes.add(switches, args)
        caller.msg("\n{c%s{n set to: {w%s{n" % (switches.capitalize(), args))
        # check off the list of stage 4 values left to define
        unfinished_values = char.attributes.get('unfinished_values')
        if unfinished_values:
            unfinished_values.discard(switches)
        if unfinished_values:
            char.attributes.add('unfinished_values', unfinished_values)
            unfinished_values = ", ".join(list(unfinished_values))
            caller.msg("%s still has to '{w@add{n': {w%s{n" % (char.key.capitalize(), unfinished_values))
            caller.msg("Can also add optional fields: {w%s{n" % ", ".join(option for option in list(_stage3_optional_)))
            return
        else:  # all done
            caller.msg("All background values are now defined.")
            caller.msg("You may still add optional fields: {w%s{n" % ", ".join(option for option in
                                                                               list(_stage3_optional_)))
            if caller.db.tutorial_stage == 3:
                caller.db.tutorial_stage += 1
                char.player_ob.db.tutorial_stage = caller.db.tutorial_stage
            caller.execute_cmd("look")
        return

    @staticmethod
    def do_stage_4(caller, args, switches, lhs, rhs):
        """Set stats/skills in stage 4"""
        char = caller.db.char
        if not args:
            caller.msg("Add or remove stats/skills by {w@add/[stat or skill] <statname>=<+ or -><value>{n")
            return
        if not rhs or not lhs:
            caller.msg(utils.fill("%rThe syntax for adding or removing skills requires an '='" +
                                  " between the stat or skill" +
                                  "you are adjusting and the value you are changing it by. For example:" +
                                  "%r%r%t%t{w@add/stat strength=+1{n%r%r would raise your character's strength " +
                                  "score by 1, provided you have the available points to do so, and it " +
                                  "does not take the stat over its maximum value."))
            return
        lhs = lhs.strip().lower()
        try:
            val = int(rhs)
        except ValueError:
            caller.msg("The value you give after the '=' must be a positive or negative number.")
            return

        def check_points(character, arguments, value, category):
            """helper function to see if we can add or remove the points"""
            if char.db.skills is None:
                char.db.skills = {}
            if not (category == "skill" or category == "stat"):
                character.msg("Error: Invalid category for check_points. 'stat' or 'skill' expected.")
                return False
            if value == 0:
                character.msg("Please enter a value other than 0 when adding or removing points.")
                return False
            # check if we have enough points for the operation
            avail_pts = char.attributes.get(category + "_points")
            if not avail_pts:
                avail_pts = 0
            if category == "stat":
                cost = value
            else:
                # xp values are 10 times higher than skill points, so we must convert.
                cost = get_skill_cost(char, arguments, adjust_value=value, check_teacher=False, unmodified=True)
                cost /= 10
            if cost > avail_pts:
                character.msg("You do not have enough available %s points. Remove points from a %s first." % (category,
                                                                                                              category))
                return False
            # check the current value of the stat we want to modify, see if it'll be within allowed bounds
            # stats have a minimum of 1, skills have a minimum of 0
            if category == 'stat':
                current_val = char.attributes.get(arguments)
            else:
                current_val = char.db.skills.get(arguments, 0)
            if not current_val:
                current_val = 0
            if category == "stat":
                a_min = 1
            elif category == "skill":
                a_min = 0
            else:
                a_min = 0
            a_max = 5
            if not (a_min <= current_val + value <= a_max):
                character.msg("The new value cannot be less than " +
                              "%s or greater than %s. Please try a different value." % (a_min, a_max))
                return False
            new_val = current_val + value
            if category == 'stat' and new_val == a_max:
                # check how many stats we have at maximum. We only allow 2
                num_max_stats = 0
                for stat in VALID_STATS:
                    if char.attributes.get(stat) == 5:
                        num_max_stats += 1
                if num_max_stats >= 2:
                    character.msg("Sorry, only a maximum of two stats are allowed to start at 5.")
                    return False
            avail_pts -= cost
            if category == 'stat':
                char.attributes.add(arguments, new_val)
            elif category == 'skill':
                # if it's a skill with value of 0, we remove it from their sheet entirely
                if new_val == 0:
                    char.db.skills.pop(arguments, None)
                else:
                    char.db.skills[arguments] = new_val
            char.attributes.add(category + "_points", avail_pts)
            character.msg("\n{c%s{n has been set to {w%s{n. You now have {w%s{n points remaining for {w%s{n." % (
                arguments.capitalize(), new_val, avail_pts, category + "s"))
            return True

        if "stat" in switches:
            if lhs not in VALID_STATS:
                matches = get_partial_match(lhs, "stat")
                if not matches:
                    caller.msg("No stat matches the value you entered. Please enter its name again.")
                    return
                if len(matches) > 1:
                    caller.msg("The word you typed for 'stat' matched more than one attribute. " +
                               "Please re-enter with more letters.")
                    return
                # we found a single unique match, set it to the right keyword
                lhs = matches[0]
            # check available points and threshold values, add it
            if not check_points(caller, lhs, val, "stat"):
                return

        if "skill" in switches:
            if lhs not in VALID_SKILLS:
                matches = get_partial_match(lhs, "skill")
                if not matches:
                    caller.msg("No skill matches the value you entered. Please enter its name again.")
                    return
                if len(matches) > 1:
                    caller.msg("The word you typed for 'skill' matched more than one skill." +
                               " Please re-enter with more letters.")
                    return
                # we found a single unique match, set it to the right keyword
                lhs = matches[0]
            # check available points and thresholds, add skill points
            if not check_points(caller, lhs, val, "skill"):
                return
        caller.execute_cmd("look")

    @staticmethod
    def do_stage_5(caller, args):
        """Handle submission/written application"""
        if not args or len(args) < 78:
            caller.msg("Please write a more detailed application for your character. " +
                       "Your application should state how you intend to RP your character, " +
                       "your preferences in stories, the type of RP you want to seek out or " +
                       "create, etc.")
            return
        from commands.base_commands.jobs import get_apps_manager
        char = caller.db.char
        # check if we're ready yet
        if char.db.skill_points or char.db.stat_points:
            caller.msg("You still have available skill or stat points to assign. " +
                       "Please assign them all before you submit your character.")
            return
        unfinished_values = char.db.unfinished_values
        if unfinished_values:
            caller.msg("You still must define the following fields: %s" % unfinished_values)
            return
        # finish up
        apps = get_apps_manager()
        if not apps:
            caller.msg("Failed to find application manager. Please inform admins.")
            return
        caller.db.tutorial_stage = 5
        char.attributes.remove("unfinished_values")
        char.attributes.remove("skill_points")
        char.attributes.remove("stat_points")
        char.player_ob.attributes.remove("tutorial_stage")
        # set initial starting xp based on social rank
        srank = char.db.social_rank or 0
        # noinspection PyBroadException
        try:
            xp_bonus = XP_BONUS_BY_SRANK.get(srank, 0)
            xp_bonus += award_bonus_by_fealty(char.db.fealty)
            xp_bonus += award_bonus_by_age(char.db.age)
            char.db.xp = xp_bonus
        except Exception:
            import traceback
            traceback.print_exc()
            caller.msg("Something went wrong when awarding starting xp. Logging error.")
        xp_msg = "Based on your character's social rank of %s and their fealty, you will " % srank
        xp_msg += "enter the game with %s xp. You will be able to spend them " % char.db.xp
        xp_msg += "with the {wxp/spend{n command."
        caller.msg(xp_msg)

        message = "{wNewly created character application by [%s] for %s" % (caller.key.capitalize(),
                                                                            char.key.capitalize())
        if char.player_ob.email == 'dummy@dummy.com' or char.player_ob.email == 'none':
            # notify GMs that the player is finished and waiting on approval
            message += ". The guest has not provided an email, and will be awaiting approval."
            message += "\nTo approve this character, manually set @userpassword of the player "
            message += "and inform the guest of the new password."
            if args:
                message += "Player added the following to their application: %s" % args
            caller.msg("Thank you for submitting your character for approval.")
            caller.msg("The GMs will review your character and page you the password if it is approved.")
            caller.msg("When the character is approved, log back in to ArxMUSH and use" +
                       " 'connect <name> <password>' to play.")
        else:
            if not args:
                args = "No message"
            email = char.player_ob.email
            apps.add_app(char, email, args)
            caller.msg("Thank you for submitting your character for approval.")
            caller.msg("GMs will review your character, and notify you via the email you provided.")
            caller.msg("If the GMs feel anything in your character needs to be changed, " +
                       "they will work with you to adjust your character for play.")
        inform_staff(message)
        try:
            from world.dominion.setup_utils import starting_money
            money = starting_money(srank) or 0
            char.db.currency = money/10
        except (ValueError, TypeError, AttributeError):
            import traceback
            traceback.print_exc()
            char.db.currency = 0

    def func(self):
        """"implement the ooc look command"""
        caller = self.caller
        char = caller.db.char
        stage = caller.db.tutorial_stage
        args = self.args
        # convert any strange diacritics to english
        args = unidecode(args)
        if args != self.args:
            caller.msg("{wEncountered non-ascii characters. Converting unicode to ascii text.{n")
        switches = self.switches
        # if we're at stage 5, we no longer allow the player to retroactively change
        # anything about the character. It's frozen until the character is approved or
        # rejected
        if stage == 5:
            caller.msg("Your character is currently pending approval and cannot be changed.")
            return
        if not switches:
            caller.msg("All uses of the {w@add{n command require you to add a 'switch' after @add to identify " +
                       "what field you're adding to your character sheet.\n"
                       "For example: {w@add/name Robert{n\nOr: {w@add/vocation criminal{n")
            return
        if 'email' in switches:
            if not args:
                caller.msg("You must supply an email address when setting your email.")
                return
            args = args.lower()
            if char:
                player = char.player_ob
                player.email = args
                player.save()
            caller.ndb.email = args
            caller.msg("Email set to %s" % args)
            return
        if not stage or not char:
            caller.msg("{w@add{n is used during character creation. To start character creation, " +
                       "use {w@charcreate <email address>{n")
            return
        if 'skip' in switches:
            if stage == 3:
                caller.db.tutorial_stage += 1
                char.player_ob.db.tutorial_stage = caller.db.tutorial_stage
                caller.execute_cmd("look")
                return
        if stage == 1 or 'name' in switches:
            self.do_stage_1(caller, args)
            return
        elif stage == 2 or 'vocation' in switches or 'newvocation' in switches:
            self.do_stage_2(caller, args, switches)
            return
        elif stage == 3 or (set(switches) & (set(_stage3_fields_) | set(_stage3_optional_))):
            self.do_stage_3(caller, args, switches)
            return
        elif 'submit' in switches:
            self.do_stage_5(caller, args)
            return
        elif stage == 4 or 'stat' in switches or 'skill' in switches:
            self.do_stage_4(caller, args, switches, self.lhs, self.rhs)
            return
        caller.msg("Unexpected state error.")
