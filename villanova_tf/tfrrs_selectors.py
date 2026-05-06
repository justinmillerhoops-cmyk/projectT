"""
TFRRS CSS selectors and URL patterns — isolated here so HTML changes only require updates in one place.
Discovered by inspecting live TFRRS pages (April 2026).
"""

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------
BASE_URL = "https://www.tfrrs.org"
TF_BASE_URL = "https://tf.tfrrs.org"

# Team page slugs — the tfrrs.org URL uses these identifiers
VILLANOVA_MEN_SLUG = "PA_college_m_Villanova"
VILLANOVA_WOMEN_SLUG = "PA_college_f_Villanova"

TEAM_PAGE_URL = BASE_URL + "/teams/tf/{slug}.html"

# ---------------------------------------------------------------------------
# Athlete page
# ---------------------------------------------------------------------------
ATHLETE_PAGE_URL = BASE_URL + "/athletes/{athlete_id}/{team}/{first}_{last}.html"
# Athlete ID is extracted from href: /athletes/{id}/...
ATHLETE_HREF_RE = r"/athletes/(\d+)/"

# Season bests tables: class="table bests", "table indoor_bests", "table outdoor_bests"
BESTS_TABLE_ALL = "table.bests"
BESTS_TABLE_INDOOR = "table.indoor_bests"
BESTS_TABLE_OUTDOOR = "table.outdoor_bests"

# Within bests tables: no header row — cells alternate event / mark pairs
# Row structure: <tr><td>event</td><td>mark (wind)</td>...</tr>

# Meet-by-meet results: tables with class "table table-hover >"
# Note the trailing " >" is literally in the class string
MEET_TABLE_CLASS = "table table-hover >"

# Meet table header: <th class="panel-heading-text" colspan="100%">
#   <a href="...">Meet Name</a>
#   <span>Date</span>
# </th>
MEET_HEADER_TH_CLASS = "panel-heading-text"

# Meet result row cells:
# col 0: event name (td class="panel-heading-text")
# col 1: mark, with wind in child <span> (td class="panel-heading-normal-text")
#         <a href="/results/{meet_id}/{result_id}/...">mark</a>
#         <span style="font-style:italic">(wind)</span>
# col 2: place and round, e.g. "4th (F)"  (td class="panel-heading-text")

RESULT_HREF_RE = r"/results/(\d+)/(\d+)/"

# ---------------------------------------------------------------------------
# Ranking list pages
# ---------------------------------------------------------------------------
# Full list page URL (returns HTML with embedded turbo-frame content)
LIST_PAGE_URL = BASE_URL + "/lists/{list_id}/{slug}"
# The turbo-frame containing all list data
LIST_TURBO_FRAME_ID = "list_data"

# Within the turbo-frame, each event section begins with a div.custom-table-title
# containing an <h3> with the event name, followed by div.performance-list

# Performance list structure (div-based, not <table>)
PERF_LIST_DIV = "performance-list"          # container div class
PERF_LIST_HEADER = "performance-list-header" # column header row
PERF_LIST_BODY = "performance-list-body"     # all result rows
PERF_LIST_ROW = "performance-list-row"       # individual result row

# Column div classes within each row
COL_PLACE = "col-place"
COL_ATHLETE = "col-athlete"
COL_NARROW = "col-narrow"  # used for year, mark, date, wind — appears multiple times
COL_TEAM = "col-team"
COL_MEET = "col-meet"

# Event section header
EVENT_SECTION_HEADER = "custom-table-title"

# data-label attributes on col-narrow divs — used to disambiguate which narrow col is which
DATA_LABEL_YEAR = "Year"
DATA_LABEL_TIME = "Time"        # also used for field marks
DATA_LABEL_DATE = "Meet Date"
DATA_LABEL_WIND = "Wind"

# ---------------------------------------------------------------------------
# Team roster table (on team page)
# ---------------------------------------------------------------------------
# The roster table has class "tablesaw table-striped table-bordered table-hover"
ROSTER_TABLE_CLASS = "tablesaw"
# Roster row columns (in order): EVENT, ATHLETE, YEAR, TIME/MARK
ROSTER_COL_EVENT = 0
ROSTER_COL_ATHLETE = 1
ROSTER_COL_YEAR = 2
ROSTER_COL_MARK = 3

# ---------------------------------------------------------------------------
# List IDs — update annually at season start
# These are stored here as defaults; override in config.yaml for new seasons.
# ---------------------------------------------------------------------------
LIST_IDS = {
    # Big East conference performance lists
    "big_east_outdoor": 5656,   # BIG EAST Outdoor Performance List (2026)
    "big_east_indoor": 5430,    # BIG EAST Indoor Performance List (2026)

    # NCAA DI East regional outdoor list (only East needed for Villanova)
    "ncaa_east_outdoor": 5622,  # 2026 NCAA Div I East Outdoor List

    # NCAA DI national qualifying/performance lists
    "ncaa_national_outdoor": 5602,  # 2026 NCAA Division I Outdoor Qualifying List
    "ncaa_national_indoor": 5352,   # 2025-2026 NCAA Division I Indoor List FINAL

    # Historical lists for bubble reference (last 5 completed seasons each)
    "ncaa_outdoor_history": [5018, 4515, 4044, 3711, 3191],  # 2025-2021
    "ncaa_indoor_history": [4867, 4364, 3901, 3492, 3157],   # 2024-25 through 2020-21
}

LIST_SLUGS = {
    "big_east_outdoor": "BIG_EAST_Outdoor_Performance_List",
    "big_east_indoor": "BIG_EAST_Indoor_Performance_List",
    "ncaa_east_outdoor": "2026_NCAA_Div_I_East_Outdoor_List",
    "ncaa_national_outdoor": "2026_NCAA_Division_I_Outdoor_Qualifying_List",
    "ncaa_national_indoor": "2025_2026_NCAA_Division_I_Indoor_List_FINAL",
}

# Gender URL parameter used by tf.tfrrs.org lists
GENDER_PARAM = {"M": "m", "F": "f"}
