#!/usr/bin/env python3
"""Extract and composite red seal pixels from multiple scanned images."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ASSET_DIR = Path("/home/ubuntu/.cursor/projects/workspace/assets")
OUTPUT_DIR = Path("/workspace/seal_restore/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_PATHS = [
    ASSET_DIR / "011ed981-b63e-487f-9a2b-d13963a81766.png",
    ASSET_DIR / "7a470a3a-973d-4d61-ba8a-b5f1e6de16c4.png",
    ASSET_DIR / "c5b5ecbf-b5ca-4f75-bfad-8a9d4a669c41.png",
    ASSET_DIR / "36e74231-c908-4b91-afc3-0a7c2e99b200.png",
    ASSET_DIR / "9a06d499-846e-464b-9465-09ad09644801.png",
]

CANVAS = 1800
TARGET_RADIUS = 700
MIN_OVERLAP = 0.22
REF_INDEX = 0


def load_bgr(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def save_rgba(path: Path, rgba_bgra: np.ndarray) -> None:
    rgb = cv2.cvtColor(rgba_bgra, cv2.COLOR_BGRA2RGBA)
    Image.fromarray(rgb).save(path)


def estimate_circle(mask: np.ndarray) -> tuple[float, float, float]:
    ys, xs = np.where(mask > 0)
    if len(xs) < 50:
        raise ValueError("Not enough stamp pixels")
    cx = float(np.median(xs))
    cy = float(np.median(ys))
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    radius = float(np.percentile(dist, 97.5))
    return cx, cy, radius


def extract_red_rgba(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    b, g, r = cv2.split(bgr)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    dark = gray < 75
    neutral_dark = (
        (np.abs(r.astype(np.int16) - g.astype(np.int16)) < 30)
        & (np.abs(r.astype(np.int16) - b.astype(np.int16)) < 30)
        & (gray < 130)
    )
    black_mask = dark | neutral_dark

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hsv_mask = cv2.inRange(hsv, (0, 28, 35), (22, 255, 255)) | cv2.inRange(
        hsv, (150, 28, 35), (180, 255, 255)
    )
    rgb_mask = (
        (r.astype(np.float32) > 1.1 * g.astype(np.float32))
        & (r.astype(np.float32) > 1.1 * b.astype(np.float32))
        & (r > 48)
    )
    raw_mask = (hsv_mask > 0) & rgb_mask & (~black_mask)

    cx, cy, radius = estimate_circle(raw_mask.astype(np.uint8))
    yy, xx = np.ogrid[: bgr.shape[0], : bgr.shape[1]]
    circle_mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= (radius * 1.03) ** 2
    stamp_u8 = (raw_mask & circle_mask).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    stamp_u8 = cv2.morphologyEx(stamp_u8, cv2.MORPH_CLOSE, kernel, iterations=1)

    rgba = np.zeros((*bgr.shape[:2], 4), dtype=np.uint8)
    rgba[:, :, 0] = b
    rgba[:, :, 1] = g
    rgba[:, :, 2] = r
    rgba[:, :, 3] = stamp_u8

    s = hsv[:, :, 1].astype(np.float32) / 255.0
    redness = np.clip((r.astype(np.float32) - np.maximum(g, b).astype(np.float32)) / 255.0, 0, 1)
    quality = (stamp_u8.astype(np.float32) / 255.0) * (0.35 + 0.65 * s) * (0.25 + 0.75 * redness)

    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    sharp = cv2.GaussianBlur(np.abs(lap), (5, 5), 0)
    if np.any(stamp_u8):
        sharp = sharp / (np.percentile(sharp[stamp_u8 > 0], 95) + 1e-6)
    quality = quality * (0.6 + 0.4 * np.clip(sharp, 0, 1))

    return rgba, quality.astype(np.float32), cx, cy, radius


def patch_radius(rgba: np.ndarray) -> float:
    ys, xs = np.where(rgba[:, :, 3] > 0)
    cx, cy = xs.mean(), ys.mean()
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    return float(np.percentile(dist, 97))


def recenter_and_scale(
    rgba: np.ndarray, quality: np.ndarray, cx: float, cy: float, radius: float
) -> tuple[np.ndarray, np.ndarray]:
    half = int(radius * 1.12)
    x0, y0 = int(cx) - half, int(cy) - half
    x1, y1 = x0 + 2 * half, y0 + 2 * half

    pad_l = max(0, -x0)
    pad_t = max(0, -y0)
    pad_r = max(0, x1 - rgba.shape[1])
    pad_b = max(0, y1 - rgba.shape[0])

    if any((pad_l, pad_t, pad_r, pad_b)):
        rgba = cv2.copyMakeBorder(rgba, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
        quality = cv2.copyMakeBorder(quality, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_CONSTANT, value=0)
        x0 += pad_l
        y0 += pad_t

    crop_rgba = rgba[y0 : y0 + 2 * half, x0 : x0 + 2 * half].copy()
    crop_q = quality[y0 : y0 + 2 * half, x0 : x0 + 2 * half].copy()

    ys, xs = np.where(crop_rgba[:, :, 3] > 0)
    if len(xs):
        dx = half - float(xs.mean())
        dy = half - float(ys.mean())
        m = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
        crop_rgba = cv2.warpAffine(
            crop_rgba, m, (2 * half, 2 * half), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0, 0)
        )
        crop_q = cv2.warpAffine(crop_q, m, (2 * half, 2 * half), flags=cv2.INTER_LINEAR, borderValue=0)

    out_rgba = cv2.resize(crop_rgba, (CANVAS, CANVAS), interpolation=cv2.INTER_CUBIC)
    out_q = cv2.resize(crop_q, (CANVAS, CANVAS), interpolation=cv2.INTER_LINEAR)

    local_r = patch_radius(out_rgba)
    if local_r > 0:
        scale = TARGET_RADIUS / local_r
        center = (CANVAS // 2, CANVAS // 2)
        m = cv2.getRotationMatrix2D(center, 0, scale)
        out_rgba = cv2.warpAffine(
            out_rgba, m, (CANVAS, CANVAS), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0, 0)
        )
        out_q = cv2.warpAffine(out_q, m, (CANVAS, CANVAS), flags=cv2.INTER_LINEAR, borderValue=0)

    return out_rgba, out_q


def rotate_patch(rgba: np.ndarray, quality: np.ndarray, angle_deg: float) -> tuple[np.ndarray, np.ndarray]:
    center = (CANVAS // 2, CANVAS // 2)
    m = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rgba_rot = cv2.warpAffine(
        rgba, m, (CANVAS, CANVAS), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0)
    )
    quality_rot = cv2.warpAffine(
        quality, m, (CANVAS, CANVAS), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )
    return rgba_rot, quality_rot


def overlap_score(ref_mask: np.ndarray, cand_mask: np.ndarray) -> float:
    ref = ref_mask > 0
    cand = cand_mask > 0
    return float(np.logical_and(ref, cand).sum()) / float(np.logical_or(ref, cand).sum() + 1e-6)


def find_best_rotation(rgba: np.ndarray, quality: np.ndarray, ref_mask: np.ndarray) -> float:
    best_angle = 0.0
    best_score = -1.0
    for angle in np.arange(0, 360, 2):
        rot_rgba, _ = rotate_patch(rgba, quality, float(angle))
        score = overlap_score(ref_mask, rot_rgba[:, :, 3])
        if score > best_score:
            best_score = score
            best_angle = float(angle)
    for angle in np.arange(best_angle - 4, best_angle + 4.1, 0.25):
        rot_rgba, _ = rotate_patch(rgba, quality, float(angle))
        score = overlap_score(ref_mask, rot_rgba[:, :, 3])
        if score > best_score:
            best_score = score
            best_angle = float(angle)
    return best_angle


def refine_translation(rgba: np.ndarray, quality: np.ndarray, ref_alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    moving = (rgba[:, :, 3] > 0).astype(np.float32)
    fixed = (ref_alpha > 0).astype(np.float32)
    if moving.sum() < 100 or fixed.sum() < 100:
        return rgba, quality
    shift, response = cv2.phaseCorrelate(fixed, moving)
    if response < 0.05:
        return rgba, quality
    dx, dy = shift
    m = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
    rgba_out = cv2.warpAffine(rgba, m, (CANVAS, CANVAS), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0, 0))
    quality_out = cv2.warpAffine(quality, m, (CANVAS, CANVAS), flags=cv2.INTER_LINEAR, borderValue=0)
    return rgba_out, quality_out


def inside_disk() -> np.ndarray:
    center = CANVAS // 2
    yy, xx = np.ogrid[:CANVAS, :CANVAS]
    return (xx - center) ** 2 + (yy - center) ** 2 <= (TARGET_RADIUS * 1.04) ** 2


def fuse_gap_only(
    base_rgba: np.ndarray,
    base_q: np.ndarray,
    donors: list[tuple[np.ndarray, np.ndarray, float]],
) -> np.ndarray:
    disk = inside_disk()
    out = base_rgba.copy()
    out_q = base_q.copy()

    for rgba, quality, overlap in sorted(donors, key=lambda item: item[2], reverse=True):
        gaps = disk & (out[:, :, 3] == 0) & (rgba[:, :, 3] > 0)
        # Prefer higher-quality donor pixels for each gap.
        better = gaps & (quality > out_q)
        out[better] = rgba[better]
        out_q[better] = quality[better]

        gaps = disk & (out[:, :, 3] == 0) & (rgba[:, :, 3] > 0)
        out[gaps] = rgba[gaps]
        out_q[gaps] = quality[gaps]

    return out


def replace_weak_pixels(
    base_rgba: np.ndarray,
    base_q: np.ndarray,
    donors: list[tuple[np.ndarray, np.ndarray, float]],
) -> np.ndarray:
    """Replace low-quality existing pixels when a donor has clearly better data."""
    out = base_rgba.copy()
    out_q = base_q.copy()
    weak = (out[:, :, 3] > 0) & (out_q < 0.28)

    for rgba, quality, _ in sorted(donors, key=lambda item: item[2], reverse=True):
        replace = weak & (rgba[:, :, 3] > 0) & (quality > out_q + 0.12)
        out[replace] = rgba[replace]
        out_q[replace] = quality[replace]
        weak &= ~replace

    return out


def postprocess(rgba: np.ndarray) -> np.ndarray:
    alpha = rgba[:, :, 3].copy()
    # Remove isolated single-pixel noise only.
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx((alpha > 0).astype(np.uint8), cv2.MORPH_OPEN, kernel, iterations=1)
    alpha[opened == 0] = 0
    out = rgba.copy()
    out[:, :, 3] = alpha
    return out


def crop_content(rgba: np.ndarray, pad: int = 40) -> np.ndarray:
    ys, xs = np.where(rgba[:, :, 3] > 0)
    if len(xs) == 0:
        return rgba
    return rgba[max(0, ys.min() - pad) : ys.max() + pad + 1, max(0, xs.min() - pad) : xs.max() + pad + 1]


def upscale_for_output(rgba: np.ndarray, scale: float = 1.5) -> np.ndarray:
    h, w = rgba.shape[:2]
    rgb = cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)
    pil = Image.fromarray(rgb)
    pil = pil.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGBA2BGRA)


def main() -> Path:
    patches: list[tuple[np.ndarray, np.ndarray, str]] = []

    for path in IMAGE_PATHS:
        bgr = load_bgr(path)
        rgba, quality, cx, cy, radius = extract_red_rgba(bgr)
        save_rgba(OUTPUT_DIR / f"extracted_{path.stem}.png", rgba)
        norm_rgba, norm_q = recenter_and_scale(rgba, quality, cx, cy, radius)
        patches.append((norm_rgba, norm_q, path.name))
        save_rgba(OUTPUT_DIR / f"patch_{path.stem}.png", norm_rgba)

    ref_rgba, ref_q, ref_name = patches[REF_INDEX]
    ref_mask = ref_rgba[:, :, 3]
    save_rgba(OUTPUT_DIR / "reference_normalized.png", ref_rgba)

    donors: list[tuple[np.ndarray, np.ndarray, float]] = []
    for idx, (rgba, quality, name) in enumerate(patches):
        if idx == REF_INDEX:
            continue

        angle = find_best_rotation(rgba, quality, ref_mask)
        rot_rgba, rot_q = rotate_patch(rgba, quality, angle)
        rot_rgba, rot_q = refine_translation(rot_rgba, rot_q, ref_mask)
        overlap = overlap_score(ref_mask, rot_rgba[:, :, 3])
        save_rgba(OUTPUT_DIR / f"aligned_{idx}_{name}.png", rot_rgba)
        print(f"aligned {name}: angle={angle:.1f} overlap={overlap:.3f}")

        if overlap >= MIN_OVERLAP:
            donors.append((rot_rgba, rot_q, overlap))

    fused = fuse_gap_only(ref_rgba, ref_q, donors)
    fused = postprocess(fused)
    fused = crop_content(fused)
    fused = upscale_for_output(fused, 1.5)

    out_path = OUTPUT_DIR / "china_tower_baoji_seal_restored.png"
    save_rgba(out_path, fused)
    print(f"Saved {out_path} size={fused.shape[1]}x{fused.shape[0]} ref={ref_name} donors={len(donors)}")
    return out_path


if __name__ == "__main__":
    main()
