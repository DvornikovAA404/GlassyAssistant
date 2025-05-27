import requests
from datetime import datetime, timedelta
from jupiter import ask_jupiter # Нейросетевой модуль

class WeatherAPI:
    BASE_URL = "https://api.openweathermap.org/data/2.5/"
    API_KEY = "b5f33022019a295fdf599f69f44fe938"

    PROMPT = """
    Ты - Юнона. Ассистент, специализирующийся на прогнозе погоды. Тебе дается json-код с параметрами погоды. Посоветовать, во что одеться. Предложить чего-нибудь. Но коротко, не расписывая это в поэму, и при этом живо."""
    def __init__(self, city):
        self.city = city

    def get_weather_now(self):
        """Получает текущую погоду."""
        url = f"{self.BASE_URL}weather?q={self.city}&appid={self.API_KEY}&units=metric"
        response = requests.get(url)
        return response.json()

    def get_forecast(self, days_ahead=1):
        """Получает прогноз погоды на заданное количество дней вперед."""
        url = f"{self.BASE_URL}forecast?q={self.city}&appid={self.API_KEY}&units=metric"
        response = requests.get(url).json()

        forecast_data = response.get("list", [])
        target_date = datetime.now().date() + timedelta(days=days_ahead)

        filtered_forecast = [
            entry for entry in forecast_data
            if datetime.fromtimestamp(entry["dt"]).date() == target_date
        ]

        return filtered_forecast

    def get_specific_date_weather(self, date):
        """Получает прогноз на конкретную дату (формат YYYY-MM-DD)."""
        url = f"{self.BASE_URL}forecast?q={self.city}&appid={self.API_KEY}&units=metric"
        response = requests.get(url).json()

        forecast_data = response.get("list", [])
        target_date = datetime.strptime(date, "%Y-%m-%d").date()

        filtered_forecast = [
            entry for entry in forecast_data
            if datetime.fromtimestamp(entry["dt"]).date() == target_date
        ]

        return filtered_forecast

    def get_weekend_weather(self):
        """Получает прогноз на выходные (субботу и воскресенье)."""
        url = f"{self.BASE_URL}forecast?q={self.city}&appid={self.API_KEY}&units=metric"
        response = requests.get(url).json()

        forecast_data = response.get("list", [])
        weekend_days = {5, 6}

        weekend_forecast = [
            entry for entry in forecast_data
            if datetime.fromtimestamp(entry["dt"]).weekday() in weekend_days
        ]

        return weekend_forecast

