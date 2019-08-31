import codecs
import re

import click

import zyaml

from .conftest import main


RE_LINE_SPLIT = re.compile(r"^\s*([%#]|-(--)?|\.\.\.)?\s*(.*?)\s*$")
RE_FLOW_SEP = re.compile(r"""(#|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{},])\s*(.*?)\s*$""")
RE_BLOCK_SEP = re.compile(r"""(#|![^\s\[\]{}]*|[&*][^\s:,\[\]{}]+|[:\[\]{}])\s*(.*?)\s*$""")


class ScannerMock:
    def __init__(self):
        self.line_regex = RE_BLOCK_SEP
        self.block_mode = True
        self.flows = 0
        self.is_match_actionable = self.is_block_match_actionable

    def __repr__(self):
        return "block" if self.block_mode else "flow"

    def next_actionable_line(self, line_number, line_text):
        comments = 0
        while True:
            m = RE_LINE_SPLIT.match(line_text)
            leader_start, leader_end = m.span(1)
            start, end = m.span(3)
            if leader_start < 0:  # No special leading token
                return line_number, start, end, line_text, comments, None
            leader = line_text[leader_start]
            if leader == "#":
                comments += 1
                return None, None, None, None, comments, "comment"
            if leader == "%":
                if leader_start != 0:
                    raise zyaml.ParseError("Directive must not be indented")
                return line_number, start, end, line_text, comments, line_text
            token = None
            if leader_end < end and line_text[leader_end] != " ":  # -, --- and ... need either a space after, or be at end of line
                start = leader_start
            elif leader_start + 1 == leader_end:  # '-' has no further constraints
                token = "-"
            elif leader_start != 0:  # --- and ... are tokens only if they start the line
                start = leader_start
            else:
                token = line_text[leader_start:leader_end]
            return line_number, start, end, line_text, comments, token

    @staticmethod
    def is_block_match_actionable(seen_colon, start, matched, mstart, rstart, rend, line_text):
        if matched == ":":  # ':' only applicable once, either at end of line or followed by a space
            if seen_colon:
                return True, False
            if rstart == rend or line_text[mstart + 1] == " ":
                if seen_colon is None and start == mstart:
                    raise zyaml.ParseError("Incomplete explicit mapping pair")
                return True, True
            return False, False
        return bool(seen_colon), start == mstart  # All others are applicable only when not following a simple key

    @staticmethod
    def is_flow_match_actionable(seen_colon, start, matched, mstart, rstart, rend, line_text):
        # ! & * : [ ] { } ,
        if matched == ":":  # Applicable either followed by space or preceeded by a " (for json-like flows)
            return seen_colon, rstart == rend or line_text[mstart - 1] == '"' or line_text[mstart + 1] == " "
        return bool(seen_colon), start == mstart or matched in "{}[],"

    def next_match(self, start, end, line_text):
        rstart = start
        seen_colon = None
        while start < end:
            m = self.line_regex.search(line_text, rstart)
            if m is None:
                break
            mstart, mend = m.span(1)  # span1: what we just matched, span2: the rest (without spaces)
            matched = line_text[mstart]
            if matched == "#":
                if line_text[mstart - 1] == " ":
                    if start < mstart:
                        yield start, line_text[start:mstart].rstrip()
                    return
                continue
            rstart, rend = m.span(2)
            seen_colon, actionable = self.is_match_actionable(seen_colon, start, matched, mstart, rstart, rend, line_text)
            if actionable:
                if start < mstart:
                    yield start, line_text[start:mstart].rstrip()
                yield mstart, line_text[mstart:mend]
                start = rstart
        if start < end:
            yield start, line_text[start:end]

    def print_matches(self, text):
        count = 0
        line_number, start, end, upcoming, comments, token = self.next_actionable_line(1, text)
        if token is not None:
            print("token: %s" % token)
        if line_number is None:
            return
        if start == end:
            print("-- empty line --")
            return
        for start, text in self.next_match(start, end, text):
            print("%s %s: '%s'" % (self, start, text))
            if text in "[{":
                self.flows += 1
                if self.flows == 1:
                    self.line_regex = RE_FLOW_SEP
                    self.is_match_actionable = self.is_flow_match_actionable
            elif text in "]}":
                self.flows -= 1
                if self.flows == 0:
                    self.line_regex = RE_BLOCK_SEP
                    self.is_match_actionable = self.is_block_match_actionable
            count += 1
        if count > 3:
            print("-- %s entries" % count)


@main.command()
@click.argument("text", nargs=-1)
def regex(text):
    """Troubleshoot token regexes"""
    try:
        text = " ".join(text)
        text = codecs.decode(text, "unicode_escape")
        s = ScannerMock()
        s.print_matches(text)
    except zyaml.ParseError as e:
        print("error: %s" % e)


if __name__ == "__main__":
    main()
