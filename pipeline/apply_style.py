#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, os, glob, random
from typing import List, Dict, Tuple
import numpy as np
from PIL import Image
import torch, torch.nn as nn
import py360convert as py360
from scipy.ndimage import gaussian_filter

FACE_ORDER = ["F", "R", "B", "L", "U", "D"]

# ===== AdaIN (jak wcześniej, skrót) =====
class VGGEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.enc = nn.Sequential()
    def forward(self, x): return self.enc(x)

class Decoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.dec = nn.Sequential()
    def forward(self, x): return self.dec(x)

def adain(c_feat: torch.Tensor, s_feat: torch.Tensor, eps: float = 1e-5):
    c_mean = c_feat.mean(dim=[2,3], keepdim=True); c_std = c_feat.std(dim=[2,3], keepdim=True)+eps
    s_mean = s_feat.mean(dim=[2,3], keepdim=True); s_std = s_feat.std(dim=[2,3], keepdim=True)+eps
    return (c_feat - c_mean)/c_std * s_std + s_mean

def pil_to_tensor(img: Image.Image) -> torch.Tensor:
    arr = np.array(img).astype(np.float32) / 255.0
    if arr.ndim == 2: arr = np.stack([arr]*3, -1)
    if arr.shape[2] == 4: arr = arr[:,:,:3]
    arr = arr.transpose(2,0,1)  # CHW
    return torch.from_numpy(arr)[None]

def tensor_to_pil(t: torch.Tensor) -> Image.Image:
    t = torch.clamp(t, 0, 1)[0].detach().cpu().numpy().transpose(1,2,0)*255
    return Image.fromarray(t.astype(np.uint8))

def stylize_adain(encoder, decoder, content_img: Image.Image, style_img: Image.Image, device="cpu", alpha=0.8):
    encoder.eval(); decoder.eval()
    c = pil_to_tensor(content_img).to(device)
    s = pil_to_tensor(style_img).to(device)
    with torch.no_grad():
        cf, sf = encoder(c), encoder(s)
        t = adain(cf, sf)
        t = alpha * t + (1 - alpha) * cf
        out = decoder(t)
    return tensor_to_pil(out)

# ===== 360 utils =====
def equirect_to_faces(equi_img: Image.Image, face_w: int) -> Dict[str, Image.Image]:
    equi_np = np.array(equi_img)[:, :, :3]
    # return cube faces as a dict directly
    cube = py360.e2c(equi_np, face_w=face_w, mode="bilinear", cube_format="dict")
    # ensure the keys are in the standard order
    return {k: Image.fromarray(cube[k]) for k in ["F","R","B","L","U","D"]}

def project_face_to_equirect(face_key: str, face_img: Image.Image, out_h: int, out_w: int) -> np.ndarray:
    blank = np.zeros((face_img.height, face_img.width, 3), dtype=np.uint8)
    cube = {k: (np.array(face_img) if k == face_key else blank) for k in FACE_ORDER}
    equi = py360.c2e(cube, h=out_h, w=out_w, mode="bilinear", cube_format="dict")
    return equi.astype(np.float32) / 255.0

def soft_edge_mask(face_img: Image.Image, sigma_px: int = 16) -> np.ndarray:
    h, w = face_img.height, face_img.width
    y, x = np.mgrid[0:h, 0:w]
    d = np.minimum.reduce([x, y, w-1-x, h-1-y]).astype(np.float32)
    d /= d.max() + 1e-6
    m = gaussian_filter(d, sigma=sigma_px).astype(np.float32)
    m -= m.min(); m /= (m.max() + 1e-6)
    return m

