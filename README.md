[![Build Status](https://travis-ci.org/Arx-Game/arxcode.svg?branch=stable_orphan)](https://travis-ci.org/Arx-Game/arxcode)

Arx is a game based on Evennia. I decided to make an orphan branch open source to let people
use code as they like for their own games and contribute if they like. In general we should
be compatible with any given Evennia branch, though I tend to stay on master and occasionally
make a branch to cherry-pick additions from develop.

The basic requirements  are added in the different setup files. Evennia sets the django settings
environmental variable at startup and looks specifically in the server/conf/ directory, so specify
`--settings=foo_settings` where `foo_settings` is a settings file in the server/conf/ directory.
The default will use production_settings unless otherwise specified.

Some django packages aren't compatible with Evennia due to clashes in middleware. Silk,
for example, will throw errors from its middleware whenever an in-game script runs.

Evennia resources:

From here on you might want to look at one of the beginner tutorials:
http://github.com/evennia/evennia/wiki/Tutorials.

Evennia's documentation is here:
https://github.com/evennia/evennia/wiki.

Enjoy!
