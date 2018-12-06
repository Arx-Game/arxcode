import re
from django.conf import settings
from evennia.utils import utils, logger
from django.utils.translation import ugettext as _


__all__ = ("ConditionalHandler", "ConditionalException")

WARNING_LOG = settings.LOCKWARNING_LOG_FILE
_MAGIC_CONDITION_FUNCS = {}


#
# Exception class. This will be raised
# by errors in lock definitions.
#

class ConditionalException(Exception):
    """
    Raised during an error in a condition.
    """
    pass


#
# pre-compiled regular expressions
#

_RE_FUNCS = re.compile(r"\w+\([^)]*\)")
_RE_SEPS = re.compile(r"(?<=[ )])AND(?=\s)|(?<=[ )])OR(?=\s)|(?<=[ )])NOT(?=\s)")
_RE_OK = re.compile(r"%s|and|or|not")


def _cache_conditionfuncs():
    """
    Updates the cache.
    """
    global _MAGIC_CONDITION_FUNCS
    _MAGIC_CONDITION_FUNCS = {}
    for modulepath in settings.MAGIC_CONDITION_MODULES:
        _MAGIC_CONDITION_FUNCS.update(utils.callables_from_module(modulepath))


class ConditionalHandler:

    def __init__(self, condition_storagestring):
        """
        Loads and pre-caches all relevant locks and their functions.
        """
        if not _MAGIC_CONDITION_FUNCS:
            _cache_conditionfuncs()

        self.conditions = self._parse_conditional_string(condition_storagestring)
        self.raw_string = condition_storagestring

    @staticmethod
    def _parse_conditional_string(storage_conditionstring):
        conditions = {}
        if not storage_conditionstring:
            return conditions
        duplicates = 0
        elist = []  # errors
        wlist = []  # warnings
        for raw_condition in storage_conditionstring.split(';'):
            if not raw_condition:
                continue
            condition_funcs = []
            try:
                access_type, rhs = (part.strip() for part in raw_condition.split(':', 1))
            except ValueError:
                logger.log_trace()
                return conditions

            # parse the lock functions and separators
            funclist = _RE_FUNCS.findall(rhs)
            evalstring = rhs
            for pattern in ('AND', 'OR', 'NOT'):
                evalstring = re.sub(r"\b%s\b" % pattern, pattern.lower(), evalstring)
            nfuncs = len(funclist)
            for funcstring in funclist:
                funcname, rest = (part.strip().strip(')') for part in funcstring.split('(', 1))
                func = _MAGIC_CONDITION_FUNCS.get(funcname, None)
                if not callable(func):
                    elist.append(_("Condition: magic condition-function '%s' is not available.") % funcstring)
                    continue
                args = list(arg.strip() for arg in rest.split(',') if arg and '=' not in arg)
                kwargs = dict([arg.split('=', 1) for arg in rest.split(',') if arg and '=' in arg])
                condition_funcs.append((func, args, kwargs))
                evalstring = evalstring.replace(funcstring, '%s')
            if len(condition_funcs) < nfuncs:
                continue
            try:
                # purge the eval string of any superfluous items, then test it
                evalstring = " ".join(_RE_OK.findall(evalstring))
                eval(evalstring % tuple(True for func in funclist), {}, {})
            except Exception:
                elist.append(_("Condition: definition '%s' has syntax errors.") % raw_condition)
                continue
            if access_type in conditions:
                duplicates += 1
                wlist.append(_("ConditionalHandler: access type '%(access_type)s' changed from "
                               "'%(source)s' to '%(goal)s' " %
                               {"access_type": access_type, "source": conditions[access_type][2],
                                "goal": raw_condition}))
            conditions[access_type] = (evalstring, tuple(condition_funcs), raw_condition)
        if wlist and WARNING_LOG:
            # a warning text was set, it's not an error, so only report
            logger.log_file("\n".join(wlist), WARNING_LOG)
        if elist:
            # an error text was set, raise exception.
            raise ConditionalException("\n".join(elist))
        # return the gathered locks in an easily executable form
        return conditions

    def check(self, caster, target, access_type, default=False):
        if access_type in self.conditions:
            # we have a lock, test it.
            evalstring, func_tup, raw_string = self.conditions[access_type]
            # execute all lock funcs in the correct order, producing a tuple of True/False results.
            true_false = tuple(bool(
                tup[0](caster, target, *tup[1], **tup[2])) for tup in func_tup)
            # the True/False tuple goes into evalstring, which combines them
            # with AND/OR/NOT in order to get the final result.
            return eval(evalstring % true_false)
        else:
            return default

    def __str__(self):
        return self.raw_string or ""
