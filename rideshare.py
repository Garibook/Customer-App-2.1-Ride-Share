from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
import time

# >>> added for logging/recording
import os, datetime, base64

APPIUM_SERVER = "http://127.0.0.1:4723"
APP_PKG = "com.garibook.user"
APP_ACT  = "com.garibook.user.MainActivity"

# Exact locators (your sheet)
XPATH_RIDE_SHARE  = '//android.widget.ImageView[@content-desc="Ride Share"]'
XPATH_DROP_OFF_IN = '//android.view.View[@content-desc="Drop Off"]//android.widget.EditText'
XPATH_SUGGESTION  = '//android.widget.ImageView[@content-desc="Mirpur-1, Dhaka, Bangladesh\nDhaka, Bangladesh"]'
XPATH_CONTINUE    = '//android.view.View[@content-desc="Continue"]'
XPATH_CONFIRM     = '//android.view.View[@content-desc="Confirm Pickup"]'

caps = {
    "platformName": "Android",
    "appium:platformVersion": "15",
    "appium:deviceName": "10BF830G2N0058R",   # update if needed
    "appium:automationName": "UiAutomator2",
    "appium:appPackage": APP_PKG,
    "appium:appActivity": APP_ACT,
    "appium:noReset": True,
    "appium:newCommandTimeout": 180,
    "appium:autoGrantPermissions": True,
    "appium:disableWindowAnimation": True,
    "appium:appWaitActivity": "*",
}

# =========================
# Paths / helpers (logs + video)
# =========================
REPORT_DIR   = "reports"
RECORD_DIR   = "recordings"
STEPLOG_XLSX = os.path.join(REPORT_DIR, "step_log.xlsx")

def _ensure_dirs():
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(RECORD_DIR, exist_ok=True)

def _clock():
    return datetime.datetime.now().strftime("%H:%M:%S")

def _ts_for_name(prefix, ext):
    return datetime.datetime.now().strftime(f"{prefix}__%Y%m%d_%H%M%S.{ext}")

class StepLogger:
    """
    Logs each step with clock time and elapsed seconds.
    Writes Excel (CSV fallback) at the end.
    """
    def __init__(self):
        _ensure_dirs()
        self.t0 = time.time()
        self.rows = []  # (Step, Status, ClockTime, +Elapsed(s), Note)

    def log(self, step, status, note=""):
        elapsed = round(time.time() - self.t0, 2)
        ct = _clock()
        print(f"{ct} [+{elapsed:.2f}s] {step} → {status}{' — ' + note if note else ''}")
        self.rows.append((step, status, ct, elapsed, note))

    def write(self):
        try:
            from openpyxl import Workbook, load_workbook
            if os.path.exists(STEPLOG_XLSX):
                wb = load_workbook(STEPLOG_XLSX)
                ws = wb.active
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "Steps"
                ws.append(["Step", "Status", "Clock Time", "Elapsed (s)", "Note"])
            for r in self.rows:
                ws.append(list(r))
            wb.save(STEPLOG_XLSX)
            return STEPLOG_XLSX
        except Exception:
            import csv
            csv_path = STEPLOG_XLSX.replace(".xlsx", ".csv")
            write_hdr = not os.path.exists(csv_path)
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if write_hdr:
                    w.writerow(["Step", "Status", "Clock Time", "Elapsed (s)", "Note"])
                for r in self.rows:
                    w.writerow(list(r))
            return csv_path

# --------- video helpers ---------
def start_recording(driver):
    try:
        driver.start_recording_screen()
    except Exception as e:
        print(f"[WARN] start_recording_screen failed: {e}")

def stop_and_save_recording(driver, name_prefix="rideshare_run"):
    _ensure_dirs()
    try:
        b64 = driver.stop_recording_screen()
        if not b64:
            return ""
        data = base64.b64decode(b64)
        path = os.path.join(RECORD_DIR, _ts_for_name(name_prefix, "mp4"))
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        print(f"[WARN] stop_recording_screen failed: {e}")
        return ""

# =========================
# Appium helpers
# =========================
def init_driver():
    d = webdriver.Remote(APPIUM_SERVER, options=UiAutomator2Options().load_capabilities(caps))
    try:
        d.update_settings({"waitForIdleTimeout": 0, "ignoreUnimportantViews": True, "waitForSelectorTimeout": 9000})
    except Exception:
        pass
    return d

def wait_click(wait, by, locator):
    return wait.until(EC.element_to_be_clickable((by, locator)))

# W3C tap (no TouchAction, no mobile:shell)
def tap_point(driver, x, y):
    finger = PointerInput("touch", "finger")
    actions = ActionBuilder(driver)
    actions.add_action(finger.create_pointer_move(0, 'viewport', int(x), int(y)))
    actions.add_action(finger.create_pointer_down(0))
    actions.add_action(finger.create_pointer_up(0))
    actions.perform()

