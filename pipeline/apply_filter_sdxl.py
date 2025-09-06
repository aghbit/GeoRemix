from segmentation_vis import *
from diffusers import (
    StableDiffusionXLControlNetInpaintPipeline,
    ControlNetModel,
    DDIMScheduler,
)
import torch, numpy as np
from PIL import Image
from typing import List, Dict, Any, Tuple, Optional
import scipy.io as sio
colors = sio.loadmat("color150.mat")["colors"]
ADE20K_PALETTE = [tuple(map(int, c)) for c in colors.astype("uint8").tolist()]

def _ensure_rgb(img):
    return img.convert("RGB") if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img).astype(np.uint8)).convert("RGB")

def _mask_from_seg_id(panoptic_seg: Image.Image | np.ndarray, seg_id: int) -> Image.Image:
    """Return a white=edit / black=keep 8-bit mask for a given segment id."""
    if isinstance(panoptic_seg, Image.Image):
        seg_np = np.array(panoptic_seg)
    else:
        seg_np = np.asarray(panoptic_seg)
    m = (seg_np == seg_id).astype(np.uint8) * 255
    return Image.fromarray(m, mode="L")

def apply_sdxl_controlnet_seg_per_region(
    image: Image.Image,
    seg_rgb_map: Image.Image,
    segments_info: List[Dict[str, Any]],
    prompt: str,
    negative_prompt: Optional[str] = None,
    # Models (change if you have preferred ones)
    base_model_id: str = "stabilityai/stable-diffusion-xl-1.0-inpainting-1.0",
    controlnet_model_id: str = "SargeZT/sdxl-controlnet-seg",
    # Inference params (same for every region)
    num_inference_steps: int = 30,
    guidance_scale: float = 5.5,
    strength: float = 0.28,         # lower = preserve more of the original
    controlnet_conditioning_scale: float = 0.85,
    control_guidance_start: float = 0.0,
    control_guidance_end: float = 1.0,
    seed: Optional[int] = 1234,
    fp16: bool = True,
    use_xformers: bool = True,
) -> Image.Image:
    """
    Apply the SAME SDXL+ControlNet (segmentation) stylization to each segment independently.
    - image: original pano (PIL)
    - seg_rgb_map: an RGB visualization of your segmentation (same size as image).
      For best results, use an ADE20K-like palette if the ControlNet expects it.
    - segments_info: list from your panoptic postprocess (each has an 'id' field at least).
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch_dtype = torch.float16 if (fp16 and device.type == "cuda") else torch.float32

    base_img = _ensure_rgb(image)
    control_img = _ensure_rgb(seg_rgb_map)

    # Load ControlNet (segmentation) + SDXL inpaint pipeline
    controlnet = ControlNetModel.from_pretrained(controlnet_model_id, torch_dtype=torch_dtype)
    pipe = StableDiffusionXLControlNetInpaintPipeline.from_pretrained(
        base_model_id,
        controlnet=controlnet,
        torch_dtype=torch_dtype,
        use_safetensors=True,
        variant="fp16" if torch_dtype == torch.float16 else None,
    )

    # Optional memory/perf tweaks
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    if device.type == "cuda":
        if use_xformers:
            try:
                pipe.enable_xformers_memory_efficient_attention()
            except Exception:
                pass
        pipe.enable_attention_slicing()
        pipe.to(device)
    else:
        pipe.enable_attention_slicing()

    # Keep a working canvas; we’ll paste each edited region back in
    canvas = base_img.copy()

    # Use fixed seed for full determinism across regions (or vary per-region if you prefer)
    g = None
    if seed is not None:
        g = torch.Generator(device=device).manual_seed(seed)

    # Sort largest-to-smallest to reduce edge artifacts when regions touch
    # (requires area; if not present, we’ll just iterate)
    segs = segments_info["segments_info"] if "segments_info" in segments_info else segments_info
    if len(segs) and "area" in segs[0]:
        segs = sorted(segs, key=lambda s: s.get("area", 0), reverse=True)

    W, H = base_img.size

    for s in segs:
        seg_id = s["id"]

        # 1) Build mask for this region (white = edit)
        mask = _mask_from_seg_id(
            panoptic_seg=s.get("panoptic_segmentation", None) or s.get("seg_map", None) or s.get("segmentation", None) or s.get("panoptic"),
            seg_id=seg_id
        ) if any(k in s for k in ("panoptic_segmentation","seg_map","segmentation","panoptic")) else _mask_from_seg_id(image.info.get("panoptic_np", np.zeros((H,W), np.int32)), seg_id)

        # If you don’t have per-entry maps in segments_info, pass your global panoptic id map via image.info["panoptic_np"] before calling this function.

        # 2) Run SDXL ControlNet Inpaint with SAME settings
        out = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=canvas,                 # current full canvas
            control_image=control_img,    # full segmentation RGB map
            mask_image=mask,              # edit only this region
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            strength=strength,
            controlnet_conditioning_scale=controlnet_conditioning_scale,
            control_guidance_start=control_guidance_start,
            control_guidance_end=control_guidance_end,
            generator=g,
            width=W, height=H,
        ).images[0]

        # 3) Composite result back (keep only this region from 'out')
        #    Use mask as alpha to blend just the edited area.
        out_np  = np.array(out, dtype=np.uint8)
        can_np  = np.array(canvas, dtype=np.uint8)
        mask_np = np.array(mask, dtype=np.uint8)[..., None] / 255.0
        blended = (out_np * mask_np + can_np * (1.0 - mask_np)).astype(np.uint8)
        canvas = Image.fromarray(blended, mode="RGB")

    return canvas

def colorize_label_map_ade(label_map: torch.Tensor | np.ndarray) -> Image.Image:
    arr = label_map.cpu().numpy().astype(np.int32) if isinstance(label_map, torch.Tensor) else np.asarray(label_map).astype(np.int32)
    h, w = arr.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    uniq = np.unique(arr)
    for lid in uniq:
        color = ADE20K_PALETTE[int(lid)]
        if color is None:
            # fallback deterministic color if id not in the small dict above
            rng = np.random.RandomState(int(lid) * 9973)
            color = tuple(rng.randint(64, 256, size=3).tolist())
        rgb[arr == lid] = color
    return Image.fromarray(rgb, mode="RGB")



cyberpunk_prompt = (
    "cyberpunk neon palette, magenta & cyan glow, wet asphalt reflections, cinematic, high contrast, soft bloom, photo-realistic"
)
neg = "low quality, blurry, artifacts, extra limbs, text, logo"

img_path = "pictures/before/164095525622425.jpg"


if __name__ == "__main__":
    img = load_image(img_path)
    seg = run_inference(img) 
    panoptic = np.array(seg["segmentation"], dtype=np.int32)   # segment ids
    class_map = np.zeros_like(panoptic, dtype=np.int32)

    # Map each segment id to its semantic class id
    for si in seg["segments_info"]:
        sid = int(si["id"])
        cid = int(si.get("label_id", si.get("category_id", 0)))  # Mask2Former uses label_id on ADE
        class_map[panoptic == sid] = cid

    # Colorize by semantic class (ADE20K palette), not by segment id!
    seg_rgb_map = colorize_label_map_ade(class_map)
    img.info["panoptic_np"] = panoptic

    stylized = apply_sdxl_controlnet_seg_per_region(
        image=img,                       
        seg_rgb_map=seg_rgb_map, 
        segments_info=seg,
        prompt=cyberpunk_prompt,
        negative_prompt=neg,
        strength=0.6,                     
        guidance_scale=7.5,
        controlnet_conditioning_scale=1.1,
        num_inference_steps=28,
        seed=1234,
    )

    stylized.save("pictures/after/164095525622425_cyberpunk.png")