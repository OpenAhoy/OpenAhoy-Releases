"""Official newspic shape, separate from the older news-only writers."""
import re
from copy import deepcopy

from .contracts import WCEError
from .editor_contracts import crop_info
from .own_draft_wire import reference_valid


def image_ids(article, *, synthetic=False):
    info = article.get('image_info')
    rows = info.get('image_list') if type(info) is dict else None
    if (type(rows) is not list or not 1 <= len(rows) <= 20
            or any(type(row) is not dict or not reference_valid(row.get('image_media_id'), synthetic)
                   for row in rows)):
        raise WCEError('WECHAT_PICTURE_IMAGES_INVALID')
    return [row['image_media_id'] for row in rows]


def picture_fields(article, *, synthetic=False, writing=False):
    title, content = article.get('title'), article.get('content')
    if type(title) is not str or not title.strip() or len(title) > (32 if writing else 128):
        raise WCEError('DRAFT_TITLE_POLICY')
    if type(content) is not str or len(content) >= 20_000 or len(content.encode()) >= 1_000_000:
        raise WCEError('DRAFT_CONTENT_POLICY')
    if writing and re.search(r'<(?:\s*[/!?]|[a-z])', content, re.IGNORECASE):
        raise WCEError('WECHAT_PICTURE_TEXT_REQUIRED')
    images = image_ids(article, synthetic=synthetic)
    result = {'article_type': 'newspic', 'title': title, 'content': content,
              'image_info': {'image_list': [{'image_media_id': media_id} for media_id in images]}}
    for name in ('need_open_comment', 'only_fans_can_comment'):
        if name in article:
            if type(article[name]) is not int or article[name] not in (0, 1):
                raise WCEError('GROUP_COMMENT_UNVERIFIED')
            result[name] = article[name]
    if 'author' in article:
        if type(article['author']) is not str or len(article['author']) > (16 if writing else 64):
            raise WCEError('WECHAT_PICTURE_AUTHOR_INVALID')
        result['author'] = article['author']
    if 'cover_info' in article and (writing or article['cover_info'] not in ({}, {'crop_percent_list': []})):
        crop_info(article['cover_info'], additional_ratios={'16_9'})
        result['cover_info'] = deepcopy(article['cover_info'])
    if 'product_info' in article and (writing or article['product_info'] not in ({}, {'footer_product_info': {}})):
        product = article['product_info']
        footer = product.get('footer_product_info') if type(product) is dict else None
        key = footer.get('product_key') if type(footer) is dict else None
        if (type(footer) is not dict or type(key) is not str or not key or len(key) > 1024
                or writing and (set(product) != {'footer_product_info'} or set(footer) != {'product_key'})):
            raise WCEError('WECHAT_PRODUCT_INVALID')
        result['product_info'] = {'footer_product_info': {'product_key': key}}
    return result
