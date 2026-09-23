"""Tests for reading MediaWiki SQL dumps.

The same parser as wikipedia-geotagged, on a much smaller wiki. Wikivoyage is
what found the escape bug: its very first geotagged page is 's-Hertogenbosch.

The dumps put their values on the lines after `INSERT INTO ... VALUES`, not on
the same line, and they write an absent value as a bare NULL. Both cost time
here: a parser that split on INSERT found nothing, and one that decoded NULL as
text stored the string "NULL" for 57.5% of rows and hid that they had no type.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import geo_pages  # noqa: E402


def test_geo_tuple_is_read_from_a_values_line():
    line = (b"(32506976,39009140,'earth',1,22.22466660,-159.54949951,"
            b"NULL,NULL,NULL,NULL,NULL,NULL,NULL),")
    m = geo_pages.GEO.search(line)
    assert m is not None
    assert int(m.group(2)) == 39009140      # page id
    assert m.group(4) == b"1"               # primary tag
    assert m.group(8) == b"NULL"            # no type


def test_a_typed_tag_keeps_its_type():
    line = b"(1,2,'earth',1,51.5,-0.12,NULL,'city',NULL,NULL,NULL,NULL,NULL),"
    m = geo_pages.GEO.search(line)
    assert m.group(8) == b"'city'"


def test_page_tuple_carries_namespace_and_redirect_flag():
    line = b"(12,0,'Anarchism',0,0,0.123,'20260101000000',NULL,1,50000,'wikitext',NULL),"
    m = geo_pages.PAGE.search(line)
    assert int(m.group(1)) == 12
    assert int(m.group(2)) == geo_pages.ARTICLE_NAMESPACE
    assert m.group(3) == b"Anarchism"
    assert m.group(4) == b"0"


def test_the_card_names_the_file_that_is_uploaded():
    """data_files in the card has to be the path publish.py writes to.

    They are set in different files, so nothing but a test connects them. Get
    it wrong and the dataset viewer finds no data while every upload succeeds.
    """
    import re
    import publish

    base = os.path.join(os.path.dirname(__file__), "..")
    card = open(os.path.join(base, "data/README.md"), encoding="utf-8").read()
    declared = re.search(r"^\s*data_files:\s*(\S+)\s*$", card, re.M)
    assert declared, "the card declares no data_files"
    assert declared.group(1) == publish.PATH_IN_REPO


def test_templates_and_tables_are_unwrapped_not_removed():
    """The cleaner keeps what is inside braces and pipes.

    A cleaner that deletes templates deletes the facts: an infobox is often
    the only place an article states a population or an elevation.
    """
    import wikitext

    out = wikitext.clean("{{Tag|railway|station}} is a [[railway station]].")
    assert "railway=station" in out
    assert "railway station" in out
    assert "{{" not in out and "[[" not in out


def test_a_dump_escape_is_undone_in_titles_and_names():
    """The dumps escape quotes and backslashes; the value is not the raw bytes.

    Found on Wikivoyage, whose first geotagged page is 's-Hertogenbosch and
    came out as \\'s-Hertogenbosch. 216 of its 29,505 titles carry an escape.
    Wikipedia hides this: its geo_pages title is only used for reporting, and
    the published title comes from the XML dump instead.
    """
    line = rb"(10,0,'\'s-Hertogenbosch',0,0,0.922237949364,'20260828224346',"
    m = geo_pages.PAGE.search(line)
    assert m
    assert geo_pages.unescape(m.group(3)) == b"'s-Hertogenbosch"


def test_unquote_undoes_escapes_too():
    assert geo_pages.unquote(rb"'Coeur d\'Alene'") == "Coeur d'Alene"
    assert geo_pages.unquote(rb"'a\\b'") == "a\\b"
    assert geo_pages.unquote(b"NULL") is None


def test_only_the_outer_quotes_come_off():
    """strip() takes every quote at the ends, not the one that delimits.

    Wikivoyage cannot show this: every name in its geo_tags is null. Wikipedia
    had 225 values of the form USS \'\'S-37\'\ left after the first fix.
    """
    assert geo_pages.unquote(rb"'USS \'\'S-37\'\''") == "USS ''S-37''"
    assert geo_pages.unquote(rb"''") is None
    assert geo_pages.unquote(rb"'Paris'") == "Paris"
