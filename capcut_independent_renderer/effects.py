"""Explicit named FFmpeg approximations. Never load CapCut binaries/shaders."""
from dataclasses import dataclass, asdict
from captions import number


@dataclass
class Effect:
    start:float
    end:float
    name:str
    identifier:str
    parameters:dict
    scope:str='composited_video_before_captions'
    method:str='ffmpeg_hdr_look_v1_approximation'

    def summary(self):
        data=asdict(self)
        data['native_capcut_equivalence']=False
        data['filter']=self.filter()
        data['unmapped_parameters']=[k for k in self.parameters if k not in (
            'effects_adjust_intensity','effects_adjust_range','effects_adjust_luminance',
            'effects_adjust_filter','effects_adjust_size')]
        return data

    def filter(self):
        p=self.parameters
        strength=max(0,min(1,number(p.get('effects_adjust_intensity'),.75)))
        radius=max(0,min(1,number(p.get('effects_adjust_range'),.23)))
        light=max(0,min(1,number(p.get('effects_adjust_luminance'),.5)))
        tint=max(0,min(1,number(p.get('effects_adjust_filter'),.8)))
        size=max(0,min(1,number(p.get('effects_adjust_size'),.7)))
        # These are openly defined independent aesthetic choices, not recovered
        # meanings or equations from the proprietary CapCut shader.
        contrast=1+strength*(.25+.5*radius)
        brightness=strength*light*.04
        saturation=1+strength*tint*.3
        amount=strength*(.25+.75*size)
        return f'eq=contrast={contrast:.8f}:brightness={brightness:.8f}:saturation={saturation:.8f},unsharp=5:5:{amount:.8f}:5:5:0'


def parse_effect(material,segment,start,end):
    if material.get('name','').strip().casefold()!='hdr':
        raise ValueError('No independent mapping for effect '+str(material.get('name') or material.get('id')))
    if segment.get('common_keyframes') or material.get('common_keyframes'):
        raise ValueError('Animated effect parameters are not supported')
    if material.get('effect_mask'):
        raise ValueError('Masked HDR effect is not supported')
    if material.get('apply_target_type',2)!=2 or material.get('bind_segment_id'):
        raise ValueError('HDR effect scope is not a global video effect')
    parameters={str(x['name']):number(x.get('value')) for x in material.get('adjust_params',[]) if isinstance(x,dict) and 'name' in x}
    value=max(0,min(1,number(material.get('value'),1)))
    parameters['effects_adjust_intensity']=max(0,min(1,number(parameters.get('effects_adjust_intensity'),.75)))*value
    return Effect(start,end,str(material.get('name')),str(material.get('id','')),parameters)
