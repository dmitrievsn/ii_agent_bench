from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import json
import re
import time
from typing import Dict, List, Optional
import urllib.parse


def get_bank_cards(url: str, service_type: str = "Дебетовая карта") -> List[Dict]:
    """
    Получает список всех карт банка с sravni.ru

    Args:
        url: URL страницы с картами банка
        service_type: Тип услуги (например, "Дебетовая карта", "Кредитная карта")

    Returns:
        Список карт с id, name и service_type
    """
    try:
        response = cffi_requests.get(url, impersonate="safari15_5")
        response.raise_for_status()
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        # Ищем JSON данные в скриптах
        scripts = soup.find_all('script')
        cards_data = []

        for script in scripts:
            if not script.string:
                continue

            script_text = script.string

            # Ищем конкретную структуру: "products": {"list": {"offers": {"items": [...]}}}
            if all(keyword in script_text for keyword in ['"products":', '"list":', '"offers":', '"items":']):
                print(f"Найдена структура продуктов для {service_type}!")

                try:
                    # Более аккуратный поиск JSON структуры
                    start_idx = script_text.find('"products":')
                    if start_idx == -1:
                        continue

                    # Находим начало items массива
                    items_start = script_text.find('"items":', start_idx)
                    if items_start == -1:
                        continue

                    # Находим начало массива [
                    array_start = script_text.find('[', items_start)
                    if array_start == -1:
                        continue

                    # Находим конец массива ]
                    bracket_count = 1
                    current_pos = array_start + 1

                    while current_pos < len(script_text) and bracket_count > 0:
                        if script_text[current_pos] == '[':
                            bracket_count += 1
                        elif script_text[current_pos] == ']':
                            bracket_count -= 1
                        current_pos += 1

                    if bracket_count == 0:
                        items_array_text = script_text[array_start:current_pos]

                        # Парсим массив items
                        try:
                            items_data = json.loads(items_array_text)
                            if isinstance(items_data, list):
                                for item in items_data:
                                    if isinstance(item, dict) and 'id' in item:
                                        card_info = {
                                            'id': item['id'],
                                            'service_type': service_type  # Добавляем тип услуги
                                        }
                                        # Добавляем доступные поля
                                        if 'productName' in item:
                                            card_info['productName'] = item['productName']
                                        if 'name' in item:
                                            card_info['name'] = item['name']
                                        if 'alias' in item:
                                            card_info['alias'] = item['alias']

                                        cards_data.append(card_info)
                                        print(f"Найдена карта: {service_type} - ID={item['id']}")
                        except json.JSONDecodeError as e:
                            print(f"Ошибка парсинга items массива: {e}")

                except Exception as e:
                    print(f"Ошибка при обработке структуры: {e}")
                    continue

        return cards_data

    except Exception as e:
        print(f"Ошибка получения карт с {url}: {e}")
        return []


