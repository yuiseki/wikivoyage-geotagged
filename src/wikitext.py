"""Flatten wikitext to prose.

Written first for the OpenStreetMap Wiki, where most of the knowledge sits
inside wikitables and {{Tag}}/{{Key}} templates rather than in paragraphs. A
cleaner that strips tables and templates deletes the content it was meant to
keep, so both are unwrapped rather than removed. The same choice suits
Wikipedia, whose infoboxes carry facts the prose does not repeat.

Vendored here rather than imported, so that this repository runs on its own.
"""

import re

# Namespaces whose links are an image or a file, not a mention of a place.
# The local names matter: ja uses ファイル and 画像, and an English-only list
# left 71.0% of Japanese articles carrying image markup as prose.
FILE_NS = re.compile(
    r"^\s*:?\s*(?:File|Image|Media|ファイル|画像|Datei|Fichier|Archivo|Imagem)\s*:",
    re.I)

# How a file link is displayed, rather than what it says. Everything here is
# dropped; whatever is left of the arguments is the caption.
FILE_OPTION = re.compile(
    r"^(?:thumb|thumbnail|frame|frameless|border|right|left|centre|center|none"
    r"|upright(?:=[\d.]+)?|baseline|middle|sub|super|text-top|text-bottom|top|bottom"
    r"|\d+\s*x?\s*\d*\s*px|link=.*|alt=.*|lang=.*|page=\d+|class=.*)$",
    re.I)

# An attribute of a table or a template, not something anybody reads.
ATTR_KEY = re.compile(
    r"^(?:style|class|id|width|height|align|valign|bgcolor|colspan|rowspan"
    r"|border|cellpadding|cellspacing|scope|title|colour|color)$", re.I)

# {{Tag|railway|station}} -> railway=station, {{Key|railway}} -> railway
TAG_TPL = re.compile(r"\{\{\s*(?:Tag|Key|Value|IconNode)\s*\|([^{}|]*)(?:\|([^{}|=]*))?(?:\|[^{}]*)?\}\}", re.I)


def _tag_repl(m):
    key = (m.group(1) or "").strip()
    val = (m.group(2) or "").strip()
    if key and val:
        return f"{key}={val}"
    return key


def _gallery_repl(m):
    """A gallery is one file per line, written without brackets. Keep captions."""
    out = []
    for line in m.group(1).split("\n"):
        parts = split_pipes(line.strip())
        if len(parts) > 1:
            out.append(parts[-1].strip())
    return "\n" + "\n".join(p for p in out if p) + "\n"


OPENERS = {"{{": "}}", "[[": "]]"}


def split_pipes(body):
    """Split on the pipes that belong here, not to something nested inside.

    A caption can hold {{Snamei||Physcomitrium patens}} or [[Hoggar]], whose
    pipes are not this one's. Splitting on those left the closing braces and
    brackets behind with nothing to open them.
    """
    parts, depth, cur = [], 0, []
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two in OPENERS:
            depth += 1; cur.append(two); i += 2; continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1); cur.append(two); i += 2; continue
        if body[i] == "|" and depth == 0:
            parts.append("".join(cur)); cur = []; i += 1; continue
        cur.append(body[i]); i += 1
    parts.append("".join(cur))
    return parts


def _link_repl(m):
    """What a wiki link leaves behind.

    A file link leaves its caption, which an editor wrote and which often names
    a place the body does not. Any other link leaves its label, which is the
    last argument. The old pattern allowed one pipe, so a file link with its
    usual three never matched and survived whole.
    """
    parts = split_pipes(m.group(1))
    if FILE_NS.match(parts[0]):
        for p in reversed(parts[1:]):
            p = p.strip()
            if p and not FILE_OPTION.match(p):
                return p
        return " "
    return (parts[-1] if len(parts) > 1 else parts[0]).strip()


# A table opens with a brace, and the innermost-template pattern cannot cross
# one, so an infobox holding a table was never unwrapped and its raw markup
# reached the text. Hiding the two table markers while templates are unwrapped
# lets the pattern reach them; they are put back before the table pass.
TABLE_OPEN, TABLE_CLOSE = "\x01", "\x02"

# MediaWiki's table markup, written as templates so it can sit inside another
# template. A Japanese city infobox builds its image montage this way.
MAGIC_TABLE = [
    (re.compile(r"\{\{\s*\(!\s*\}\}"), "\n{|"),
    (re.compile(r"\{\{\s*!\)\s*\}\}"), "\n|}\n"),
    (re.compile(r"\{\{\s*!-\s*\}\}"), "\n|-\n"),
    (re.compile(r"\{\{\s*!!\s*\}\}"), "||"),
    (re.compile(r"\{\{\s*!\s*\}\}"), "|"),
    (re.compile(r"\{\{\s*=\s*\}\}"), "="),
]

# Blocks that are not sentences. Their braces and pipes confuse everything
# downstream, and a page of LilyPond is not text about a place.
NON_PROSE = re.compile(
    r"<(score|math|chem|syntaxhighlight|source|nowiki|timeline|hiero|mapframe|maplink|graph)\b[^>]*"
    r"(?:/>|>.*?</\1>)", re.S | re.I)