def tap_ratio(driver, rx, ry):
    size = driver.get_window_size()
    tap_point(driver, rx * size["width"], ry * size["height"])

# ===== Review skip (kept exactly as before) =====
def skip_review_if_present(driver, overall_timeout=6):
    end = time.time() + overall_timeout
    while time.time() < end:
        clicked = False
        for by, loc in [
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("Skip")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("Skip")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().descriptionContains("Skip")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("এড়িয়ে যান")'),
            (AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().textContains("এড়িয়ে")'),
        ]:
            try:
                els = driver.find_elements(by, loc)
                if els:
                    els[0].click()
                    clicked = True
                    break
            except WebDriverException:
                pass
        if clicked:
            time.sleep(0.3)
            return
        try:
            tap_ratio(driver, 0.89, 0.148)   # fallback position
            time.sleep(0.3)
            return
        except Exception:
            pass
        time.sleep(0.2)

def click_confirm_with_retry(driver, total_timeout=35, poll=0.6):
    end = time.time() + total_timeout
    last_err = None
    while time.time() < end:
        try:
            el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((AppiumBy.XPATH, XPATH_CONFIRM)))
            el.click()
            return True
        except (TimeoutException, StaleElementReferenceException, WebDriverException) as e:
            last_err = e
            time.sleep(poll)
    if last_err:
        print(f"Confirm Pickup click failed: {type(last_err).__name__}: {last_err}")
    return False

# =========================
# Main
# =========================
def main():
    logger = StepLogger()
    d = init_driver()
    wait = WebDriverWait(d, 30)

    # start video recording for the whole run
    start_recording(d)
    video_path = ""

    try:
        # 1) Skip review
        skip_review_if_present(d)
        logger.log("Skip Review", "PASS")
        time.sleep(2.0)  # as per your flow: pause before Ride Share

        # 2) Ride Share
        try:
            wait_click(wait, AppiumBy.XPATH, XPATH_RIDE_SHARE).click()
            logger.log("Ride Share", "PASS")
        except TimeoutException:
            logger.log("Ride Share", "WARN", "Ride card not present (maybe already on page)")

        # 3) Type 'mirpur'
        try:
            inp = wait_click(wait, AppiumBy.XPATH, XPATH_DROP_OFF_IN)
        except TimeoutException:
            logger.log("Drop Off Input", "FAIL", "Input not found")
            return

        try:
            inp.click()
            try:
                inp.clear()
            except Exception:
                pass
            inp.send_keys("mirpur")
            logger.log("Type Drop Off", "PASS", "Typed 'mirpur'")
        except WebDriverException as e:
            logger.log("Type Drop Off", "FAIL", f"{e}")
            return

        # 4) Suggestion (try XPath, else ratio tap)
        time.sleep(1.2)
        try:
            wait_click(WebDriverWait(d, 15), AppiumBy.XPATH, XPATH_SUGGESTION).click()
            logger.log("Select Suggestion", "PASS", "Exact XPath")
        except TimeoutException:
            try:
                d.hide_keyboard()
            except Exception:
                pass
            try:
                tap_ratio(d, 0.36, 0.44)  # first row approx
                logger.log("Select Suggestion", "PASS", "Tapped by ratio (0.36,0.44)")
            except Exception:
                logger.log("Select Suggestion", "FAIL", "XPath and ratio both failed")
                return

        # 5) Continue
        try:
            wait_click(WebDriverWait(d, 20), AppiumBy.XPATH, XPATH_CONTINUE).click()
            logger.log("Continue", "PASS")
        except TimeoutException:
            logger.log("Continue", "WARN", "Continue not present (auto-advance?)")

        # 6) Confirm Pickup (after 2s wait, with retries)
        time.sleep(2.0)
        if not click_confirm_with_retry(d, total_timeout=35):
            logger.log("Confirm Pickup", "FAIL", "Button not clickable after retries")
            return
        logger.log("Confirm Pickup", "PASS")

        logger.log("Submission", "PASS", "Flow completed: request submitted.")
        print("✅ Flow completed: request submitted.")

    finally:
        # stop/save video, then quit and write step log
        try:
            video_path = stop_and_save_recording(d, "rideshare_run")
        except Exception:
            video_path = ""
        d.quit()

        # add a final row with video path for traceability
        if video_path:
            logger.log("Video Saved", "INFO", video_path)

        path = logger.write()
        print("🎞️ Video:", os.path.abspath(video_path) if video_path else "(none)")
        print(f"🧾 Step log saved to: {os.path.abspath(path)}")

if __name__ == "__main__":
    main()
