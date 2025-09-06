#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SDXL-Turbo img2img stylization of an equirectangular panorama as ONE whole image,
with horizontal wrap-around (no seam at 0°/360°).

Requirements (add to your requirements.txt if needed):
  diffusers>=0.29.0
  transformers>=4.41.0
  accelerate>=0.30.0
  safetensors>=0.4.2
  torch>=2.0.0
  Pillow>=9.5.0
  numpy>=1.23.0

Model: stabilityai/sdxl-turbo  (Hugging Face)
Docs/recs: guidance_scale=0.0, 1–4 steps, timestep_spacing='trailing'
"""

import argparse
import math
import os
from typing import Tuple

import numpy as np
from PIL import Image

import torch
from diffusers import StableDiffusionXLImg2ImgPipeline, EulerAncestralDiscreteScheduler


def load_image_rgb(path: str) -> Image.Image:
    img = Image.open(path).convert("RGB")
    return img


def save_jpeg(img: Image.Image, path: str, quality: int = 92):
    img.save(path, format="JPEG", quality=quality, optimize=True, progressive=True)


def circular_pad_horizontal(img: Image.Image, pad: int) -> Image.Image:
    """
    Horizontally wrap-pad an equirectangular image.
    New width = W + 2*pad. Left pad = rightmost 'pad' cols. Right pad = leftmost 'pad' cols.
    """
    if pad <= 0:
        return img
    w, h = img.size
    arr = np.array(img)
    left_pad = arr[:, w - pad : w, :]
    right_pad = arr[:, 0 : pad, :]
    padded = np.concatenate([left_pad, arr, right_pad], axis=1)
    return Image.fromarray(padded)


def crop_center_width(img: Image.Image, orig_w: int) -> Image.Image:
    """
    Remove horizontal padding, preserving original width centered.
    """
    w, h = img.size
    start_x = (w - orig_w) // 2
    end_x = start_x + orig_w
    return img.crop((start_x, 0, end_x, h))


def best_fit_size(
    w: int, h: int, max_side: int, require_multiple_of: int = 8
) -> Tuple[int, int, float]:
    """
    Downscale (preserving aspect) so that max(width,height) <= max_side and both dims are multiples of 'require_multiple_of'.
    Returns (new_w, new_h, scale_factor) where scale_factor is applied to original.
    """
    if max(w, h) <= max_side:
        new_w, new_h = w, h
    else:
        s = max_side / float(max(w, h))
        new_w, new_h = int(w * s), int(h * s)
    # round to multiple of N for diffusers
    new_w = max(require_multiple_of, (new_w // require_multiple_of) * require_multiple_of)
    new_h = max(require_multiple_of, (new_h // require_multiple_of) * require_multiple_of)
    # avoid zero
    new_w = max(new_w, require_multiple_of)
    new_h = max(new_h, require_multiple_of)
    scale = new_w / float(w)
    return new_w, new_h, scale


def main():
    parser = argparse.ArgumentParser("SDXL-Turbo 360° whole-image retro stylization with horizontal wrap")
    parser.add_argument("--input", required=True, help="Input equirectangular panorama (JPG/PNG, ideally 2:1).")
    parser.add_argument("--output", required=True, help="Output stylized panorama JPG.")
    parser.add_argument("--prompt", default="retro film look, faded colors, warm tones, film grain, subtle vignette, vintage aesthetic",
                        help="Positive prompt describing target style.")
    parser.add_argument("--negative_prompt", default="text, watermark, logo, extra objects, artifacts, distorted geometry",
                        help="Negative prompt to avoid unwanted content.")
    parser.add_argument("--strength", type=float, default=0.3,
                        help="How much to change the image (0.1–0.4 recommended for preserving scene).")
    parser.add_argument("--steps", type=int, default=4, help="1–4 recommended for SDXL Turbo.")
    parser.add_argument("--wrap_pad", type=int, default=96,
                        help="Pixels of horizontal wrap padding (try 64–192 depending on resolution).")
    parser.add_argument("--max_side", type=int, default=1536,
                        help="Downscale so max(width,height) <= this to fit VRAM; 1024–2048 typical.")
    parser.add_argument("--seed", type=int, default=12345, help="Random seed (determinism).")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Inference device.")
    parser.add_argument("--dtype", default="fp16", choices=["fp16", "fp32"], help="Torch dtype to load the model.")
    parser.add_argument("--hf_model", default="stabilityai/sdxl-turbo", help="Hugging Face model id.")
    args = parser.parse_args()

    # Device & dtype
    device = "cuda" if (args.device == "auto" and torch.cuda.is_available()) else (args.device if args.device != "auto" else "cpu")
    torch_dtype = torch.float16 if (args.dtype == "fp16" and device == "cuda") else torch.float32

    # Load model (Turbo recs: guidance_scale=0, 1–4 steps, trailing spacing)
    # HF model card & docs: stabilityai/sdxl-turbo
    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        args.hf_model,
        torch_dtype=torch_dtype,
        variant="fp16" if torch_dtype == torch.float16 else None,
        use_safetensors=True,
    )

    # Use a fast Turbo-friendly scheduler with trailing timestep spacing
    pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")

    # Optional memory optimizations
    if device == "cuda":
        pipe.enable_model_cpu_offload()  # safe default; or use .to("cuda") if you prefer
        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass
    else:
        pipe.to(device)

    # Load input
    base = load_image_rgb(args.input)
    W, H = base.size
    if W < 64 or H < 64:
        raise ValueError("Image is too small.")

    # Horizontal wrap padding to avoid seam at 0°/360°
    padded = circular_pad_horizontal(base, args.wrap_pad)
    Wp, Hp = padded.size

    # Scale to fit VRAM if necessary (keep aspect)
    new_w, new_h, scale = best_fit_size(Wp, Hp, max_side=args.max_side, require_multiple_of=8)
    padded_resized = padded.resize((new_w, new_h), Image.LANCZOS)

    # Determinism
    generator = torch.Generator(device=device)
    generator = generator.manual_seed(args.seed)

    # Run SDXL Turbo img2img
    # Turbo guidance_scale MUST be 0.0; low steps; low strength to preserve geometry.
    result = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        image=padded_resized,
        strength=args.strength,
        guidance_scale=0.0,
        num_inference_steps=max(1, min(4, args.steps)),
        generator=generator,
    )

    out_img_small = result.images[0]

    # Restore original padded size if we downscaled
    if (out_img_small.size != (Wp, Hp)):
        out_img = out_img_small.resize((Wp, Hp), Image.LANCZOS)
    else:
        out_img = out_img_small

    # Remove horizontal padding -> back to original width
    out_cropped = crop_center_width(out_img, orig_w=W)

    # Save
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    save_jpeg(out_cropped, args.output, quality=92)
    print(f"[OK] Saved: {args.output}")
    print(f"Input: {W}x{H}  |  Padded: {Wp}x{Hp}  |  Proc: {new_w}x{new_h}  |  Steps={args.steps}, strength={args.strength}, guidance_scale=0.0")


if __name__ == "__main__":
    main()
