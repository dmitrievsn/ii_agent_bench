from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

def extract_component_data(url, component_name, component_properties=None):
    """
    Извлекает тексты из указанного компонента с дополнительными параметрами поиска

    Args:
        url (str): URL страницы для парсинга
        component_name (str): Название компонента для поиска (например, "ModalV2" или "Tabs.TabsPanelV2")
        component_properties (dict, optional): Свойства компонента для точного поиска

    Returns:
        str: Строка с объединенными текстами из компонента или сообщение об ошибке
    """

    def find_component(data):
        """Рекурсивно ищет компонент с указанным именем и свойствами в структуре JSON"""
        if isinstance(data, dict):
            # Проверяем совпадение по имени
            if data.get('name') == component_name:
                # Если заданы свойства, проверяем и их
                if component_properties:
                    properties_match = all(
                        data.get('properties', {}).get(key) == value
                        for key, value in component_properties.items()
                    )
                    if properties_match:
                        return data
                else:
                    # Если свойства не заданы, возвращаем первый найденный компонент с таким именем
                    return data

            # Рекурсивно ищем в значениях словаря
            for value in data.values():
                result = find_component(value)
                if result:
                    return result

        elif isinstance(data, list):
            # Рекурсивно ищем в элементах списка
            for item in data:
                result = find_component(item)
                if result:
                    return result
        return None

    def extract_text_fields(obj, texts_list):
        """Рекурсивно извлекает поля 'title' и 'text' из объекта"""
        if isinstance(obj, dict):
            if 'title' in obj:
                texts_list.append(obj['title'])
            if 'text' in obj:
                texts_list.append(obj['text'])
            for value in obj.values():
                extract_text_fields(value, texts_list)
        elif isinstance(obj, list):
            for item in obj:
                extract_text_fields(item, texts_list)

    try:
        response = cffi_requests.get(url, impersonate="safari15_5")
        response.raise_for_status()
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        target_block = soup.find('script', id='app_state')

        if not target_block:
            return "Целевой блок не найден на странице."

        # Парсим JSON content из script tag
        data = json.loads(target_block.string)

        # Ищем компонент с указанными параметрами
        component_data = find_component(data)

        if not component_data:
            properties_info = f" со свойствами {component_properties}" if component_properties else ""
            return f"Компонент {component_name}{properties_info} не найден в JSON структуре"

        # Извлекаем все текстовые поля
        found_texts = []
        extract_text_fields(component_data, found_texts)

        # Объединяем все найденные тексты в одну строку через пробел
        result_string = ' '.join(found_texts)

        # Удаляем NBSP, NNBSP, THSP и другие нежелательные символы
        result_string = (result_string
                         .replace('\xa0', ' ')  # NBSP
                         .replace('\u202F', ' ')  # NNBSP
                         .replace('\u2009', ' ')  # THSP
                         .replace('\r', ' ')  # Carriage return
                         .replace('\n', ' ')  # New line
                         .strip())

        return result_string

    except json.JSONDecodeError as e:
        return f"Ошибка парсинга JSON: {e}"
    except Exception as e:
        return f"Ошибка: {e}"


def save_to_json(data_to_save, filename="extracted_data.json", mode="overwrite"):
    """
    Усовершенствованная функция сохранения с поддержкой разных режимов

    Args:
        data_to_save (list): Список записей для сохранения
        filename (str): Имя файла для сохранения
        mode (str): Режим сохранения - "overwrite" (перезапись) или "append" (добавление)
    """
    try:
        if mode == "append":
            # Пытаемся загрузить существующие данные
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except FileNotFoundError:
                existing_data = []

            # Добавляем новые данные
            existing_data.extend(data_to_save)
            data_to_save = existing_data

        # Добавляем метаданные
        save_data = {
            "metadata": {
                "version": "1.0",
                "export_date": datetime.now().isoformat(),
                "total_records": len(data_to_save)
            },
            "data": data_to_save
        }

        # Сохраняем данные
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        print(f"Успешно сохранено {len(data_to_save)} записей в {filename}")
        return True

    except Exception as e:
        print(f"Ошибка при сохранении: {e}")
        return False


# Структурированный подход к сбору данных
def collect_bank_data():
    """Централизованная функция сбора данных"""

    # Конфигурация всех URL для сбора
    scrape_configs = [
        {
            "url": "https://alfabank.ru/everyday/debit-cards/alfacard/",
            "service_type": "Дебетовая карта",
            "component": "ModalV2",
            "component_properties": None
        },
        {
            "url": "https://alfabank.ru/lp/retail/dc/nfc/",
            "service_type": "Стикеры",
            "component": "ModalV2",
            "component_properties": None
        },
        {
            "url": "https://alfabank.ru/everyday/debit-cards/apelsin/",
            "service_type": "Дебетовая карта",
            "component": "Tabs.TabsPanelV2",
            "component_properties": {
                "widthTabPanel": "fullBlock",
                "widthTab": "equal"
            }
        }
    ]

    all_data = []

    for config in scrape_configs:
        try:
            print(f"Обрабатывается: {config['url']}")

            content = extract_component_data(
                config["url"],
                config["component"],
                component_properties=config["component_properties"]
            )

            all_data.append({
                "url": config["url"],
                "service_type": config["service_type"],
                "component": config["component"],
                "content": content,
                "scrape_date": datetime.now().isoformat()
            })

        except Exception as e:
            print(f"Ошибка при обработке {config['url']}: {e}")
            # Можно добавить запись об ошибке в данные
            all_data.append({
                "url": config["url"],
                "service_type": config["service_type"],
                "error": str(e),
                "scrape_date": datetime.now().isoformat()
            })

    return all_data


if __name__ == "__main__":
    # Сбор данных
    collected_data = collect_bank_data()

    # Сохранение
    save_to_json(collected_data, "bank_data.json")