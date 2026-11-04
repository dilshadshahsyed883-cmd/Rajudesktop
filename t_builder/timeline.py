"""Pure keyword allocation and microsecond timeline planning; no filesystem mutations."""
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
import math
import random
import re

class FeasibilityError(ValueError):
    pass


def keyword(path):
    stem = Path(path).stem
    return re.sub(r'[\s_-]+\d+$', '', stem).strip() or stem


def used(path):
    return any(p.casefold() == 'used' for p in Path(path).parts[:-1])


def distribute(weights, total=100):
    keys = list(weights)
    if not keys:
        return {}
    denominator = sum(weights.values())
    raw = {k: total * (weights[k] / denominator if denominator else 1 / len(keys)) for k in keys}
    result = {k: int(raw[k]) for k in keys}
    for k in sorted(keys, key=lambda k: raw[k] - result[k], reverse=True)[:total-sum(result.values())]:
        result[k] += 1
    return result


def rebalance(weights, changed=None, value=None):
    if not weights:
        return {}
    if len(weights) == 1:
        return {next(iter(weights)): 100}
    if changed is None:
        return distribute(weights)
    value = max(0, min(100, int(value)))
    return {changed: value, **distribute({k:v for k,v in weights.items() if k != changed}, 100-value)}


@dataclass
class Clip:
    path: str
    kind: str
    keyword: str
    start: int
    duration: int
    trim: int = 0

    @property
    def end(self):
        return self.start + self.duration


@dataclass
class Timeline:
    duration: int
    images: list
    videos: list
    warnings: list

    def to_dict(self):
        return asdict(self)


def validate_weights(weights, label):
    if not weights or sum(weights.values()) != 100 or any(v < 0 for v in weights.values()):
        raise FeasibilityError(f'{label}: select keywords with strengths totaling exactly 100%.')


def groups(assets, kind, weights):
    pool = defaultdict(list)
    for a in assets:
        k = keyword(a['path'])
        if a['kind'] == kind and a.get('exists', True) and not used(a['path']) and weights.get(k, 0)>0:
            pool[k].append(a)
    for k, weight in weights.items():
        if weight and not pool[k]:
            raise FeasibilityError(f'{kind}: no available media for {k}. Refresh keyword selection.')
    return dict(pool)


def pick_key(pool, weights, counts, rng, previous=None):
    choices = [k for k,v in pool.items() if v and k != previous]
    if not choices:
        choices = [k for k,v in pool.items() if v]
    # Deficit weights keep allocations near the requested proportions, with random ties.
    n = sum(counts.values())+1
    scores = [max(.1, n*weights[k]/100-counts[k]) for k in choices]
    return rng.choices(choices, scores)[0]


