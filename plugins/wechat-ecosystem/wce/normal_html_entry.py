"""Trusted local HTML preparation for the existing persistent connection route.

Each selected HTML is self-contained; no URL, HTML directive or data item can
select another local file. This module never uploads, saves or publishes.
"""
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import tempfile

from .contracts import WCEError
from .prepared_contracts import ID, DIGEST
from .tools import schema
from .html_document import NORMAL_ARTICLE
from .service import canonical

_METADATA={k:deepcopy(NORMAL_ARTICLE['properties'][k]) for k in
    ('author','digest','source_url','cover_info','cover_dimensions','editorial_intent')}
HTML_SOURCE=schema({'absolute_path':{'type':'string','minLength':1,'maxLength':4096},
    'expected_sha256':DIGEST,'article_id':deepcopy(NORMAL_ARTICLE['properties']['id'])}, {'metadata_title':{'type':'string','minLength':1,'maxLength':128},
    'metadata':schema({},_METADATA)})
ARGUMENTS=schema({'connection_id':ID,'request_key':ID,
    'html_sources':{'type':'array','minItems':1,'maxItems':8,'items':HTML_SOURCE}})


def _key(request_key,article_index,role,position):
    return 'html-'+sha256(canonical([request_key,article_index,role,position]).encode()).hexdigest()


def prepare(policy, arguments, send, scratch_root=None):
    """Extract all members first, then once prepare the complete ordered group.

    send is the original broker transport. Calls are local receive/prepare only;
    stable derived request keys make interrupted local intake resumable.
    """
    from .normal_html_import import acquire,bind_assets
    from .normal_html_limits import POLICY
    from .own_connection_input import stage
    from .own_bootstrap_security import path_check
    from .own_connection_registry import mkdir
    from .prepared_contracts import strict_validate
    strict_validate(arguments,ARGUMENTS,-16)
    if len({s['article_id'] for s in arguments['html_sources']})!=len(arguments['html_sources']):
        raise WCEError('DOCUMENT_INVALID')
    policy.check()
    if scratch_root is None:
        scratch_root=policy.root/'html-input'
        if not os.path.lexists(scratch_root):mkdir(policy.root,scratch_root.name)
    scratch_root=Path(scratch_root);path_check(scratch_root,True)
    with tempfile.TemporaryDirectory(prefix='html-',dir=scratch_root) as selected:
        root=Path(selected);prepared=[]
        for index,source in enumerate(arguments['html_sources']):
            policy.check();path=Path(source['absolute_path'])
            if not path.is_absolute() or '..' in path.parts:raise WCEError('INVALID_LOCAL_FILE')
            scratch=root/str(index);scratch.mkdir(mode=0o700)
            prepared.append(acquire(path.parent,path.name,source['expected_sha256'],scratch,
                metadata_title=source.get('metadata_title'),guard=policy.check))
        # Complete pure field checks for every member before any local receive.
        from .html_technical_standard import validate_metadata
        for index,(source,result) in enumerate(zip(arguments['html_sources'],prepared)):
            validate_metadata({'title':result['title'],**source.get('metadata',{})},
                article_count=len(prepared),prefix='articles['+str(index)+']')
        articles=[]
        for index,(source,result) in enumerate(zip(arguments['html_sources'],prepared)):
            refs={};cover_ref=None
            roles=[('cover',0,result['images'][0])]+[('body',i,image) for i,image in enumerate(result['images'])]
            for role,position,image in roles:
                policy.check()
                relative=stage(policy,image['path'],image['mime'])
                received=send('own.assets.receive',{'connection_id':arguments['connection_id'],
                    'request_key':_key(arguments['request_key'],index,role,position),'role':role,
                    'declared_type':image['mime'],'relative_path':relative})
                if type(received) is not dict or type(received.get('asset_ref')) is not str:
                    raise WCEError('HTML_IMPORT_ASSET_RESULT')
                if role=='cover':cover_ref=received['asset_ref']
                else:refs[image['slot']]=received['asset_ref']
            doc=bind_assets(result,source['article_id'],cover_ref,refs,metadata=source.get('metadata'))
            articles.extend(doc['articles'])
        document={'format':3,'policy':POLICY,'articles':articles}
        from .documents import normalize
        normalize(document);policy.check()
        # Exactly one prepare for all 1..8 articles. No single-article split.
        return send('own.documents.prepare',{'connection_id':arguments['connection_id'],
            'request_key':arguments['request_key'],'document':document})
