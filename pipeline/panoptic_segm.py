#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
End-to-end:
- Load equirectangular panorama (JPG/PNG).
- Panoptic segmentation (Mask2Former, COCO).
- Per-segment stylization (demo: non-destructive color grading presets).
- Two modes:
    A) direct equirect (no cubemap)
    B) cubemap split + per-face processing + weighted blending back to equirect
"""

import argparse, os, random
from typing import Dict, Tuple, List
import numpy as np
from PIL import Image, ImageFilter

import torch
from diffusers import StableDiffusionXLImg2ImgPipeline
from transformers import Mask2FormerImageProcessor, Mask2FormerForUniversalSegmentation

import py360convert as py360
from scipy.ndimage import gaussian_filter

FACE_ORDER = ["F","R","B","L","U","D"]
IMG_EXTS = (".jpg",".jpeg",".png",".webp")

# ------------------------------
# Utility: IO
# ------------------------------
def load_rgb(path: str) -> Image.Image:
    return Image.open(path).convert("RGB")

def save_jpeg(img: Image.Image, path: str, quality: int = 92):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, format="JPEG", quality=quality, optimize=True, progressive=True)

# ------------------------------
# 360 helpers
# ------------------------------
def equirect_to_faces(equi_img: Image.Image, face_w: int) -> Dict[str, Image.Image]:
    equi_np = np.array(equi_img)[:,:,:3]
    cube = py360.e2c(equi_np, face_w=face_w, mode="bilinear")
    if isinstance(cube, dict):
        return {k: Image.fromarray(cube[k]) for k in FACE_ORDER}
    # fallback przez projekcję perspektywiczną (stabilne na różnych wersjach py360convert)
    faces = {}
    for k, yaw, pitch in [("F",0,0),("R",90,0),("B",180,0),("L",-90,0),("U",0,90),("D",0,-90)]:
        f = py360.e2p(equi_np, fov_deg=90, u_deg=yaw, v_deg=pitch, out_hw=(face_w, face_w), mode="bilinear")
        faces[k] = Image.fromarray(f)
    return faces

def project_face_to_equirect(face_key: str, face_img: Image.Image, out_h: int, out_w: int) -> np.ndarray:
    blank = np.zeros((face_img.height, face_img.width, 3), dtype=np.uint8)
    cube = {k: (np.array(face_img) if k==face_key else blank) for k in FACE_ORDER}
    equi = py360.c2e(cube, h=out_h, w=out_w, mode="bilinear")
    return equi.astype(np.float32)/255.0  # HxWx3

def soft_edge_mask(face_img: Image.Image, sigma_px: int = 24) -> np.ndarray:
    h,w = face_img.height, face_img.width
    y,x = np.mgrid[0:h,0:w]
    d = np.minimum.reduce([x,y,w-1-x,h-1-y]).astype(np.float32)
    d /= (d.max()+1e-6)
    m = gaussian_filter(d, sigma=sigma_px)
    m -= m.min(); m /= (m.max()+1e-6)
    return m  # HxW 0..1

def project_mask_to_equirect(face_key: str, mask: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    h,w = mask.shape
    mask_rgb = np.clip(mask,0,1)[:,:,None].repeat(3,axis=2)
    blank = np.zeros((h,w,3),dtype=np.float32)
    cube = {k:(mask_rgb if k==face_key else blank) for k in FACE_ORDER}
    equi = py360.c2e({k:((cube[k]*255).astype(np.uint8)) for k in FACE_ORDER}, h=out_h, w=out_w, mode="bilinear")
    equi = equi.astype(np.float32)/255.0
    return equi.mean(axis=2)

def multiband_blend(numer: np.ndarray, denom: np.ndarray, levels: int = 3) -> np.ndarray:
    eps = 1e-6
    out = np.zeros_like(numer)
    sigmas = [0,2,6][:levels]
    for s in sigmas:
        if s==0:
            n_s, d_s = numer, denom
        else:
            n_s = gaussian_filter(numer, sigma=[s,s,0])
            d_s = gaussian_filter(denom, sigma=s)
        out += n_s / (d_s[...,None] + eps)
    out /= len(sigmas)
    return np.clip(out,0,1)

# ------------------------------
# Panoptic segmentation (Mask2Former)
# ------------------------------
def load_panoptic_model(device: str):
    processor = Mask2FormerImageProcessor.from_pretrained("facebook/mask2former-swin-base-coco-panoptic")
    model = Mask2FormerForUniversalSegmentation.from_pretrained("facebook/mask2former-swin-base-coco-panoptic")
    model.to(device).eval()
    return processor, model

def run_panoptic(processor, model, img: Image.Image, device: str):
    inputs = processor(images=img, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    pred = processor.post_process_panoptic_segmentation(outputs, target_sizes=[img.size[::-1]])[0]
    # pred: {"segmentation": HxW (tensor), "segments_info":[{id,label_id,score,isthing},...]}
    return pred

# ------------------------------
# Simple color-grade stylization per segment
# (tu możesz podmienić na AdaIN/SDXL dla maski)
# ------------------------------
# przykładowe etykiety COCO (skrót):
COCO_LABELS = {
    0:"unlabeled", 1:"person", 2:"bicycle", 3:"car", 4:"motorcycle", 5:"airplane", 6:"bus", 7:"train",
    8:"truck", 9:"boat", 10:"traffic light", 11:"fire hydrant", 13:"stop sign", 15:"bench",
    16:"bird", 17:"cat", 18:"dog", 19:"horse", 20:"sheep", 21:"cow",
    24:"zebra", 25:"giraffe", 27:"backpack", 28:"umbrella",
    32:"sports ball", 33:"kite", 34:"baseball bat", 35:"baseball glove", 36:"skateboard", 37:"surfboard", 38:"tennis racket",
    39:"bottle", 40:"wine glass", 41:"cup", 42:"fork", 43:"knife", 44:"spoon", 45:"bowl",
    46:"banana", 47:"apple", 48:"sandwich", 49:"orange", 50:"broccoli", 51:"carrot", 52:"hot dog", 53:"pizza", 54:"donut", 55:"cake",
    56:"chair", 57:"couch", 58:"potted plant", 59:"bed",
    61:"dining table", 62:"toilet",
    63:"tv", 64:"laptop", 65:"mouse", 66:"remote", 67:"keyboard", 68:"cell phone",
    69:"microwave", 70:"oven", 71:"toaster", 72:"sink", 73:"refrigerator",
    74:"book", 75:"clock", 76:"vase", 77:"scissors", 78:"teddy bear", 79:"hair drier", 80:"toothbrush",
}

def apply_color_grade(arr: np.ndarray, mode: str) -> np.ndarray:
    # arr: HxWx3 float32 0..1
    x = arr.copy()
    if mode == "cyberpunk":
        # chłodny push + neon glow light
        x[...,1] *= 0.95  # G down
        x[...,2] = np.clip(x[...,2]*1.08, 0, 1)  # B up
        x = np.clip(np.power(x, 0.9), 0, 1)      # lekka gamma<1
        x = np.clip(x + 0.02, 0, 1)             # odrobina „glow”
    elif mode == "retro":
        m = np.array([[1.07, -0.03, -0.04],
                      [-0.02, 1.02, -0.02],
                      [0.02, -0.02, 0.98]], dtype=np.float32)
        x = np.clip(x @ m.T, 0, 1)
        x = np.clip((x*0.97)+0.02, 0, 1)        # lekkie ocieplenie
    elif mode == "contrast":
        x = np.clip((x-0.5)*1.1 + 0.5, 0, 1)
    return x

# Cache SDXL Turbo pipeline (global, lazy init)
_sdxl_turbo_pipe = None
def get_sdxl_turbo_pipe(device="cpu"):
    global _sdxl_turbo_pipe
    if _sdxl_turbo_pipe is None:
        _sdxl_turbo_pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            "stabilityai/sdxl-turbo", torch_dtype=torch.float16 if device.startswith("cuda") else torch.float32
        )
        _sdxl_turbo_pipe.to(device)
    return _sdxl_turbo_pipe

def stylize_segment(base: Image.Image, mask_bin: np.ndarray, class_id: int, isthing:bool, device="cuda") -> Image.Image:
    arr = np.array(base).astype(np.float32)/255.0
    h,w,_ = arr.shape
    mask = mask_bin.astype(bool)

    if isthing:
        prompt = "cyberpunk object, vibrant, neon, sharp, detailed, futuristic"
    else:
        prompt = "cyberpunk background, vibrant, neon, cinematic"

    # Only stylize masked region using SDXL Turbo
    if mask.sum() > 0:
        pipe = get_sdxl_turbo_pipe(device)
        # Prepare masked image for SDXL Turbo (white outside mask)
        base_arr = arr.copy()
        base_arr[~mask] = 1.0  # white background for out-of-mask
        base_img = Image.fromarray(np.clip(base_arr*255,0,255).astype(np.uint8))
        # SDXL Turbo expects PIL.Image in RGB, 1024x1024 or similar
        sdxl_in = base_img.resize((min(1024, w), min(1024, h)), Image.LANCZOS)
        # Run SDXL Turbo
        with torch.autocast(device_type=device):
            result = pipe(prompt=prompt, image=sdxl_in, strength=0.7, guidance_scale=1.0, num_inference_steps=4)
        stylized = result.images[0].resize((w, h), Image.LANCZOS)
        stylized_arr = np.array(stylized).astype(np.float32)/255.0
        # Blend only masked region
        out = arr.copy()
        out[mask] = stylized_arr[mask]
    else:
        out = arr

    return Image.fromarray(np.clip(out*255,0,255).astype(np.uint8))

# ------------------------------
# Core pipelines
# ------------------------------
def process_equirect(img: Image.Image, device: str, seg_stride: int = 2048) -> Image.Image:
    """
    Tryb A: bez cubemapy — panoptic na całym obrazie, per-segment stylizacja.
    seg_stride: jeśli obraz bardzo duży, można go chwilowo przeskalować (<= seg_stride dłuższy bok)
    """
    W,H = img.width, img.height
    scale = 1.0
    if max(W,H) > seg_stride:
        scale = seg_stride / float(max(W,H))
        resized = img.resize((int(W*scale), int(H*scale)), Image.LANCZOS)
    else:
        resized = img

    processor, model = load_panoptic_model(device)
    pred = run_panoptic(processor, model, resized, device)

    seg = pred["segmentation"].cpu().numpy().astype(np.int32)    # Hs x Ws
    segments = pred["segments_info"]                              # list of dicts

    # przeskaluj maski do oryginalu, jeśli segmentacja była na mniejszym
    if scale != 1.0:
        seg_img = Image.fromarray(seg.astype(np.int32))
        seg = np.array(seg_img.resize((W,H), Image.NEAREST)).astype(np.int32)

    # per-segment stylizacja i compositing
    base = img
    out = np.array(base).astype(np.float32)/255.0
    for s in segments:
        sid = s["id"]
        class_id = s.get("label_id", -1)
        isthing = bool(s.get("isthing", True))
        mask = (seg == sid)
        if mask.sum() == 0:
            continue
        seg_img = stylize_segment(base, mask, class_id, isthing)
        seg_arr = np.array(seg_img).astype(np.float32)/255.0
        out[mask] = seg_arr[mask]

    return Image.fromarray(np.clip(out*255,0,255).astype(np.uint8))

def process_cubemap(img: Image.Image, device: str, face_size: int = 1024, mask_sigma: int = 24, pyr_levels: int = 3) -> Image.Image:
    """
    Tryb B: cubemap — na każdej ścianie panoptic + stylizacja, potem składanie z featheringiem.
    """
    H,W = img.height, img.width
    faces = equirect_to_faces(img, face_w=face_size)

    processor, model = load_panoptic_model(device)

    # wynik ważony w domenie equirect
    numer = np.zeros((H,W,3), dtype=np.float32)
    denom = np.zeros((H,W), dtype=np.float32)

    for k in FACE_ORDER:
        face = faces[k]

        # panoptic na ścianie
        pred = run_panoptic(processor, model, face, device)
        seg = pred["segmentation"].cpu().numpy().astype(np.int32)
        segments = pred["segments_info"]

        # dla każdej maski zrób stylizację w przestrzeni ściany
        base_face_arr = np.array(face).astype(np.float32)/255.0
        out_face = base_face_arr.copy()

        for s in segments:
            sid = s["id"]
            class_id = s.get("label_id", -1)
            isthing = bool(s.get("isthing", True))
            mask = (seg == sid)
            if mask.sum() == 0: continue

            seg_img = stylize_segment(face, mask, class_id, isthing)
            seg_arr = np.array(seg_img).astype(np.float32)/255.0
            out_face[mask] = seg_arr[mask]

        out_face_img = Image.fromarray(np.clip(out_face*255,0,255).astype(np.uint8))

        # projekcja do equirect i blending
        proj = project_face_to_equirect(k, out_face_img, out_h=H, out_w=W)  # HxWx3
        m_face = soft_edge_mask(out_face_img, sigma_px=mask_sigma)
        m_equi = project_mask_to_equirect(k, m_face, out_h=H, out_w=W)      # HxW

        numer += proj * m_equi[...,None]
        denom += m_equi

    out = multiband_blend(numer, denom, levels=pyr_levels)
    return Image.fromarray(np.clip(out*255,0,255).astype(np.uint8))

# ------------------------------
# CLI
# ------------------------------
def main():
    ap = argparse.ArgumentParser("Panoptic 360 stylization (Mask2Former) — equirect or cubemap")
    ap.add_argument("--input", required=True, help="Wejściowy panorama JPG/PNG (2:1 zalecane).")
    ap.add_argument("--output", required=True, help="Wyjściowy JPG.")
    ap.add_argument("--mode", default="equirect", choices=["equirect","cubemap"], help="Tryb przetwarzania.")
    ap.add_argument("--device", default="auto", choices=["auto","cpu","cuda"])
    ap.add_argument("--face_size", type=int, default=1024, help="Rozmiar ścian cubemap (dla mode=cubemap).")
    ap.add_argument("--mask_sigma", type=int, default=24, help="Miękkość featheringu na krawędziach (cubemap).")
    ap.add_argument("--pyr_levels", type=int, default=3, help="Multi-band blending levels (cubemap).")
    ap.add_argument("--seg_stride", type=int, default=2048, help="Maks. dłuższy bok do segmentacji (equirect).")
    args = ap.parse_args()

    device = "cuda" if (args.device=="auto" and torch.cuda.is_available()) else (args.device if args.device!="auto" else "cpu")

    img = load_rgb(args.input)

    if args.mode == "equirect":
        out = process_equirect(img, device=device, seg_stride=args.seg_stride)
    else:
        out = process_cubemap(img, device=device, face_size=args.face_size,
                              mask_sigma=args.mask_sigma, pyr_levels=args.pyr_levels)

    save_jpeg(out, args.output, quality=92)
    print(f"[OK] Saved: {args.output}")

if __name__ == "__main__":
    main()
