import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

SEED = 42
ROOT = Path(__file__).parent
FEATURES = ROOT / "dsr_data/loso_f03/features.pt"
OUT = ROOT / "dsr_data/personalized_m01"


class Model(nn.Module):
    def __init__(self, classes):
        super().__init__()
        self.project = nn.Sequential(nn.Linear(6144, 256), nn.GELU(), nn.Dropout(0.15), nn.Linear(256, 128))
        self.class_weight = nn.Parameter(torch.empty(classes, 128))
        nn.init.normal_(self.class_weight, std=0.02)

    def forward(self, x):
        z = F.normalize(self.project(x), dim=-1)
        return 20 * z @ F.normalize(self.class_weight, dim=-1).T


def make_split(words):
    rng = random.Random(SEED)
    groups = defaultdict(list)
    for i, word in enumerate(words): groups[word].append(i)
    split = [None] * len(words)
    for indices in groups.values():
        rng.shuffle(indices)
        n = len(indices)
        n_train, n_val = max(1, round(n * 0.5)), max(1, round(n * 0.2))
        if n_train + n_val >= n:
            n_train = n - n_val - 1
        for i in indices[:n_train]: split[i] = "train"
        for i in indices[n_train:n_train + n_val]: split[i] = "val"
        for i in indices[n_train + n_val:]: split[i] = "test"
    desired = {"train": round(len(words) * 0.5), "val": round(len(words) * 0.2)}
    desired["test"] = len(words) - desired["train"] - desired["val"]
    while True:
        current = Counter(split)
        donors = [s for s in desired if current[s] > desired[s]]
        receivers = [s for s in desired if current[s] < desired[s]]
        if not donors: break
        donor, receiver = donors[0], receivers[0]
        movable = next(indices for indices in groups.values() if sum(split[i] == donor for i in indices) > 1)
        split[next(i for i in movable if split[i] == donor)] = receiver
    assert all({split[i] for i in indices} == {"train", "val", "test"} for indices in groups.values())
    return split


def evaluate(model, x, y, indices, device):
    model.eval()
    logits = []
    with torch.inference_mode():
        for start in range(0, len(indices), 512):
            logits.append(model(x[indices[start:start + 512]].to(device).float()).cpu())
    logits = torch.cat(logits)
    target = y[indices]
    top3 = logits.topk(3, dim=1).indices
    return {
        "top1": (top3[:, 0] == target).float().mean().item(),
        "top3": (top3 == target[:, None]).any(1).float().mean().item(),
        "prediction_ids": top3[:, 0].tolist(),
    }


def main():
    random.seed(SEED)
    torch.manual_seed(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    bundle = torch.load(FEATURES, map_location="cpu", weights_only=False)
    selected = [i for i, speaker in enumerate(bundle["speaker"]) if speaker == "M01"]
    x = bundle["x"][selected]
    words = [bundle["word"][i] for i in selected]
    keys = [bundle["key"][i] for i in selected]
    vocabulary = sorted(set(words))
    word_to_id = {word: i for i, word in enumerate(vocabulary)}
    y = torch.tensor([word_to_id[word] for word in words])
    split = make_split(words)
    indices = {name: [i for i, value in enumerate(split) if value == name] for name in ["train", "val", "test"]}

    loader = DataLoader(TensorDataset(x[indices["train"]], y[indices["train"]]), batch_size=256, shuffle=True)
    model = Model(len(vocabulary)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    best, stale, history = -1.0, 0, []
    for epoch in range(1, 61):
        model.train()
        losses = []
        for bx, by in loader:
            loss = F.cross_entropy(model(bx.to(device).float()), by.to(device), label_smoothing=0.05)
            optimizer.zero_grad(); loss.backward(); optimizer.step(); losses.append(loss.item())
        val = evaluate(model, x, y, indices["val"], device)
        history.append({"epoch": epoch, "loss": sum(losses) / len(losses), "top1": val["top1"], "top3": val["top3"]})
        print(f"epoch {epoch:02d} loss={history[-1]['loss']:.3f} val={val['top1']:.3%}", flush=True)
        if val["top1"] > best:
            best, stale = val["top1"], 0
            torch.save({"model": model.state_dict(), "vocabulary": vocabulary}, OUT / "best.pt")
        else:
            stale += 1
            if stale >= 8: break

    model.load_state_dict(torch.load(OUT / "best.pt", map_location=device, weights_only=False)["model"])
    val = evaluate(model, x, y, indices["val"], device)
    test = evaluate(model, x, y, indices["test"], device)
    predictions = [{
        "key": keys[index], "target": words[index], "prediction": vocabulary[prediction],
        "correct": words[index] == vocabulary[prediction],
    } for index, prediction in zip(indices["test"], test.pop("prediction_ids"))]
    val.pop("prediction_ids")
    report = {
        "speaker": "M01", "split": "speaker×word stratified 50/20/30",
        "counts": {name: len(value) for name, value in indices.items()},
        "validation": val, "test": test,
        "best_epoch": max(history, key=lambda row: row["top1"])["epoch"],
        "predictions": predictions, "history": history,
    }
    (OUT / "split.json").write_text(json.dumps([{"key": key, "word": word, "split": value} for key, word, value in zip(keys, words, split)], indent=2))
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in {"predictions", "history"}}, indent=2))


if __name__ == "__main__": main()
