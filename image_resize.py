import torch

class ImageResize:
    def __init__(self):
        pass


    ACTION_TYPE_RESIZE = "resize only"
    ACTION_TYPE_CROP = "crop to ratio"
    ACTION_TYPE_PAD = "pad to ratio"
    RESIZE_MODE_DOWNSCALE = "reduce size only"
    RESIZE_MODE_UPSCALE = "increase size only"
    RESIZE_MODE_ANY = "any"
    RETURN_TYPES = ("IMAGE", "MASK",)
    FUNCTION = "resize"
    CATEGORY = "image"


    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "pixels": ("IMAGE",),
                "action": ([s.ACTION_TYPE_RESIZE, s.ACTION_TYPE_CROP, s.ACTION_TYPE_PAD],),
                "smaller_side": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "larger_side": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 8}),
                "scale_factor": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.1}),
                "resize_mode": ([s.RESIZE_MODE_DOWNSCALE, s.RESIZE_MODE_UPSCALE, s.RESIZE_MODE_ANY],),
                "side_ratio": ("STRING", {"default": "4:3"}),
                "crop_pad_position": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "pad_feathering": ("INT", {"default": 20, "min": 0, "max": 8192, "step": 1}),
            },
            "optional": {
                "mask_optional": ("MASK",),
            },
        }


    @classmethod
    def VALIDATE_INPUTS(s, action, smaller_side, larger_side, scale_factor, resize_mode, side_ratio, **_):
        if side_ratio is not None:
            if action != s.ACTION_TYPE_RESIZE and s.parse_side_ratio(side_ratio) is None:
                return f"Invalid side ratio: {side_ratio}"

        if smaller_side is not None and larger_side is not None and scale_factor is not None:
            if int(smaller_side > 0) + int(larger_side > 0) + int(scale_factor > 0) > 1:
                return f"At most one scaling rule (smaller_side, larger_side, scale_factor) should be enabled by setting a non-zero value"

        if scale_factor is not None:
            if resize_mode == s.RESIZE_MODE_DOWNSCALE and scale_factor > 1.0:
                return f"For resize_mode {s.RESIZE_MODE_DOWNSCALE}, scale_factor should be less than one but got {scale_factor}"
            if resize_mode == s.RESIZE_MODE_UPSCALE and scale_factor > 0.0 and scale_factor < 1.0:
                return f"For resize_mode {s.RESIZE_MODE_UPSCALE}, scale_factor should be larger than one but got {scale_factor}"

        return True


    @classmethod
    def parse_side_ratio(s, side_ratio):
        try:
            x, y = map(int, side_ratio.split(":", 1))
            if x < 1 or y < 1:
                raise Exception("Ratio factors have to be positive numbers")
            return float(x) / float(y)
        except:
            return None


    def resize(self, pixels, action, smaller_side, larger_side, scale_factor, resize_mode, side_ratio, crop_pad_position, pad_feathering, mask_optional=None):
        validity = self.VALIDATE_INPUTS(action, smaller_side, larger_side, scale_factor, resize_mode, side_ratio)
        if validity is not True:
            raise Exception(validity)

        height, width = pixels.shape[1:3]
        if mask_optional is None:
            mask = torch.zeros(1, height, width, dtype=torch.float32)
        else:
            mask = mask_optional
            if mask.shape[1] != height or mask.shape[2] != width:
                mask = torch.nn.functional.interpolate(mask.unsqueeze(0), size=(height, width), mode="bicubic").squeeze(0).clamp(0.0, 1.0)

        crop_x, crop_y, pad_x, pad_y = (0.0, 0.0, 0.0, 0.0)
        if action == self.ACTION_TYPE_CROP:
            target_ratio = self.parse_side_ratio(side_ratio)
            if height * target_ratio < width:
                crop_x = width - height * target_ratio
            else:
                crop_y = height - width / target_ratio
        elif action == self.ACTION_TYPE_PAD:
            target_ratio = self.parse_side_ratio(side_ratio)
            if height * target_ratio > width:
                pad_x = height * target_ratio - width
            else:
                pad_y = width / target_ratio - height

        if smaller_side > 0:
            if width + pad_x - crop_x > height + pad_y - crop_y:
                scale_factor = float(smaller_side) / (height + pad_y - crop_y)
            else:
                scale_factor = float(smaller_side) / (width + pad_x - crop_x)
        if larger_side > 0:
            if width + pad_x - crop_x > height + pad_y - crop_y:
                scale_factor = float(larger_side) / (width + pad_x - crop_x)
            else:
                scale_factor = float(larger_side) / (height + pad_y - crop_y)

        if (resize_mode == self.RESIZE_MODE_DOWNSCALE and scale_factor >= 1.0) or (resize_mode == self.RESIZE_MODE_UPSCALE and scale_factor <= 1.0):
            scale_factor = 0.0

        if scale_factor > 0.0:
            pixels = torch.nn.functional.interpolate(pixels.movedim(-1, 1), scale_factor=scale_factor, mode="bicubic", antialias=True).movedim(1, -1).clamp(0.0, 1.0)
            mask = torch.nn.functional.interpolate(mask.unsqueeze(0), scale_factor=scale_factor, mode="bicubic", antialias=True).squeeze(0).clamp(0.0, 1.0)
            height, width = pixels.shape[1:3]

            crop_x *= scale_factor
            crop_y *= scale_factor
            pad_x *= scale_factor
            pad_y *= scale_factor

        if crop_x > 0.0 or crop_y > 0.0:
            remove_x = (round(crop_x * crop_pad_position), round(crop_x * (1 - crop_pad_position))) if crop_x > 0.0 else (0, 0)
            remove_y = (round(crop_y * crop_pad_position), round(crop_y * (1 - crop_pad_position))) if crop_y > 0.0 else (0, 0)
            pixels = pixels[:, remove_y[0]:height - remove_y[1], remove_x[0]:width - remove_x[1], :]
            mask = mask[:, remove_y[0]:height - remove_y[1], remove_x[0]:width - remove_x[1]]
        elif pad_x > 0.0 or pad_y > 0.0:
            add_x = (round(pad_x * crop_pad_position), round(pad_x * (1 - crop_pad_position))) if pad_x > 0.0 else (0, 0)
            add_y = (round(pad_y * crop_pad_position), round(pad_y * (1 - crop_pad_position))) if pad_y > 0.0 else (0, 0)

            new_pixels = torch.zeros(pixels.shape[0], height + add_y[0] + add_y[1], width + add_x[0] + add_x[1], pixels.shape[3], dtype=torch.float32)
            new_pixels[:, add_y[0]:height + add_y[0], add_x[0]:width + add_x[0], :] = pixels
            pixels = new_pixels

            new_mask = torch.ones(mask.shape[0], height + add_y[0] + add_y[1], width + add_x[0] + add_x[1], dtype=torch.float32)
            new_mask[:, add_y[0]:height + add_y[0], add_x[0]:width + add_x[0]] = mask
            mask = new_mask

            if pad_feathering > 0:
                for i in range(mask.shape[0]):
                    for j in range(pad_feathering):
                        feather_strength = (1 - j / pad_feathering) * (1 - j / pad_feathering)
                        if add_x[0] > 0 and j < width:
                            for k in range(height):
                                mask[i, k, add_x[0] + j] = max(mask[i, k, add_x[0] + j], feather_strength)
                        if add_x[1] > 0 and j < width:
                            for k in range(height):
                                mask[i, k, width + add_x[0] - j - 1] = max(mask[i, k, width + add_x[0] - j - 1], feather_strength)
                        if add_y[0] > 0 and j < height:
                            for k in range(width):
                                mask[i, add_y[0] + j, k] = max(mask[i, add_y[0] + j, k], feather_strength)
                        if add_y[1] > 0 and j < height:
                            for k in range(width):
                                mask[i, height + add_y[0] - j - 1, k] = max(mask[i, height + add_y[0] - j - 1, k], feather_strength)

        return (pixels, mask)


NODE_CLASS_MAPPINGS = {
    "ImageResize": ImageResize
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageResize": "Image Resize"
}
