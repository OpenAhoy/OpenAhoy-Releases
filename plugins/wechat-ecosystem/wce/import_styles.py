"""Finite CSS language for a declared mobile projection; never executes CSS."""
import re
from .contracts import WCEError

POLICY = 'WCE_IMPORTED_HTML_V1'
FONT = 'Arial,"PingFang SC",sans-serif'
INLINE_FONT = 'PingFang SC,sans-serif'
SYSTEM_FONT = '-apple-system,BlinkMacSystemFont,sans-serif'
INHERITED = {'font-family','font-size','font-weight','font-style','line-height','color','text-align','overflow-wrap','text-decoration','letter-spacing'}
COLOR = re.compile(r'(?:#[a-f0-9]{3}|#[a-f0-9]{6}|black|white)')
NUM = re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,4})?')
TAGS = {'body','article','section','p','h1','h2','h3','img','a','span','strong','em','figure','figcaption','br'}
FIGURE_WIDTH = 'var(--figure-width,400px)'


def figure_width(value,position=(1,0)):
    match=re.fullmatch(r'--figure-width:('+NUM.pattern+r')px;?',value)
    if not match or not numeric(match[1]+'px',1,1024):fail(position)
    return match[1]+'px'


def fail(position=(1,0)):
    error = WCEError('HTML_IMPORT_CSS_UNSUPPORTED'); error.line,error.column=position[0],position[1]+1
    raise error


def numeric(value,low,high,unit='px'):
    if unit:
        if not value.endswith(unit): return False
        value=value[:-len(unit)]
    return bool(NUM.fullmatch(value)) and low<=float(value)<=high


def declaration(prop,val,tag,position=(1,0)):
    val=' '.join(val.strip().split())
    valid=False
    if prop=='font-family': valid=val in (FONT, INLINE_FONT, SYSTEM_FONT)
    elif prop in ('color','background-color'):
        val=val.lower();valid=bool(COLOR.fullmatch(val))
    elif prop=='font-size': valid=numeric(val,10,36)
    elif prop=='line-height': valid=numeric(val,1,3,'')
    elif prop=='letter-spacing': valid=numeric(val,0,2)
    elif prop in ('margin-top','margin-bottom','margin-left','margin-right','padding-top','padding-bottom','padding-left','padding-right'):
        valid=val=='0' or numeric(val,0,64) or prop in ('margin-left','margin-right') and val=='auto'
    elif prop in ('font-weight','font-style','text-align','overflow-wrap','text-decoration','box-sizing','flex-direction'):
        valid=val in {'font-weight':{'normal','bold','400','500','600','700'},'font-style':{'normal','italic'},
                     'text-align':{'left','center','right','justify'},'overflow-wrap':{'normal','anywhere','break-word'},
                     'text-decoration':{'none','underline'},'box-sizing':{'border-box','content-box'},'flex-direction':{'column'}}[prop]
    elif prop=='max-width': valid=val in ('100%','none') or numeric(val,1,1024)
    elif prop=='display': valid=val=='block' or tag in ('section','article') and val=='flex'
    elif prop=='width': valid=tag in ('img','article','section') and val=='100%' or tag=='img' and val=='90.91%'
    elif prop=='height': valid=tag=='img' and val=='auto'
    elif prop=='break-inside': valid=tag in ('figure','section') and val=='avoid'
    if not valid: fail(position)
    return val


def declarations(text,tag,position=(1,0),canonical=False,figure_variable=False,normal=False):
    lexical=text.replace(FIGURE_WIDTH,'400px') if figure_variable and not canonical else text
    forbidden='\\@()<>!{}' if normal and not canonical else '\\/@()<>!{}'
    if not text or (not normal and len(text)>8192) or any(c in lexical for c in forbidden) or '/*' in text: fail(position)
    result=[]
    parts=text.split(';')
    if not parts[-1].strip(): parts.pop()
    if not len(parts) or not normal and len(parts)>32: fail(position)
    for part in parts:
        if part.count(':')!=1: fail(position)
        prop,val=(x.strip() for x in part.split(':',1))
        if not re.fullmatch('[a-z-]+',prop): fail(position)
        if not canonical and prop=='letter-spacing':
            if re.fullmatch(r'\.[0-9]{1,4}px',val): val='0'+val
            elif val=='0': val='0px'
        if prop=='background' and not canonical: prop='background-color'
        if prop=='font' and normal and not canonical:
            # A normal HTML source may use CSS's size/line-height shorthand.
            # Decode only the already-supported unitless line height and font
            # families; never pass arbitrary CSS or remote font requests through.
            match=re.fullmatch('('+NUM.pattern+r'px)/('+NUM.pattern+r')\s+(.+)',val)
            if not match:fail(position)
            font=[('font-style','normal'),('font-weight','normal'),
                  ('font-size',match[1]),('line-height',match[2]),('font-family',match[3])]
            result.extend((name,declaration(name,value,tag,position)) for name,value in font)
        elif prop in ('margin','padding') and not canonical:
            words=val.split()
            if not 1<=len(words)<=4: fail(position)
            expanded=words*4 if len(words)==1 else [words[0],words[1],words[0],words[1]] if len(words)==2 else [*words,words[1]] if len(words)==3 else words
            for side,item in zip(('top','right','bottom','left'),expanded):
                if prop=='margin' and tag=='article' and side in ('top','bottom') and item=='auto': item='0'
                result.append((prop+'-'+side,declaration(prop+'-'+side,item,tag,position)))
        elif figure_variable and not canonical and prop=='max-width' and val==FIGURE_WIDTH:
            result.append((prop,val))
        else: result.append((prop,declaration(prop,val,tag,position)))
    return result


