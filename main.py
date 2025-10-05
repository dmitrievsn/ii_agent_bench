from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import json


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


def save_to_json(data_to_save, filename="extracted_data.json"):
    """
    Полностью перезаписывает JSON-файл с новыми данными

    Args:
        data_to_save (list): Список записей для сохранения
        filename (str): Имя файла для сохранения
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Список для хранения всех данных
    all_data = []

    # Обработка первой URL с указанием типа услуги
    url1 = 'https://alfabank.ru/everyday/debit-cards/alfacard/'
    service_type1 = "Дебетовая карта"
    result1 = extract_component_data(url1,'ModalV2')

    all_data.append({
        "url": url1,
        "service_type": service_type1,
        "content": result1
    })

    # Обработка второй URL с указанием типа услуги
    url2 = 'https://alfabank.ru/lp/retail/dc/nfc/'
    service_type2 = "Стикеры"
    result2 = extract_component_data(url2,'ModalV2')

    all_data.append({
        "url": url2,
        "service_type": service_type2,
        "content": result2
    })

    url3 = 'https://alfabank.ru/everyday/debit-cards/apelsin/'
    service_type3 = "Дебетовая карта"
    result3 = extract_component_data(url3,'Tabs.TabsPanelV2',component_properties={
        "widthTabPanel": "fullBlock",
        "widthTab": "equal"
    })

    all_data.append({
        "url": url3,
        "service_type": service_type3,
        "content": result3
    })
    # Сохраняем все данные заново
    save_to_json(all_data)