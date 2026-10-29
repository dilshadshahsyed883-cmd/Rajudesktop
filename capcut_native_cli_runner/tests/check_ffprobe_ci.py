"""Real FFprobe of a synthetic decoder fixture; never a CapCut export test."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner import verify_probe
probe = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
print(verify_probe(probe, {'duration': 1000000, 'fps': 30, 'canvas_config': {'width': 1920, 'height': 1080}}, True))