def fetch_card_details(card_id: str, product_name: str = "debit-cards", service_type: str = "Дебетовая карта") -> Optional[Dict]:
    """
    Отправляет POST запрос для получения деталей карты

    Args:
        card_id: ID карты
        product_name: название продукта для API ("debit-cards", "credit-cards", etc.)
        service_type: тип услуги для логирования

    Returns:
        Словарь с данными карты или None в случае ошибки
    """
    api_url = "https://public.sravni.ru/v2/vitrins/product/byId"

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://www.sravni.ru',
        'Referer': 'https://www.sravni.ru/'
    }

    payload = {
        "productName": product_name,
        "id": card_id
    }

    try:
        print(f"Отправляем запрос для {service_type} - карта {card_id} (productName: {product_name})...")
        response = cffi_requests.post(
            api_url,
            json=payload,
            headers=headers,
            impersonate="chrome110"
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✓ Успешно получены данные для {card_id}")
            return data
        else:
            print(f"✗ Ошибка API для карты {card_id}: {response.status_code}")
            print(f"Текст ответа: {response.text[:200]}...")
            return None

    except Exception as e:
        print(f"✗ Ошибка запроса для карты {card_id}: {e}")
        return None


def process_all_cards_with_api(cards_list: List[Dict]) -> Dict[str, Dict]:
    """
    Обрабатывает все карты через API запросы

    Args:
        cards_list: список карт с id, name и service_type

    Returns:
        Словарь где ключ - ID карты, значение - данные из API + service_type
    """
    cards_details = {}

    print(f"\nНачинаем обработку {len(cards_list)} карт через API...")

    for i, card in enumerate(cards_list, 1):
        card_id = card['id']
        card_name = card.get('name', 'Без названия')
        service_type = card.get('service_type', 'Неизвестно')

        # Определяем product_name на основе service_type
        product_name = "debit-cards"  # по умолчанию
        if "кредит" in service_type.lower():
            product_name = "credit-cards"
        elif "ипотек" in service_type.lower():
            product_name = "mortgage"
        elif "вклад" in service_type.lower() or "депозит" in service_type.lower():
            product_name = "deposit"

        print(f"\n[{i}/{len(cards_list)}] Обрабатываем: {service_type} - {card_name} (ID: {card_id}, productName: {product_name})")

        # Отправляем POST запрос с правильным product_name
        card_details = fetch_card_details(card_id, product_name, service_type)

        if card_details:
            # Добавляем service_type в данные карты
            if isinstance(card_details, dict):
                card_details['service_type'] = service_type
            cards_details[card_id] = card_details
        else:
            print(f"⚠ Не удалось получить данные для {card_id}")

        # Пауза между запросами чтобы не перегружать сервер
        time.sleep(1)

    return cards_details


def save_api_results(cards_details: Dict[str, Dict], filename: str = "cards_api_results.json"):
    """Сохраняет результаты API запросов в JSON файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(cards_details, f, ensure_ascii=False, indent=2)

    print(f"\nРезультаты API сохранены в {filename}")


def extract_bank_cards_from_url(url: str, service_type: str = "Дебетовая карта") -> List[Dict]:
    """
    Извлекает карты банка из структуры products->list->offers->items

    Args:
        url: URL страницы с картами
        service_type: Тип банковской услуги
    """
    cards = get_bank_cards(url, service_type)

    # Убираем дубликаты
    unique_cards = []
    seen_ids = set()

    for card in cards:
        if card['id'] not in seen_ids:
            seen_ids.add(card['id'])
            unique_cards.append(card)

    # Выводим результаты
    if unique_cards:
        print(f"\nНайдено уникальных карт: {len(unique_cards)}")
        print(f"\nСписок карт ({service_type}):")
        for i, card in enumerate(unique_cards, 1):
            print(f"{i}. ID: {card['id']}")
            if 'productName' in card:
                print(f"   Название: {card['productName']}")
            if 'name' in card:
                print(f"   Имя: {card['name']}")
            print(f"   Тип услуги: {card['service_type']}")
            print()

        # Сохраняем базовый список
        filename = f"bank_cards_{service_type.replace(' ', '_').lower()}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(unique_cards, f, ensure_ascii=False, indent=2)
        print(f"Базовый список сохранен в {filename}")

        return unique_cards
    else:
        print(f"Не удалось найти данные о картах для {service_type}")
        return []


def prepare_structured_data_for_llm(cards_details: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Подготавливает структурированные данные для LLM
    """
    structured_cards = {}

    for card_id, card_data in cards_details.items():
        item_data = card_data.get('item', card_data)  # Если нет item, используем сам card_data

        # Получаем service_type (может быть на верхнем уровне)
        service_type = card_data.get('service_type', 'Неизвестно')

        # Создаем очищенную структуру только с важными полями
        clean_card = {
            "id": item_data.get("id"),
            "name": item_data.get("name"),
            "service_type": service_type,  # Добавляем тип услуги
            "nameAlias": item_data.get("nameAlias"),
            "link": item_data.get("link"),
            "description": clean_html(item_data.get("description", "")),
            "status": item_data.get("status"),
            "paymentSystem": item_data.get("paymentSystem", []),
            "cardClass": item_data.get("cardCLass", []),
            "features": item_data.get("feature", []),
            "benefits": item_data.get("benefits", []),
            "ageFrom": item_data.get("ageFrom"),
            "demands": item_data.get("demands", []),
            "currency": item_data.get("currency"),
            "smartphone": item_data.get("smartphone", ""),
            "maintenance": extract_maintenance_info(item_data),
            # Кешбэк
            "cashback": extract_cashback_info(item_data),
            # Снятие наличных
            "withdrawal": extract_withdrawal_info(item_data),
            # Дополнительные условия
            "conditions": extract_conditions_info(item_data)
        }

        # Убираем пустые поля
        clean_card = {k: v for k, v in clean_card.items() if v not in [None, "", [], {}]}
        structured_cards[card_id] = clean_card

    return structured_cards


def extract_maintenance_info(item_data: Dict) -> Dict:
    """Извлекает информацию об обслуживании с учетом новой структуры"""
    maintenance_info = {}

    # Основные поля (могут быть на верхнем уровне)
    if item_data.get("maintenancePrice") is not None:
        maintenance_info["price"] = item_data["maintenancePrice"]
        maintenance_info["currency"] = item_data.get("currencyMaintenance", "RUB")
        maintenance_info["frequency"] = item_data.get("frequencyNew", "")

    if item_data.get("maintenanceComment"):
        maintenance_info["comment"] = clean_html(item_data["maintenanceComment"])

    if item_data.get("conditionsNew"):
        maintenance_info["conditions"] = item_data["conditionsNew"]

    # Детали из maintenanceReleaseFeeTab
    maintenance_details = []
    for maint_id, maint_data in item_data.get("maintenanceReleaseFeeTab", {}).items():
        detail = {}
        if maint_data.get("maintenancePrice") is not None:
            detail["price"] = maint_data["maintenancePrice"]
            detail["type"] = maint_data.get("maintenanceRelease", [])
            detail["frequency"] = maint_data.get("frequencyNew", "")
            if maint_data.get("conditionsNew"):
                detail["conditions"] = maint_data["conditionsNew"]
            maintenance_details.append(detail)

    if maintenance_details:
        maintenance_info["details"] = maintenance_details

    return maintenance_info


def extract_cashback_info(item_data: Dict) -> Dict:
    """Извлекает информацию о кешбэке с учетом новой структуры"""
    cashback_info = {}

    # Основные поля
    if item_data.get("cashbackValue") is not None:
        cashback_info["value"] = item_data["cashbackValue"]

    if item_data.get("cashbackMaxValue") is not None:
        cashback_info["maxValue"] = item_data["cashbackMaxValue"]
        cashback_info["maxValueType"] = item_data.get("cashbackMaxValueType", "")

    if item_data.get("cashbackComment"):
        cashback_info["comment"] = item_data["cashbackComment"]

    if item_data.get("cashbackDescription"):
        cashback_info["description"] = clean_html(item_data["cashbackDescription"])

    # Категории кешбэка
    categories = []
    for cb_id, cb_data in item_data.get("cashbackCategoriesTab", {}).items():
        category_info = {
            "categories": cb_data.get("cashbackCategories", []),
            "value": cb_data.get("cashbackValue"),
            "comment": cb_data.get("cashbackComment", "")
        }
        if cb_data.get("cashbackMaxValue") is not None:
            category_info["maxValue"] = cb_data["cashbackMaxValue"]
            category_info["maxValueType"] = cb_data.get("cashbackMaxValueType", "")
        categories.append(category_info)

    if categories:
        cashback_info["categories"] = categories

    if item_data.get("cashbackCategories"):
        cashback_info["allCategories"] = item_data["cashbackCategories"]

    return cashback_info


def extract_withdrawal_info(item_data: Dict) -> Dict:
    """Извлекает информацию о снятии наличных с учетом новой структуры"""
    withdrawal_info = {}

    # Основные поля
    if item_data.get("withdrawRateFrom") is not None:
        withdrawal_info["rateFrom"] = item_data["withdrawRateFrom"]

    if item_data.get("withdrawRateTo") is not None:
        withdrawal_info["rateTo"] = item_data["withdrawRateTo"]

    if item_data.get("withdrawComment"):
        withdrawal_info["comment"] = clean_html(item_data["withdrawComment"])

    if item_data.get("withdrawPlace"):
        withdrawal_info["places"] = item_data["withdrawPlace"]

    return withdrawal_info


def extract_conditions_info(item_data: Dict) -> Dict:
    """Извлекает дополнительные условия с учетом новой структуры"""
    conditions_info = {}

    for cond_id, cond_data in item_data.get("conditionsTab", {}).items():
        if cond_data.get("additionalConditions"):
            conditions_info[cond_id] = clean_html(cond_data["additionalConditions"])

    return conditions_info


def clean_html(text: str) -> str:
    """Очищает HTML теги, но сохраняет структуру текста"""
    if not text:
        return ""
    # Убираем теги, но сохраняем переносы строк
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def save_structured_for_llm(structured_cards: Dict[str, Dict], filename: str = "cards_structured_llm.json"):
    """Сохраняет структурированные данные для LLM"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(structured_cards, f, ensure_ascii=False, indent=2)

    print(f"Структурированные данные для LLM сохранены в {filename}")


# Примеры использования с разными URL и типами услуг
BANK_CONFIGS = [
    {
        "url": "https://www.sravni.ru/debetovye-karty/bank/t-bank/",
        "service_type": "Дебетовая карта",
        "product_name": "debit-cards"
    },
    {
        "url": "https://www.sravni.ru/karty/bank/t-bank/",
        "service_type": "Кредитная карта",
        "product_name": "credit-cards"
    }
]

if __name__ == "__main__":
    all_cards = []

    # Обрабатываем несколько типов услуг
    for config in BANK_CONFIGS:
        print(f"\n{'=' * 50}")
        print(f"Обрабатываем: {config['service_type']}")
        print(f"URL: {config['url']}")
        print(f"{'=' * 50}")

        cards = extract_bank_cards_from_url(config['url'], config['service_type'])
        all_cards.extend(cards)

    if all_cards:
        # Обрабатываем все карты через API
        cards_details = process_all_cards_with_api(all_cards)

        # Подготавливаем структурированные данные для LLM
        structured_cards = prepare_structured_data_for_llm(cards_details)

        # Сохраняем для LLM
        save_structured_for_llm(structured_cards)

        print(f"\n=== ИТОГИ ===")
        print(f"Всего обработано карт: {len(structured_cards)}")

        # Группируем по типам услуг для статистики
        service_stats = {}
        for card_id, card_data in structured_cards.items():
            service_type = card_data.get('service_type', 'Неизвестно')
            service_stats[service_type] = service_stats.get(service_type, 0) + 1

        print("Статистика по типам услуг:")
        for service_type, count in service_stats.items():
            print(f"  {service_type}: {count} карт")

    else:
        print("Не удалось найти ни одной карты")