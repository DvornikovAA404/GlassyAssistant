import requests
from bs4 import BeautifulSoup
from jupiter import ask_jupiter # Нейросетевой модуль


CATEGORIES = {
    "мировые": {"rbc": "/world/", "ria": "/world/"},
    "российские": {"rbc": "/", "ria": "/russia/"},
    "городские": {"rbc": "/tag/город/", "ria": "/region/"},
    "экономика": {"rbc": "/economics/", "ria": "/economy/"},
    "политика": {"rbc": "/politics/", "ria": "/politics/"},
    "авто": {"rbc": "/auto/", "ria": "/auto/"},
    "наука": {"rbc": "/science_and_technology/", "ria": "/science/"},
    "будни": {"rbc": "/", "ria": "/society/"}
}
API_KEY = '5GbXmau93XwA5QJwtrx5lugncxLUylcf'


def get_news_from_rbc(section_url: str, limit=5):
    """Получает новости с сайта РБК"""
    base_url = "https://www.rbc.ru"
    full_url = base_url + section_url
    response = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.content, "lxml")

    articles = soup.select("a.main__feed__link")
    news = []

    for a in articles[:limit]:
        title = a.get_text(strip=True)
        link = a['href']
        try:
            article_resp = requests.get(link, headers={"User-Agent": "Mozilla/5.0"})
            article_soup = BeautifulSoup(article_resp.content, "lxml")
            body = article_soup.select_one("div.article__text, div.article__content")
            text = body.get_text(" ", strip=True) if body else ""
            if text:
                news.append(text[:500])
        except Exception:
            continue
    return news


def get_news_from_ria(section_url: str, limit=5):
    """Получает новости с сайта РИА"""
    base_url = "https://ria.ru"
    full_url = base_url + section_url
    response = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.content, "lxml")

    articles = soup.select("a.list-item__title, a.cell-main-photo__link")
    news = []

    for a in articles[:limit]:
        title = a.get_text(strip=True)
        href = a['href']
        link = href if href.startswith("http") else base_url + href
        try:
            article_resp = requests.get(link, headers={"User-Agent": "Mozilla/5.0"})
            article_soup = BeautifulSoup(article_resp.content, "lxml")
            content_div = article_soup.select_one("div.article__body, div.article__text, div.article")
            text = content_div.get_text(" ", strip=True) if content_div else ""
            if text:
                news.append(text[:500])
        except Exception:
            continue
    return news


def fetch_news(topic: str, count=5):
    """Парсит новости"""
    topic = topic.lower()
    category = CATEGORIES.get(topic, {"rbc": "/", "ria": "/"})

    print(f"📡 Получаю новости по теме: «{topic}»")

    rbc_news = get_news_from_rbc(category["rbc"], limit=count)
    ria_news = get_news_from_ria(category["ria"], limit=count)

    all_news = rbc_news + ria_news
    return "\n".join(all_news[:count])


def get_traffic_data():
    """Получает данные о дорожной обстановке"""
    api_url = "https://api.codd.mos.ru/traffic"

    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        for item in data['features']:
            properties = item['properties']
            print(f"Участок: {properties['name']}")
            print(f"Состояние: {properties['status']}")
            print(f"Описание: {properties['description']}\n")

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении данных: {e}")
def get_traffic_info(city="Москва"):
    """
    Парсит дорожную обстановку с ria.ru для Москвы и даёт краткий текст для Юпитера.
    """
    print(f"🚗 Анализ трафика для города: {city}")
    traffic_url = "https://ria.ru/traffic/"

    try:
        response = requests.get(traffic_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.content, "lxml")

        articles = soup.select("a.list-item__title")
        traffic_news = []

        for a in articles[:3]:  # берём 3 актуальные заметки
            title = a.get_text(strip=True)
            href = a['href']
            full_url = href if href.startswith("http") else "https://ria.ru" + href

            art_resp = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"})
            art_soup = BeautifulSoup(art_resp.content, "lxml")
            body = art_soup.select_one("div.article__text, div.article__body")
            if body:
                text = body.get_text(" ", strip=True)
                if city.lower() in text.lower():
                    traffic_news.append(text[:500])

        if not traffic_news:
            return "Данных по дорожной обстановке пока нет."

        prompt = (
            f"Сделай краткую сводку ситуации на дорогах в городе {city} на основе этих новостей:\n"
            + "\n\n".join(traffic_news)
        )

        return ask_jupiter(prompt)

    except Exception as e:
        print(f"⚠️ Ошибка при получении данных о трафике: {e}")
        return "Не удалось получить информацию о пробках."


