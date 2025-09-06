# two_gpu_controlnet_seg_inpaint.py
from segmentation_vis import *
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from PIL import Image
import torch, os
import copy
from diffusers import (
    StableDiffusionXLControlNetInpaintPipeline,
    ControlNetModel,
    DDIMScheduler,
)

# ---------- ADE20K palette ----------
import scipy.io as sio
colors = sio.loadmat("color150.mat")["colors"]
ADE20K_PALETTE = [tuple(map(int, c)) for c in colors.astype("uint8").tolist()]

# ---------- Utils ----------
def _ensure_rgb(img: Image.Image | np.ndarray) -> Image.Image:
    return img.convert("RGB") if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img).astype(np.uint8)).convert("RGB")

def _mask_from_seg_id(panoptic_np: np.ndarray, seg_id: int) -> Image.Image:
    m = (panoptic_np == seg_id).astype(np.uint8) * 255
    return Image.fromarray(m, mode="L")

def colorize_label_map_ade(label_map: np.ndarray) -> Image.Image:
    arr = np.asarray(label_map).astype(np.int32)
    h, w = arr.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    uniq = np.unique(arr)
    for lid in uniq:
        color = ADE20K_PALETTE[int(lid)] if int(lid) < len(ADE20K_PALETTE) else (127, 127, 127)
        rgb[arr == lid] = color
    return Image.fromarray(rgb, mode="RGB")

@dataclass
class EditConfig:
    base_model_id: str = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1"  # SDXL inpaint UNet
    controlnet_model_id: str = "SargeZT/sdxl-controlnet-seg"
    num_inference_steps: int = 35
    guidance_scale: float = 7.5
    strength: float = 0.6
    controlnet_conditioning_scale: float = 1.1
    control_guidance_start: float = 0.0
    control_guidance_end: float = 1.0
    fp16: bool = True
    use_xformers: bool = True
    seed: Optional[int] = 1234

