"""Only bounded document locations and closed technical rules cross processes."""
from .contracts import WCEError
from .normal_html_limits import ARTICLES, IMAGE_POSITIONS

JPEG_REPAIR = {
    'HTML_IMPORT_JPEG_APP1': '检查 EXIF/XMP 元数据，从原图重新导出时保留正确方向。',
    'HTML_IMPORT_JPEG_APP2': '检查 ICC 色彩配置是否完整，从原图导出时保留颜色或转换为 sRGB。',
    'HTML_IMPORT_JPEG_APP13': '检查 Photoshop/IPTC 资源块，重新导出传输副本并保留原图。',
    'HTML_IMPORT_JPEG_TRUNCATED': '内嵌 JPEG 不完整，请用完整原图重新生成 HTML。',
    'HTML_IMPORT_JPEG_LIMIT': '内嵌 JPEG 超出本地解码尺寸或字节边界，请用符合边界的传输副本。',
    'HTML_IMPORT_JPEG_INVALID': '无法解码内嵌 JPEG，请用可正常解码的 RGB JPEG 或 PNG 重新生成 HTML。',
}


def location(error):
    result={}
    if error.code.startswith('HTML_') or error.code.startswith('DOCUMENT_MARKDOWN_'):
        for key in ('line','column'):
            value=getattr(error,key,None)
            if type(value) is int and 1<=value<=12001:result[key]=value
    if error.code in JPEG_REPAIR:
        result['repair'] = JPEG_REPAIR[error.code]
    if error.code.startswith(('HTML_IMPORT_', 'HTMLQA_')):
        for key, maximum in (('article_position', ARTICLES), ('image_position', IMAGE_POSITIONS)):
            value = getattr(error, key, None)
            if type(value) is int and 1 <= value <= maximum:
                result[key] = value
    if error.code in {'DIRECTOR_CHARACTER_MANIFEST_INVALID', 'DIRECTOR_CHARACTER_DUPLICATE',
                      'DIRECTOR_ASSET_OUTSIDE_PROJECT', 'BOOTSTRAP_UNSAFE_PATH'}:
        field = getattr(error, 'manifest_field', None)
        if field in ('json', 'manifest', 'schema', 'assets', 'entry', 'id', 'character', 'character.id',
                     'character.name', 'character.series', 'character.aliases', 'use', 'initial_status',
                     'label', 'description', 'source', 'path', 'sha256'):
            result['manifest_field'] = field
            if field == 'use':
                from .character_library import USE
                result['allowed_values'] = list(USE['enum'])
            position = getattr(error, 'manifest_position', None)
            if type(position) is int and 1 <= position <= 4 * 1024 * 1024:
                result['manifest_position'] = position
    from .html_technical_standard import safe_diagnostic
    technical=safe_diagnostic(getattr(error,'technical_rule',None),error.code)
    if technical is not None:result['technical_rule']=technical
    return result


def restore(code, fields):
    error=WCEError(code)
    if type(fields) is not dict or set(fields)-{'line','column','technical_rule',
            'article_position','image_position','manifest_position','manifest_field','repair','allowed_values'}:
        raise WCEError('CONNECTION_RESULT_UNDETERMINED')
    for key,value in fields.items():setattr(error,key,value)
    if location(error)!=fields:
        raise WCEError('CONNECTION_RESULT_UNDETERMINED')
    return error