def project_mask_to_equirect(face_key: str, mask: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    h, w = mask.shape
    mask_rgb = np.clip(mask, 0, 1)[:, :, None].repeat(3, axis=2)
    blank = np.zeros((h, w, 3), dtype=np.float32)
    cube = {k: (mask_rgb if k == face_key else blank) for k in FACE_ORDER}
    # convert to uint8 for py360 and specify dict format
    cube_u8 = {k: (np.clip(v*255, 0, 255).astype(np.uint8)) for k, v in cube.items()}
    equi = py360.c2e(cube_u8, h=out_h, w=out_w, mode="bilinear", cube_format="dict")
    equi = equi.astype(np.float32) / 255.0
    return equi.mean(axis=2)

def multiband_blend(numer: np.ndarray, denom: np.ndarray, levels: int = 3) -> np.ndarray:
    eps = 1e-6
    out = np.zeros_like(numer)
    sigmas = [0, 2, 6][:levels]
    for s in sigmas:
        if s == 0:
            n_s, d_s = numer, denom
        else:
            n_s = gaussian_filter(numer, sigma=[s,s,0])
            d_s = gaussian_filter(denom, sigma=s)
        out += n_s / (d_s[...,None] + eps)
    out /= len(sigmas)
    return np.clip(out, 0, 1)

# ===== Style helpers (plik lub folder) =====
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

def load_style_file_list(path: str) -> List[str]:
    files = []
    for ext in IMG_EXTS:
        files += glob.glob(os.path.join(path, f"*{ext}"))
        files += glob.glob(os.path.join(path, f"*{ext.upper()}"))
    return sorted(files)

def make_blended_style(style_paths: List[str], size: Tuple[int,int], max_count: int) -> Image.Image:
    """Uśrednia pixele z kilku obrazów stylu do jednego stylu (prosty, szybki mix)."""
    if len(style_paths) == 0:
        raise RuntimeError("Brak plików stylu w katalogu.")
    pick = style_paths if max_count <= 0 else random.sample(style_paths, k=min(max_count, len(style_paths)))
    acc = None
    for p in pick:
        img = Image.open(p).convert("RGB").resize(size, Image.BICUBIC)
        arr = np.array(img).astype(np.float32) / 255.0
        acc = arr if acc is None else (acc + arr)
    arr = (acc / len(pick))
    return Image.fromarray(np.clip(arr*255,0,255).astype(np.uint8))

def resolve_style_provider(style_arg: str, default_size: Tuple[int,int], mode: str, blend_count: int):
    """
    Zwraca krotkę (get_style_for_face, summary_str)
    - get_style_for_face(face_key, face_size) -> PIL.Image
    """
    if style_arg and os.path.isdir(style_arg):
        files = load_style_file_list(style_arg)
        if not files:
            raise RuntimeError(f"Nie znaleziono plików stylu w katalogu: {style_arg}")
        if mode == "consistent":
            chosen = random.choice(files)
            base_img = Image.open(chosen).convert("RGB").resize(default_size, Image.BICUBIC)
            def _provider(face_key, face_size):
                return base_img.resize(face_size, Image.BICUBIC)
            return _provider, f"style_dir={style_arg} (consistent: {os.path.basename(chosen)})"
        elif mode == "random_per_face":
            def _provider(face_key, face_size):
                p = random.choice(files)
                return Image.open(p).convert("RGB").resize(face_size, Image.BICUBIC)
            return _provider, f"style_dir={style_arg} (random_per_face)"
        elif mode == "blend":
            blended = make_blended_style(files, default_size, blend_count)
            def _provider(face_key, face_size):
                return blended.resize(face_size, Image.BICUBIC)
            return _provider, f"style_dir={style_arg} (blend, count={blend_count})"
        else:
            raise ValueError(f"Nieznany style_mode: {mode}")
    else:
        # pojedynczy plik lub None -> użyj tego samego dla wszystkich ścian
        if style_arg and os.path.isfile(style_arg):
            img = Image.open(style_arg).convert("RGB").resize(default_size, Image.BICUBIC)
            def _provider(face_key, face_size):
                return img.resize(face_size, Image.BICUBIC)
            return _provider, f"style_file={style_arg}"
        else:
            # fallback: syntetyczny retro
            w, h = default_size
            base = np.zeros((h,w,3), np.float32); base[...,0]=.76; base[...,1]=.65; base[...,2]=.52
            y,x = np.mgrid[0:h,0:w]; r = np.sqrt((x-w/2)**2+(y-h/2)**2); r/=r.max()+1e-6
            vig = 1-0.35*(r**2); noise = np.random.normal(0,0.02,(h,w,3)).astype(np.float32)
            synth = Image.fromarray(np.clip((base*vig[...,None]+noise)*255,0,255).astype(np.uint8))
            def _provider(face_key, face_size):
                return synth.resize(face_size, Image.BICUBIC)
            return _provider, "style_synthetic_retro"

def main():
    ap = argparse.ArgumentParser("AdaIN 360° PRO (feathering + multiband) z katalogiem stylów")
    ap.add_argument("--input", required=True, help="Wejściowy equirectangular JPG/PNG (2:1).")
    ap.add_argument("--output", required=True, help="Wyjściowy equirectangular JPG.")
    ap.add_argument("--style", default=None, help="Plik stylu LUB katalog stylów (.jpg/.png).")
    ap.add_argument("--style_mode", default="blend", choices=["consistent","random_per_face","blend"],
                    help="Jak używać katalogu stylów (domyślnie: consistent).")
    ap.add_argument("--style_blend_count", type=int, default=0, help="Ile plików mieszać w trybie blend (0=wszystkie).")
    ap.add_argument("--face_size", type=int, default=1024)
    ap.add_argument("--alpha", type=float, default=0.8)
    ap.add_argument("--vgg_weights", required=True)
    ap.add_argument("--decoder_weights", required=True)
    ap.add_argument("--device", default="auto", choices=["auto","cpu","cuda"])
    ap.add_argument("--mask_sigma", type=int, default=24)
    ap.add_argument("--pyr_levels", type=int, default=3)
    args = ap.parse_args()

    device = "cuda" if (args.device=="auto" and torch.cuda.is_available()) else (args.device if args.device!="auto" else "cpu")

    equi = Image.open(args.input).convert("RGB")
    H, W = equi.height, equi.width

    faces = equirect_to_faces(equi, args.face_size)

    # Provider stylu: plik, folder (różne tryby) albo preset syntetyczny
    style_provider, info = resolve_style_provider(args.style, (args.face_size, args.face_size),
                                                  mode=args.style_mode, blend_count=args.style_blend_count)
    print(f"[STYLE] {info}")

    # Załaduj AdaIN
    encoder, decoder = VGGEncoder(), Decoder()
    enc_state = torch.load(args.vgg_weights, map_location="cpu")
    dec_state = torch.load(args.decoder_weights, map_location="cpu")
    if isinstance(enc_state, dict) and "state_dict" in enc_state: enc_state = enc_state["state_dict"]
    if isinstance(dec_state, dict) and "state_dict" in dec_state: dec_state = dec_state["state_dict"]
    encoder.load_state_dict(enc_state, strict=False)
    decoder.load_state_dict(dec_state, strict=False)
    encoder.to(device); decoder.to(device)

    # Stylizacja każdej ściany
    stylized: Dict[str, Image.Image] = {}
    for k in FACE_ORDER:
        style_img = style_provider(k, faces[k].size)
        stylized[k] = stylize_adain(encoder, decoder, faces[k], style_img, device=device, alpha=args.alpha)

    # Składanie PRO
    numer = np.zeros((H, W, 3), dtype=np.float32)
    denom = np.zeros((H, W), dtype=np.float32)
    for k in FACE_ORDER:
        proj = project_face_to_equirect(k, stylized[k], out_h=H, out_w=W)
        m_face = soft_edge_mask(stylized[k], sigma_px=args.mask_sigma)
        m_equi = project_mask_to_equirect(k, m_face, out_h=H, out_w=W)
        numer += proj * m_equi[...,None]
        denom += m_equi

    out = multiband_blend(numer, denom, levels=args.pyr_levels)
    out_img = Image.fromarray((out*255).astype(np.uint8))
    out_img.save(args.output, format="JPEG", quality=92, optimize=True, progressive=True)
    print(f"[OK] Zapisano: {args.output}")

if __name__ == "__main__":
    main()
