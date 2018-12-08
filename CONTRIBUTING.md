Pull requests are cheerfully accepted. As far as coding style goes, I'd prefer adhering to PEP8
and standard python conventions, aside from line length - 100/120 character lines are fine.

We tend to use google-style documentation, though I've been pretty lax about documenting things
myself, so I'm not very strict about it. I do ask that you write tests for any pull request,
though. Testing in Evennia can be a little difficult. When running the test runner for evennia,
you'll typically do so with `test_settings.py` and a switch for opting out of migrations, since
those take a very long time to run. For example:
```
evennia test --settings=test_settings --nomigrations .
```
would run the test runner without migrations being checked. You'll need to generate migrations
for any schema changes, and I'd ask that those be squashed down into a single migration file
if possible.
