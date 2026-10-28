"""Small read-only SFNT name/advance reader; no font installation or pip needed.

Width is an estimate for background geometry; shaping/kerning remains libass's
job. TTC and complex layout use a visible fallback warning instead of guessing.
"""
from functools import lru_cache
from pathlib import Path
import os
import struct


class FontInfo:
    def __init__(self,path):
        path=Path(path)
        if path.stat().st_size>50*1024*1024: raise ValueError('Font is too large')
        self.data=path.read_bytes()
        if self.data[:4] not in (b'\x00\x01\x00\x00',b'OTTO',b'true'):
            raise ValueError('Font collection or non-SFNT font is not supported by the metric reader')
        self.tables={}
        for index in range(min(256,self.u16(4))):
            offset=12+index*16
            tag=self.data[offset:offset+4].decode('ascii')
            begin,length=struct.unpack_from('>II',self.data,offset+8)
            if begin+length>len(self.data): raise ValueError('Invalid font table bounds')
            self.tables[tag]=begin
        head=self.tables['head'];hhea=self.tables['hhea']
        self.units=max(1,self.u16(head+18))
        self.metrics=max(1,self.u16(hhea+34))
        self.family=self._family()
        self.cmap=self._cmap()

    def u16(self,p): return struct.unpack_from('>H',self.data,p)[0]
    def i16(self,p): return struct.unpack_from('>h',self.data,p)[0]
    def u32(self,p): return struct.unpack_from('>I',self.data,p)[0]

    def _family(self):
        base=self.tables['name'];storage=base+self.u16(base+4)
        names=[]
        for index in range(min(4096,self.u16(base+2))):
            platform,encoding,language,kind,length,offset=struct.unpack_from('>HHHHHH',self.data,base+6+index*12)
            if kind not in (1,16): continue
            raw=self.data[storage+offset:storage+offset+length]
            try:
                name=raw.decode('utf-16-be' if platform in (0,3) else 'mac_roman').strip('\x00 ')
                if name:names.append(((kind==16,language==0x409,platform==3),name))
            except UnicodeError: continue
        if not names: raise ValueError('Font has no readable family name')
        return max(names)[1]

    def _cmap(self):
        base=self.tables['cmap'];options=[]
        for index in range(min(256,self.u16(base+2))):
            platform,encoding,offset=struct.unpack_from('>HHI',self.data,base+4+index*8)
            if platform not in (0,3):continue
            table=base+offset;fmt=self.u16(table)
            if fmt in (4,12):options.append((fmt,table))
        if not options:raise ValueError('Font has no supported Unicode cmap')
        return max(options)

    def glyph(self,code):
        fmt,base=self.cmap
        if fmt==12:
            low,high=0,self.u32(base+12)-1
            while low<=high:
                mid=(low+high)//2;p=base+16+mid*12
                first,last,glyph=struct.unpack_from('>III',self.data,p)
                if code<first:high=mid-1
                elif code>last:low=mid+1
                else:return glyph+code-first
            return 0
        if code>65535:return 0
        count=self.u16(base+6)//2;end=base+14
        start=end+2*count+2;delta=start+2*count;ranges=delta+2*count
        for i in range(count):
            if self.u16(end+2*i)<code:continue
            if self.u16(start+2*i)>code:return 0
            change=self.i16(delta+2*i);distance=self.u16(ranges+2*i)
            if distance==0:return (code+change)&65535
            glyph=self.u16(ranges+2*i+distance+2*(code-self.u16(start+2*i)))
            return (glyph+change)&65535 if glyph else 0
        return 0

    def width(self,text,size):
        table=self.tables['hmtx']
        return sum(self.u16(table+min(self.glyph(ord(char)),self.metrics-1)*4) for char in text)*size/self.units


@lru_cache(maxsize=32)
def read_font(path):
    return FontInfo(path)


def fallback_font():
    options=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf',
             Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
             Path('/System/Library/Fonts/Supplemental/Arial.ttf')]
    return next((str(p) for p in options if p.is_file()),'')


def measure(text,size,font_path):
    if font_path:
        try:return read_font(font_path).width(text,size)
        except (OSError,ValueError,KeyError,struct.error,UnicodeError):pass
    return sum(.33 if c.isspace() else .62 for c in text)*size