def plan_timeline(assets, duration, image_weights, video_weights=None, coverage=20, seed=None):
    rng = random.Random(seed)
    total = round(float(duration)*1_000_000)
    if total <= 0:
        raise FeasibilityError('Audio duration must be positive.')
    validate_weights(image_weights, 'Images')
    pool = groups(assets, 'image', image_weights)
    bags = {k:rng.sample(v, len(v)) for k,v in pool.items()}
    images, counts, cursor, previous, last_path = [], defaultdict(int), 0, None, None
    while cursor < total:
        k = pick_key(pool, image_weights, counts, rng)
        # Deficit allocation naturally limits clustering while preserving unequal strengths.
        if not bags[k]:
            bags[k] = rng.sample(pool[k],len(pool[k]))
        if len(bags[k])>1 and bags[k][-1]['path']==last_path:
            bags[k].insert(0,bags[k].pop())
        a = bags[k].pop()
        dur = min(rng.randint(3_000_000,5_000_000),total-cursor)
        images.append(Clip(a['path'],'image',k,cursor,dur))
        counts[k]+=1;cursor+=dur;previous=k;last_path=a['path']
    videos, warnings = [], []
    if not 0 <= coverage <= 100:
        raise FeasibilityError('Video coverage must be between 0 and 100%.')
    if video_weights is None or coverage == 0:
        return Timeline(total, images, videos, warnings)
    validate_weights(video_weights,'Videos')
    vpool = groups(assets,'video',video_weights)
    vpool = {k:[a for a in v if a.get('duration',0)>=2.5] for k,v in vpool.items()}
    target = round(total*coverage/100)
    lower = math.ceil(target/4_000_000)
    upper = min(target//2_500_000,sum(len(v) for v in vpool.values()))
    possible = list(range(lower,upper+1))
    rng.shuffle(possible)
    for n in possible:
        if n > 1 and sum(bool(v) for v in vpool.values()) < 2:
            continue
        # Try weighted, nonrepeating keyword sequences and source duration bounds.
        for attempt in range(100):
            vp={k:rng.sample(v,len(v)) for k,v in vpool.items()}
            selected=[];vc=defaultdict(int);prev=None
            for i in range(n):
                choices={k:v for k,v in vp.items() if v and k!=prev}
                if not choices: break
                k=pick_key(choices,video_weights,vc,rng)
                a=vp[k].pop();selected.append((k,a));vc[k]+=1;prev=k
            if len(selected)!=n: continue
            caps=[min(4_000_000,round(a['duration']*1e6)) for k,a in selected]
            if sum(caps)<target: continue
            durs=[];remaining=target
            for i,cap in enumerate(caps):
                lo=max(2_500_000,remaining-sum(caps[i+1:]))
                hi=min(cap,remaining-2_500_000*(n-i-1))
                d=rng.randint(lo,hi);durs.append(d);remaining-=d
            # Prefer a whole base-image segment between overlays.
            cursor=0;positions=[]
            for d in durs:
                positions.append(cursor);end=cursor+d
                full=next((im for im in images if im.start>=end),None)
                cursor=full.end if full else total+1
            fits=positions[-1]+durs[-1]<=total
            if not fits:
                # Positive image-only gaps remain mandatory; the full-image preference may be infeasible.
                spare=total-target
                if n>1 and spare < (n-1)*250_000: continue
                gaps=[spare//(n+1)]*(n+1)
                gaps[-1]+=spare-sum(gaps)
                if n>1 and min(gaps[1:-1])<250_000:
                    gaps=[0]+[spare//(n-1)]*(n-1)+[spare%(n-1)]
                positions=[];cursor=gaps[0]
                for i,d in enumerate(durs):
                    positions.append(cursor);cursor+=d+gaps[i+1]
            else:
                slack=total-(positions[-1]+durs[-1])
                # Shift within slack without losing complete image gaps.
                if n==1: positions[0]=rng.randint(0,slack)
            for (k,a),start,d in zip(selected,positions,durs):
                trim=rng.randint(0,max(0,round(a['duration']*1e6)-d))
                videos.append(Clip(a['path'],'video',k,start,d,trim))
            if any(not any(im.start>=a.end and im.end<=b.start for im in images) for a,b in zip(videos,videos[1:])):
                warnings.append('Coverage allows image-only gaps, but not a complete visible image in every gap.')
            result=Timeline(total,images,videos,warnings)
            validate_timeline(result)
            return result
    detail=' Select at least two video keywords for multiple clips.' if sum(bool(v) for v in vpool.values())<2 else ''
    raise FeasibilityError(f'{coverage}% video coverage is infeasible with the selected usable clips, 2.5–4s durations and image-only gaps.{detail} Reduce coverage or add clips/keywords.')


def validate_timeline(t):
    cursor=0
    for i,c in enumerate(t.images):
        if c.start!=cursor or c.duration<=0 or c.duration>5_000_000 or (i<len(t.images)-1 and c.duration<3_000_000):
            raise ValueError('Invalid continuous image base layer')
        cursor=c.end
    if cursor!=t.duration: raise ValueError('Images do not match audio endpoint')
    seen=set()
    for i,c in enumerate(t.videos):
        if not 2_500_000<=c.duration<=4_000_000 or c.end>t.duration or c.start<0 or c.path in seen:
            raise ValueError('Invalid video duration, position or reuse')
        seen.add(c.path)
        if i and (c.start<=t.videos[i-1].end or c.keyword==t.videos[i-1].keyword):
            raise ValueError('Videos require image gaps and alternating keywords')
