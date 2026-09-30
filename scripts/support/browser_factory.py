import logging
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService


ROOT_DIR = Path(__file__).resolve().parents[2]
PROFILE_CACHE_DIRS = (
    Path("Default/Cache"),
    Path("Default/Code Cache"),
    Path("Default/GPUCache"),
    Path("Default/Service Worker/CacheStorage"),
    Path("component_crx_cache"),
    Path("GrShaderCache"),
    Path("GraphiteDawnCache"),
    Path("ShaderCache"),
)

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
IPHONE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/137.0.7151.107 "
    "Mobile/15E148 Safari/604.1"
)


def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _profile_cache_limit_bytes() -> int:
    try:
        limit_mb = max(float(os.getenv("BROWSER_PROFILE_CACHE_MAX_MB", "128")), 0)
    except ValueError:
        logging.warning("Invalid BROWSER_PROFILE_CACHE_MAX_MB; using 128 MB.")
        limit_mb = 128
    return int(limit_mb * 1024 * 1024)


def prune_profile_cache(profile_dir: Path, limit_bytes: int | None = None) -> tuple[int, int]:
    limit_bytes = _profile_cache_limit_bytes() if limit_bytes is None else max(int(limit_bytes), 0)
    if limit_bytes == 0:
        return 0, 0

    files = []
    total_bytes = 0
    for relative_dir in PROFILE_CACHE_DIRS:
        cache_dir = profile_dir / relative_dir
        if not cache_dir.exists():
            continue
        for path in cache_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((stat.st_mtime_ns, path, stat.st_size))
            total_bytes += stat.st_size

    if total_bytes <= limit_bytes:
        return 0, 0

    removed_files = 0
    removed_bytes = 0
    for _mtime, path, size in sorted(files, key=lambda item: (item[0], str(item[1]))):
        if total_bytes - removed_bytes <= limit_bytes:
            break
        try:
            path.unlink()
        except OSError:
            continue
        removed_files += 1
        removed_bytes += size

    if removed_files:
        logging.info(
            "Pruned Chromium profile cache: files=%s reclaimed_mb=%.1f.",
            removed_files,
            removed_bytes / 1024 / 1024,
        )
    return removed_files, removed_bytes


def _profile_defaults(profile: str) -> dict:
    if profile == "iphone":
        return {
            "window_size": "390,844",
            "language": "zh-Hans-CN,zh-CN,zh,en-US,en",
            "user_agent": IPHONE_UA,
            "device_scale_factor": 3,
            "platform": "iPhone",
            "mobile": True,
            "touch_points": 5,
            "hardware_concurrency": 6,
            "device_memory": 4,
        }
    return {
        "window_size": "1158,848",
        "language": "zh-HK,zh,en-US,en,zh-CN",
        "user_agent": DESKTOP_UA,
        "device_scale_factor": 2,
        "platform": "MacIntel",
        "mobile": False,
        "touch_points": 0,
        "hardware_concurrency": 12,
        "device_memory": 32,
    }


def _add_persistent_profile_options(chrome_options, profile: str) -> None:
    if not _truthy_env("BROWSER_PERSIST_PROFILE", "true"):
        return
    profile_dir = os.getenv("BROWSER_PROFILE_DIR") or str(ROOT_DIR / "data" / "chrome-profile" / profile)
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    prune_profile_cache(profile_path)
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")
    chrome_options.add_argument("--profile-directory=Default")


