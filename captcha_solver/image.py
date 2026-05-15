import logging
import re
from copy import deepcopy
from functools import lru_cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageFilter

try:
    import cv2
except Exception:  # pragma: no cover - depends on optional runtime package
    cv2 = None

"""Reusable image-based captcha solvers.

This module intentionally avoids 95598- or Tencent-specific DOM logic.
It only deals with image capture/cropping and point-click image matching
so it can be reused by other integrations.
"""


def capture_element_image(driver, element, scroll_to_center: bool = True) -> bytes:
    if scroll_to_center:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            element,
        )

    screenshot = Image.open(BytesIO(driver.get_screenshot_as_png())).convert("RGB")
    dpr = float(driver.execute_script("return window.devicePixelRatio || 1;") or 1)
    scroll_x = float(driver.execute_script("return window.pageXOffset || 0;") or 0)
    scroll_y = float(driver.execute_script("return window.pageYOffset || 0;") or 0)
    rect = element.rect or {}
    left = max(int(round(((rect.get("x") or 0) - scroll_x) * dpr)), 0)
    top = max(int(round(((rect.get("y") or 0) - scroll_y) * dpr)), 0)
    width = max(int(round((rect.get("width") or 0) * dpr)), 1)
    height = max(int(round((rect.get("height") or 0) * dpr)), 1)
    right = min(left + width, screenshot.width)
    bottom = min(top + height, screenshot.height)
    if right <= left or bottom <= top:
        raise ValueError(f"Invalid element crop rect: {rect}")

    cropped = screenshot.crop((left, top, right, bottom))
    buffer = BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()