class TwoGPUControlSegInpaint:
    """
    Runs SDXL+ControlNet(inpaint) on two GPUs in parallel.
    Strategy:
      - Partition segments into batches of *non-overlapping* masks.
      - For each batch: dispatch jobs across GPU0 and GPU1 concurrently.
      - Each job returns (seg_id, out_np, mask_np). We composite serially after.
    """

    def __init__(self, cfg: EditConfig):
        assert torch.cuda.device_count() >= 2, "Need at least 2 CUDA GPUs."
        self.cfg = cfg

        # Dtypes
        self.dtype = torch.float16 if (cfg.fp16 and torch.cuda.is_available()) else torch.float32

        # Load ControlNet weights once per GPU
        self.control_0 = ControlNetModel.from_pretrained(cfg.controlnet_model_id, torch_dtype=self.dtype)
        self.control_1 = ControlNetModel.from_pretrained(cfg.controlnet_model_id, torch_dtype=self.dtype)

        # Pipelines on two devices
        self.pipe0 = StableDiffusionXLControlNetInpaintPipeline.from_pretrained(
            cfg.base_model_id,
            controlnet=self.control_0,
            torch_dtype=self.dtype,
            use_safetensors=True,
            variant="fp16" if self.dtype == torch.float16 else None,
        )
        self.pipe1 = StableDiffusionXLControlNetInpaintPipeline.from_pretrained(
            cfg.base_model_id,
            controlnet=self.control_1,
            torch_dtype=self.dtype,
            use_safetensors=True,
            variant="fp16" if self.dtype == torch.float16 else None,
        )

        # Schedulers + perf tweaks
        for i, pipe in enumerate([self.pipe0, self.pipe1]):
            pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
            dev = torch.device(f"cuda:{i}")
            if cfg.use_xformers:
                try:
                    pipe.enable_xformers_memory_efficient_attention()
                except Exception:
                    pass
            pipe.enable_attention_slicing()
            pipe.to(dev)

    def _generator(self, device_idx: int, seg_idx_seed_offset: int = 0) -> Optional[torch.Generator]:
        if self.cfg.seed is None:
            return None
        g = torch.Generator(device=f"cuda:{device_idx}")
        g.manual_seed(int(self.cfg.seed) + int(seg_idx_seed_offset))
        return g

    @staticmethod
    def _bbox_from_mask(mask_np_u8: np.ndarray) -> Tuple[int, int, int, int]:
        ys, xs = np.where(mask_np_u8 > 0)
        if len(xs) == 0:
            return (0, 0, 0, 0)
        return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)  # (x1,y1,x2,y2)

    @staticmethod
    def _boxes_overlap(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> bool:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        if ax1 >= bx2 or bx1 >= ax2: return False
        if ay1 >= by2 or by1 >= ay2: return False
        return True

    def _greedy_nonoverlap_batches(self, masks_np_u8: Dict[int, np.ndarray]) -> List[List[int]]:
        """
        Simple greedy coloring: fill current batch with segments whose bboxes
        don't overlap any already in the batch. Repeat until all scheduled.
        """
        seg_ids = list(masks_np_u8.keys())
        bboxes = {sid: self._bbox_from_mask(masks_np_u8[sid]) for sid in seg_ids}
        remaining = set(seg_ids)
        batches: List[List[int]] = []

        while remaining:
            batch = []
            used_boxes = []
            for sid in list(remaining):
                bb = bboxes[sid]
                if (bb[2] - bb[0]) == 0 or (bb[3] - bb[1]) == 0:
                    remaining.remove(sid)
                    continue
                conflict = any(self._boxes_overlap(bb, ubb) for ubb in used_boxes)
                if not conflict:
                    batch.append(sid)
                    used_boxes.append(bb)
                    remaining.remove(sid)
            if batch:
                batches.append(batch)
        return batches

    def _run_one_segment(
        self,
        device_idx: int,
        pipe: StableDiffusionXLControlNetInpaintPipeline,
        canvas_img: Image.Image,
        control_img: Image.Image,
        mask_img: Image.Image,
        prompt: str,
        negative_prompt: Optional[str],
        W: int, H: int,
        seg_idx_seed_offset: int,
    ) -> np.ndarray:
        g = self._generator(device_idx, seg_idx_seed_offset)
        with torch.inference_mode():
            out_img = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                image=canvas_img,
                control_image=control_img,
                mask_image=mask_img,
                num_inference_steps=self.cfg.num_inference_steps,
                guidance_scale=self.cfg.guidance_scale,
                strength=self.cfg.strength,
                controlnet_conditioning_scale=self.cfg.controlnet_conditioning_scale,
                control_guidance_start=self.cfg.control_guidance_start,
                control_guidance_end=self.cfg.control_guidance_end,
                generator=g,
                width=W, height=H,
            ).images[0]
        return np.array(out_img, dtype=np.uint8)

    def edit(
        self,
        image: Image.Image,
        seg_rgb_map: Image.Image,
        panoptic_np: np.ndarray,
        segments_info: List[Dict[str, Any]],
        prompt: str,
        negative_prompt: Optional[str] = None,
    ) -> Image.Image:

        base_img = _ensure_rgb(image)
        control_img = _ensure_rgb(seg_rgb_map)

        if control_img.size != base_img.size:
            control_img = control_img.resize(base_img.size, resample=Image.NEAREST)

        W, H = base_img.size
        canvas_np = np.array(base_img, dtype=np.uint8)

        # Precompute masks & filter empty
        masks_np: Dict[int, np.ndarray] = {}
        segs = segments_info
        if isinstance(segments_info, dict) and "segments_info" in segments_info:
            segs = segments_info["segments_info"]

        # Sort largest area first (helps quality and reduces edge nicks)
        if segs and "area" in segs[0]:
            segs = sorted(segs, key=lambda s: s.get("area", 0), reverse=True)

        for s in segs:
            sid = int(s["id"])
            m = (panoptic_np == sid).astype(np.uint8) * 255
            if m.max() > 0:
                masks_np[sid] = m

        if not masks_np:
            raise RuntimeError("No non-empty masks; check your panoptic map vs segment ids.")

        # Partition into batches of non-overlapping segments
        batches = self._greedy_nonoverlap_batches(masks_np)

        # Process batches; within each batch, run up to 2 jobs in parallel on 2 GPUs
        for batch_idx, batch in enumerate(batches):
            # Prepare jobs
            jobs = []
            with ThreadPoolExecutor(max_workers=2) as ex:
                for j, sid in enumerate(batch):
                    mask_np = masks_np[sid]
                    mask_img = Image.fromarray(mask_np, mode="L")

                    # Every worker reads the *same* canvas snapshot for this batch
                    canvas_img = Image.fromarray(canvas_np, mode="RGB")

                    if j % 2 == 0:
                        device_idx, pipe = 0, self.pipe0
                    else:
                        device_idx, pipe = 1, self.pipe1

                    fut = ex.submit(
                        self._run_one_segment,
                        device_idx, pipe, canvas_img, control_img, mask_img,
                        prompt, negative_prompt, W, H,
                        seg_idx_seed_offset=(batch_idx * 10_000 + j),
                    )
                    jobs.append((sid, mask_np, fut))

                # Collect and composite
                for sid, mask_np, fut in jobs:
                    out_np = fut.result()
                    alpha = (mask_np.astype(np.float32) / 255.0)[..., None]
                    canvas_np = (out_np * alpha + canvas_np * (1.0 - alpha)).astype(np.uint8)

        return Image.fromarray(canvas_np, mode="RGB")


