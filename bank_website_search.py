import pandas as pd
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import warnings
import time
import random
import requests
from const import GIGACHAT_TOKEN_CORP
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.edge.service import Service
from urllib.parse import urljoin, urlparse
import os
from datetime import datetime

# Импорты для langchain из langchain_community
from langchain_community.chat_models import GigaChat
from langchain_core.messages import HumanMessage, SystemMessage

# Отключаем предупреждения
warnings.filterwarnings("ignore")


@dataclass
class BenchmarkResult:
    bank: str
    service: str
    service_details: str  # Общие данные об услуге вместо разделенных полей
    source_url: str
    exact_url: str  # Точная ссылка на предложение
    confidence: float
    is_best_practice: bool
    comparison_with_sber: str


class BankBenchmarkAgent:
    def __init__(self, gigachat_token: str):
        # Обновляем словарь банков с конкретными URL для парсинга
        self.banks = {
            'alfabank': {
                'url': 'https://alfabank.ru/',
                'specific_urls': [
                    'https://alfabank.ru/everyday/debit-cards/',
                    'https://alfabank.ru/get-money/credit-cards/',
                    'https://alfabank.ru/make-money/deposits/',
                    'https://alfabank.ru/make-money/savings-account/',
                    'https://alfabank.ru/get-money/',
                    'https://alfabank.ru/get-money/mortgage/',
                    'https://alfabank.ru/make-money/investments/',
                    'https://alfabank.ru/everyday/smart/'
                ]
            },
            'tbank': {
                'url': 'https://tbank.ru/',
                'specific_urls': [
                    'https://www.tbank.ru/cards/debit-cards/',
                    'https://www.tbank.ru/cards/credit-cards/',
                    'https://www.tbank.ru/loans/',
                    'https://www.tbank.ru/cards/debit-cards/tinkoff-black/pension/',
                    'https://www.tbank.ru/savings/deposit/',
                    'https://www.tbank.ru/savings/saving-account/',
                    'https://www.tbank.ru/pro/',
                    'https://www.tbank.ru/cards/debit-cards/tinkoff-black/selfemployed/',
                    'https://www.tbank.ru/invest/account/'
                ]
            },
            'vtb': {
                'url': 'https://vtb.ru/',
                'specific_urls': [
                    'https://www.vtb.ru/personal/kredit/',
                    'https://www.vtb.ru/personal/ipoteka/',
                    'https://www.vtb.ru/personal/avtokredity/',
                    'https://www.vtb.ru/personal/vklady-i-scheta/',
                    'https://www.vtb.ru/personal/investicii/',
                    'https://www.vtb.ru/personal/platezhi/',
                    'https://www.vtb.ru/personal/pensioneram/'
                ]
            },
            'tochka': {
                'url': 'https://tochka.com/',
                'specific_urls': [
                    'https://tochka.com/rko/plus/',
                    'https://tochka.com/account-opening/',
                    'https://tochka.com/tariffs/',
                    'https://tochka.com/payment-card/'
                ]
            },
            'gazprombank': {
                'url': 'https://gazprombank.ru/',
                'specific_urls': [
                    'https://www.gazprombank.ru/personal/cards/',
                    'https://www.gazprombank.ru/personal/credit-cards/',
                    'https://www.gazprombank.ru/personal/accounts/',
                    'https://www.gazprombank.ru/personal/increase/deposits/',
                    'https://www.gazprombank.ru/personal/take_credit/consumer_credit/',
                    'https://www.gazprombank.ru/premium/',
                    'https://www.gazprombank.ru/personal/page/increase/investment/',
                    'https://www.gazprombank.ru/personal/avtokredit/',
                    'https://www.gazprombank.ru/personal/mortgage/'
                ]
            },
            'rshb': {
                'url': 'https://rshb.ru/',
                'specific_urls': [
                    'https://www.rshb.ru/natural/creditcards',
                    'https://www.rshb.ru/natural/debetcards',
                    'https://www.rshb.ru/natural/loans',
                    'https://www.rshb.ru/natural/deposits',
                    'https://www.rshb.ru/natural/mortgage',
                    'https://www.rshb.ru/natural/packages',
                    'https://www.rshb.ru/natural/investments'
                ]
            },
            'domrf': {
                'url': 'https://domrfbank.ru/',
                'specific_urls': [
                    'https://domrfbank.ru/mortgage/?from=menu&type=link&product=mortgage',
                    'https://domrfbank.ru/deposits/?from=menu&type=link&product=deposit',
                    'https://domrfbank.ru/deposits/savings-account/?from=menu&type=link&product=savings.account',
                    'https://domrfbank.ru/loans/?from=menu&type=link&product=credit',
                    'https://domrfbank.ru/premium/?from=menu&type=link&product=premium',
                    'https://domrfbank.ru/cards/?from=menu&type=link&product=card',
                    'https://domrfbank.ru/escrow/?from=menu&type=link&product=escrow'
                ]
            },
            'sberbank': {
                'url': 'https://www.sberbank.ru/',
                'specific_urls': [
                    'https://www.sberbank.com/ru/person/credits/money',
                    'https://www.sberbank.ru/ru/person/credits/homenew',
                    'https://www.sberbank.ru/ru/person/bank_cards/debit',
                    'https://www.sberbank.ru/ru/person/bank_cards/credit_cards',
                    'https://www.sberbank.ru/ru/person/contributions/deposits',
                    'https://www.sberbank.ru/ru/person/investments',
                    'https://www.sberbank.ru/ru/person/sb_premier_new'
                ]
            }
        }

        self.gigachat_token = gigachat_token
        self.llm = self._init_gigachat()
        self.driver = self._init_selenium_driver()
        self.all_bank_data = {}  # Для хранения данных всех банков
        self.raw_data_storage = {}  # Для хранения сырых данных парсинга
        self.product_links_storage = {}
        self.parsing_results_dir = "parsing_results"
        self.target_service = ""  # Целевая услуга для анализа

    def _init_gigachat(self):
        """Инициализация GigaChat через langchain"""
        try:
            llm = GigaChat(
                credentials=self.gigachat_token,
                verify_ssl_certs=False,
                scope="GIGACHAT_API_B2B",
                model="GigaChat-2-Max",
                temperature=0.1,
                timeout=120,
                verbose=False
            )
            return llm

        except Exception as e:
            print(f"❌ Ошибка инициализации GigaChat: {e}")
            return None

    def _init_selenium_driver(self):
        """Инициализация Selenium WebDriver с обходом проблем сети"""
        try:
            edge_options = EdgeOptions()

            # Базовые настройки
            edge_options.add_argument('--no-sandbox')
            edge_options.add_argument('--disable-dev-shm-usage')
            edge_options.add_argument('--disable-gpu')
            edge_options.add_argument('--window-size=1920,1080')

            # Реалистичный User-Agent
            edge_options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            edge_options.add_argument('--accept-language=ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7')

            # Настройки для обхода детекта
            edge_options.add_argument('--disable-blink-features=AutomationControlled')
            edge_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            edge_options.add_experimental_option('useAutomationExtension', False)

            # Игнорируем ошибки сертификатов
            edge_options.add_argument('--ignore-certificate-errors')
            edge_options.add_argument('--ignore-ssl-errors')

            # Отключаем прокси
            edge_options.add_argument('--no-proxy-server')

            # Пробуем разные методы инициализации

            # Метод 1: Простая инициализация без менеджера
            try:
                print("🔄 Попытка 1: Простая инициализация...")
                driver = webdriver.Edge(options=edge_options)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)

                # Убираем навигационные свойства WebDriver
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                print("✅ Драйвер инициализирован через простой метод")
                return driver
            except Exception as e:
                print(f"❌ Метод 1 не сработал: {e}")

            # Метод 2: Пробуем с service но без менеджера
            try:
                print("🔄 Попытка 2: Инициализация с Service...")
                service = Service()
                driver = webdriver.Edge(service=service, options=edge_options)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)

                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                print("✅ Драйвер инициализирован через Service")
                return driver
            except Exception as e:
                print(f"❌ Метод 2 не сработал: {e}")

            # Метод 3: Пробуем с менеджером (последняя попытка)
            try:
                print("🔄 Попытка 3: Используем менеджер драйверов...")
                service = Service(EdgeChromiumDriverManager().install())
                driver = webdriver.Edge(service=service, options=edge_options)
                driver.set_page_load_timeout(30)
                driver.implicitly_wait(10)

                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                print("✅ Драйver инициализирован через менеджер")
                return driver
            except Exception as e:
                print(f"❌ Метод 3 не сработал: {e}")

            raise Exception("Все методы инициализации не сработали")

        except Exception as e:
            print(f"❌ Критическая ошибка инициализации Selenium Edge: {e}")
            return None

    def _create_results_directory(self):
        """Создание директории для сохранения результатов"""
        if not os.path.exists(self.parsing_results_dir):
            os.makedirs(self.parsing_results_dir)
            print(f"📁 Создана директория для результатов: {self.parsing_results_dir}")

    def save_parsing_data_to_txt(self, service_name: str = "general"):
        """Сохранение сырых данных парсинга в TXT файлы"""
        self._create_results_directory()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{self.parsing_results_dir}/parsing_data_{service_name}_{timestamp}"

        # Сохраняем общую информацию о парсинге
        summary_file = f"{base_filename}_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"ОТЧЕТ О ПАРСИНГЕ БАНКОВСКИХ ДАННЫХ\n")
            f.write(f"Услуга: {service_name}\n")
            f.write(f"Время парсинга: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"=" * 80 + "\n\n")

            f.write("СТАТУС ПАРСИНГА ПО БАНКАМ:\n")
            for bank_name in self.banks.keys():
                status = "✅ УСПЕШНО" if bank_name in self.all_bank_data else "❌ НЕ УДАЛОСЬ"
                f.write(f"{bank_name.upper():<15}: {status}\n")

            f.write(f"\nВСЕГО ОБРАБОТАНО БАНКОВ: {len(self.all_bank_data)}/{len(self.banks)}\n")

        print(f"📄 Сохранен общий отчет: {summary_file}")

        # Сохраняем детальные данные по каждому банку
        for bank_name, bank_data in self.all_bank_data.items():
            bank_file = f"{base_filename}_{bank_name}.txt"
            with open(bank_file, 'w', encoding='utf-8') as f:
                f.write(f"ДАННЫЕ ПАРСИНГА: {bank_name.upper()}\n")
                f.write(f"URL: {bank_data['url']}\n")
                f.write(f"Время: {bank_data['timestamp']}\n")
                f.write(f"Заголовок: {bank_data['title']}\n")
                f.write(f"Длина контента: {bank_data['content_length']} символов\n")
                f.write(f"=" * 80 + "\n\n")

                f.write("ОЧИЩЕННЫЙ ТЕКСТ:\n")
                f.write(
                    bank_data['content'][:5000] + "..." if len(bank_data['content']) > 5000 else bank_data['content'])
                f.write("\n\n" + "=" * 80 + "\n\n")

                f.write("НАЙДЕННЫЕ ССЫЛКИ НА ПРОДУКТЫ:\n")
                for i, link in enumerate(bank_data.get('product_links', [])[:20], 1):
                    f.write(f"{i}. [{link['type']}] {link['text']}\n")
                    f.write(f"   URL: {link['url']}\n\n")

                if len(bank_data.get('product_links', [])) > 20:
                    f.write(f"... и еще {len(bank_data['product_links']) - 20} ссылок\n")

            print(f"📄 Сохранены данные {bank_name}: {bank_file}")

        # Сохраняем сырые HTML данные (первые 5000 символов)
        raw_html_file = f"{base_filename}_raw_html.txt"
        with open(raw_html_file, 'w', encoding='utf-8') as f:
            f.write("СЫРЫЕ HTML ДАННЫЕ (ПЕРВЫЕ 5000 СИМВОЛОВ)\n")
            f.write("=" * 80 + "\n\n")

            for bank_name, raw_data in self.raw_data_storage.items():
                f.write(f"{bank_name.upper()}:\n")
                f.write(f"URL: {raw_data['url']}\n")
                f.write("-" * 50 + "\n")
                f.write(raw_data['page_source'] + "\n\n")
                f.write("=" * 80 + "\n\n")

        print(f"📄 Сохранены сырые HTML данные: {raw_html_file}")
        print(f"✅ Все данные парсинга сохранены в папку '{self.parsing_results_dir}'")

    def fetch_all_banks_data(self):
        """Сбор данных со всех банков через Selenium"""
        print("📥 Собираем данные со всех банков через Selenium...")

        for bank_name, bank_info in self.banks.items():
            print(f"🛠️ Парсим {bank_name}...")

            # Для каждого банка используем специальную функцию парсинга
            if bank_name == 'sovcombank':
                bank_data = self._fetch_bank_data_with_urls(bank_name, bank_info)
            elif bank_name == 'sberbank':
                bank_data = self._fetch_bank_data_with_urls(bank_name, bank_info)
            else:
                # Общий метод для всех банков с использованием specific_urls
                bank_data = self._fetch_bank_data_with_urls(bank_name, bank_info)

            if bank_data:
                self.all_bank_data[bank_name] = bank_data
                print(f"✅ Данные {bank_name} получены")
            else:
                print(f"❌ Не удалось получить данные для {bank_name}")

    def _fetch_bank_data_with_urls(self, bank_name: str, bank_info: Dict) -> Optional[Dict[str, Any]]:
        """Функция парсинга банка с использованием multiple URLs через Selenium"""
        try:
            print(f"🌐 Парсим {bank_name} с использованием специальных URL...")

            all_content = ""
            all_product_links = []

            # Парсим каждый специальный URL через Selenium
            for url in bank_info['specific_urls']:
                print(f"   📍 Парсим: {url}")
                try:
                    # Используем Selenium для парсинга
                    self.driver.get(url)
                    time.sleep(3)  # Ждем загрузки страницы

                    # Имитируем человеческое поведение
                    self._simulate_human_behavior()

                    # Получаем содержимое страницы
                    page_content = self.driver.page_source
                    page_data = self._process_page_content(page_content, bank_name, url)

                    if page_data:
                        all_content += " " + page_data['content']
                        all_product_links.extend(page_data.get('product_links', []))
                        time.sleep(2)  # Задержка между запросами

                except Exception as e:
                    print(f"   ⚠️ Ошибка при парсинге {url}: {e}")
                    continue

            # Если не удалось получить данные через Selenium, пробуем requests
            if not all_content:
                print("   🔄 Пробуем requests как fallback...")
                for url in bank_info['specific_urls']:
                    try:
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
                        }
                        response = requests.get(url, headers=headers, timeout=15, verify=False)
                        if response.status_code == 200:
                            page_data = self._process_page_content(response.text, bank_name, url)
                            if page_data:
                                all_content += " " + page_data['content']
                                all_product_links.extend(page_data.get('product_links', []))
                                time.sleep(1)
                    except Exception as e:
                        print(f"   ⚠️ Ошибка при fallback парсинге {url}: {e}")
                        continue

            if all_content:
                return {
                    'bank': bank_name,
                    'url': bank_info['url'],
                    'content': all_content[:10000],  # Ограничиваем длину
                    'title': f'{bank_name.capitalize()} - Multiple Pages',
                    'description': f'Данные собраны с нескольких страниц {bank_name}',
                    'timestamp': pd.Timestamp.now(),
                    'content_length': len(all_content),
                    'product_links': all_product_links
                }

            return None

        except Exception as e:
            print(f"❌ Ошибка при парсинге {bank_name}: {e}")
            return None

    def _simulate_human_behavior(self):
        """Имитация человеческого поведения на странице - безопасная версия"""
        try:
            # Случайная прокрутка - самый безопасный метод
            scroll_actions = [
                (0, 300), (0, 600), (0, 400), (0, 200), (0, 800)
            ]

            for x, y in scroll_actions:
                try:
                    self.driver.execute_script(f"window.scrollBy({x}, {y});")
                    time.sleep(random.uniform(0.3, 0.7))
                except:
                    pass

            # Клик по случайному элементу (если есть)
            try:
                clickable_elements = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a, button, [onclick], [role='button']"
                )
                if clickable_elements:
                    random_element = random.choice(clickable_elements[:5])  # Берем из первых 5
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth'});", random_element)
                    time.sleep(0.5)
            except:
                pass

        except Exception as e:
            print(f"⚠️  Ошибка при имитации поведения: {e}")
            # Игнорируем ошибки имитации, чтобы не прерывать основной процесс

    def _process_page_content(self, page_content: str, bank_name: str, url: str) -> Dict[str, Any]:
        """Обработка содержимого страницы"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_content, 'html.parser')

        self.raw_data_storage[bank_name] = {
            'url': url,
            'page_source': page_content[:5000] + "..." if len(page_content) > 5000 else page_content,
            'title': str(soup.find('title')),
            'timestamp': pd.Timestamp.now()
        }

        product_links = self._find_product_links(soup, url, bank_name)
        self.product_links_storage[bank_name] = product_links

        # Улучшенная очистка контента
        for element in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "form", "button"]):
            element.decompose()

        # Получаем заголовок
        title = soup.find('title')
        title_text = title.get_text().strip() if title else ""

        # Получаем основной контент - ищем основные текстовые блоки
        main_content = ""

        # Пробуем найти основные текстовые блоки
        content_selectors = [
            'main', 'article', 'section', '.content', '.main-content',
            '.text-block', '.product-description', '.bank-product',
            '.product-info', '.offer', '.tariff', '.condition'
        ]

        for selector in content_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(separator=' ', strip=True)
                if len(text) > 100:  # Только значимые блоки
                    main_content += " " + text

        # Если не нашли структурированный контент, берем весь текст
        if not main_content:
            text = soup.get_text(separator=' ', strip=True)
            # Убираем лишние пробелы и переносы
            text = re.sub(r'\s+', ' ', text)
            main_content = text

        # Объединяем с заголовком и ограничиваем длину
        full_content = f"{title_text} {main_content}"
        full_content = re.sub(r'\s+', ' ', full_content).strip()[:8000]

        return {
            'bank': bank_name,
            'url': url,
            'content': full_content,
            'title': title_text,
            'description': "",
            'timestamp': pd.Timestamp.now(),
            'content_length': len(full_content),
            'product_links': product_links
        }

    def _find_product_links(self, soup, base_url: str, bank_name: str) -> List[Dict]:
        """Поиск ссылок на банковские продукты с улучшенной обработкой"""
        product_links = []
        product_keywords = {
            'credit': ['кредит', 'займ', 'ссуд', 'credit', 'loan', 'рассрочк'],
            'deposit': ['вклад', 'депозит', 'сбережен', 'deposit', 'savings', 'накопит'],
            'card': ['карт', 'card', 'дебетов', 'кредитн', 'visa', 'mastercard', 'платежн'],
            'mortgage': ['ипотек', 'mortgage', 'недвиж', 'жиль', 'квартир'],
            'investment': ['инвест', 'вложен', 'акци', 'облигац', 'investment', 'фонд'],
            'insurance': ['страхов', 'insurance', 'защит'],
            'account': ['счет', 'account', 'расчетн', 'текущ']
        }

        # Ищем все ссылки
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            link_text = link.get_text(strip=True).lower()

            # Пропускаем нерелевантные ссылки
            if any(x in href for x in ['javascript:', '#', 'mailto:', 'tel:', 'void(0)']):
                continue

            # Пропускаем социальные сети и служебные ссылки
            social_keywords = ['facebook', 'twitter', 'instagram', 'vk.com', 'youtube',
                               'linkedin', 'telegram', 'whatsapp', 'viber']
            if any(social in href for social in social_keywords):
                continue

            # Пропускаем ссылки на политики и соглашения
            policy_keywords = ['policy', 'agreement', 'terms', 'condition', 'правил', 'соглашен']
            if any(keyword in href or keyword in link_text for keyword in policy_keywords):
                continue

            # Определяем тип продукта
            product_type = None
            for p_type, keywords in product_keywords.items():
                if any(keyword in href or keyword in link_text for keyword in keywords):
                    product_type = p_type
                    break

            # Если тип не определен, но ссылка выглядит как продуктовая
            if not product_type and self._looks_like_product_link(href, link_text):
                product_type = 'other'

            if product_type:
                try:
                    absolute_url = urljoin(base_url, link['href'])
                    if urlparse(absolute_url).netloc:
                        product_links.append({
                            'url': absolute_url,
                            'text': link.get_text(strip=True),
                            'type': product_type
                        })
                except:
                    continue

        return product_links

    def _looks_like_product_link(self, href: str, link_text: str) -> bool:
        """Проверяет, похожа ли ссылка на продуктовую"""
        # Исключаем служебные пути
        exclude_paths = ['/about', '/contact', '/news', '/press', '/career', '/job',
                         '/support', '/help', '/login', '/register', '/signin', '/signup']

        if any(path in href for path in exclude_paths):
            return False

        # Исключаем короткий или бессмысленный текст
        if len(link_text) < 3 or link_text in ['читать далее', 'подробнее', 'узнать больше']:
            return False

        # Включаем пути, которые выглядят как продукты
        product_paths = ['/credit', '/deposit', '/card', '/mortgage', '/investment',
                         '/insurance', '/account', '/product', '/service', '/offer',
                         '/tariff', '/condition', '/apply', '/order', '/request']

        return any(path in href for path in product_paths)

    def _find_exact_product_url(self, bank_name: str, service_type: str, product_details: str) -> str:
        """Улучшенный поиск точной ссылки на продукт"""
        if bank_name not in self.product_links_storage:
            return ""

        product_links = self.product_links_storage[bank_name]
        service_type_lower = service_type.lower()
        product_details_lower = product_details.lower()

        # Расширенное сопоставление типов услуг
        type_mapping = {
            'ипотек': 'mortgage', 'ипотечн': 'mortgage', 'жиль': 'mortgage', 'недвиж': 'mortgage',
            'кредит': 'credit', 'займ': 'credit', 'ссуд': 'credit', 'loan': 'credit',
            'вклад': 'deposit', 'депозит': 'deposit', 'сбережен': 'deposit', 'накопит': 'deposit',
            'карт': 'card', 'card': 'card', 'дебетов': 'card', 'visa': 'card', 'mastercard': 'card',
            'инвест': 'investment', 'брокер': 'investment', 'акци': 'investment', 'облигац': 'investment',
            'страхов': 'insurance', 'insurance': 'insurance', 'защит': 'insurance',
            'счет': 'account', 'account': 'account', 'рко': 'account', 'расчетн': 'account'
        }

        target_type = None
        for rus_type, eng_type in type_mapping.items():
            if rus_type in service_type_lower:
                target_type = eng_type
                break

        best_match = ""
        best_score = 0

        for link_info in product_links:
            current_score = 0
            link_text = link_info['text'].lower()
            link_url = link_info['url'].lower()

            # Совпадение по типу
            if target_type and link_info['type'] == target_type:
                current_score += 3

            # Ключевые слова из названия услуги
            service_keywords = service_type_lower.split()
            for keyword in service_keywords:
                if len(keyword) > 3 and (keyword in link_text or keyword in link_url):
                    current_score += 2

            # Ключевые слова из описания
            description_keywords = product_details_lower.split()[:8]
            for keyword in description_keywords:
                if len(keyword) > 3 and (keyword in link_text or keyword in link_url):
                    current_score += 1

            # Дополнительные критерии
            if 'оформить' in link_text or 'подробнее' in link_text or 'условия' in link_text:
                current_score += 1
            if 'оформить' in link_url or 'заявк' in link_url:
                current_score += 2

            if current_score > best_score:
                best_score = current_score
                best_match = link_info['url']

        return best_match if best_score >= 3 else ""  # Повышаем порог

    def show_parsed_data(self):
        """Показать полученные данные после парсинга"""
        print("\n" + "=" * 80)
        print("📊 ПРОСМОТР ПОЛУЧЕННЫХ ДАННЫХ")
        print("=" * 80)
        if not self.all_bank_data:
            print("❌ Данные еще не собраны!")
            return

        for bank_name, data in self.all_bank_data.items():
            print(f"\n🏦 {bank_name.upper()}:")
            print(f"   URL: {data['url']}")
            print(f"   Заголовок: {data['title']}")
            print(f"   Длина контента: {data['content_length']} символов")
            print(f"   Найдено ссылок на продукты: {len(data.get('product_links', []))}")

            # Показываем первые 5 ссылок для примера
            for i, link in enumerate(data.get('product_links', [])[:5], 1):
                print(f"   {i}. [{link['type']}] {link['text']} -> {link['url']}")

    def analyze_bank_service_with_llm(self, bank_name: str, bank_data: Dict, target_service: str) -> List[
        BenchmarkResult]:
        """Анализ конкретного банка с помощью LLM для целевой услуги"""
        if not self.llm:
            print(f"❌ GigaChat не инициализирован для банка {bank_name}")
            return []

        try:
            # Очищаем текст от специальных символов
            clean_content = re.sub(r'[<>{}[\]\\]', '', bank_data['content'])

            # Создаем промпт для конкретной услуги
            prompt_text = f"""Проанализируй предоставленный текст банка {bank_name} и найди информацию о предложениях по услуге: {target_service}.

            Текст содержит описания различных предложений банка. Найди упоминания услуги "{target_service}", ее условий, характеристик и тарифов.

            Верни в формате JSON список найденных предложений:
            - bank: название банка
            - service: категория предложения (должна соответствовать или быть связана с "{target_service}")
            - service_details: детальная информация об услуге (условия, параметры, характеристики, тарифы)
            - product_description: краткое описание предложения

            Если услуга "{target_service}" не найдена, верни пустой список.

            Текст для анализа:{clean_content[:15000]}"""

            messages = [
                SystemMessage(
                    content="Ты анализируешь текстовые данные банков и извлекаешь структурированную информацию о конкретных услугах."),
                HumanMessage(content=prompt_text)
            ]

            print(f"📤 Отправляем запрос к GigaChat для банка {bank_name}...")
            response = self.llm.invoke(messages, timeout=60)
            result_text = response.content

            # Проверяем на блокировку
            if "blacklist" in result_text.lower() or "Giga generation stopped" in result_text:
                print(f"⚠️  Обнаружена блокировка запроса для банка {bank_name}")
                return []

            # Обработка JSON ответа
            try:
                # Очищаем ответ
                clean_text = result_text.strip()
                clean_text = re.sub(r'^```json|```$', '', clean_text, flags=re.IGNORECASE)
                clean_text = clean_text.strip()

                # Парсим JSON
                data = json.loads(clean_text)

                # Обрабатываем разные форматы ответа
                if isinstance(data, dict):
                    services = data.get('services', [])
                elif isinstance(data, list):
                    services = data
                else:
                    print(f"❌ Неожиданный формат ответа для банка {bank_name}: {type(data)}")
                    services = []

                results = []
                for item in services:
                    if isinstance(item, dict):
                        # Формируем общие данные об услуге
                        service_details = item.get('service_details', '')
                        product_description = item.get('product_description', '')

                        # Объединяем всю информацию в одно поле
                        full_service_info = f"{service_details}"
                        if product_description:
                            full_service_info += f" {product_description}"

                        results.append(BenchmarkResult(
                            bank=bank_name,
                            service=item.get('service', ''),
                            service_details=full_service_info.strip(),
                            source_url=bank_data['url'],
                            exact_url=self._find_exact_product_url(bank_name, item.get('service', ''),
                                                                   full_service_info),
                            confidence=0.9,
                            is_best_practice=False,
                            comparison_with_sber=""
                        ))

                print(f"✅ Для банка {bank_name} извлечено {len(results)} записей")
                return results

            except json.JSONDecodeError as e:
                print(f"❌ Ошибка парсинга JSON для банка {bank_name}: {e}")
                print(f"Ответ: {result_text[:500]}...")
                return []

        except Exception as e:
            print(f"❌ Ошибка анализа для банка {bank_name}: {e}")
            return []

    def analyze_all_banks_service(self, target_service: str) -> List[BenchmarkResult]:
        """Анализ целевой услуги для всех банков с отдельными запросами к LLM"""
        all_benchmarks = []

        print(f"🔍 Анализируем услугу '{target_service}' для всех банков...")

        for bank_name, bank_data in self.all_bank_data.items():
            print(f"\n🏦 Анализируем банк: {bank_name}")

            # Для каждого банка делаем отдельный запрос к LLM
            bank_benchmarks = self.analyze_bank_service_with_llm(bank_name, bank_data, target_service)

            if bank_benchmarks:
                all_benchmarks.extend(bank_benchmarks)
                print(f"✅ Для банка {bank_name} найдено {len(bank_benchmarks)} предложений")
            else:
                print(f"⚠️  Для банка {bank_name} не найдено предложений по услуге '{target_service}'")

            # Задержка между запросами к разным банкам
            time.sleep(2)

        return all_benchmarks

    def compare_benchmarks(self, benchmarks: List[BenchmarkResult]) -> pd.DataFrame:
        """Сравнение бенчмарков между банками"""
        if not benchmarks:
            return pd.DataFrame()

        data = []
        for b in benchmarks:
            data.append({
                'Банк': b.bank,
                'Услуга': b.service,
                'Данные об услуге': b.service_details,  # Единое поле с данными
                'Точная ссылка': b.exact_url if b.exact_url else "❌ Не найдена",
                'Доверие': b.confidence,
                'Источник': b.source_url
            })

        return pd.DataFrame(data)

    def generate_excel_report(self, df: pd.DataFrame, service_name: str) -> str:
        """Генерация Excel отчета с использованием стандартного движка"""
        if df.empty:
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_report_{service_name.replace(' ', '_')}_{timestamp}.xlsx"

        try:
            # Используем стандартный Excel writer без openpyxl
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                # Основной лист с данными
                df.to_excel(writer, sheet_name='Данные', index=False)

                # Лист с суммарной статистикой
                summary_data = {
                    'Метрика': ['Всего записей', 'Уникальных банков', 'Услуга', 'Дата анализа'],
                    'Значение': [len(df), df['Банк'].nunique(), service_name,
                                 datetime.now().strftime('%Y-%m-%d %H:%M')]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Статистика', index=False)

                # Получаем workbook и worksheet для форматирования
                workbook = writer.book
                worksheet_data = writer.sheets['Данные']
                worksheet_stats = writer.sheets['Статистика']

                # Форматирование для листа с данными
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BC',
                    'border': 1
                })

                # Применяем форматирование к заголовкам
                for col_num, value in enumerate(df.columns.values):
                    worksheet_data.write(0, col_num, value, header_format)

                # Автоподбор ширины столбцов
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2
                    worksheet_data.set_column(i, i, min(max_len, 50))

                # Особенно широкий столбец для данных об услуге
                worksheet_data.set_column(2, 2, 60)  # Столбец "Данные об услуге"

                # Форматирование для листа статистики
                for i, col in enumerate(summary_df.columns):
                    max_len = max(
                        summary_df[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2
                    worksheet_stats.set_column(i, i, min(max_len, 30))

            print(f"✅ Excel отчет сохранен: {filename}")
            return filename

        except ImportError:
            # Если xlsxwriter тоже не доступен, используем CSV
            print("⚠️  xlsxwriter не установлен, сохраняем в CSV")
            csv_filename = f"benchmark_report_{service_name.replace(' ', '_')}_{timestamp}.csv"
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            return csv_filename

        except Exception as e:
            print(f"❌ Ошибка при создании Excel отчета: {e}")
            # Fallback to CSV
            csv_filename = f"benchmark_report_{service_name.replace(' ', '_')}_{timestamp}.csv"
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            return csv_filename

    def run_analysis(self, service_name: str) -> str:
        """Основной метод запуска анализа"""
        print(f"🚀 Запуск анализа услуги '{service_name}' для всех банков")
        self.target_service = service_name

        # Собираем данные всех банков
        self.fetch_all_banks_data()
        self.save_parsing_data_to_txt(service_name)
        self.show_parsed_data()

        # Анализируем целевую услугу для каждого банка отдельно
        all_benchmarks = self.analyze_all_banks_service(service_name)

        if not all_benchmarks:
            print("❌ Не удалось извлечь данные о продуктах")
            return ""

        # Создаем DataFrame и Excel отчет
        df = self.compare_benchmarks(all_benchmarks)
        excel_file = self.generate_excel_report(df, service_name)

        if excel_file:
            print(f"📊 Отчет сохранен в файл: {excel_file}")

            # Показываем статистику
            print(f"\n📈 Статистика анализа:")
            print(f"   Всего записей: {len(df)}")
            print(f"   Уникальных банков: {df['Банк'].nunique()}")
            print(f"   Уникальных услуг: {df['Услуга'].nunique()}")
            print(
                f"   Услуги в отчете: {', '.join(df['Услуга'].unique()[:5])}{'...' if len(df['Услуга'].unique()) > 5 else ''}")

            return excel_file
        else:
            return "❌ Не удалось создать отчет"

    def get_user_input(self) -> str:
        """Функция для ввода услуги пользователем"""
        print("🎯 Введите банковскую услугу для анализа:")
        print("Примеры: 'ипотека', 'кредит наличными', 'вклады', 'дебетовые карты', 'инвестиции'")
        print("=" * 50)

        service_name = input("Услуга: ").strip().lower()
        while not service_name:
            print("❌ Пожалуйста, введите название услуги!")
            service_name = input("Услуга: ").strip().lower()

        return service_name

    def close_driver(self):
        """Закрытие драйвера при завершении"""
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
            print("✅ Edge драйвер закрыт")

    def __del__(self):
        self.close_driver()


def main():
    GIGACHAT_TOKEN = GIGACHAT_TOKEN_CORP
    agent = BankBenchmarkAgent(GIGACHAT_TOKEN)

    try:
        service_name = agent.get_user_input()
        report_file = agent.run_analysis(service_name)

        print("\n" + "=" * 80)
        print("📋 РЕЗУЛЬТАТЫ АНАЛИЗА:")
        print("=" * 80)
        print(f"Отчет сохранен в файл: {report_file}")

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
    finally:
        agent.close_driver()


if __name__ == "__main__":
    main()