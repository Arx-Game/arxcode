"""

MSSP (Mud Server Status Protocol) meta information

MUD website listings (that you have registered with) can use this
information to keep up-to-date with your game stats as you change
them. Also number of currently active players and uptime will
automatically be reported. You don't have to fill in everything
(and most are not used by all crawlers); leave the default
if so needed. You need to @reload the game before updated
information is made available to crawlers (reloading does not
affect uptime).

"""

MSSPTable = {
    # Required fieldss
    "NAME": "Arx: After the Reckoning",
    # Generic
    "CRAWL DELAY": "-1",  # limit how often crawler updates the listing. -1 for no limit
    "HOSTNAME": "play.arxgame.org",  # current or new hostname
    "PORT": ["3000"],  # most important port should be last in list
    "CODEBASE": "Evennia",
    "CONTACT": "arxmush@gmail.com",  # email for contacting the mud
    "CREATED": "2016",  # year MUD was created
    "ICON": "http://play.arxgame.org/static/images/arx_badge_small.png",  # url to icon 32x32 or larger; <32kb.
    "IP": "",  # current or new IP address
    "LANGUAGE": "English",  # name of language used, e.g. English
    "LOCATION": "United States",  # full English name of server country
    "MINIMUM AGE": "18",  # set to 0 if not applicable
    "WEBSITE": "play.arxgame.org",
    # Categorisation
    "FAMILY": "Custom",  # evennia goes under 'Custom'
    "GENRE": "Fantasy",  # Adult, Fantasy, Historical, Horror, Modern, None, or Science Fiction
    "GAMEPLAY": "",  # Adventure, Educational, Hack and Slash, None,
    # Player versus Player, Player versus Environment,
    # Roleplaying, Simulation, Social or Strategy
    "STATUS": "Open Beta",  # Alpha, Closed Beta, Open Beta, Live
    "GAMESYSTEM": "Custom",  # D&D, d20 System, World of Darkness, etc. Use Custom if homebrew
    "INTERMUD": "IMC2",  # evennia supports IMC2.
    "SUBGENRE": "None",  # LASG, Medieval Fantasy, World War II, Frankenstein,
    # Cyberpunk, Dragonlance, etc. Or None if not available.
    # World
    "AREAS": "0",
    "HELPFILES": "0",
    "MOBILES": "0",
    "OBJECTS": "0",
    "ROOMS": "0",  # use 0 if room-less
    "CLASSES": "0",  # use 0 if class-less
    "LEVELS": "0",  # use 0 if level-less
    "RACES": "0",  # use 0 if race-less
    "SKILLS": "0",  # use 0 if skill-less
    # Protocols set to 1 or 0)
    "ANSI": "1",
    "GMCP": "0",
    "MCCP": "0",
    "MCP": "0",
    "MSDP": "0",
    "MSP": "0",
    "MXP": "0",
    "PUEBLO": "0",
    "UTF-8": "1",
    "VT100": "0",
    "XTERM 256 COLORS": "1",
    # Commercial set to 1 or 0)
    "PAY TO PLAY": "0",
    "PAY FOR PERKS": "0",
    # Hiring  set to 1 or 0)
    "HIRING BUILDERS": "0",
    "HIRING CODERS": "0",
    # Extended variables
    # World
    "DBSIZE": "0",
    "EXITS": "0",
    "EXTRA DESCRIPTIONS": "0",
    "MUDPROGS": "0",
    "MUDTRIGS": "0",
    "RESETS": "0",
    # Game  (set to 1 or 0, or one of the given alternatives)
    "ADULT MATERIAL": "0",
    "MULTICLASSING": "0",
    "NEWBIE FRIENDLY": "0",
    "PLAYER CITIES": "0",
    "PLAYER CLANS": "0",
    "PLAYER CRAFTING": "0",
    "PLAYER GUILDS": "0",
    "EQUIPMENT SYSTEM": "None",  # "None", "Level", "Skill", "Both"
    "MULTIPLAYING": "Restricted",  # "None", "Restricted", "Full"
    "PLAYERKILLING": "Restricted",  # "None", "Restricted", "Full"
    "QUEST SYSTEM": "None",  # "None", "Immortal Run", "Automated", "Integrated"
    "ROLEPLAYING": "Enforced",  # "None", "Accepted", "Encouraged", "Enforced"
    "TRAINING SYSTEM": "Skill",  # "None", "Level", "Skill", "Both"
    "WORLD ORIGINALITY": "All Original",  # "All Stock", "Mostly Stock", "Mostly Original", "All Original"
    # Protocols (only change if you added/removed something manually)
    "ATCP": "0",
    "MSDP": "0",
    "MCCP": "1",
    "SSL": "1",
    "UTF-8": "1",
    "ZMP": "0",
    "XTERM 256 COLORS": "1",
}
