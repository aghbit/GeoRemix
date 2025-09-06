from transformers import AutoImageProcessor, Mask2FormerForUniversalSegmentation

from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import os
import torch
import numpy as np

processor = AutoImageProcessor.from_pretrained("facebook/mask2former-swin-large-ade-semantic")
model = Mask2FormerForUniversalSegmentation.from_pretrained("facebook/mask2former-swin-large-ade-semantic")


def load_image(image_path: str) -> Image.Image:
    return Image.open(image_path).convert("RGB")

def save_jpeg(image: Image.Image, path: str, quality: int = 92):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, format="JPEG", quality=quality)

def run_inference(image: Image.Image):
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    result = processor.post_process_panoptic_segmentation(outputs, target_sizes=[(image.height, image.width)])[0]

    return result



# Visualize panoptic segmentation ==========================================================

def _color_for_label(label_id):
    rng = np.random.RandomState(label_id * 9973)
    c = rng.randint(64, 256, size=3, dtype=np.uint8)
    return tuple(c.tolist())

def visualize_panoptic(
    image_pil: Image.Image,
    panoptic_seg,                # torch.Tensor[H,W] or PIL.Image "P"/"I" style with ids
    segments_info: list,         # result["segments_info"]
    id2label: dict,              # model.config.id2label
    alpha: float = 0.6,
    save_path: str | None = None
):
    # 1) Convert panoptic segmentation to numpy (H, W) of segment ids
    if isinstance(panoptic_seg, Image.Image):
        seg_ids = np.array(panoptic_seg, dtype=np.int32)
    elif isinstance(panoptic_seg, torch.Tensor):
        seg_ids = panoptic_seg.detach().cpu().numpy().astype(np.int32)
    else:
        seg_ids = np.asarray(panoptic_seg).astype(np.int32)

    H, W = seg_ids.shape
    img = np.array(image_pil.convert("RGB"))

    # 2) Build a color image keyed by segment id
    color_map = np.zeros((H, W, 3), dtype=np.uint8)
    legend_entries = []  # (label_name, color, score, area_px)

    # Map segment id -> (label_id, score) from segments_info
    meta_by_id = {s["id"]: s for s in segments_info}

    for seg_id, meta in meta_by_id.items():
        mask = (seg_ids == seg_id)
        if not np.any(mask):
            continue
        label_id = meta["label_id"]
        label_name = id2label.get(label_id, f"id_{label_id}")
        score = float(meta.get("score", 1.0))
        color = _color_for_label(label_id)
        color_map[mask] = color
        legend_entries.append((label_name, color, score, int(mask.sum())))

    # 3) Alpha-blend overlay
    overlay = (alpha * color_map + (1 - alpha) * img).astype(np.uint8)

    # 4) Compose side-by-side (original | overlay)
    vis = np.concatenate([img, overlay], axis=1)

    # 5) Draw a legend on the right margin
    # Make a new canvas with room for legend
    legend_w = 260
    pad = 12
    canvas = Image.new("RGB", (vis.shape[1] + legend_w, vis.shape[0]), (255, 255, 255))
    canvas.paste(Image.fromarray(vis), (0, 0))

    draw = ImageDraw.Draw(canvas)
    y = pad
    x = vis.shape[1] + pad
    draw.text((x, y), "Legend (class • score • px)", fill=(0,0,0))
    y += 24

    # Sort legend by area descending
    legend_entries.sort(key=lambda t: t[3], reverse=True)

    for name, color, score, area in legend_entries[:30]:  # cap to keep it readable
        # color swatch
        draw.rectangle([x, y, x+18, y+18], fill=tuple(color), outline=(0,0,0))
        # text
        draw.text((x+24, y), f"{name} • {score:.2f} • {area}", fill=(0,0,0))
        y += 22
        if y > canvas.size[1] - 24:
            break

    # 6) Save/show
    if save_path is not None:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        canvas.save(save_path)
        print(f"Saved visualization to: {save_path}")

    plt.figure(figsize=(16, 9))
    plt.axis("off")
    plt.imshow(canvas)
    plt.show()

if __name__ == "__main__":
    image = Image.open("pictures/before/164095525622425.jpg").convert("RGB")
    inputs = image_processor(images=image, return_tensors="pt")

    outputs = model(**inputs)
    class_queries_logits = outputs.class_queries_logits
    masks_queries_logits = outputs.masks_queries_logits

    result = image_processor.post_process_panoptic_segmentation(outputs, target_sizes=[(image.height, image.width)])[0]

    predicted_panoptic_map = result["segmentation"]
    print(list(predicted_panoptic_map.shape))
    
    print(result["segmentation"].shape)


    # --- use it after your inference ---
    pred = image_processor.post_process_panoptic_segmentation(
        outputs,
        target_sizes=[(image.height, image.width)],
        label_ids_to_fuse=set()  # or a set of label_ids to fuse
    )[0]

    visualize_panoptic(
        image_pil=image,
        panoptic_seg=result["segmentation"],
        segments_info=result["segments_info"],
        id2label=model.config.id2label,
        alpha=0.6,
        save_path="outputs/panoptic_overlay.png"
    )
# ==========================================================================================