def inline_style(text,tag,position=(1,0)):
    if len(text.encode())>2048: fail(position)
    values=declarations(text,tag,position,True)
    if len({p for p,_ in values})!=len(values): fail(position)
    result=dict(values)
    if ('flex-direction' in result or result.get('display')=='flex') and not (result.get('display')=='flex' and result.get('flex-direction')=='column'): fail(position)
    if tag=='a' and not {'color','text-decoration'}<=set(result): fail(position)
    return ''.join(p+':'+v+';' for p,v in sorted(result.items()))


def stylesheet(text,viewport=390,*,normal=False):
    """A brace/token parser for simple selectors and one finite media grammar."""
    if type(text) is not str or not text or (not normal and len(text.encode())>8192): fail()
    rules=[]; index=0; order=0
    def point(i):
        before=text[:i]
        return before.count('\n')+1,len(before.rsplit('\n',1)[-1])
    def space(i):
        while i<len(text) and text[i].isspace(): i+=1
        return i
    def block(i,media=False):
        nonlocal order
        while True:
            i=space(i)
            if i==len(text):
                if media: fail()
                return i
            if text[i]=='}':
                if not media: fail()
                return i+1
            if text.startswith('@media',i):
                if media: fail()
                match=re.match(r'@media\s*\(max-width\s*:\s*(430|675)px\)\s*\{',text[i:])
                if not match: fail()
                i=block(i+match.end(),int(match[1])); continue
            start=i
            while i<len(text) and text[i]!='{':
                if text[i] in '{}@;': fail()
                i+=1
            if i==len(text): fail()
            selector=text[start:i].strip(); i+=1
            selectors=[s.strip() for s in selector.split(',')]
            if len(selectors)>1 and (len(selectors)!=2 or set(selectors)!={'figcaption','.source'}):fail(point(start))
            if any(s not in {'*','.source','.caption','.source a','.backend','.sources-title','.narrow img','article>img',*TAGS-{'section'}} for s in selectors): fail(point(start))
            start=i
            while i<len(text) and text[i]!='}':
                if text[i]=='{': fail()
                i+=1
            if i==len(text): fail()
            tag=selectors[0] if selectors[0] in TAGS else 'a' if selectors[0]=='.source a' else 'img' if selectors[0] in ('.narrow img','article>img') else 'p'
            props=declarations(text[start:i],tag,point(start),figure_variable=selectors==['.narrow img'],normal=normal)
            if not media or viewport<=media:
                rules.extend((s,props,order) for s in selectors)
            order+=1; i+=1
            if not normal and (order>64 or len(rules)>64 or sum(len(x[1]) for x in rules)>256): fail()
    block(0)
    return rules


def matches(selector,node,ancestors):
    if selector=='*': return True
    if selector=='article>img': return node['tag']=='img' and bool(ancestors) and ancestors[-1]['tag']=='article'
    if selector.startswith('.'):
        if selector=='.narrow img': return node['tag']=='img' and any(a['tag']=='figure' and a.get('attrs',{}).get('class')=='narrow' for a in ancestors)
        if selector=='.source a': return node['tag']=='a' and any('source' in a.get('attrs',{}).get('class','').split() for a in ancestors)
        return selector[1:] in node['attrs'].get('class','').split()
    return selector==node['tag']


def computed(node,ancestors,parent,rules):
    result={p:v for p,v in parent.items() if p in INHERITED}; ranked={}
    # UA values are explicit for tags whose defaults override inherited values.
    if node['tag'] in ('h1','h2','h3','strong'): result['font-weight']='bold'
    if node['tag']=='em': result['font-style']='italic'
    if node['tag']=='a': result.update(color='#0000ee',**{'text-decoration':'underline'})
    for selector,props,order in rules:
        if not matches(selector,node,ancestors): continue
        specificity=101 if selector=='.source a' else 100 if selector.startswith('.') else 0 if selector=='*' else 2 if selector=='article>img' else 1
        for declaration_index,(prop,val) in enumerate(props):
            if val==FIGURE_WIDTH:
                figure=next(a for a in reversed(ancestors) if a['tag']=='figure' and a.get('attrs',{}).get('class')=='narrow')
                val=figure_width(figure['attrs']['style']) if 'style' in figure['attrs'] else '400px'
            priority=(specificity,order,declaration_index)
            if prop not in ranked or priority>=ranked[prop]:result[prop]=val;ranked[prop]=priority
    return result
