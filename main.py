from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import json


def extract_modal_texts(url):
    """
    Извлекает тексты из компонента ModalV2 с указанного URL

    Args:
        url (str): URL страницы для парсинга

    Returns:
        str: Строка с объединенными текстами из ModalV2 или сообщение об ошибке
    """

    def find_modal(data):
        """Рекурсивно ищет компонент ModalV2 в структуре JSON"""
        if isinstance(data, dict):
            if data.get('name') == 'ModalV2':
                return data
            for value in data.values():
                result = find_modal(value)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = find_modal(item)
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
        response.raise_for_status()  # Проверка на HTTP ошибки
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        target_block = soup.find('script', id='app_state')

        if not target_block:
            return "Целевой блок не найден на странице."

        # Парсим JSON content из script tag
        data = json.loads(target_block.string)

        # Ищем ModalV2
        modal_data = find_modal(data)

        if not modal_data:
            return "ModalV2 не найден в JSON структуре"

        # Извлекаем все текстовые поля
        found_texts = []
        extract_text_fields(modal_data, found_texts)

        # Объединяем все найденные тексты в одну строку через пробел
        result_string = ' '.join(found_texts)
        return result_string

    except json.JSONDecodeError as e:
        return f"Ошибка парсинга JSON: {e}"
    except Exception as e:
        return f"Ошибка: {e}"


# Пример использования
if __name__ == "__main__":
    url = 'https://alfabank.ru/everyday/debit-cards/alfacard/'
    result = extract_modal_texts(url)
    print("Результат:")
    print(result)