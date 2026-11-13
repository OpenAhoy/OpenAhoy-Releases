"""Verified draft/get subset and test-only single-news draft/add candidate.

The response does not echo media_id. Each immutable codec is bound to the
requested object; response data never invents a platform reference. News-only
projection and size/field requirements below are candidate acceptance policy,
not claims that WeChat marks those response fields mandatory.
"""
from dataclasses import dataclass, replace
import json
import re
from typing import ClassVar
from urllib.parse import urlencode

from .contracts import WCEError
from .http_transport import HTTPRequest, MAX_BODY, Operation, WireReply

DRAFT_GET_SOURCE = "https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_getdraft.html"
DRAFT_GET_SHA256 = "f31731dde6868b530a5dff60b77d427224dae63752ae64817c923e3d27ece8b6"
ERROR_SOURCE = "https://developers.weixin.qq.com/doc/oplatform/developers/errCode/"
TOKEN_INVALID_CODES = {40001, 40014, 42001}
DRAFT_ADD_SOURCE = "https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html"
DRAFT_ADD_SHA256 = "cb18600f28cf8a2bfbe5680f27eb077f7722d8d3728f26e21888cd3565f784bc"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


@dataclass(frozen=True)
class DraftGetCodec:
    media_id: str

    def __post_init__(self):
        if (not isinstance(self.media_id, str) or not self.media_id.strip()
                or len(self.media_id) > 128 or any(ord(c) < 32 for c in self.media_id)):
            raise WCEError("INVALID_DRAFT_REFERENCE")

    def request(self, payload, token):
        if payload != {"media_id": self.media_id}:
            raise WCEError("DRAFT_OBJECT_CONTEXT_MISMATCH")
        return HTTPRequest("POST", "/cgi-bin/draft/get?" + urlencode({"access_token": token.reveal_for_adapter()}),
                           {"Content-Type": "application/json; charset=utf-8"},
                           json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"))

    def response(self, response):
        try:
            if (not 200 <= response.status < 300 or not isinstance(response.body, bytes)
                    or len(response.body) > MAX_BODY):
                return WireReply()
            value = json.loads(response.body.decode("utf-8"), object_pairs_hook=unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                return WireReply()
            code = value.get("errcode", 0)
            if type(code) is not int:
                return WireReply()
            if code in TOKEN_INVALID_CODES:
                return WireReply(token_invalid=True)
            if code != 0:
                return WireReply()  # no raw errmsg or guessed rejection semantics
            items = value.get("news_item")
            if not isinstance(items, list) or not 1 <= len(items) <= 10:
                return WireReply()
            projected = []
            for item in items:
                if not isinstance(item, dict) or item.get("article_type", "news") != "news":
                    return WireReply()
                article = {key: item.get(key) for key in ("title", "content", "thumb_media_id")}
                article.update({key: item.get(key, "") for key in ("author", "digest")})
                if any(not isinstance(field, str) for field in article.values()):
                    return WireReply()
                if not article["title"].strip() or not article["content"].strip() or not article["thumb_media_id"].strip():
                    return WireReply()
                if (len(article["title"]) > 256 or len(article["author"]) > 256
                        or len(article["digest"]) > 4096 or len(article["thumb_media_id"]) > 128
                        or len(article["content"]) >= 20000 or len(article["content"].encode("utf-8")) >= 1000000):
                    return WireReply()
                projected.append(article)
            # HTML remains untrusted text; URLs/images are neither opened nor fetched.
            return WireReply(state="SUCCEEDED", items=tuple(projected))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return WireReply()

    def reconcile_payload(self, reference):
        if reference != self.media_id:
            raise WCEError("DRAFT_OBJECT_CONTEXT_MISMATCH")
        return {"media_id": self.media_id}

    def page_payload(self, payload, cursor):
        raise WCEError("DRAFT_GET_HAS_NO_PAGINATION")


def draft_get_operation(media_id):
    """Trusted test/adapter entry only; deliberately absent from MCP tools."""
    return Operation("draft.get", False, DraftGetCodec(media_id), DRAFT_GET_SOURCE, DRAFT_GET_SHA256)


@dataclass(frozen=True)
class NewsArticle:
    """Candidate policy: one news, small UTF-8 text, fixture permanent cover.

    Omitting image_info follows the official news example and remains a
    conditional-field inference. It is not a verified live write schema.
    """
    title: str
    content: str
    thumb_media_id: str
    author: str | None = None
    digest: str | None = None

    def __post_init__(self):
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 32:
            raise WCEError("INVALID_NEWS_TITLE")
        if not isinstance(self.content, str) or not self.content.strip():
            raise WCEError("INVALID_NEWS_CONTENT")
        try:
            if len(self.content.encode("utf-8")) >= 2000:
                raise WCEError("INVALID_NEWS_CONTENT")
        except UnicodeError:
            raise WCEError("INVALID_NEWS_CONTENT") from None
        if not isinstance(self.thumb_media_id, str) or not re.fullmatch(r"mock-material-[a-f0-9]{32}", self.thumb_media_id):
            raise WCEError("FIXTURE_COVER_REQUIRED")
        for value, maximum in ((self.author, 16), (self.digest, 120)):
            if value is not None and (not isinstance(value, str) or len(value) > maximum):
                raise WCEError("INVALID_NEWS_OPTIONAL_FIELD")
        try:
            for value in (self.title, self.author, self.digest):
                if value is not None:
                    value.encode("utf-8")
        except UnicodeError:
            raise WCEError("INVALID_NEWS_OPTIONAL_FIELD") from None

    def payload(self):
        article = {"article_type": "news", "title": self.title, "content": self.content,
                   "thumb_media_id": self.thumb_media_id}
        for key in ("author", "digest"):
            value = getattr(self, key)
            if value is not None:
                article[key] = value
        return {"articles": [article]}


@dataclass(frozen=True)
class DraftAddCodec:
    article: NewsArticle
    test_only: ClassVar[bool] = True

    def __post_init__(self):
        if not isinstance(self.article, NewsArticle):
            raise WCEError("INVALID_NEWS_ARTICLE")

    def request(self, payload, token):
        if payload != self.article.payload():
            raise WCEError("DRAFT_OBJECT_CONTEXT_MISMATCH")
        return HTTPRequest("POST", "/cgi-bin/draft/add?" + urlencode({"access_token": token.reveal_for_adapter()}),
                           {"Content-Type": "application/json; charset=utf-8"},
                           json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"), test_only=True)

    def response(self, response):
        try:
            if not 200 <= response.status < 300 or not isinstance(response.body, bytes) or len(response.body) > MAX_BODY:
                return WireReply()
            value = json.loads(response.body.decode("utf-8"), object_pairs_hook=unique_object,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict) or type(value.get("errcode", 0)) is not int:
                return WireReply()
            code = value.get("errcode", 0)
            if code in TOKEN_INVALID_CODES:
                return WireReply(token_invalid=True)
            if code != 0:
                return WireReply()  # official error bodies do not certify no effect
            reference = value.get("media_id")
            if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", reference):
                return WireReply()
            return WireReply(state="SUCCEEDED", reference=reference)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return WireReply()

    def reconcile_payload(self, reference):
        raise WCEError("DRAFT_ADD_HAS_NO_STATUS_QUERY")

    def page_payload(self, payload, cursor):
        raise WCEError("DRAFT_ADD_HAS_NO_PAGINATION")


def draft_add_operation(article):
    return Operation("draft.add", True, DraftAddCodec(article), DRAFT_ADD_SOURCE, DRAFT_ADD_SHA256, test_only=True)


@dataclass(frozen=True)
class FixtureDraftGetCodec(DraftGetCodec):
    test_only: ClassVar[bool] = True

    def request(self, payload, token):
        return replace(super().request(payload, token), test_only=True)


def fixture_draft_get_operation(media_id):
    return replace(draft_get_operation(media_id), codec=FixtureDraftGetCodec(media_id), test_only=True)
