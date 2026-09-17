"""Classify discover_shows.py candidates into seat-finding platforms.

Mirrors the rules documented in
`.claude/skills/cinema-seat-finder/references/platforms.md` - see that
file for why each rule is what it is (Filmgrail by a fixed `firmName`
allow-list; ODEON/ebillett.no/NFkino by `ticketSaleUrl` domain, since
each of those spans many different `firmName`s on one shared backend).

Moving this out of SKILL.md prose and into code means Claude no longer
manually checks every candidate's `firmName`/`ticketSaleUrl` against the
table itself - for a nationwide search that can mean dozens of
candidates - it just reads back this script's already-classified JSON.
"""
import argparse
import json
import sys

FILMGRAIL_FIRM_NAMES = {
    "Trondheim Kino", "Steinkjer kino", "Kimen kino", "Haugesund kino",
    "Caroline kino Kristiansund", "Tromsø Kino", "Narvik kino", "Alta kino",
    "Kirkenes kino", "Lakselv kino", "Setermoen kino", "Bergen kino",
}


def classify(shows):
    """Group `shows` (discover_shows.py's output shape) by seat-finding
    platform, order preserved within each group. Returns
    {"filmgrail": [...], "odeon": [...], "ebillett": [...],
    "nfkino": [...], "out_of_scope": [...]}."""
    result = {"filmgrail": [], "odeon": [], "ebillett": [], "nfkino": [], "out_of_scope": []}
    for show in shows:
        ticket_url = show.get("ticketSaleUrl") or ""
        if show.get("firmName") in FILMGRAIL_FIRM_NAMES:
            result["filmgrail"].append(show)
        elif ticket_url.startswith("https://www.odeonkino.no/"):
            result["odeon"].append(show)
        elif ticket_url.startswith("https://checkout.ebillett.no/"):
            result["ebillett"].append(show)
        elif ticket_url.startswith("https://nfkino.no/"):
            result["nfkino"].append(show)
        else:
            result["out_of_scope"].append(show)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Classify discover_shows.py candidates into seat-finding platforms (reads a JSON array from stdin)")
    parser.parse_args()
    shows = json.load(sys.stdin)
    print(json.dumps(classify(shows)))


if __name__ == "__main__":
    main()
