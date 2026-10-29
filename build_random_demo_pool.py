import json
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import torch

from train_personalized_m01 import Model, make_split

ROOT = Path(__file__).parent
FEATURES = ROOT / "dsr_data/loso_f03/features.pt"
CHECKPOINT = ROOT / "dsr_data/personalized_m01/best.pt"
REPORT = ROOT / "dsr_data/personalized_m01/report.json"
OUT = ROOT / "dsr_demo/random_pool"

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "original").mkdir(exist_ok=True)
bundle = torch.load(FEATURES, map_location="cpu", weights_only=False)
selected = [i for i, speaker in enumerate(bundle["speaker"]) if speaker == "M01"]
x = bundle["x"][selected]
words = [bundle["word"][i] for i in selected]
keys = [bundle["key"][i] for i in selected]
split = make_split(words)
test = [i for i, value in enumerate(split) if value == "test"]

checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
vocabulary = checkpoint["vocabulary"]
model = Model(len(vocabulary))
model.load_state_dict(checkpoint["model"])
model.eval()

all_logits = []
with torch.inference_mode():
    for start in range(0, len(test), 256):
        all_logits.append(model(x[test[start:start + 256]].float()))
probabilities = torch.cat(all_logits).softmax(1)
top_prob, top_id = probabilities.topk(3, dim=1)

by_file = defaultdict(list)
for pool_id, local_index in enumerate(test):
    filename, row = keys[local_index].split(":")
    by_file[filename].append((pool_id, int(row)))

for filename, rows in by_file.items():
    audio = pq.read_table(ROOT / "dsr_data/uaspeech" / filename, columns=["audio"])["audio"]
    for pool_id, row in rows:
        (OUT / "original" / f"{pool_id:04d}.wav").write_bytes(audio[row].as_py()["bytes"])

pool = []
for pool_id, local_index in enumerate(test):
    ids, scores = top_id[pool_id].tolist(), top_prob[pool_id].tolist()
    target = words[local_index]
    prediction = vocabulary[ids[0]]
    feature = x[local_index].float().view(8, 48, 16).mean(2)
    feature = ((feature - feature.min()) / (feature.max() - feature.min() + 1e-8) * 255).byte().flatten().tolist()
    pool.append({
        "id": pool_id,
        "original": f"original/{pool_id:04d}.wav",
        "target": target,
        "target_id": vocabulary.index(target),
        "prediction": prediction,
        "prediction_id": ids[0],
        "correct": prediction == target,
        "confidence": round(scores[0], 4),
        "top3": [{"word": vocabulary[i], "confidence": round(score, 4)} for i, score in zip(ids, scores)],
        "feature_map": feature,
    })

report = json.loads(REPORT.read_text())
(OUT / "pool.json").write_text(json.dumps(pool, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(OUT / "vocabulary.json").write_text(json.dumps([{"id": i, "word": word} for i, word in enumerate(vocabulary)], indent=2), encoding="utf-8")
(OUT / "summary.json").write_text(json.dumps({"speaker": "M01", "test_size": len(test), "top1": report["test"]["top1"], "top3": report["test"]["top3"]}, indent=2), encoding="utf-8")
print(f"pool={len(pool)} correct={sum(item['correct'] for item in pool)}")
