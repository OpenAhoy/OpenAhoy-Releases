"""An immutable, named reading profile; source layout remains the default."""
from .contracts import WCEError
from .service import digest

PROFILE = 'reading-spacious-v1'
PARAMETERS = {
    'renderer': 'WCE_READING_SPACIOUS_V1',
    'tags': {
        'body': {'font-size': '16px', 'line-height': '1.8', 'letter-spacing': '0.5px'},
        'p': {'font-size': '16px', 'line-height': '1.8', 'letter-spacing': '0.5px', 'margin-bottom': '18px'},
        'h1': {'font-size': '26px', 'line-height': '1.4', 'letter-spacing': '0px', 'margin-bottom': '20px'},
        'h2': {'font-size': '20px', 'line-height': '1.5', 'letter-spacing': '0px',
               'padding-top': '24px', 'padding-bottom': '12px'},
        'h3': {'font-size': '18px', 'line-height': '1.5', 'letter-spacing': '0px',
               'padding-top': '22px', 'padding-bottom': '10px'},
        'img': {'margin-top': '12px', 'margin-bottom': '20px'}},
    'classes': {name: {'font-size': '12px', 'line-height': '1.6', 'letter-spacing': '0px',
                      'margin-bottom': '12px'} for name in ('source', 'caption')}}
PARAMETER_SHA256 = digest(PARAMETERS)


def apply(node, style, profile):
    if type(profile) is not str or profile not in ('source', PROFILE):
        raise WCEError('HTML_IMPORT_LAYOUT_PROFILE')
    if profile == 'source':
        return style
    output = dict(style)
    output.update(PARAMETERS['tags'].get(node['tag'], {}))
    for name in node.get('attrs', {}).get('class', '').split():
        output.update(PARAMETERS['classes'].get(name, {}))
    return output
