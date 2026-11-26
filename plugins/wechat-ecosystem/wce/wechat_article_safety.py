"""Check body changes without stripping original WeChat blocks."""
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .contracts import WCEError

FORMATTING = frozenset('p div section h1 h2 h3 h4 h5 h6 strong b em i u s ul ol li blockquote br pre code span hr'.split())
HARD_VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())


class PreservedMarkup(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=False)
        self.protected = []
        self.capture = []
        self.stack = []
        self.feed(content)
        self.close()
        if self.stack:
            raise WCEError('WECHAT_DRAFT_EDIT_OPEN_OFFICIAL')

    def handle_starttag(self, tag, attrs):
        special = tag not in FORMATTING or any(
            key not in {'style','class','dir','lang','title','aria-label'} for key,_ in attrs)
        raw = self.get_starttag_text()
        if self.stack or special:
            self.capture.append(raw)
            if tag not in HARD_VOID:
                self.stack.append(tag)
            elif not self.stack:
                self._finish()
        elif attrs:
            # Existing style and class are allowed but edits cannot introduce
            # independently active markup or arbitrary stylesheet declarations.
            self.protected.append(('format',tag,tuple(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in HARD_VOID and self.stack and self.stack[-1]==tag:
            self.stack.pop()
            if not self.stack:
                self._finish()

    def handle_endtag(self, tag):
        if self.stack:
            self.capture.append('</'+tag+'>')
            if self.stack[-1]==tag:
                self.stack.pop()
                if not self.stack:
                    self._finish()

    def handle_data(self, data):
        if self.stack:
            self.capture.append(data)

    def handle_entityref(self, name):
        self.handle_data('&'+name+';')

    def handle_charref(self, name):
        self.handle_data('&#'+name+';')

    def handle_comment(self, data):
        data='<!--'+data+'-->'
        if self.stack:
            self.capture.append(data)
        else:
            self.protected.append(('comment',data))

    def _finish(self):
        self.protected.append(('original',''.join(self.capture)))
        self.capture.clear()


def validate_manual_body(original, updated):
    if PreservedMarkup(original).protected != PreservedMarkup(updated).protected:
        raise WCEError('WECHAT_DRAFT_EDIT_PRESERVE_BLOCKS')


def image_url(value):
    if not isinstance(value,str):
        return ''
    try:
        parsed=urlsplit(value)
        return value if (parsed.scheme=='https' and (parsed.hostname in {'mmbiz.qpic.cn','mmbiz.qlogo.cn'})
                         and not parsed.username and not parsed.password and parsed.port in (443,None)) else ''
    except ValueError:
        return ''