def modify_image(img, cfg: EditConfig, result, save_path) -> Dict[str, Any]:

    panoptic = np.array(result["segmentation"], dtype=np.int32)  # segment ids
    # Build semantic class map from segments_info
    class_map = np.zeros_like(panoptic, dtype=np.int32)
    for si in result["segments_info"]:
        sid = int(si["id"])
        cid = int(si.get("label_id", si.get("category_id", 0)))  # ADE usually label_id
        class_map[panoptic == sid] = cid

    seg_rgb_map = colorize_label_map_ade(class_map)

    # Prompts
    cyberpunk_prompt = "cyberpunk night city, pitch-black sky; overwhelming dense neon + holograms; rain-slick reflections, " \
    "mist, bloom, volumetric beams, bokeh; NON-DESTRUCTIVE — preserve building structure and every window (count/placement/shape); " \
    "photoreal, high-contrast."
    
    neg = "structural edits, window changes, extra floors, daylight/blue sky, text/logos/watermarks, " \
    "blur/low-res/artifacts, oversaturation, cartoon/3D-render look, duplicates, floating objects, harsh vignette."

    editor = TwoGPUControlSegInpaint(cfg)

    out = editor.edit(
        image=img,
        seg_rgb_map=seg_rgb_map,
        panoptic_np=panoptic,
        segments_info=result,
        prompt=cyberpunk_prompt,
        negative_prompt=neg,
    )

    out.save(save_path)


if __name__ == "__main__":
    img_path = "pictures/before/164095525622425.jpg"
    img = load_image(img_path)
    result = run_inference(img)

    # strengths = [0.8, 0.9, 1.0, 1.2, ]
    strengths = [0.7, 0.8, 0.9]
    guidance_scales = [7.5, 8.5, 9.5]
    num_inference_steps = [55]
    controlnet_conditioning_scales = [1.2]

    for strength in strengths:
        for guidance_scale in guidance_scales:
            for n_steps in num_inference_steps:
                for controlnet_conditioning_scale in controlnet_conditioning_scales:
                    cfg = EditConfig(
                        strength=strength,
                        guidance_scale=guidance_scale,
                        num_inference_steps=n_steps,
                        controlnet_conditioning_scale=controlnet_conditioning_scale,
                        seed=1234,
                    )
                    save_path = f"pictures/after/164095525622425_cyberpunk_s{int(strength*100)}_g{int(guidance_scale*10)}_n{n_steps}_c{int(controlnet_conditioning_scale*10)}.png"

                    res_temp = copy.deepcopy(result)
                    img_temp = load_image(img_path)
                    modify_image(img_temp, cfg = EditConfig(
                        strength=strength,
                        guidance_scale=guidance_scale,
                        num_inference_steps=n_steps,
                        controlnet_conditioning_scale=controlnet_conditioning_scale,
                        seed=1234,
                    ), result=res_temp, save_path=save_path)