GALLERY = re.compile(r"<gallery\b[^>]*>(.*?)</gallery>", re.S | re.I)

# The body of a template. A lone brace is allowed, so that {{chem2|C_{n}H_{2n+2} }}
# is matched, but a doubled one is not, which keeps the match innermost-first.
TEMPLATE = re.compile(r"\{\{((?:[^{}]|\{(?!\{)|\}(?!\}))*?)\}\}")

# A run of attributes standing on its own, which is what a mangled table cell
# leaves behind. Never prose in any language.
ATTR = r'[A-Za-z][A-Za-z0-9-]*\s*=\s*(?:"[^"]*"|\'[^\']*\'|[\w#%.:-]+)'
BARE_ATTRS = re.compile(r'^\s*(?:' + ATTR + r'\s*)+\|?\s*$')
# The attributes at the head of a table cell, ending at the pipe that starts
# its content. Both quoted and unquoted: colspan="2" data-sort-type=number |
CELL_ATTRS = re.compile(r'^\s*(?:' + ATTR + r'\s*)+\|(?!\|)')


def unwrap_links(t):
    """Replace every wiki link with what it leaves behind, innermost first."""
    for _ in range(6):
        new = re.sub(r"\[\[([^\[\]]*)\]\]", _link_repl, t)
        if new == t:
            return t
        t = new
    return t


def clean(t):
    # References first. They are never content, and leaving them until after
    # the templates are split on the pipe tore them in half and left the
    # fragments behind. Self-closing before paired, because <ref name="x" />
    # also matches the opening pattern and the search for a closing tag then
    # runs past everything in between.
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = NON_PROSE.sub(" ", t)
    t = re.sub(r"<ref[^>]*/>", " ", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", " ", t, flags=re.S)

    # Links before templates, for the same reason: a template body is split on
    # the pipe, and [[a|b]] inside one was split with it. Galleries after the
    # links, because a gallery caption is often a link.
    t = unwrap_links(t)
    t = GALLERY.sub(_gallery_repl, t)

    for rx, repl in MAGIC_TABLE:
        t = rx.sub(repl, t)

    # Only at the start of a line, which is the only place MediaWiki reads
    # them. Hiding every "|}" took the closing brace off any template whose
    # last argument was empty, and {{as of|2023|February|}} survived whole.
    t = re.sub(r"(?m)^([ \t]*)\{\|", r"\1" + TABLE_OPEN, t)
    # Not when another brace follows: a line beginning "|}}" is a template
    # whose last argument was empty, and taking its first two characters left
    # the template unclosed.
    t = re.sub(r"(?m)^([ \t]*)\|\}(?!\})", r"\1" + TABLE_CLOSE, t)

    # Unwrap tag templates first, innermost-out, before anything strips braces.
    for _ in range(3):
        new = TAG_TPL.sub(_tag_repl, t)
        if new == t:
            break
        t = new

    # Remaining templates: keep argument values that read like prose, drop the rest.
    def tpl_repl(m):
        body = m.group(1)
        parts = [p.strip() for p in body.split("|")[1:]]
        keep = []
        for p in parts:
            if "=" in p:
                key, p = p.split("=", 1)
                if ATTR_KEY.match(key.strip()):
                    continue
                p = p.strip()
            if len(p) > 25 and " " in p:
                keep.append(p)
        return " " + " ".join(keep) + " "

    # Until nothing changes. Wikipedia nests templates deeper than a fixed
    # count allows: {{as of}} inside five others survived a limit of four.
    for _ in range(12):
        new = TEMPLATE.sub(tpl_repl, t)
        if new == t:
            break
        t = new

    t = t.replace(TABLE_OPEN, "{|").replace(TABLE_CLOSE, "|}")

    # Tables: drop the syntax, keep the cells. This is where the content is.
    out = []
    for line in t.split("\n"):
        s = line.strip()
        if s.startswith("{|") or s.startswith("|}") or s.startswith("|-"):
            continue
        if BARE_ATTRS.match(s):
            continue
        if s.startswith("|") or s.startswith("!"):
            s = s.lstrip("|!")
            if s.startswith("+"):        # |+ opens a table caption
                s = s[1:]
            # A leading "class=..." style attribute block ends at the first |
            cells = re.split(r"\|\||!!", s)
            cleaned = []
            for c in cells:
                c = c.strip()
                # Drop cell attributes such as rowspan="3" or style="..."
                c = CELL_ATTRS.sub("", c).strip()
                if BARE_ATTRS.match(c):
                    continue
                if c:
                    cleaned.append(c)
            s = " | ".join(cleaned)
        out.append(s)
    t = "\n".join(out)

    # Again, for links a template expansion produced.
    t = unwrap_links(t)
    t = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\]", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"^=+\s*(.*?)\s*=+$", r"\1", t, flags=re.M)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
