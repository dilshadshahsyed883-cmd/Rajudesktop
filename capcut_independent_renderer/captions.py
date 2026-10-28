"""Read common CapCut plain/rich text JSON and emit safe, timed ASS captions.

Text, placement and first-style appearance are approximations. Proprietary
templates/animations are deliberately not interpreted as native CapCut effects.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import re
from fontinfo import measure


def number(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError):
        return default


def obj(value):
    return value if isinstance(value, dict) else {}


@dataclass
class Caption:
    start: float
    end: float
    text: str
    track: int
    font: str = 'Arial'
    font_path: str = ''
    size: float = 5.0  # approximate percent of canvas height
    color: str = '&H00FFFFFF'
    bold: bool = False
    italic: bool = False
    x: float = 0.0
    y: float = -0.72
    rotation: float = 0.0
    alpha: float = 1.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    base_alpha: float = 1.0
    background_color: str = ''
    background_alpha: float = 0.0
    background_style: int = 0
    background_width: float = 0.0
    background_height: float = 0.0
    background_radius: float = 0.0
    background_x: float = 0.0
    background_y: float = 0.0
    line_max_width: float = .82
    letter_spacing: float = 0.0
    outline_color: str = '&H00000000'
    outline_width: float = 0.0
    shadow_color: str = '&H00000000'
    shadow_alpha: float = 0.0
    shadow_distance: float = 0.0
    underline: bool = False


def color(value):
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        rgb = [int(value[i:i+2], 16) for i in (1, 3, 5)]
    elif isinstance(value, (list, tuple)) and len(value) >= 3:
        rgb = [max(0, min(255, round(number(x) * 255))) for x in value[:3]]
    else:
        rgb = [255, 255, 255]
    return '&H00%02X%02X%02X' % (rgb[2], rgb[1], rgb[0])


def parse_caption(material, segment, start, end, track):
    """Return (caption, warnings), raising on an unrecognized nonempty schema."""
    warnings = []
    content = material.get('content', material.get('text', ''))
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith(('{"', '[{', '["')):
            try:
                content = json.loads(content)
            except ValueError as error:
                raise ValueError('Malformed structured caption content') from error
    if isinstance(content, dict):
        text = content.get('text')
        styles = content.get('styles') or []
        if not isinstance(text, str):
            raise ValueError('Structured caption has no plain text field')
    elif isinstance(content, str):
        text = content
        styles = []
    else:
        raise ValueError('Caption content is not supported text')
    if not text.strip():
        raise ValueError('Caption has empty text or is a proprietary template')
    style = obj(styles[0]) if isinstance(styles, list) and styles else {}
    if isinstance(styles, list) and len(styles) > 1:
        warnings.append('Rich caption uses multiple styles; first style applied to the whole caption.')
    if style.get('range') and style['range'] not in ([0,len(text)],[0,len(text.encode('utf-16-le'))//2]):
        warnings.append('Partial caption style ranges are approximated; word highlights are not reproduced.')
    font = obj(style.get('font'))
    clip = obj(segment.get('clip'))
    transform = obj(clip.get('transform'))
    scale = obj(clip.get('scale'))
    solid = obj(obj(obj(style.get('fill')).get('content')).get('solid'))
    size = max(0.5, min(30, number(style.get('size', material.get('font_size')), 5)))
    name = str(font.get('family') or font.get('name') or material.get('font_name') or 'Arial')
    name = re.sub(r'[\x00-\x1f,{}\\]', '', name)[:100] or 'Arial'
    caption=Caption(start, end, text, track, name,
                   str(font.get('path') or material.get('font_path') or ''), size,
                   color(solid.get('color', material.get('text_color'))),
                   bool(style.get('bold', material.get('bold', False))),
                   bool(style.get('italic', material.get('italic', False))),
                   number(transform.get('x')), number(transform.get('y'), -0.72),
                   number(clip.get('rotation')), max(0, min(1, number(clip.get('alpha'), 1))),
                   max(.02, min(12, number(scale.get('x'), 1))),
                   max(.02, min(12, number(scale.get('y'), 1))))
    caption.base_alpha=max(0,min(1,number(clip.get('alpha'),1)*number(material.get('global_alpha'),1)))
    caption.alpha=max(0,min(1,caption.base_alpha*number(material.get('text_alpha'),1)*number(obj(style.get('fill')).get('alpha'),1)*number(solid.get('alpha'),1)))
    caption.background_style=int(number(material.get('background_style')))
    if material.get('background_color') and caption.background_style!=0:
        caption.background_color=color(material['background_color'])
        caption.background_alpha=max(0,min(1,number(material.get('background_alpha'),1)))
        caption.background_width=max(0,min(3,number(material.get('background_width'))))
        caption.background_height=max(0,min(3,number(material.get('background_height'))))
        caption.background_radius=max(0,min(1,number(material.get('background_round_radius'))))
        caption.background_x=number(material.get('background_horizontal_offset'))
        caption.background_y=number(material.get('background_vertical_offset'))
    caption.line_max_width=max(.1,min(1,number(material.get('line_max_width'),.82)))
    caption.letter_spacing=number(material.get('letter_spacing'))
    caption.underline=bool(material.get('underline'))
    if material.get('border_color'):
        caption.outline_color=color(material['border_color'])
        caption.outline_width=max(0,min(.5,number(material.get('border_width'))))
    if material.get('has_shadow'):
        caption.shadow_color=color(material.get('shadow_color'))
        caption.shadow_alpha=max(0,min(1,number(material.get('shadow_alpha'),.9)))
        caption.shadow_distance=max(0,min(30,number(material.get('shadow_distance'),5)))
        warnings.append('Caption shadow direction/blur is approximated.')
    if caption.background_style not in (0,1):
        warnings.append('Caption background style uses an approximate whole-caption rounded box.')
    return caption,warnings


def ass_time(seconds):
    cs = max(0, round(seconds * 100))
    hours, cs = divmod(cs, 360000)
    minutes, cs = divmod(cs, 6000)
    secs, cs = divmod(cs, 100)
    return f'{hours}:{minutes:02}:{secs:02}.{cs:02}'


def literal_text(text):
    # Fullwidth glyphs preserve literal braces/backslashes without allowing ASS
    # override injection (e.g. a caption that literally contains {\p1}).
    return text.replace('\\', '＼').replace('{', '｛').replace('}', '｝').replace('\r\n', '\n').replace('\r', '\n').replace('\n', r'\N').replace('\x00', '')


def wrapped_lines(c,fontsize,width):
    maximum=width*c.line_max_width/max(.02,c.scale_x)
    def length(text):
        return measure(text,fontsize,c.font_path)+(len(text)-1)*c.letter_spacing*fontsize
    result=[]
    for paragraph in c.text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        current=''
        for word in paragraph.split(' '):
            candidate=(current+' '+word) if current else word
            if current and length(candidate)>maximum:
                result.append(current);current=word
            else:current=candidate
        result.append(current)
    return result,max((length(line) for line in result),default=0)


def rounded_rect(width,height,radius):
    w,h=width,height;r=max(0,min(radius,w/2,h/2));k=.55228475*r
    if r<.01:return f'm 0 0 l {w:.2f} 0 {w:.2f} {h:.2f} 0 {h:.2f}'
    return (f'm {r:.2f} 0 l {w-r:.2f} 0 '
            f'b {w-r+k:.2f} 0 {w:.2f} {r-k:.2f} {w:.2f} {r:.2f} '
            f'l {w:.2f} {h-r:.2f} b {w:.2f} {h-r+k:.2f} {w-r+k:.2f} {h:.2f} {w-r:.2f} {h:.2f} '
            f'l {r:.2f} {h:.2f} b {r-k:.2f} {h:.2f} 0 {h-r+k:.2f} 0 {h-r:.2f} '
            f'l 0 {r:.2f} b 0 {r-k:.2f} {r-k:.2f} 0 {r:.2f} 0')


def write_ass(path, captions, width, height, limit, fade=False):
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{height*.05:.2f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = [header]
    count = 0
    for c in captions:
        start, end = max(0, c.start), min(limit, c.end)
        if end <= start:continue
        x,y=width*(.5+c.x/2),height*(.5-c.y/2)
        alpha=round((1-c.alpha)*255)
        fontsize=height*c.size/100
        textlines,textwidth=wrapped_lines(c,fontsize,width)
        textheight=fontsize*len(textlines)
        textwidth*=c.scale_x;textheight*=c.scale_y
        fade_tags=''
        if fade:
            ms=min(120,int((end-start)*1000/4));fade_tags=rf'\fad({ms},{ms})'
        event=f'{ass_time(start)},{ass_time(end)},Default,,0,0,0,,'
        if c.background_color and c.background_alpha>0:
            padding_x=fontsize*c.background_width*c.scale_x
            padding_y=fontsize*c.background_height*c.scale_y
            boxw,boxh=textwidth+2*padding_x,textheight+2*padding_y
            radius=min(boxw,boxh)*c.background_radius/2
            bx=x-boxw/2+c.background_x*fontsize
            by=y-boxh/2-c.background_y*fontsize
            bg_alpha=round((1-c.background_alpha*c.base_alpha)*255)
            bg=(rf'{{\an7\pos({bx:.2f},{by:.2f})\org({x:.2f},{y:.2f})\frz{-c.rotation:.2f}'
                rf'\bord0\shad0\1c{c.background_color}\alpha&H{bg_alpha:02X}&\p1'+fade_tags+'}')
            lines.append(f'Dialogue: {max(0,c.track)*2},'+event+bg+rounded_rect(boxw,boxh,radius)+'\n')
        tags=(rf'\an5\pos({x:.2f},{y:.2f})\q2\fn{c.font}\fs{fontsize:.2f}'
              rf'\c{c.color}\alpha&H{alpha:02X}&\b{int(c.bold)}\i{int(c.italic)}\u{int(c.underline)}'
              rf'\fscx{c.scale_x*100:.2f}\fscy{c.scale_y*100:.2f}\frz{-c.rotation:.2f}'
              rf'\fsp{c.letter_spacing*fontsize:.2f}\3c{c.outline_color}\bord{c.outline_width*fontsize:.2f}'
              rf'\4c{c.shadow_color}\4a&H{round((1-c.shadow_alpha)*255):02X}&\shad{c.shadow_distance*height/1080:.2f}')
        text='{'+tags+fade_tags+'}'+literal_text('\n'.join(textlines))
        lines.append(f'Dialogue: {max(0,c.track)*2+1},'+event+text+'\n')
        count+=1
    Path(path).write_text(''.join(lines),encoding='utf-8-sig')
    return count


def filter_path(path):
    """Escape both FFmpeg filter parsing levels, including apostrophes/drives."""
    text = str(Path(path).resolve()).replace('\\', '/')
    # Level 1 option parser, then level 2 filtergraph parser. No shell involved.
    first = ''.join('\\'+c if c in "\\':" else c for c in text)
    return ''.join('\\'+c if c in "\\'[],; " else c for c in first)
