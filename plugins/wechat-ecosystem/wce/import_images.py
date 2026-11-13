"""Local opaque image decoding/transport candidates, separate from remote proof.

The fixed macOS ImageIO front end (/usr/bin/sips) is an explicit dependency for
JPEG. No token, account, network, image generator or arbitrary program argument.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import zlib

from .contracts import WCEError
from .own_png import decode_png, Raster
from .bounded_file import FileSource, file_state


def fail(): raise WCEError('HTML_IMPORT_IMAGE_UNSUPPORTED')


def decode_import_png(raw):
    """Local RGB8/RGBA8 metadata adapter; never changes remote proof policy.

    Original bytes remain the source/transport identity. Only a transient
    decoding view omits validated full-precision sBIT, background/density and
    the finite standard sRGB/gAMA metadata pair. Original bytes are retained.
    This returns every unpremultiplied RGBA byte without compositing a background.
    """
    if type(raw) is not bytes or not 0<len(raw)<=2097152 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):fail()
    pos=8;count=0;channels=None;seen=False;background=False;idat=False;parts=[raw[:8]]
    ancillary=set();omitted=False
    while pos<len(raw):
        count+=1
        if count>256 or pos+12>len(raw):fail()
        length=int.from_bytes(raw[pos:pos+4],'big');kind=raw[pos+4:pos+8];end=pos+12+length
        if end>len(raw):fail()
        data=raw[pos+8:end-4]
        if zlib.crc32(data,zlib.crc32(kind))&0xffffffff!=int.from_bytes(raw[end-4:end],'big'):fail()
        if count==1:
            if kind!=b'IHDR' or length!=13 or data[8]!=8 or data[9] not in (2,6):fail()
            channels=3 if data[9]==2 else 4
        if kind==b'sBIT':
            if seen or idat or channels is None or data!=b'\x08'*channels:fail()
            seen=True;omitted=True
        elif kind==b'bKGD':
            if background or idat or channels is None or length!=6 or any(v>255 for v in struct.unpack('>HHH',data)):fail()
            background=True;omitted=True
        elif kind in (b'pHYs',b'sRGB',b'gAMA'):
            if kind in ancillary or idat or channels is None:fail()
            if kind==b'pHYs':
                if length!=9:fail()
                x,y,unit=struct.unpack('>IIB',data)
                if x==0 or y==0 or unit not in (0,1):fail()
            elif kind==b'sRGB':
                if length!=1 or data[0]>3:fail()
            elif length!=4 or int.from_bytes(data,'big')!=45455:fail()
            ancillary.add(kind);omitted=True
        else:
            parts.append(raw[pos:end])
        if kind==b'IDAT':idat=True
        pos=end
    if b'gAMA' in ancillary and b'sRGB' not in ancillary:fail()
    return decode_png(b''.join(parts) if omitted else raw)


# Exact empty IPTC dataset and its MD5 resource, with empty Pascal names. This
# is a finite ImageMagick/Photoshop metadata shape, not an opaque APP13 parser.
EMPTY_IPTC_APP13=(b'Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x00'
                 b'8BIM\x04\x25\x00\x00\x00\x00\x00\x10'
                 b'\xd4\x1d\x8c\xd9\x8f\x00\xb2\x04\xe9\x80\x09\x98\xec\xf8\x42\x7e')


def jpeg(raw,generated=False):
    if not 0<len(raw)<=2097152 or not raw.startswith(b'\xff\xd8') or not raw.endswith(b'\xff\xd9'):fail()
    i=2;dimensions=None;segments=[];scans=0;count=0;exif=[];empty_iptc=False
    while i<len(raw):
        start=i;count+=1
        if count>1024 or raw[i]!=255:fail()
        while i<len(raw) and raw[i]==255:i+=1
        if i==len(raw):fail()
        marker=raw[i];i+=1
        if marker==0xd9:
            if i!=len(raw) or not dimensions or not scans:fail()
            if exif:
                w,h=dimensions
                expected=(b'Exif\x00\x00MM\x00*'+struct.pack('>I',8)+struct.pack('>H',1)+
                    struct.pack('>HHII',0x8769,4,1,26)+struct.pack('>I',0)+struct.pack('>H',3)+
                    struct.pack('>HHI',0xa001,3,1)+b'\x00\x01\x00\x00'+
                    struct.pack('>HHII',0xa002,4,1,w)+struct.pack('>HHII',0xa003,4,1,h)+struct.pack('>I',0))
                if not (generated or empty_iptc) or exif!=[expected]:fail()
            if empty_iptc and not exif:fail()
            return dimensions,segments
        if marker in (0xd8,0x01) or 0xd0<=marker<=0xd7:fail()
        if i+2>len(raw):fail()
        size=int.from_bytes(raw[i:i+2],'big')
        if size<2 or i+size>len(raw):fail()
        payload=raw[i+2:i+size];end=i+size
        if marker in (0xc0,0xc2):
            if dimensions or len(payload)!=15 or payload[0]!=8 or payload[5]!=3:fail()
            h,w=struct.unpack_from('>HH',payload,1);dimensions=(w,h)
            if not 0<w<=4096 or not 0<h<=4096 or w*h>4194304:fail()
        elif marker==0xe0:
            if size!=16 or payload[:5]!=b'JFIF\x00' or payload[-2:]!=b'\x00\x00':fail()
        elif marker==0xe1:exif.append(payload)
        elif marker==0xed:
            if empty_iptc or scans or payload!=EMPTY_IPTC_APP13:fail()
            empty_iptc=True
        elif marker not in (0xdb,0xc4,0xda,0xdd,0xfe):fail()
        segments.append((marker,start,end))
        i=end
        if marker==0xda:
            scans+=1
            # Entropy bytes are opaque, but byte stuffing/restarts/EOI are parsed.
            while i<len(raw):
                if type(raw) is bytes:
                    # Entropy is opaque: skip only bytes before the next marker.
                    found=raw.find(b'\xff',i)
                    if found<0:
                        i=len(raw)
                        break
                    i=found
                elif raw[i]!=255:i+=1;continue
                j=i+1
                while j<len(raw) and raw[j]==255:j+=1
                if j==len(raw):fail()
                if raw[j]==0 or 0xd0<=raw[j]<=0xd7:i=j+1;continue
                break
    fail()


def bmp(raw):
    if not 54<=len(raw)<=20*1024*1024 or raw[:2]!=b'BM':fail()
    length,offset=struct.unpack_from('<IxxxxI',raw,2)
    header,w,h,planes,bits,compression=struct.unpack_from('<IiiHHI',raw,14)
    if (length!=len(raw) or header!=40 or planes!=1 or bits!=24 or compression!=0 or
        not 0<w<=4096 or not 0<abs(h)<=4096 or w*abs(h)>4194304 or offset<54):fail()
    stride=((w*3+3)//4)*4
    if offset+stride*abs(h)!=len(raw):fail()
    rgba=bytearray(w*abs(h)*4)
    for y in range(abs(h)):
        row=offset+(abs(h)-1-y if h>0 else y)*stride
        for x in range(w):
            b,g,r=raw[row+3*x:row+3*x+3];k=(y*w+x)*4;rgba[k:k+4]=bytes((r,g,b,255))
    return Raster(w,abs(h),bytes(rgba))


def read_output(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_uid!=os.getuid() or not 0<before.st_size<=limit:fail()
        raw=bytearray()
        while True:
            chunk=os.read(fd,min(65536,limit+1-len(raw)))
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>limit:fail()
        if len(raw)!=before.st_size or file_state(before)!=file_state(os.fstat(fd)) or file_state(before)!=file_state(os.stat(path,follow_symlinks=False)):fail()
        return bytes(raw)
    finally:os.close(fd)


def run(args):
    try:
        result=subprocess.run(['/usr/bin/sips',*args],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired):fail()
    if result.returncode:fail()


def decode(raw,mime,scratch,*,_generated=False):
    if mime=='image/png':
        return decode_import_png(raw)
    if mime!='image/jpeg':fail()
    size,_=jpeg(raw,_generated)
    FileSource(scratch)  # Reject symlink roots/components before producing files.
    with tempfile.TemporaryDirectory(prefix='decode-',dir=scratch) as temp:
        root=Path(temp);source=root/'source.jpg';source.write_bytes(raw);source.chmod(0o600)
        target=root/'decoded.bmp';run(['-s','format','bmp',str(source),'-o',str(target)])
        raster=bmp(read_output(target,20*1024*1024))
    if (raster.width,raster.height)!=size:fail()
    return raster


def candidate(raw,scratch):
    """One finite lossless attempt then one explicit lossy80 candidate; never sends."""
    original=decode(raw,'image/jpeg',scratch);_,segments=jpeg(raw)
    remove=[(start,end) for marker,start,end in segments if marker in (0xe0,0xfe)]
    output=[];start=0
    for first,last in remove:output.append(raw[start:first]);start=last
    output.append(raw[start:]);lossless=b''.join(output)
    exact=decode(lossless,'image/jpeg',scratch)
    if exact!=original:fail()
    if len(lossless)<1000000:
        return lossless,{'policy':'LOCAL_SIPS_BMP_RGB24_V1','lossy':False,'rgba_equal':True,'source_size':len(raw),'transport_size':len(lossless)}
    with tempfile.TemporaryDirectory(prefix='encode-',dir=scratch) as temp:
        root=Path(temp);source=root/'source.jpg';source.write_bytes(raw);source.chmod(0o600)
        target=root/'candidate.jpg';run(['-s','format','jpeg','-s','formatOptions','80',str(source),'-o',str(target)])
        transport=read_output(target,2097152)
    actual=decode(transport,'image/jpeg',scratch,_generated=True)
    if (actual.width,actual.height)!=(original.width,original.height) or len(transport)>=1000000:fail()
    total=sum(abs(a-b) for a,b in zip(original.rgba,actual.rgba))
    return transport,{'policy':'LOCAL_SIPS_BMP_RGB24_V1','lossy':True,'rgba_equal':actual==original,
        'mean_absolute_rgba_difference':total/len(original.rgba),'source_rgba_sha256':sha256(original.rgba).hexdigest(),
        'transport_rgba_sha256':sha256(actual.rgba).hexdigest(),'source_size':len(raw),'transport_size':len(transport),
        'width':actual.width,'height':actual.height,'quality':80,'headroom_target_met':len(transport)<900000}
