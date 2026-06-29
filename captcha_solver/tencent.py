import json
import logging
import os
import random
import re
import time
from io import BytesIO

from PIL import Image
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from captcha_solver.image import PointClickImageSolver, capture_element_image
from captcha_solver.learning import CaptchaLearningStore


class TencentCaptchaHandler:
    """Tencent-specific adapter around the generic captcha solvers."""

    capture_element_image = staticmethod(capture_element_image)
    POINT_CLICK_MAX_REFRESHES = 2
    POINT_CLICK_REFRESH_KEYWORDS = (
        "刷新",
        "换一张",
        "重试",
        "换图",
        "重载",
        "看不清",
        "reload",
        "refresh",
        "retry",
    )

    def __init__(self, trace_dir, log_page_state, step_sleep, confirm_login_success):
        self._trace_dir = trace_dir
        self._log_page_state = log_page_state
        self._step_sleep = step_sleep
        self._confirm_login_success = confirm_login_success
        self._point_click_solver = PointClickImageSolver()
        self.point_click_max_refreshes = int(
            os.getenv("CAPTCHA_POINT_CLICK_MAX_REFRESHES", self.POINT_CLICK_MAX_REFRESHES)
        )
        self._learning_store = None

    def _get_learning_store(self) -> CaptchaLearningStore:
        if self._learning_store is None:
            self._learning_store = CaptchaLearningStore(self._trace_dir().parent / "captcha_samples")
        return self._learning_store

    def has_captcha(self, driver) -> bool:
        try:
            return self._get_visible_widget(driver) is not None
        except Exception:
            return False

    @staticmethod
    def _get_visible_widget(driver):
        try:
            return driver.execute_script(
                """
                const selectors = [
                  '.tencent-captcha-dy__warp',
                  '.tencent-captcha-dy__wrapper',
                  '.tencent-captcha__wrapper',
                  '.tencent-captcha-dy__body-wrap',
                  '.tencent-captcha-dy__image-area',
                  '.tencent-captcha-dy__verify-bg',
                  '.tencent-captcha-dy__verify-bg-img',
                  '[class*="tencent-captcha-dy__content"]'
                ];
                const visible = (el, doc) => {
                  const rect = el.getBoundingClientRect();
                  const style = doc.defaultView.getComputedStyle(el);
                  const inViewport = rect.bottom > 0 && rect.right > 0
                    && rect.top < doc.defaultView.innerHeight && rect.left < doc.defaultView.innerWidth;
                  return rect.width > 40 && rect.height > 40
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && inViewport;
                };
                const search = (doc) => {
                  const nodes = selectors.flatMap((selector) => Array.from(doc.querySelectorAll(selector)));
                  const found = nodes.find((el) => visible(el, doc));
                  if (found) {
                    return found;
                  }
                  const frames = Array.from(doc.querySelectorAll('iframe,frame'));
                  for (const frame of frames) {
                    try {
                      const child = frame.contentDocument;
                      if (child) {
                        const nested = search(child);
                        if (nested) {
                          return nested;
                        }
                      }
                    } catch (err) {}
                  }
                  return null;
                };
                return search(document);
                """
            )
        except Exception:
            return None

    def get_visible_descendant(self, driver, selectors, min_width: int = 20, min_height: int = 20):
        try:
            widget = self._get_visible_widget(driver)
            if not widget:
                return None
            return driver.execute_script(
                """
                const root = arguments[0];
                const selectors = arguments[1];
                const minWidth = arguments[2];
                const minHeight = arguments[3];
                const search = (node) => {
                  const doc = node.ownerDocument || node;
                  const nodes = selectors.flatMap((selector) => Array.from(node.querySelectorAll(selector)));
                  const visible = nodes
                    .filter((el) => {
                      const rect = el.getBoundingClientRect();
                      const style = doc.defaultView.getComputedStyle(el);
                      const inViewport = rect.bottom > 0 && rect.right > 0
                        && rect.top < doc.defaultView.innerHeight && rect.left < doc.defaultView.innerWidth;
                      return rect.width >= minWidth
                        && rect.height >= minHeight
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && inViewport;
                    })
                    .sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      return (br.width * br.height) - (ar.width * ar.height);
                    });
                  if (visible.length > 0) {
                    return visible[0];
                  }
                  const frames = Array.from(node.querySelectorAll('iframe,frame'));
                  for (const frame of frames) {
                    try {
                      const child = frame.contentDocument;
                      if (child) {
                        const nested = search(child);
                        if (nested) {
                          return nested;
                        }
                      }
                    } catch (err) {}
                  }
                  return null;
                };
                return search(root);
                """,
                widget,
                selectors,
                min_width,
                min_height,
            )
        except Exception:
            return None

    def get_info(self, driver):
        try:
            return driver.execute_script(
                """
                const textOf = (selector) => {
                  const docs = [document];
                  const seen = new Set();
                  while (docs.length) {
                    const doc = docs.pop();
                    if (!doc || seen.has(doc)) continue;
                    seen.add(doc);
                    const el = doc.querySelector(selector);
                    if (el) {
                      return (el.innerText || el.textContent || '').trim();
                    }
                    Array.from(doc.querySelectorAll('iframe,frame')).forEach((frame) => {
                      try {
                        if (frame.contentDocument) {
                          docs.push(frame.contentDocument);
                        }
                      } catch (err) {}
                    });
                  }
                  return '';
                };
                const exists = (selector) => {
                  const docs = [document];
                  const seen = new Set();
                  while (docs.length) {
                    const doc = docs.pop();
                    if (!doc || seen.has(doc)) continue;
                    seen.add(doc);
                    if (doc.querySelector(selector)) {
                      return true;
                    }
                    Array.from(doc.querySelectorAll('iframe,frame')).forEach((frame) => {
                      try {
                        if (frame.contentDocument) {
                          docs.push(frame.contentDocument);
                        }
                      } catch (err) {}
                    });
                  }
                  return false;
                };
                const prompt =
                  textOf('.tencent-captcha-dy__header-text') ||
                  textOf('.tencent-captcha-dy__question') ||
                  textOf('.tencent-captcha-dy__title') ||
                  textOf('.tencent-captcha__title') ||
                  textOf('.tencent-captcha-dy__sub-title') ||
                  textOf('.tencent-captcha__sub-title') ||
                  textOf('.tencent-captcha-dy__network-status-text') ||
                  '';
                const hasPointClick =
                  /依次点击|顺序点击|点击下图|文字点选|请点击/i.test(prompt) ||
                  exists('.tencent-captcha-dy__click-type-wrap') ||
                  exists('.tencent-captcha-dy__click-word') ||
                  exists('.tencent-captcha-dy__point-area') ||
                  exists('.tencent-captcha-dy__word-content');
                const hasSlider =
                  /拖动.*拼图|拖动下方拼图|滑动验证/i.test(prompt) ||
                  exists('.tencent-captcha-dy__slider') ||
                  exists('[class*="tencent-captcha-dy__slider"]') ||
                  exists('[class*="slider-btn"]');

                let mode = 'unknown';
                if (hasPointClick) {
                  mode = 'point_click';
                } else if (hasSlider) {
                  mode = 'slider';
                }
                return {
                  mode,
                  prompt,
                  has_mask: exists('.tencent-captcha-dy__mask, .tencent-captcha__mask-layer'),
                  has_point_area: exists('.tencent-captcha-dy__point-area, .tencent-captcha-dy__click-word'),
                  has_click_type_wrap: exists('.tencent-captcha-dy__click-type-wrap'),
                  has_slider: hasSlider,
                };
                """
            ) or {"mode": "unknown", "prompt": ""}
        except Exception as exc:
            return {"mode": "unknown", "prompt": "", "error": str(exc)}

    def get_presence_snapshot(self, driver):
        try:
            return driver.execute_script(
                """
                const selectors = [
                  '.tencent-captcha-dy__warp',
                  '.tencent-captcha-dy__wrapper',
                  '.tencent-captcha__wrapper',
                  '.tencent-captcha-dy__body-wrap',
                  '.tencent-captcha-dy__image-area',
                  '.tencent-captcha-dy__verify-bg',
                  '.tencent-captcha-dy__verify-bg-img'
                ];
                return selectors.map((selector) => {
                  const elements = Array.from(document.querySelectorAll(selector));
                  return {
                    selector,
                    count: elements.length,
                    items: elements.slice(0, 3).map((el) => {
                      const rect = el.getBoundingClientRect();
                      const style = window.getComputedStyle(el);
                      return {
                        className: el.className || '',
                        text: (el.innerText || el.textContent || '').trim().slice(0, 80),
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left,
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity,
                      };
                    }),
                  };
                });
                """
            )
        except Exception as exc:
            return {"error": str(exc)}

    def capture_state(self, driver, label: str) -> None:
        self._log_page_state(driver, label)
        trace_dir = self._trace_dir()
        safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label)[:80]
        info_path = trace_dir / f"{safe_label}.captcha.txt"
        shot_path = trace_dir / f"{safe_label}.captcha.png"
        info = self.get_info(driver)
        try:
            info_path.write_text(
                json.dumps(info, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logging.warning("Failed to write Tencent captcha info for [%s]: %s", label, exc)
        try:
            widget = self._get_visible_widget(driver)
            if not widget:
                logging.info("Tencent captcha widget element not found for screenshot [%s].", label)
                return
            shot_path.write_bytes(self.capture_element_image(driver, widget))
            logging.info("Saved Tencent captcha widget screenshot to %s", shot_path)
        except Exception as exc:
            logging.warning("Failed to save Tencent captcha widget screenshot for [%s]: %s", label, exc)

    def clear_overlay(self, driver) -> None:
        try:
            driver.execute_script(
                """
                const selectors = [
                  '.tencent-captcha-dy__mask',
                  '.tencent-captcha-dy__wrapper',
                  '.tencent-captcha__mask-layer',
                  '[class*="tencent-captcha-dy__mask"]',
                  '[class*="tencent-captcha-dy__wrapper"]'
                ];
                selectors.forEach((selector) => {
                  document.querySelectorAll(selector).forEach((element) => {
                    element.style.display = 'none';
                    element.style.visibility = 'hidden';
                    element.style.pointerEvents = 'none';
                  });
                });
                """
            )
        except Exception:
            pass

    def _click_point_click_refresh(self, driver) -> bool:
        try:
            widget = self._get_visible_widget(driver)
            if not widget:
                return False
            refresh = driver.execute_script(
                """
                const root = arguments[0];
                const keywords = arguments[1];
                const visible = (el, doc) => {
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  const view = doc.defaultView;
                  const style = view.getComputedStyle(el);
                  return rect.width >= 10 && rect.height >= 10
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && style.opacity !== '0';
                };
                const textOf = (el) => {
                  const attrs = [
                    el.innerText || '',
                    el.textContent || '',
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('title') || '',
                    el.getAttribute('alt') || '',
                    el.className || '',
                    el.id || ''
                  ].join(' ');
                  return attrs.trim();
                };
                const isKeywordMatch = (el) => {
                  const text = textOf(el);
                  return keywords.some((keyword) => text.includes(keyword));
                };
                const clickElement = (el) => {
                  if (!el) return false;
                  const target = el.closest('button,[role="button"],a,[class*="btn"],[class*="refresh"]') || el;
                  try {
                    target.click();
                    return true;
                  } catch (err) {
                    return false;
                  }
                };
                const searchDoc = (doc) => {
                  const view = doc.defaultView;
                  const selectors = [
                    'button',
                    '[role="button"]',
                    'a',
                    '[class*="btn"]',
                    '[class*="refresh"]',
                    '[aria-label]',
                    '[title]',
                    'svg',
                    'path',
                    'i',
                    'span',
                    'div'
                  ];
                  const nodes = selectors.flatMap((selector) => Array.from(doc.querySelectorAll(selector)));
                  const keywordNode = nodes.find((el) => visible(el, doc) && isKeywordMatch(el));
                  if (keywordNode && clickElement(keywordNode)) {
                    return true;
                  }
                  const clickable = nodes
                    .filter((el) => visible(el, doc))
                    .filter((el) => {
                      const style = view.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      const nearBottomRight = rect.right > view.innerWidth - 120 && rect.bottom > view.innerHeight - 120;
                      const isSmall = rect.width <= 80 && rect.height <= 80;
                      const hasPointer = style.cursor === 'pointer' || el.onclick || el.getAttribute('role') === 'button';
                      return nearBottomRight && isSmall && (hasPointer || el.tagName === 'BUTTON' || el.tagName === 'A');
                    })
                    .sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      const ad = Math.abs((ar.right + ar.left) / 2 - view.innerWidth) + Math.abs((ar.bottom + ar.top) / 2 - view.innerHeight);
                      const bd = Math.abs((br.right + br.left) / 2 - view.innerWidth) + Math.abs((br.bottom + br.top) / 2 - view.innerHeight);
                      return ad - bd;
                    })[0];
                  if (clickable && clickElement(clickable)) {
                    return true;
                  }
                  const rect = root.getBoundingClientRect();
                  const x = Math.max(rect.right - 22, rect.left + 1);
                  const y = Math.max(rect.bottom - 22, rect.top + 1);
                  const point = doc.elementFromPoint(x, y);
                  if (!point) {
                    return false;
                  }
                  const ancestor = point.closest('button,[role="button"],a,[class*="btn"],[class*="refresh"]') || point;
                  return clickElement(ancestor);
                };
                const searchFrames = (doc) => {
                  if (searchDoc(doc)) {
                    return true;
                  }
                  const frames = Array.from(doc.querySelectorAll('iframe,frame'));
                  for (const frame of frames) {
                    try {
                      const child = frame.contentDocument;
                      if (child && searchFrames(child)) {
                        return true;
                      }
                    } catch (err) {}
                  }
                  return false;
                };
                return searchFrames(root.ownerDocument || document);
                """,
                widget,
                list(self.POINT_CLICK_REFRESH_KEYWORDS),
            )
            if refresh:
                logging.info("Clicked Tencent point-click captcha refresh button.")
                time.sleep(random.uniform(0.8, 1.4))
                return True
        except Exception as exc:
            logging.info("Failed to click Tencent point-click refresh button: %s", exc)
        try:
            widget = self._get_visible_widget(driver)
            if not widget:
                return False
            rect = widget.rect
            x_offset = int((rect.get("width", 0) / 2) - 20)
            y_offset = int((rect.get("height", 0) / 2) - 20)
            ActionChains(driver).move_to_element_with_offset(widget, x_offset, y_offset).click().perform()
            logging.info("Clicked Tencent point-click captcha refresh fallback area.")
            time.sleep(random.uniform(0.8, 1.4))
            return True
        except Exception as exc:
            logging.info("Failed to click Tencent point-click refresh fallback area: %s", exc)
        return False

    @staticmethod
    def _save_point_click_assets(trace_dir, answer_image, bg_image, suffix: str) -> None:
        answer_path = trace_dir / f"tencent_point_click_answer_{suffix}.png"
        bg_path = trace_dir / f"tencent_point_click_bg_{suffix}.png"
        answer_image.save(answer_path)
        bg_image.save(bg_path)
        logging.info("Saved Tencent point-click assets to %s and %s", answer_path, bg_path)

    def _save_point_click_report(self, suffix: str) -> None:
        try:
            report = self._point_click_solver.get_last_diagnostics()
            if not report:
                return
            report_path = self._trace_dir() / f"tencent_point_click_report_{suffix}.json"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logging.info("Saved Tencent point-click report to %s", report_path)
        except Exception as exc:
            logging.info("Failed to save Tencent point-click report: %s", exc)

    def _record_learning_sample(self, outcome: str, answer_image, bg_image, suffix: str) -> None:
        self._get_learning_store().record(
            outcome=outcome,
            answer_image=answer_image,
            bg_image=bg_image,
            diagnostics=self._point_click_solver.get_last_diagnostics(),
            suffix=suffix,
        )

    def solve_point_click_captcha(self, driver) -> bool:
        trace_dir = self._trace_dir()
        answer_image = None
        bg_image = None
        try:
            info = self.get_info(driver)
            if info.get("mode") != "point_click":
                return False

            for attempt in range(self.point_click_max_refreshes + 1):
                try:
                    answer_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".tencent-captcha-dy__header-answer img"))
                    )
                    bg_element = WebDriverWait(driver, 5).until(
                        lambda _driver: self.get_visible_descendant(
                            _driver,
                            [
                                ".tencent-captcha-dy__point-area",
                                ".tencent-captcha-dy__click-type-wrap",
                                ".tencent-captcha-dy__verify-bg-img",
                                ".tencent-captcha-dy__verify-bg",
                                ".tencent-captcha-dy__image-area",
                            ],
                            min_width=80,
                            min_height=80,
                        )
                        or False
                    )
                except Exception as exc:
                    logging.info("Point-click captcha elements not ready on attempt %s: %s", attempt, exc)
                    self.capture_state(driver, f"tencent_point_click_elements_not_ready_{attempt}")
                    if attempt < self.point_click_max_refreshes and self._click_point_click_refresh(driver):
                        continue
                    return False
                answer_image = self._point_click_solver.trim_nonwhite_border(
                    Image.open(BytesIO(self.capture_element_image(driver, answer_element))).convert("RGB"),
                    threshold=245,
                    padding=4,
                )
                bg_image = Image.open(BytesIO(self.capture_element_image(driver, bg_element))).convert("RGB")
                thresholds = self._get_learning_store().thresholds()
                solutions = self._point_click_solver.ranked_solutions_from_images(
                    answer_image,
                    bg_image,
                    limit=1,
                    min_average_score=thresholds["min_average_score"],
                    min_point_score=thresholds["min_point_score"],
                    min_score_gap=thresholds["min_score_gap"],
                )
                if not solutions:
                    self._save_point_click_assets(trace_dir, answer_image, bg_image, f"low_confidence_{attempt}")
                    self._save_point_click_report(f"low_confidence_{attempt}")
                    self._record_learning_sample("rejected", answer_image, bg_image, f"low_confidence_{attempt}")
                    if attempt < self.point_click_max_refreshes and self._click_point_click_refresh(driver):
                        self.capture_state(driver, f"tencent_point_click_refresh_{attempt + 1}")
                        continue
                    return False

                average_score, points = solutions[0]
                logging.info(
                    "Trying point-click image solution after %s refresh(es): points=%s average_score=%.3f",
                    attempt,
                    [(round(x, 1), round(y, 1), round(score, 3)) for x, y, score in points],
                    average_score,
                )
                bg_rect = bg_element.rect
                x_scale = bg_rect["width"] / bg_image.width
                y_scale = bg_rect["height"] / bg_image.height
                for x, y, _score in points:
                    x_offset = int((x * x_scale) - (bg_rect["width"] / 2))
                    y_offset = int((y * y_scale) - (bg_rect["height"] / 2))
                    ActionChains(driver).move_to_element_with_offset(
                        bg_element, x_offset, y_offset
                    ).pause(random.uniform(0.05, 0.15)).click().perform()
                    time.sleep(random.uniform(0.25, 0.55))

                confirm = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".tencent-captcha-dy__verify-confirm-btn"))
                )
                WebDriverWait(driver, 5).until(
                    lambda _driver: "disabled" not in (confirm.get_attribute("class") or "")
                )
                driver.execute_script("arguments[0].click();", confirm)
                self._step_sleep(driver, "after_tencent_point_click_submit")
                success = self._confirm_login_success(driver) or not self.has_captcha(driver)
                if success:
                    self._save_point_click_report(f"success_{attempt}")
                    self._record_learning_sample("success", answer_image, bg_image, f"success_{attempt}")
                    return True
                self._save_point_click_assets(trace_dir, answer_image, bg_image, f"post_click_failed_{attempt}")
                self._save_point_click_report(f"post_click_failed_{attempt}")
                self._record_learning_sample("failed_click", answer_image, bg_image, f"post_click_failed_{attempt}")
                if attempt < self.point_click_max_refreshes and self._click_point_click_refresh(driver):
                    self.capture_state(driver, f"tencent_point_click_retry_{attempt + 1}")
                    continue
                return False
            return False
        except Exception as exc:
            logging.warning("Tencent point-click captcha solver failed: %s", exc)
            if answer_image is not None and bg_image is not None:
                try:
                    answer_path = trace_dir / "tencent_point_click_answer_failed.png"
                    bg_path = trace_dir / "tencent_point_click_bg_failed.png"
                    answer_image.save(answer_path)
                    bg_image.save(bg_path)
                    logging.info("Saved Tencent point-click exception assets to %s and %s", answer_path, bg_path)
                except Exception:
                    pass
            self.capture_state(driver, "tencent_point_click_solver_failed")
            return False
