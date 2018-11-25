"""
These are scripts that were run once that might be difficult to do as migrations (for example, they'd heavily
leverage the pickled values of Attributes, where class properties such as the automatic conversion of pickled
fields won't have access to. Although they only run once, they're useful as references, but shunted aside here
so they don't clutter regular packages.
"""