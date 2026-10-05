"""
Scratch: pretrained ResNet-50 (ImageNet) features for every 224 x 224 tile (50 nm/px,
11.2 um), as a generic, assumption-free texture representation.

Per tile: global mean and sd of stage-3 activations (1024 + 1024) and the final pooled
features (2048). Tiles are contrast-normalised per image (1-99 percentile) first.
"""

import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import tifffile

PROJECT_DIR = Path(__file__).resolve().parents[1]  # batch_match/
sys.path.insert(0, str(PROJECT_DIR))  # so batch_classifier / get4 import when run from anywhere

from batch_classifier import ROOT, index  # noqa: E402

MODEL = PROJECT_DIR / "out" / "models" / "resnet50-v2-7.onnx"
OUT = PROJECT_DIR / "out" / "classifier" / "deep_features.npz"
T = 224
MEAN, STD = np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32)


def session():
    m = onnx.load(str(MODEL))
    stage3 = [n.output[0] for n in m.graph.node if n.op_type == "Add" and "stage3" in n.output[0]][-1]
    for name in (stage3, "resnetv24_pool1_fwd"):
        m.graph.output.append(onnx.helper.make_tensor_value_info(name, onnx.TensorProto.FLOAT, None))
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    return ort.InferenceSession(m.SerializeToString(), opts), [stage3, "resnetv24_pool1_fwd"]


def tiles_of(path):
    a = tifffile.imread(path)
    g = (a[..., 0] if a.ndim == 3 else a).astype(np.float32)[:, 8:-8]
    h, w = g.shape[0] // 2 * 2, g.shape[1] // 2 * 2
    g = g[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))
    lo, hi = np.percentile(g[::4, ::4], [1, 99])
    g = np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1)
    ny, nx = g.shape[0] // T, g.shape[1] // T
    y0, x0 = (g.shape[0] - ny * T) // 2, (g.shape[1] - nx * T) // 2
    out = [g[y0 + i * T : y0 + (i + 1) * T, x0 + j * T : x0 + (j + 1) * T] for i in range(ny) for j in range(nx)]
    x = np.stack(out)[..., None].repeat(3, axis=-1)
    return ((x - MEAN) / STD).transpose(0, 3, 1, 2).astype(np.float32)


def main():
    sess, names = session()
    rows = index(ROOT)
    feats, image_of_tile = [], []
    for i, r in enumerate(rows):
        x = tiles_of(r["path"])
        for k in range(0, len(x), 16):
            s3, pool = sess.run(names, {"data": x[k : k + 16]})
            f = np.concatenate([s3.mean(axis=(2, 3)), s3.std(axis=(2, 3)), pool.reshape(len(pool), -1)], axis=1)
            feats.append(f.astype(np.float16))
            image_of_tile += [i] * len(f)
        print(f"  {i + 1}/{len(rows)} {r['batch']}/{r['path'].name}: {len(x)} tiles", flush=True)
    np.savez(
        OUT, X=np.vstack(feats), image_of_tile=np.array(image_of_tile), paths=np.array([str(r["path"]) for r in rows])
    )


if __name__ == "__main__":
    main()
