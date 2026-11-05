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


def _image_gap_lengths(image_total, gap_count, rng):
    """Distribute image-only time across the whole narration without visual overlap."""
    if gap_count <= 0 or image_total < gap_count * 3_000_000:
        raise FeasibilityError('Not enough time for an image between every video.')
    # Where possible, reserve enough time for complete 3–5s pictures in each gap.
    floor = 6_000_000 if image_total >= gap_count * 6_000_000 else 3_000_000
    spare = image_total - gap_count * floor
    jitter = [rng.uniform(.75, 1.25) for _ in range(gap_count)]
    denominator = sum(jitter)
    gaps = [floor + int(spare * weight / denominator) for weight in jitter]
    gaps[-1] += image_total - sum(gaps)
    return gaps


def _image_durations(span, rng):
    """Fit random pictures within a precise image-only gap, without exceeding 5s."""
    if span <= 0:
        return []
    minimum = math.ceil(span / 5_000_000)
    maximum = span // 3_000_000
    if minimum > maximum:
        # Short audio endpoints or rare 5–6s gaps need shorter boundary pictures.
        count = minimum
        return [span // count + (1 if i < span % count else 0) for i in range(count)]
    count = max(minimum, min(maximum, round(span / 4_000_000)))
    durations = []
    remaining = span
    for i in range(count):
        others = count - i - 1
        low = max(3_000_000, remaining - others * 5_000_000)
        high = min(5_000_000, remaining - others * 3_000_000)
        duration = rng.randint(low, high)
        durations.append(duration)
        remaining -= duration
    return durations


def plan_timeline(assets, duration, image_weights, video_weights=None, coverage=20, seed=None):
    rng = random.Random(seed)
    total = round(float(duration) * 1_000_000)
    if total <= 0:
        raise FeasibilityError('Audio duration must be positive.')
    validate_weights(image_weights, 'Images')
    image_pool = groups(assets, 'image', image_weights)
    if not 0 <= coverage <= 100:
        raise FeasibilityError('Video coverage must be between 0 and 100%.')
    videos, warnings = [], []
    gaps = [total]
    if video_weights is not None and coverage > 0:
        validate_weights(video_weights, 'Videos')
        pool = groups(assets, 'video', video_weights)
        pool = {k: [a for a in available if a.get('duration', 0) >= 2.5]
                for k, available in pool.items()}
        target = round(total * coverage / 100)
        lower = math.ceil(target / 4_000_000)
        upper = min(target // 2_500_000, sum(len(items) for items in pool.values()))
        possibilities = list(range(lower, upper + 1))
        rng.shuffle(possibilities)
        found = False
        for n in possibilities:
            # Every video must be preceded and followed by actual image footage.
            if total - target < (n + 1) * 3_000_000:
                continue
            if n > 1 and sum(bool(items) for items in pool.values()) < 2:
                continue
            for attempt in range(100):
                available = {k: rng.sample(items, len(items)) for k, items in pool.items()}
                chosen, counts, previous = [], defaultdict(int), None
                for i in range(n):
                    choices = {k: items for k, items in available.items() if items and k != previous}
                    if not choices:
                        break
                    k = pick_key(choices, video_weights, counts, rng)
                    chosen.append((k, available[k].pop()))
                    counts[k] += 1
                    previous = k
                if len(chosen) != n:
                    continue
                caps = [min(4_000_000, round(a['duration'] * 1_000_000)) for _, a in chosen]
                if sum(caps) < target:
                    continue
                remaining = target
                durations = []
                for i, cap in enumerate(caps):
                    lo = max(2_500_000, remaining - sum(caps[i + 1:]))
                    hi = min(cap, remaining - 2_500_000 * (n - i - 1))
                    if lo > hi:
                        break
                    d = rng.randint(lo, hi)
                    durations.append(d)
                    remaining -= d
                if len(durations) != n or remaining:
                    continue
                gaps = _image_gap_lengths(total - target, n + 1, rng)
                cursor = gaps[0]
                videos = []
                for i, ((k, a), clip_duration) in enumerate(zip(chosen, durations)):
                    trim = rng.randint(0, max(0, round(a['duration'] * 1_000_000) - clip_duration))
                    videos.append(Clip(a['path'], 'video', k, cursor, clip_duration, trim))
                    cursor += clip_duration + gaps[i + 1]
                if cursor != total:
                    raise AssertionError('Sequential video timing did not reach narration endpoint')
                found = True
                break
            if found:
                break
        if not found:
            detail = (' Select at least two video keywords for multiple clips.'
                      if sum(bool(items) for items in pool.values()) < 2 else '')
            raise FeasibilityError(
                f'{coverage}% video coverage is infeasible with the selected clips, '
                '2.5–4s video lengths and mandatory image-only gaps.'
                f'{detail} Reduce coverage or add media.'
            )

    # Construct image footage only between video slots. Exactly one type of visual
    # occupies each timestamp; the cut boundaries match to the microsecond.
    bags = {k: rng.sample(items, len(items)) for k, items in image_pool.items()}
    image_counts = defaultdict(int)
    images, cursor, last_path = [], 0, None
    for index, gap in enumerate(gaps):
        for length in _image_durations(gap, rng):
            k = pick_key(image_pool, image_weights, image_counts, rng)
            if not bags[k]:
                bags[k] = rng.sample(image_pool[k], len(image_pool[k]))
            if len(bags[k]) > 1 and bags[k][-1]['path'] == last_path:
                bags[k].insert(0, bags[k].pop())
            asset = bags[k].pop()
            images.append(Clip(asset['path'], 'image', k, cursor, length))
            last_path = asset['path']
            image_counts[k] += 1
            cursor += length
        if index < len(videos):
            if cursor != videos[index].start:
                raise AssertionError('Image end must equal video start')
            cursor += videos[index].duration
    if cursor != total:
        raise AssertionError('Last image must finish with narration')
    result = Timeline(total, images, videos, warnings)
    validate_timeline(result)
    return result


def validate_timeline(t):
    """Reject even a one-microsecond image/video gap or overlap."""
    visuals = sorted(t.images + t.videos, key=lambda c: c.start)
    if not t.images or not visuals:
        raise ValueError('At least one image is required')
    cursor, previous = 0, None
    video_paths = set()
    for clip in visuals:
        if clip.start != cursor or clip.duration <= 0:
            raise ValueError('Image/video boundary has a gap or overlap')
        if clip.kind == 'image':
            if clip.duration > 5_000_000:
                raise ValueError('Invalid image duration')
        elif clip.kind == 'video':
            if not 2_500_000 <= clip.duration <= 4_000_000 or clip.path in video_paths:
                raise ValueError('Invalid video duration or source reuse')
            if previous is not None and previous.kind == 'video':
                raise ValueError('Consecutive videos need an image between them')
            video_paths.add(clip.path)
        else:
            raise ValueError('Unknown media kind')
        cursor = clip.end
        previous = clip
    if cursor != t.duration:
        raise ValueError('Visual timeline does not match narration endpoint')
    for left, right in zip(t.videos, t.videos[1:]):
        if left.keyword == right.keyword or left.end >= right.start:
            raise ValueError('Video keywords must alternate with an image-only gap')