def _apply_stealth_overrides(driver, *, language: str, platform: str, touch_points: int, hardware_concurrency: int, device_memory: int) -> None:
    import json

    languages = [item.strip() for item in language.split(",") if item.strip()]
    primary_language = languages[0] if languages else "zh-CN"
    script = f"""
    (() => {{
      const platformValue = {json.dumps(platform)};
      const languageValue = {json.dumps(primary_language)};
      const languagesValue = {json.dumps(languages, ensure_ascii=False)};
      const hardwareConcurrencyValue = {int(hardware_concurrency)};
      const deviceMemoryValue = {int(device_memory)};
      const maxTouchPointsValue = {int(touch_points)};
      const define = (target, key, value) => {{
        try {{ Object.defineProperty(target, key, {{ get: () => value, configurable: true }}); }} catch (e) {{}}
      }};
      define(Navigator.prototype, 'webdriver', undefined);
      define(Navigator.prototype, 'platform', platformValue);
      define(Navigator.prototype, 'language', languageValue);
      define(Navigator.prototype, 'languages', languagesValue);
      define(Navigator.prototype, 'hardwareConcurrency', hardwareConcurrencyValue);
      define(Navigator.prototype, 'deviceMemory', deviceMemoryValue);
      define(Navigator.prototype, 'maxTouchPoints', maxTouchPointsValue);
      window.chrome = window.chrome || {{ runtime: {{}} }};
    }})();
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})


def create_chromium_driver(driver_wait_time: int):
    browser_profile = os.getenv("BROWSER_PROFILE", "desktop").strip().lower() or "desktop"
    defaults = _profile_defaults(browser_profile)
    browser_window_size = os.getenv("BROWSER_WINDOW_SIZE", defaults["window_size"])
    browser_language = os.getenv("BROWSER_LANGUAGE", defaults["language"])
    browser_ua = os.getenv("BROWSER_USER_AGENT", defaults["user_agent"])
    browser_device_scale_factor = float(os.getenv("BROWSER_DEVICE_SCALE_FACTOR", str(defaults["device_scale_factor"])))
    browser_platform = os.getenv("BROWSER_PLATFORM", defaults["platform"])
    browser_touch_points = int(os.getenv("BROWSER_MAX_TOUCH_POINTS", str(defaults["touch_points"])))
    browser_hardware_concurrency = int(os.getenv("BROWSER_HARDWARE_CONCURRENCY", str(defaults["hardware_concurrency"])))
    browser_device_memory = int(os.getenv("BROWSER_DEVICE_MEMORY", str(defaults["device_memory"])))
    browser_language_primary = browser_language.split(",")[0]

    chrome_options = webdriver.ChromeOptions()
    if os.geteuid() == 0 or _truthy_env("BROWSER_DISABLE_SANDBOX"):
        chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    cache_limit_bytes = _profile_cache_limit_bytes()
    if cache_limit_bytes:
        chrome_options.add_argument(f"--disk-cache-size={cache_limit_bytes}")
    chrome_options.add_argument(f"--window-size={browser_window_size}")
    chrome_options.add_argument(f"--lang={browser_language_primary}")
    chrome_options.add_argument("--disable-features=Translate")
    chrome_options.add_argument(f"--force-device-scale-factor={browser_device_scale_factor}")
    chrome_options.add_argument("--high-dpi-support=1")
    chrome_options.add_argument("--password-store=basic")
    chrome_options.add_argument("--use-mock-keychain")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument(f"user-agent={browser_ua}")
    _add_persistent_profile_options(chrome_options, browser_profile)

    prefs = {
        "intl.accept_languages": browser_language,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if defaults["mobile"]:
        width, height = [int(item.strip()) for item in browser_window_size.split(",", 1)]
        chrome_options.add_experimental_option(
            "mobileEmulation",
            {
                "deviceMetrics": {
                    "width": width,
                    "height": height,
                    "pixelRatio": browser_device_scale_factor,
                    "touch": True,
                    "mobile": True,
                },
                "userAgent": browser_ua,
            },
        )
    else:
        chrome_options.add_argument("--start-maximized")

    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})

    if "PYTHON_IN_DOCKER" in os.environ:
        chrome_options.binary_location = "/usr/bin/chromium"
        service = ChromeService(executable_path="/usr/bin/chromedriver")
    else:
        service = ChromeService()

    driver = webdriver.Chrome(
        options=chrome_options,
        service=service,
    )
    driver.set_page_load_timeout(int(os.getenv("BROWSER_PAGE_LOAD_TIMEOUT", "60")))
    _apply_stealth_overrides(
        driver,
        language=browser_language,
        platform=browser_platform,
        touch_points=browser_touch_points,
        hardware_concurrency=browser_hardware_concurrency,
        device_memory=browser_device_memory,
    )
    driver.implicitly_wait(driver_wait_time)
    return driver
