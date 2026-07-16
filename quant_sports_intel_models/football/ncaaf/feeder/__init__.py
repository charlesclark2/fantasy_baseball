"""NCAAF NFL-feeder package (the college→NFL bridge).

The feeder turns college production + combine measurables into NFL rookie
projections — the football analog of MLB Edge E7 (MiLB→MLB MLEs). Its spine is the
college↔NFL player-ID crosswalk built here (NCAAF-P0.3):

  • xref.py       — the college↔NFL ID xref builder (the E7.4 identity-xref analog).
  • name_norm.py  — shared name normalisation (suffix/apostrophe/accent) for the
                    surname-agreement validation + the UDFA fuzzy match.

The college→NFL *translation* model (the E7.3 MLE analog) is a later Phase-1 story
(NCAAF-P1A) that keys on the xref this package produces.
"""
