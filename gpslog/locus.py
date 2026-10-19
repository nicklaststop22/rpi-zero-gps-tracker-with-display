"""Vendor logging commands for the GPS module's ONBOARD logger.

The app sends these as NMEA sentences; gpsreader.build_sentence() adds the '$'
prefix and the '*checksum' automatically, so each value below is the BARE body
only, e.g. "PMTK185,0"  (NOT "$PMTK185,0*2F").

Many Adafruit GPS breakouts are the MTK3339 chipset (Ultimate GPS), whose
onboard "LOCUS" flash logger is driven by PMTK commands. But the exact strings
depend on the module you actually have - so they're left for you to fill in.
"""

# When READ runs, the module streams its stored log back as NMEA sentences.
# This is the talker-prefix the app watches for to capture the dump (e.g. for
# MTK3339 LOCUS it is "PMTKLOX"). Adjust to match your module's dump output.
READ_DUMP_PREFIX = "PMTKLOX"

# Seconds to keep capturing dump sentences after pressing READ.
READ_CAPTURE_SECS = 8


# Adafruit Ultimate GPS HAT (MTK3339) LOCUS flash-logger commands. Bare bodies
# only; build_sentence() adds '$' and the '*checksum'. Verified checksums shown
# in comments for reference against the Adafruit guide.
COMMANDS = {
    "START": "PMTK185,0",   # start LOCUS logger            -> $PMTK185,0*22
    "STOP":  "PMTK185,1",   # stop LOCUS logger             -> $PMTK185,1*23
    "READ":  "PMTK622,1",   # dump stored log ($PMTKLOX...) -> $PMTK622,1*29
    "CLEAR": "PMTK184,1",   # erase onboard flash log       -> $PMTK184,1*22
}

# Query logger status (count / % full): $PMTK183*38 -> reply $PMTKLOG,...
STATUS_QUERY = "PMTK183"


def command_for(action: str):
    """Return the bare NMEA body for an action label, or None if unset."""
    return COMMANDS.get(action)
