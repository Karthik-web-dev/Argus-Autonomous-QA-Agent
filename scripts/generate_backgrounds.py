"""Generate Argus's original, dithered rolling-hill marketing backgrounds."""
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1] / "packages/ui/public/images"


def landscape(name: str, width: int, height: int, seed: int, sky_top, sky_bottom,
              hills, path=False, flowers=True):
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    img = np.zeros((height, width, 3), dtype=np.float32)
    top, bottom = np.array(sky_top), np.array(sky_bottom)
    sky_mix = np.clip(y / 0.72, 0, 1)[..., None]
    img[:] = top[None, None, :] * (1 - sky_mix) + bottom[None, None, :] * sky_mix
    broad = rng.normal(0, 0.018, (1, width)).astype(np.float32)
    broad = np.convolve(broad[0], np.ones(61) / 61, mode="same")[None, :]
    img += broad[..., None] * 255

    xx = np.arange(width, dtype=np.float32)
    for index, (base, amp, color, phase) in enumerate(hills):
        curve = base + amp * (0.55 * np.sin(xx / (width * 0.095) + phase)
                              + 0.28 * np.sin(xx / (width * 0.031) + phase * 1.7)
                              + 0.17 * np.sin(xx / (width * 0.014) - phase))
        curve += np.convolve(rng.normal(0, 0.007, width), np.ones(41) / 41, mode="same")
        edge = curve[None, :]
        mask = y >= edge
        shade = np.clip((y - edge) / (1 - edge + 0.001), 0, 1)
        texture = (0.94 + 0.06 * np.sin(x * (16 + index * 5) + y * 22 + phase))
        layer = np.array(color)[None, None, :] * texture[..., None]
        layer = layer * (1 - shade[..., None] * 0.15)
        img = np.where(mask[..., None], layer, img)

    if path:
        # A softly winding, bright trail running through the valley.
        center = 0.79 - 0.08 * np.sin(x * 5.1 + 0.4) + 0.025 * np.sin(x * 14)
        thickness = 0.016 + 0.012 * np.clip(x * 1.3, 0, 1)
        pathmask = np.abs(y - center) < thickness
        glow = np.abs(y - center) < thickness * 2.8
        img = np.where(glow[..., None], img * 0.77 + np.array([96, 151, 72])[None, None, :] * 0.23, img)
        img = np.where(pathmask[..., None], np.array([190, 224, 112])[None, None, :], img)

    if flowers:
        # Distant flower flecks are sparse and grow denser toward the foreground.
        count = width * height // 230
        px = rng.integers(0, width, count)
        py = rng.integers(int(height * 0.7), height, count)
        colors = np.array([[190, 112, 171], [135, 105, 183], [211, 159, 192], [116, 165, 106]])
        for cx, cy in zip(px, py):
            if rng.random() < (cy / height - 0.65) * 1.8:
                img[cy, cx] = colors[rng.integers(0, len(colors))]
                if rng.random() < 0.22 and cy + 1 < height:
                    img[cy + 1, cx] = colors[rng.integers(0, len(colors))]

    # Fine analog grain before ordered palette reduction.
    img += rng.normal(0, 3.8, img.shape).astype(np.float32)
    img = np.clip(img, 0, 255)
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)
    threshold = np.tile((bayer / 16 - 0.5) * 13, (height // 4 + 1, width // 4 + 1))[:height, :width]
    img = np.clip(img + threshold[..., None], 0, 255)
    # A compact palette preserves the reference's distinctly dithered character.
    img = np.round(img / 12) * 12
    Image.fromarray(img.astype(np.uint8), "RGB").save(ROOT / f"{name}.webp", "WEBP", quality=88, method=6)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    landscape("hero-bg", 2400, 1460, 14, (88, 80, 113), (156, 117, 152), [
        (0.59, 0.08, (44, 49, 86), 0.4), (0.68, 0.09, (15, 20, 35), 1.5),
        (0.81, 0.07, (7, 10, 18), 2.4)], path=True)
    landscape("hills-green-purple", 1200, 1200, 25, (25, 36, 66), (76, 67, 105), [
        (0.52, 0.12, (110, 160, 112), 0.5), (0.65, 0.13, (66, 125, 101), 2.1),
        (0.82, 0.11, (29, 60, 62), 3.2)], flowers=False)
    landscape("hills-console", 1400, 1120, 33, (30, 49, 55), (89, 100, 77), [
        (0.48, 0.12, (134, 174, 121), 1.2), (0.63, 0.11, (67, 126, 95), 2.8),
        (0.79, 0.12, (35, 57, 69), 0.1)])
    landscape("hills-code", 1200, 1200, 47, (50, 43, 83), (125, 101, 139), [
        (0.53, 0.1, (133, 176, 112), 2.3), (0.67, 0.12, (76, 127, 96), 1.1),
        (0.82, 0.12, (50, 50, 85), 3.0)], flowers=False)


if __name__ == "__main__":
    main()