class PointClickImageSolver:
    """Solve point-click captchas from answer and candidate images."""

    ROTATION_ANGLES = (-180, -135, -90, -60, -45, -35, -25, -15, -8, 0, 8, 15, 25, 35, 45, 60, 90, 135, 180)
    COMPLEX_ICON_SIZE_THRESHOLD = 22

    def __init__(self):
        self.last_diagnostics = {}

    def get_last_diagnostics(self) -> dict:
        return deepcopy(self.last_diagnostics)

    @staticmethod
    def _box_to_dict(box) -> dict:
        left, top, right, bottom, area = box
        return {
            "left": int(left),
            "top": int(top),
            "right": int(right),
            "bottom": int(bottom),
            "width": int(right - left),
            "height": int(bottom - top),
            "area": int(area),
            "center": [round((left + right) / 2, 2), round((top + bottom) / 2, 2)],
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_ddddocr():
        try:
            import ddddocr
        except Exception as exc:
            logging.info("ddddocr is not available: %s", exc)
            return None, None
        try:
            return (
                ddddocr.DdddOcr(det=True, show_ad=False),
                ddddocr.DdddOcr(show_ad=False),
            )
        except Exception as exc:
            logging.warning("Failed to initialize ddddocr: %s", exc)
            return None, None

    @staticmethod
    def dark_mask(image: Image.Image, threshold: int) -> np.ndarray:
        rgb = np.array(image.convert("RGB"))
        gray = np.array(image.convert("L"))
        channel_max = rgb.max(axis=2)
        channel_min = rgb.min(axis=2)
        chroma = channel_max - channel_min
        return (gray < threshold) & (channel_max < min(160, threshold + 45)) & (chroma < 58)

    @staticmethod
    def dilate_mask(mask: np.ndarray, radius: int = 1, iterations: int = 1) -> np.ndarray:
        if mask.size == 0 or radius <= 0 or iterations <= 0:
            return mask
        result = mask.astype(bool)
        for _ in range(iterations):
            padded = np.pad(result, radius, mode="constant", constant_values=False)
            grown = np.zeros_like(result, dtype=bool)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    grown |= padded[
                        radius + dy : radius + dy + result.shape[0],
                        radius + dx : radius + dx + result.shape[1],
                    ]
            result = grown
        return result

    @staticmethod
    def erode_mask(mask: np.ndarray, radius: int = 1, iterations: int = 1) -> np.ndarray:
        if mask.size == 0 or radius <= 0 or iterations <= 0:
            return mask
        result = mask.astype(bool)
        for _ in range(iterations):
            padded = np.pad(result, radius, mode="constant", constant_values=False)
            shrunk = np.ones_like(result, dtype=bool)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    shrunk &= padded[
                        radius + dy : radius + dy + result.shape[0],
                        radius + dx : radius + dx + result.shape[1],
                    ]
            result = shrunk
        return result

    @classmethod
    def close_mask(cls, mask: np.ndarray, radius: int = 1, iterations: int = 1) -> np.ndarray:
        return cls.erode_mask(cls.dilate_mask(mask, radius=radius, iterations=iterations), radius=radius, iterations=iterations)

    @staticmethod
    def connected_boxes(mask: np.ndarray, min_area: int = 100, connectivity: int = 8):
        height, width = mask.shape
        seen = np.zeros_like(mask, dtype=bool)
        boxes = []
        if connectivity == 8:
            neighbors = (
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
                (1, 1),
                (1, -1),
                (-1, 1),
                (-1, -1),
            )
        else:
            neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
        for y in range(height):
            for x in range(width):
                if seen[y, x] or not mask[y, x]:
                    continue
                stack = [(x, y)]
                seen[y, x] = True
                xs = []
                ys = []
                while stack:
                    cx, cy = stack.pop()
                    xs.append(cx)
                    ys.append(cy)
                    for dx, dy in neighbors:
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((nx, ny))
                area = len(xs)
                if area >= min_area:
                    boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, area))
        return boxes

    def segment_answer_icons(self, answer_image: Image.Image):
        mask = self.close_mask(self.dark_mask(answer_image, 135), radius=1)
        xs = np.where(mask.any(axis=0))[0]
        if len(xs) == 0:
            return []

        segments = []
        start = int(xs[0])
        prev = int(xs[0])
        for x in xs[1:]:
            x = int(x)
            if x - prev > 5:
                segments.append((start, prev + 1))
                start = x
            prev = x
        segments.append((start, prev + 1))

        boxes = []
        for left, right in segments:
            submask = mask[:, left:right]
            ys = np.where(submask.any(axis=1))[0]
            area = int(submask.sum())
            if len(ys) and right - left >= 4 and area >= 25:
                boxes.append((left, int(ys[0]), right, int(ys[-1]) + 1, area))
        return boxes

    @staticmethod
    def union_box(boxes):
        return (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
            sum(box[4] for box in boxes),
        )

    @staticmethod
    def expand_box(box, padding: int, width: int, height: int):
        return (
            max(0, box[0] - padding),
            max(0, box[1] - padding),
            min(width, box[2] + padding),
            min(height, box[3] + padding),
            box[4],
        )

    @staticmethod
    def trim_nonwhite_border(image: Image.Image, threshold: int = 245, padding: int = 4) -> Image.Image:
        gray = np.array(image.convert("L"))
        mask = gray < threshold
        if not mask.any():
            return image
        ys, xs = np.where(mask)
        left = max(int(xs.min()) - padding, 0)
        top = max(int(ys.min()) - padding, 0)
        right = min(int(xs.max()) + 1 + padding, image.width)
        bottom = min(int(ys.max()) + 1 + padding, image.height)
        if right <= left or bottom <= top:
            return image
        return image.crop((left, top, right, bottom))

    @staticmethod
    def normalize_ocr_token(text: str) -> str:
        token = (text or "").strip()
        token = token.replace("电", "田")
        token = token.replace("G", "6")
        token = token.replace("O", "0")
        token = token.replace("o", "0")
        return token

    @staticmethod
    def is_digit_like_token(token: str) -> bool:
        return bool(re.fullmatch(r"[0-9]+", token or ""))

    @staticmethod
    def token_aliases(token: str) -> set[str]:
        token = (token or "").strip()
        aliases = {token}
        if token == "0":
            aliases.update({"0", "O", "o"})
        elif token == "1":
            aliases.update({"1", "l", "I", "i"})
        elif token == "6":
            aliases.update({"6", "G", "g"})
        elif token == "8":
            aliases.update({"8", "B", "b"})
        return aliases

    def solve_widget_mixed_ocr(self, answer_image: Image.Image, bg_image: Image.Image, candidate_box):
        det, ocr = self._load_ddddocr()
        if not det or not ocr:
            return []

        answer_bytes = BytesIO()
        answer_image.save(answer_bytes, format="PNG")
        answer_boxes = det.detection(answer_bytes.getvalue()) or []
        bg_bytes = BytesIO()
        bg_image.save(bg_bytes, format="PNG")
        candidate_boxes = det.detection(bg_bytes.getvalue()) or []

        if not answer_boxes or not candidate_boxes:
            logging.info("ddddocr detection returned no boxes for mixed point-click captcha.")
            return []

        answer_boxes = [box for box in answer_boxes if box[1] < 45]

        def classify_box(image: Image.Image, box):
            crop = image.crop(tuple(box))
            buf = BytesIO()
            crop.save(buf, format="PNG")
            return self.normalize_ocr_token(ocr.classification(buf.getvalue()))

        answer_tokens = []
        for box in sorted(answer_boxes, key=lambda item: item[0]):
            token = classify_box(answer_image, box)
            if token in {"", "请", "点", "击", "次", "点击"}:
                continue
            kind = "digit" if self.is_digit_like_token(token) else "icon"
            answer_tokens.append((token, kind, box))

        candidate_tokens = []
        for box in sorted(candidate_boxes, key=lambda item: (item[1], item[0])):
            token = classify_box(bg_image, box)
            candidate_tokens.append((token, box))

        logging.info(
            "Point-click mixed OCR tokens: answers=%s candidates=%s",
            [(token, kind) for token, kind, _box in answer_tokens],
            [(token, box) for token, box in candidate_tokens],
        )

        if len(answer_tokens) < 2 or len(candidate_tokens) < 3:
            return []

        top_matches = []
        for token, kind, answer_box in answer_tokens:
            target = self.expand_box(answer_box, 2, answer_image.width, answer_image.height)
            target_image = answer_image.crop(target[:4])
            target_mask = self.dark_mask(target_image, 130)
            scores = []
            for candidate_token, candidate_box_item in candidate_tokens:
                if kind == "digit":
                    candidate_norm = self.normalize_ocr_token(candidate_token)
                    if candidate_norm not in self.token_aliases(token):
                        continue
                    score = 1.0 if candidate_norm == token else 0.92
                else:
                    candidate = self.expand_box(candidate_box_item, 3, bg_image.width, bg_image.height)
                    candidate_image = bg_image.crop(candidate[:4])
                    candidate_mask = self.dark_mask(candidate_image, 100)
                    score = float(self.combined_match_score(
                        target_image,
                        candidate_image,
                        target_mask,
                        candidate_mask,
                        answer_box,
                        candidate_box_item,
                    ))
                scores.append((score, candidate_box_item))
            if not scores:
                return []
            top_matches.append(sorted(scores, key=lambda item: item[0], reverse=True)[:10])

        for index, matches in enumerate(top_matches):
            if len(matches) < 2:
                continue
            best_score = matches[0][0]
            second_score = matches[1][0]
            if best_score - second_score < 0.03 and best_score < 0.80:
                logging.info(
                    "Rejected mixed OCR target %s: ambiguous scores best=%.3f second=%.3f gap=%.3f",
                    index,
                    best_score,
                    second_score,
                    best_score - second_score,
                )
                return []

        ranked = []

        def search(index: int, used: set, score_sum: float, chosen: list):
            if index == len(top_matches):
                ranked.append((score_sum, list(chosen)))
                return
            for score, box in top_matches[index]:
                key = box[:4]
                if key in used:
                    continue
                used.add(key)
                chosen.append((score, box))
                search(index + 1, used, score_sum + score, chosen)
                chosen.pop()
                used.remove(key)

        search(0, set(), 0.0, [])
        if not ranked:
            return []
        ranked.sort(key=lambda item: item[0], reverse=True)
        solutions = []
        for score_sum, chosen in ranked[:3]:
            average_score = score_sum / len(chosen)
            min_score = min(score for score, _box in chosen)
            if average_score < 0.62:
                continue
            if min_score < 0.45:
                continue
            points = []
            for _score, box in chosen:
                center_x = (box[0] + box[2]) / 2 - candidate_box[0]
                center_y = (box[1] + box[3]) / 2 - candidate_box[1]
                points.append((center_x, center_y, _score))
            solutions.append((average_score, points))
        return solutions

    def solve_widget_ocr(self, widget_image: Image.Image, candidate_box):
        det, ocr = self._load_ddddocr()
        if not det or not ocr:
            return []

        widget_bytes = BytesIO()
        widget_image.save(widget_bytes, format="PNG")
        boxes = det.detection(widget_bytes.getvalue()) or []
        if not boxes:
            logging.info("ddddocr detection returned no boxes for point-click captcha.")
            return []

        answer_boxes = [box for box in boxes if box[1] < 45]
        candidate_boxes = [box for box in boxes if box[1] >= candidate_box[1]]

        def classify_box(box):
            crop = widget_image.crop(tuple(box))
            buf = BytesIO()
            crop.save(buf, format="PNG")
            return self.normalize_ocr_token(ocr.classification(buf.getvalue()))

        answer_tokens = []
        for box in sorted(answer_boxes, key=lambda item: item[0]):
            token = classify_box(box)
            if token in {"", "请", "点", "击", "次", "点击"}:
                continue
            answer_tokens.append((token, box))

        candidate_tokens = []
        for box in sorted(candidate_boxes, key=lambda item: (item[1], item[0])):
            token = classify_box(box)
            if token:
                candidate_tokens.append((token, box))

        logging.info(
            "Point-click OCR tokens: answers=%s candidates=%s",
            [token for token, _box in answer_tokens],
            [(token, box) for token, box in candidate_tokens],
        )

        if len(answer_tokens) < 3 or len(candidate_tokens) < 3:
            return []

        matched = []
        used_indexes = set()
        for answer_token, _answer_box in answer_tokens:
            match_index = next(
                (
                    index
                    for index, (candidate_token, _candidate_box) in enumerate(candidate_tokens)
                    if index not in used_indexes and candidate_token == answer_token
                ),
                None,
            )
            if match_index is None and answer_token == "0":
                match_index = next(
                    (
                        index
                        for index, (candidate_token, _candidate_box) in enumerate(candidate_tokens)
                        if index not in used_indexes and candidate_token in {"0", "6"}
                    ),
                    None,
                )
            if match_index is None:
                return []
            used_indexes.add(match_index)
            matched.append(candidate_tokens[match_index][1])

        points = []
        for box in matched:
            center_x = (box[0] + box[2]) / 2 - candidate_box[0]
            center_y = (box[1] + box[3]) / 2 - candidate_box[1]
            points.append((center_x, center_y))
        return points

    def find_click_candidates(self, bg_image: Image.Image):
        raw_boxes = []
        for threshold in (75, 95, 115, 135):
            mask = self.dark_mask(bg_image, threshold)
            merged_mask = self.close_mask(mask, radius=1)
            merged_mask = self.dilate_mask(merged_mask, radius=1)
            for box in self.connected_boxes(merged_mask, min_area=45, connectivity=8):
                left, top, right, bottom, _area = box
                width = right - left
                height = bottom - top
                if not (12 <= width <= 130 and 12 <= height <= 130):
                    continue
                if width * height > 9000:
                    continue
                original_area = int(mask[top:bottom, left:right].sum())
                fill_ratio = original_area / max(width * height, 1)
                # Tencent point-click glyphs are black line drawings. This keeps
                # dense photo patches out while allowing thin digits and icons.
                if 45 <= original_area and 0.015 <= fill_ratio <= 0.65:
                    raw_boxes.append((left, top, right, bottom, original_area))

        unique_boxes = self.deduplicate_boxes(raw_boxes, tolerance=4)
        merged_boxes = self.merge_nearby_candidate_boxes(unique_boxes, bg_image.width, bg_image.height)
        # Keep both raw glyph boxes and conservative unions. Raw boxes are better
        # for glyphs near wheat/texture; unions rescue icons split into strokes.
        return self.deduplicate_boxes(unique_boxes + merged_boxes, tolerance=6)

    @staticmethod
    def boxes_overlap_or_close(first, second, gap: int = 8) -> bool:
        return not (
            first[2] + gap < second[0]
            or second[2] + gap < first[0]
            or first[3] + gap < second[1]
            or second[3] + gap < first[1]
        )

    def merge_nearby_candidate_boxes(self, boxes, image_width: int, image_height: int):
        merged = list(boxes)
        changed = True
        while changed:
            changed = False
            next_boxes = []
            used = [False] * len(merged)
            for index, box in enumerate(merged):
                if used[index]:
                    continue
                current = box
                used[index] = True
                for other_index in range(index + 1, len(merged)):
                    if used[other_index]:
                        continue
                    other = merged[other_index]
                    if not self.boxes_overlap_or_close(current, other, gap=10):
                        continue
                    union = self.union_box((current, other))
                    width = union[2] - union[0]
                    height = union[3] - union[1]
                    if 12 <= width <= 135 and 12 <= height <= 135 and width * height <= 10000:
                        current = union
                        used[other_index] = True
                        changed = True
                next_boxes.append(self.expand_box(current, 1, image_width, image_height))
            merged = next_boxes
        return merged

    @staticmethod
    def deduplicate_boxes(boxes, tolerance: int = 5):
        final = []
        for box in sorted(boxes, key=lambda item: (item[1], item[0], -(item[2] - item[0]) * (item[3] - item[1]))):
            if not any(
                abs(box[0] - existing[0]) <= tolerance
                and abs(box[1] - existing[1]) <= tolerance
                and abs(box[2] - existing[2]) <= tolerance
                and abs(box[3] - existing[3]) <= tolerance
                for existing in final
            ):
                final.append(box)
        return final

    @staticmethod
    def normalize_mask(mask: np.ndarray, size: int = 96) -> np.ndarray:
        if mask.size == 0 or not mask.any():
            return np.zeros((size, size), dtype=bool)
        ys, xs = np.where(mask)
        top, bottom = int(ys.min()), int(ys.max()) + 1
        left, right = int(xs.min()), int(xs.max()) + 1
        cropped = mask[top:bottom, left:right].astype("uint8") * 255
        image = Image.fromarray(cropped, mode="L")
        scale = min((size - 8) / max(image.width, 1), (size - 8) / max(image.height, 1))
        resized = image.resize(
            (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
            Image.Resampling.NEAREST,
        )
        canvas = Image.new("L", (size, size), 0)
        offset = ((size - resized.width) // 2, (size - resized.height) // 2)
        canvas.paste(resized, offset)
        return np.array(canvas) > 128

    @staticmethod
    def normalize_grayscale(image: Image.Image, size: int = 96, threshold: int = 245) -> np.ndarray:
        trimmed = PointClickImageSolver.trim_nonwhite_border(image, threshold=threshold, padding=4).convert("L")
        scale = min((size - 8) / max(trimmed.width, 1), (size - 8) / max(trimmed.height, 1))
        resized = trimmed.resize(
            (max(1, int(round(trimmed.width * scale))), max(1, int(round(trimmed.height * scale)))),
            Image.Resampling.BILINEAR,
        )
        canvas = Image.new("L", (size, size), 255)
        offset = ((size - resized.width) // 2, (size - resized.height) // 2)
        canvas.paste(resized, offset)
        return np.array(canvas, dtype=np.float32) / 255.0

    @staticmethod
    def normalize_edge_map(image: Image.Image, size: int = 96) -> np.ndarray:
        trimmed = PointClickImageSolver.trim_nonwhite_border(image, threshold=245, padding=4).convert("L")
        array = np.array(trimmed)
        if array.size == 0:
            return np.zeros((size, size), dtype=bool)
        if cv2 is not None:
            blurred = cv2.GaussianBlur(array, (3, 3), 0)
            edges = cv2.Canny(blurred, 35, 120) > 0
        else:
            vertical = np.zeros_like(array, dtype=bool)
            horizontal = np.zeros_like(array, dtype=bool)
            vertical[:, 1:] = np.abs(array[:, 1:].astype(np.int16) - array[:, :-1].astype(np.int16)) > 24
            horizontal[1:, :] = np.abs(array[1:, :].astype(np.int16) - array[:-1, :].astype(np.int16)) > 24
            edges = vertical | horizontal
        return PointClickImageSolver.normalize_mask(edges, size=size)

    def score_icon_match(self, target_mask: np.ndarray, candidate_mask: np.ndarray) -> float:
        if target_mask.size == 0 or candidate_mask.size == 0 or not target_mask.any() or not candidate_mask.any():
            return 0.0
        target = self.normalize_mask(target_mask)
        candidate = self.normalize_mask(candidate_mask)
        best = 0.0
        candidate_image = Image.fromarray((candidate.astype("uint8") * 255), mode="L")
        for angle in self.ROTATION_ANGLES:
            rotated = candidate_image.rotate(angle, expand=False, resample=Image.Resampling.BILINEAR, fillcolor=0)
            rotated_mask = np.array(rotated) > 128
            intersection = np.logical_and(target, rotated_mask).sum()
            union = np.logical_or(target, rotated_mask).sum()
            if union:
                best = max(best, float(intersection / union))
        return best

    @staticmethod
    def _largest_contour(mask: np.ndarray):
        if cv2 is None:
            return None
        image = (mask.astype("uint8") * 255)
        contours, _hierarchy = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        return max(contours, key=cv2.contourArea)

    def score_shape_match(self, target_mask: np.ndarray, candidate_mask: np.ndarray) -> float:
        if cv2 is None:
            return self.score_soft_mask_match(target_mask, candidate_mask)
        if target_mask.size == 0 or candidate_mask.size == 0 or not target_mask.any() or not candidate_mask.any():
            return 0.0
        target = self.normalize_mask(target_mask, size=128)
        target_contour = self._largest_contour(target)
        if target_contour is None:
            return 0.0

        candidate = self.normalize_mask(candidate_mask, size=128)
        candidate_image = Image.fromarray((candidate.astype("uint8") * 255), mode="L")
        best_distance = None
        for angle in self.ROTATION_ANGLES:
            rotated = candidate_image.rotate(angle, expand=False, resample=Image.Resampling.BILINEAR, fillcolor=0)
            rotated_mask = np.array(rotated) > 128
            rotated_contour = self._largest_contour(rotated_mask)
            if rotated_contour is None:
                continue
            distance = float(cv2.matchShapes(target_contour, rotated_contour, cv2.CONTOURS_MATCH_I1, 0))
            best_distance = distance if best_distance is None else min(best_distance, distance)

        if best_distance is None:
            return 0.0
        return 1.0 / (1.0 + (best_distance * 1000.0))

    @staticmethod
    def soft_mask(mask: np.ndarray, size: int = 96) -> np.ndarray:
        normalized = PointClickImageSolver.normalize_mask(mask, size=size)
        image = Image.fromarray((normalized.astype("uint8") * 255), mode="L")
        blurred = image.filter(ImageFilter.GaussianBlur(radius=2.0))
        array = np.array(blurred, dtype=np.float32) / 255.0
        max_value = float(array.max())
        if max_value > 0:
            array /= max_value
        return array

    def score_soft_mask_match(self, target_mask: np.ndarray, candidate_mask: np.ndarray) -> float:
        if target_mask.size == 0 or candidate_mask.size == 0 or not target_mask.any() or not candidate_mask.any():
            return 0.0
        target = self.soft_mask(target_mask, size=112)
        candidate = self.soft_mask(candidate_mask, size=112)
        candidate_image = Image.fromarray(np.uint8(candidate * 255), mode="L")
        target_norm = float(np.linalg.norm(target))
        if target_norm <= 0:
            return 0.0
        best = 0.0
        for angle in self.ROTATION_ANGLES:
            rotated = candidate_image.rotate(angle, expand=False, resample=Image.Resampling.BILINEAR, fillcolor=0)
            rotated_arr = np.array(rotated, dtype=np.float32) / 255.0
            denom = target_norm * float(np.linalg.norm(rotated_arr))
            if denom <= 0:
                continue
            correlation = float(np.sum(target * rotated_arr) / denom)
            overlap = float(np.sum(np.minimum(target, rotated_arr)))
            recall = overlap / max(float(np.sum(target)), 1.0)
            precision = overlap / max(float(np.sum(rotated_arr)), 1.0)
            coverage = (2.0 * precision * recall) / max(precision + recall, 1e-6)
            best = max(best, (correlation * 0.62) + (coverage * 0.38))
        return best

    def score_visual_match(self, target_image: Image.Image, candidate_image: Image.Image) -> float:
        target = self.normalize_grayscale(target_image, size=112)
        candidate = self.normalize_grayscale(candidate_image, size=112)
        candidate_image_pil = Image.fromarray(np.uint8(candidate * 255), mode="L")
        best = 0.0
        for angle in self.ROTATION_ANGLES:
            rotated = candidate_image_pil.rotate(
                angle,
                expand=False,
                resample=Image.Resampling.BILINEAR,
                fillcolor=255,
            )
            rotated_arr = np.array(rotated, dtype=np.float32) / 255.0
            diff = np.mean(np.abs(target - rotated_arr))
            score = 1.0 - diff
            if score > best:
                best = score
        return best

    def score_edge_match(self, target_image: Image.Image, candidate_image: Image.Image) -> float:
        target = self.normalize_edge_map(target_image, size=112)
        candidate = self.normalize_edge_map(candidate_image, size=112)
        if target.size == 0 or candidate.size == 0 or not target.any() or not candidate.any():
            return 0.0
        candidate_image_pil = Image.fromarray((candidate.astype("uint8") * 255), mode="L")
        best = 0.0
        for angle in self.ROTATION_ANGLES:
            rotated = candidate_image_pil.rotate(angle, expand=False, resample=Image.Resampling.NEAREST, fillcolor=0)
            rotated_mask = np.array(rotated) > 128
            intersection = np.logical_and(target, rotated_mask).sum()
            union = np.logical_or(target, rotated_mask).sum()
            if union:
                best = max(best, float(intersection / union))
        return best

    def combined_match_score(
        self,
        target_image: Image.Image,
        candidate_image: Image.Image,
        target_mask: np.ndarray,
        candidate_mask: np.ndarray,
        target_box: tuple,
        candidate_box: tuple,
    ) -> float:
        icon_score = self.score_icon_match(target_mask, candidate_mask)
        soft_score = self.score_soft_mask_match(target_mask, candidate_mask)
        shape_score = self.score_shape_match(target_mask, candidate_mask)
        visual_score = self.score_visual_match(target_image, candidate_image)
        edge_score = self.score_edge_match(target_image, candidate_image)
        target_width = target_box[2] - target_box[0]
        target_height = target_box[3] - target_box[1]
        candidate_width = candidate_box[2] - candidate_box[0]
        candidate_height = candidate_box[3] - candidate_box[1]
        width_ratio = min(target_width, candidate_width) / max(target_width, candidate_width, 1)
        height_ratio = min(target_height, candidate_height) / max(target_height, candidate_height, 1)
        size_score = (width_ratio + height_ratio) / 2.0
        if min(target_width, target_height) >= self.COMPLEX_ICON_SIZE_THRESHOLD:
            return (
                (soft_score * 0.34)
                + (visual_score * 0.12)
                + (icon_score * 0.12)
                + (shape_score * 0.16)
                + (edge_score * 0.16)
                + (size_score * 0.10)
            )
        return (
            (soft_score * 0.42)
            + (visual_score * 0.10)
            + (icon_score * 0.30)
            + (shape_score * 0.04)
            + (edge_score * 0.09)
            + (size_score * 0.05)
        )

    def ranked_solutions_from_images(
        self,
        answer_image: Image.Image,
        bg_image: Image.Image,
        limit: int = 3,
        min_average_score: float = 0.42,
        min_point_score: float = 0.20,
        min_score_gap: float = 0.005,
    ):
        target_boxes = self.segment_answer_icons(answer_image)
        candidates = self.find_click_candidates(bg_image)
        diagnostics = {
            "answer_size": [answer_image.width, answer_image.height],
            "background_size": [bg_image.width, bg_image.height],
            "target_count": len(target_boxes),
            "candidate_count": len(candidates),
            "targets": [self._box_to_dict(box) for box in target_boxes],
            "candidates": [self._box_to_dict(box) for box in candidates],
            "thresholds": {
                "min_average_score": min_average_score,
                "min_point_score": min_point_score,
                "min_score_gap": min_score_gap,
            },
            "top_matches": [],
            "solutions": [],
            "accepted": False,
            "rejection_reason": None,
        }
        logging.info(
            "Point-click solver image stats: targets=%s candidates=%s",
            len(target_boxes),
            len(candidates),
        )
        if not target_boxes or len(candidates) < len(target_boxes):
            diagnostics["rejection_reason"] = "insufficient_objects"
            self.last_diagnostics = diagnostics
            logging.warning(
                "Point-click solver has insufficient objects: targets=%s, candidates=%s",
                len(target_boxes),
                len(candidates),
            )
            return []

        top_matches = []
        for target_box in target_boxes:
            target = self.expand_box(target_box, 2, answer_image.width, answer_image.height)
            target_image = answer_image.crop(target[:4])
            target_mask = self.dark_mask(target_image, 130)
            scores = []
            for candidate_box in candidates:
                candidate = self.expand_box(candidate_box, 3, bg_image.width, bg_image.height)
                candidate_image = bg_image.crop(candidate[:4])
                candidate_mask = self.dark_mask(candidate_image, 100)
                scores.append(
                    (
                        float(self.combined_match_score(
                            target_image,
                            candidate_image,
                            target_mask,
                            candidate_mask,
                            target_box,
                            candidate_box,
                        )),
                        candidate_box,
                    )
                )
            top_matches.append(sorted(scores, key=lambda item: item[0], reverse=True)[:10])
            diagnostics["top_matches"].append(
                {
                    "target": self._box_to_dict(target_box),
                    "matches": [
                        {
                            "score": round(float(score), 6),
                            "candidate": self._box_to_dict(candidate_box),
                        }
                        for score, candidate_box in top_matches[-1][:10]
                    ],
                }
            )

        for index, matches in enumerate(top_matches):
            if len(matches) < 2:
                continue
            best_score = matches[0][0]
            second_score = matches[1][0]
            if best_score - second_score < min_score_gap:
                diagnostics["rejection_reason"] = "ambiguous_target"
                diagnostics["ambiguous_target"] = {
                    "index": index,
                    "best_score": round(float(best_score), 6),
                    "second_score": round(float(second_score), 6),
                    "gap": round(float(best_score - second_score), 6),
                }
                self.last_diagnostics = diagnostics
                logging.info(
                    "Rejected point-click target %s: ambiguous scores best=%.3f second=%.3f gap=%.3f below threshold %.3f",
                    index,
                    best_score,
                    second_score,
                    best_score - second_score,
                    min_score_gap,
                )
                return []

        ranked = []

        def search(index: int, used: set, score_sum: float, chosen: list):
            if index == len(top_matches):
                ranked.append((score_sum, list(chosen)))
                return
            for score, box in top_matches[index]:
                key = box[:4]
                if key in used:
                    continue
                used.add(key)
                chosen.append((score, box))
                search(index + 1, used, score_sum + score, chosen)
                chosen.pop()
                used.remove(key)

        search(0, set(), 0.0, [])
        if not ranked:
            diagnostics["rejection_reason"] = "no_non_overlapping_combination"
            self.last_diagnostics = diagnostics
            return []

        ranked.sort(key=lambda item: item[0], reverse=True)
        solutions = []
        rejected_solutions = []
        for score_sum, chosen in ranked[:limit]:
            average_score = score_sum / len(chosen)
            min_score = min(score for score, _box in chosen)
            if average_score < min_average_score:
                rejected_solutions.append(
                    {
                        "reason": "average_score_below_threshold",
                        "average_score": round(float(average_score), 6),
                        "min_point_score": round(float(min_score), 6),
                    }
                )
                logging.info(
                    "Rejected point-click solution: average_score=%.3f below threshold %.3f, min_point_score=%.3f",
                    average_score,
                    min_average_score,
                    min_score,
                )
                continue
            if min_score < min_point_score:
                rejected_solutions.append(
                    {
                        "reason": "point_score_below_threshold",
                        "average_score": round(float(average_score), 6),
                        "min_point_score": round(float(min_score), 6),
                    }
                )
                logging.info(
                    "Rejected point-click solution: min_point_score=%.3f below threshold %.3f, average_score=%.3f",
                    min_score,
                    min_point_score,
                    average_score,
                )
                continue
            points = []
            for score, box in chosen:
                left, top, right, bottom, _ = box
                points.append(((left + right) / 2, (top + bottom) / 2, score))
            solutions.append((average_score, points))
            diagnostics["solutions"].append(
                {
                    "average_score": round(float(average_score), 6),
                    "min_point_score": round(float(min_score), 6),
                    "points": [
                        {
                            "x": round(float(x), 2),
                            "y": round(float(y), 2),
                            "score": round(float(score), 6),
                        }
                        for x, y, score in points
                    ],
                }
            )
        diagnostics["rejected_solutions"] = rejected_solutions
        diagnostics["accepted"] = bool(solutions)
        if not solutions and diagnostics["rejection_reason"] is None:
            diagnostics["rejection_reason"] = "all_solutions_below_threshold"
        self.last_diagnostics = diagnostics
        return solutions

    def solve_from_images(self, answer_image: Image.Image, bg_image: Image.Image):
        solutions = self.ranked_solutions_from_images(answer_image, bg_image, limit=1)
        if not solutions:
            return []
        average_score, points = solutions[0]
        logging.info(
            "Point-click solver points=%s, average_score=%.3f",
            [(round(x, 1), round(y, 1), round(score, 3)) for x, y, score in points],
            average_score,
        )
        return points