def main(topic, count, city):
    topic = topic.strip().lower()
    count_input = count

    try:
        count = int(count_input)
    except ValueError:
        count = 5

    if topic == "трафик":
        city = city.strip() or "Москва"
        summary = get_traffic_info(city)
        print("📢 Юпитер:\n")
        print(summary)
        return

    raw_news = fetch_news(topic, count)
    if not raw_news:
        print("⚠️ Не удалось получить новости.")
        return


    combined_text = "\n\n".join(raw_news)
    prompt = f"Сделай живую краткую сводку новостей на тему: {topic}. Вот тексты:\n{combined_text}"

    print("\n🧠 Юпитер готовит сводку...\n")
    summary = ask_jupiter(prompt)
    print("📢 Юпитер:\n")
    return summary

def get_traffic_news():
    headers = {'User-Agent': 'Mozilla/5.0'}
    news_data = []

    rbc_url = 'https://www.rbc.ru/tags/?tag=пробки'
    rbc_response = requests.get(rbc_url, headers=headers)
    if rbc_response.status_code == 200:
        rbc_soup = BeautifulSoup(rbc_response.text, 'html.parser')
        rbc_articles = rbc_soup.find_all('a', class_='item__link', limit=5)
        for article in rbc_articles:
            title = article.get_text(strip=True)
            link = article['href']
            news_data.append(f"{title} ({link})")

    ria_url = 'https://ria.ru/tag_traffic_jam/'
    ria_response = requests.get(ria_url, headers=headers)
    if ria_response.status_code == 200:
        ria_soup = BeautifulSoup(ria_response.text, 'html.parser')
        ria_articles = ria_soup.find_all('a', class_='list-item__title', limit=5)
        for article in ria_articles:
            title = article.get_text(strip=True)
            link = article['href']
            news_data.append(f"{title} ({link})")

    return news_data


def get_traffic_flow():
    """Определяет загруженные улицы в Новосибирске через TomTom API."""
    city_lat, city_lon = 55.0084, 82.9357
    url = f'https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json?point={city_lat}%2C{city_lon}&key={API_KEY}'

    try:
        response = requests.get(url)

        if response.status_code != 200:
            print(f"⚠️ Ошибка HTTP {response.status_code}: {response.text}")
            return None

        data = response.json()
        if not isinstance(data, dict) or "flowSegmentData" not in data:
            print("⚠️ API вернул некорректные данные.")
            return None

        segment = data["flowSegmentData"]
        current_speed = segment.get("currentSpeed", 0)
        free_flow_speed = segment.get("freeFlowSpeed", 0)
        confidence = int(segment.get("confidence", 0) * 100)

        congestion_level = free_flow_speed - current_speed
        status = "🚦 Затруднённое движение" if congestion_level > 10 else "✅ Движение свободное"

        report = (
            f"Средняя скорость в городе: {current_speed} км/ч\n"
            f"Обычно свободное движение: {free_flow_speed} км/ч\n"
            f"Надёжность данных: {confidence}%\n"
            f"Состояние: {status}"
        )

        return report

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при подключении к API: {e}")

    return "🚗 Нет достоверных данных о движении."


def get_traffic_incidents():
    """Получает данные о дорожных инцидентах в Новосибирске."""
    bbox = "82.5,54.8,83.4,55.4"
    url = f'https://api.tomtom.com/traffic/services/5/incidentDetails?bbox={bbox}&key={API_KEY}'

    try:
        response = requests.get(url)

        if response.status_code != 200:
            print(f"⚠️ Ошибка HTTP {response.status_code}: {response.text}")
            return None

        data = response.json()
        if not isinstance(data, dict) or "incidents" not in data:
            print("⚠️ API вернул некорректные данные.")
            return None

        incidents = [
            {
                "description": i['properties'].get('description', 'Без описания'),
                "start": i['properties'].get('startTime', ''),
                "end": i['properties'].get('endTime', '')
            }
            for i in data.get('incidents', [])
        ]

        return incidents if incidents else "🚗 Нет сообщений о происшествиях."

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при подключении к API: {e}")

    return "🚗 Нет данных о дорожных инцидентах."


def summarize_traffic():
    """Создаёт краткую сводку дорожной ситуации через нейросеть."""
    flow = get_traffic_flow()
    incidents = get_traffic_incidents()

    if not flow:
        flow_text = "Нет достоверных данных о движении."
    else:
        flow_text = flow

    if incidents and isinstance(incidents, list):
        incident_text = "\n".join([f"{i['description']}" for i in incidents[:5]])
    else:
        incident_text = "Нет сообщений о происшествиях."

    combined_data = f"Обзор трафика: {flow_text}\nИнциденты: {incident_text}"

    return ask_jupiter(f"Ты — ассистент Юнона(Забудь о части с описанием Юпитера), специализирующийся на анализе дорожной ситуации. "
                       f"Используя данные ниже, сформируй краткую, полезную сводку пробок и инцидентов. "
                       f"Также предложи рекомендации по объезду загруженных участков: {combined_data}")



if __name__ == "__main__":
    print(summarize_traffic())
    main()
