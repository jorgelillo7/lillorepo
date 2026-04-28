import csv
import json
import os
import re
import shutil
import tempfile
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.utils import get_logger
from packages.biwenger_tools.teams_analyzer import config
from packages.biwenger_tools.teams_analyzer.logic.player_matching import normalize_name

logger = get_logger(__name__)

# Solo importa WebDriverManager si estamos en local
RUNNING_IN_DOCKER = os.path.exists("/.dockerenv")
if not RUNNING_IN_DOCKER:
    from webdriver_manager.chrome import ChromeDriverManager


def fetch_jp_player_tips():
    logger.info("Fetching Jornada Perfecta recommendations...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(config.JORNADA_PERFECTA_MERCADO_URL, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", string=re.compile(r"\s*const marketCaching=\["))
    if not script_tag:
        raise Exception(
            "No se pudo encontrar el script 'marketCaching' en la página de Jornada Perfecta."
        )
    json_str = re.search(
        r"const marketCaching=(\[.*\]);", script_tag.string, re.DOTALL
    ).group(1)
    jp_data = json.loads(json_str)
    jp_tips_map = {
        normalize_name(player.get("name", "")): player.get("tip", "N/A")
        for player in jp_data
    }
    logger.info("Jornada Perfecta database built.", extra={"count": len(jp_tips_map)})
    return jp_tips_map


def create_chrome_driver():
    """Initializes headless Chromium with options for Docker ARM64 and local."""
    temp_dir = tempfile.mkdtemp()
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"--user-data-dir={temp_dir}")
    chrome_options.add_argument("--remote-allow-origins=*")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        if RUNNING_IN_DOCKER:
            chrome_options.binary_location = "/usr/bin/chromium"
            driver = webdriver.Chrome(
                service=Service("/usr/bin/chromedriver"), options=chrome_options
            )
        else:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=chrome_options
            )
        driver.get("about:blank")
        return driver
    except Exception as e:
        if driver:
            driver.quit()
        raise Exception(f"No se pudo iniciar Chrome/Chromium: {e}") from e
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def fetch_analitica_fantasy_coeffs():
    """Downloads player coefficients from Analítica Fantasy via Selenium."""
    logger.info("Fetching Analítica Fantasy coefficients...")
    driver = None
    coeffs_map = {}

    try:
        driver = create_chrome_driver()
        driver.get(config.ANALITICA_FANTASY_URL)
        wait = WebDriverWait(driver, 60)

        try:
            cookie_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'ACEPTO')]"))
            )
            driver.execute_script("arguments[0].click();", cookie_button)
            logger.info("Cookie popup accepted.")
            time.sleep(2)
        except TimeoutException:
            logger.warning("Cookie button not found — continuing.")

        logger.info("Waiting for data table...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr.MuiTableRow-root")))
        logger.info("Data table loaded.")

        try:
            logger.info("Configuring 50-player page size...")
            pagination_container = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.MuiTableContainer-root + div")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", pagination_container
            )
            time.sleep(1)

            page_size_dropdown_xpath = (
                "//label[text()='Elementos por página']/following-sibling::div/div[@role='combobox']"
            )
            page_size_dropdown = wait.until(
                EC.element_to_be_clickable((By.XPATH, page_size_dropdown_xpath))
            )
            ActionChains(driver).move_to_element(page_size_dropdown).click().perform()

            option_50 = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//ul[@role='listbox']/li[@data-value='50']"))
            )
            option_50.click()
            logger.info("Page size set to 50.")
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)
        except Exception:
            logger.warning("Could not set page size to 50 — using default pagination.", exc_info=True)

        page_number = 1
        while True:
            logger.info("Scraping page.", extra={"page": page_number})
            player_rows = driver.find_elements(By.CSS_SELECTOR, "tr.MuiTableRow-root")
            if not player_rows:
                logger.info("No more player rows found.")
                break

            for row in player_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) > 6:
                        player_name = (
                            cells[1]
                            .find_element(By.CSS_SELECTOR, "p.MuiTypography-root")
                            .text.strip()
                        )
                        coefficient = (
                            cells[2]
                            .find_element(By.CSS_SELECTOR, "p.MuiTypography-root")
                            .text.strip()
                        )
                        expected_score = cells[6].text.strip().replace("\n", " / ")
                        if player_name and coefficient:
                            coeffs_map[normalize_name(player_name)] = {
                                "coeficiente": coefficient,
                                "puntuacion_esperada": expected_score,
                            }
                except (NoSuchElementException, IndexError):
                    continue

            try:
                next_button = driver.find_element(By.XPATH, "//button[contains(., 'Siguiente')]")
                if not next_button.is_enabled():
                    logger.info("Next button disabled — scraping complete.")
                    break
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", next_button)
                page_number += 1
                time.sleep(3)
            except NoSuchElementException:
                logger.info("Next button not found — scraping complete.")
                break
    except Exception:
        logger.exception("Error during Analítica Fantasy scraping.")
    finally:
        if driver:
            driver.quit()

    if coeffs_map:
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", config.BACKUP_COEFFS_CSV
        )
        try:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["nombre_normalizado", "coeficiente", "puntuacion_esperada"])
                for name, data in coeffs_map.items():
                    writer.writerow([name, data["coeficiente"], data["puntuacion_esperada"]])
            logger.info("Backup CSV saved.", extra={"path": output_path})
        except Exception:
            logger.exception("Could not save backup CSV.")

    logger.info("Analítica Fantasy database built.", extra={"count": len(coeffs_map)})
    return coeffs_map
