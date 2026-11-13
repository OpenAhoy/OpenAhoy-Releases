"""Deterministic, evidence-bounded publication comparison, separate from strict."""
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .contracts import WCEError
from .service import digest
from .editor_contracts import geometry
from .publication_contract import QUALITY_PROFILE, fail


class Events(HTMLParser):
    def __init__(self, html, expected_images=None):
        super().__init__(convert_charrefs=True)
        self.events, self.images, self.anchors = [], [], []
        self.text_offset, self.anchor_stack = 0, []
        self.expected_images = expected_images
        self.feed(html); self.close()

    def handle_starttag(self, tag, attrs):
        # Links carry content: neither their destination/style nor their DOM
        # position/count may disappear under a wrapper-normalization rule.
        value = dict(attrs)
        if len(value) != len(attrs): fail('PUBLICATION_HTML_UNVERIFIED')
        if tag == 'a':
            if self.anchor_stack: fail('PUBLICATION_HTML_UNVERIFIED')
            self.anchor_stack.append((self.text_offset,tuple(sorted(value.items()))))
        if tag == 'img':
            if 'data-src' in value:
                if 'src' in value: fail('PUBLICATION_HTML_UNVERIFIED')
                value['src'] = value.pop('data-src')
            if 'src' not in value: fail('PUBLICATION_HTML_UNVERIFIED')
            if self.expected_images is not None:
                index = len(self.images)
                if index >= len(self.expected_images) or not same_image(self.expected_images[index], value['src']):
                    fail('PUBLICATION_IMAGE_UNVERIFIED')
                value['src'] = self.expected_images[index]
            self.images.append(value['src'])
        self.events.append(('start',tag,tuple(sorted(value.items()))))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in {'img','br','hr'}: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'a':
            if not self.anchor_stack: fail('PUBLICATION_HTML_UNVERIFIED')
            start,attrs = self.anchor_stack.pop()
            self.anchors.append((start,self.text_offset,attrs))
        if tag not in {'img','br','hr'}:
            self.events.append(('end',tag))

    def handle_data(self, data):
        self.text_offset += len(data)
        if self.events and self.events[-1][0]=='text':
            self.events[-1]=('text',self.events[-1][1]+data)
        else: self.events.append(('text',data))

    def handle_comment(self, value): fail('PUBLICATION_HTML_UNVERIFIED')
    def handle_decl(self, value): fail('PUBLICATION_HTML_UNVERIFIED')
    def unknown_decl(self, value): fail('PUBLICATION_HTML_UNVERIFIED')


def same_image(expected, actual):
    if expected == actual: return True
    if any(type(url) is not str or any(ord(c)<=32 or ord(c)==127 or c.isspace() for c in url) for url in (expected,actual)):
        return False
    try:
        first, second = urlsplit(expected), urlsplit(actual)
        # Actual sealed six-article evidence: only http->https and final 0->640
        # on the very same qpic path, with the identical query. No URL fetch or
        # claim about exact remote raster bytes is made.
        return (first.hostname == second.hostname == 'mmbiz.qpic.cn'
            and first.scheme in {'http','https'} and second.scheme == 'https'
            and first.username is None and second.username is None
            and first.password is None and second.password is None
            and first.port is None and second.port is None
            and not first.fragment and not second.fragment
            and first.path.endswith('/0') and second.path == first.path[:-1]+'640'
            and first.query == second.query)
    except (TypeError, ValueError): return False


def compare(expected, actual, document, policy):
    if (type(expected) is not dict or type(actual) is not dict
            or set(expected) != {'articles'} or set(actual) != {'articles'}):
        fail('PUBLICATION_DRAFT_UNVERIFIED')
    e, a = expected['articles'], actual['articles']
    if len(e) != len(a) or len(a) != len(document['articles']) or not 1 <= len(a) <= 8:
        fail('PUBLICATION_DRAFT_UNVERIFIED')
    differences, summaries = [], []
    for index,(before,after,article) in enumerate(zip(e,a,document['articles'])):
        if set(before) != set(after): fail('PUBLICATION_DRAFT_UNVERIFIED')
        for field in set(before)-{'content','digest','cover_info'}:
            if before[field] != after[field]: fail('PUBLICATION_DRAFT_UNVERIFIED')
        original = Events(before['content'])
        current = Events(after['content'],original.images)
        if (any(anchor not in original.anchors for anchor in current.anchors)
                or original.anchor_stack or current.anchor_stack):
            fail('PUBLICATION_HTML_UNVERIFIED')
        if original.events != current.events: fail('PUBLICATION_HTML_UNVERIFIED')
        if before['content'] != after['content']:
            differences.append({'article':index+1,'rule':'HTML_ENTITY_ATTRIBUTE_ORDER_AND_IMAGE_PROJECTION_V2'})
        if before.get('cover_info') != after.get('cover_info'):
            if ('cover_dimensions' not in article or not geometry(before.get('cover_info'),after.get('cover_info'),article['cover_dimensions'])):
                fail('PUBLICATION_CROP_UNVERIFIED')
            differences.append({'article':index+1,'rule':'CROP_WITHIN_ONE_SOURCE_PIXEL_V1'})
        if before.get('digest') != after.get('digest'):
            if policy['summary_mode'] != 'PLATFORM_AUTO_ACCEPTED':
                fail('PUBLICATION_SUMMARY_REQUIRES_EDIT')
            if type(after.get('digest')) is not str:
                fail('PUBLICATION_SUMMARY_UNVERIFIED')
            differences.append({'article':index+1,'rule':'HUMAN_POLICY_PLATFORM_SUMMARY_V1'})
        if policy['summary_mode']=='EMPTY_REQUIRED' and after.get('digest'):
            fail('PUBLICATION_SUMMARY_REQUIRES_EDIT')
        if policy['originality']=='required':
            # Neither an author nor the old editorial hint is a platform claim.
            fail('PUBLICATION_ORIGINALITY_UNVERIFIED')
        summaries.append({'article':index+1,'actual_summary':after.get('digest',''),
            'summary_state':('PLATFORM_AUTO_ACCEPTED' if policy['summary_mode']=='PLATFORM_AUTO_ACCEPTED'
                             else 'CUSTOM_MATCHED' if after.get('digest') else 'EMPTY_CONFIRMED'),
            'originality':'NOT_REQUESTED'})
    return {'profile':QUALITY_PROFILE,'state':'DETERMINISTIC_MATCH',
        'snapshot_sha':digest(actual),'expected_sha':digest(expected),
        'differences':differences,'summaries':summaries,
        'strict_readback_unchanged':True,'remote_pixels_verified':False,
        'visual_scope':'SOURCE_AND_LOCAL_PROJECTION_ONLY'}
