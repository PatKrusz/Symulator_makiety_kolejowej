import json
import os

global DEBUG_MODE

# Wczytywanie ustawień symulatora z pliku konfiguracyjnego
class Skaler:
    """
    Klasa odpowiedzialna za skalowanie wartości w symulatorze.
    """
    def __init__(self, skala_w_metrach: float = 10.0, rozmiar_kafelka_px: int = 48):
        self.skala_w_metrach = skala_w_metrach
        self.rozmiar_kafelka_px = rozmiar_kafelka_px
        self.px_na_metr = self.rozmiar_kafelka_px / self.skala_w_metrach
        if DEBUG_MODE:
            print(f"[DEBUG] Inicjalizacja Scalera: skala_w_metrach={self.skala_w_metrach}, rozmiar_kafelka_px={self.rozmiar_kafelka_px}, px_na_metr={self.px_na_metr}")

    def kmh_na_pxs(self, predkosc_kmh: float) -> float:
        """Konwertuje prędkość z km/h na piksele na sekundę."""
        predkosc_ms = predkosc_kmh * 1000 / 3600  # km/h -> m/s
        predkosc_pxs = predkosc_ms * self.px_na_metr  # m/s -> px/s
        if DEBUG_MODE:
            print(f"[DEBUG] Konwersja prędkości: {predkosc_kmh} km/h -> {predkosc_pxs} px/s")
        return predkosc_pxs

    def pxs_na_kmh(self, predkosc_pxs: float) -> float:
        """Konwertuje prędkość z pikseli na sekundę na km/h."""
        predkosc_ms = predkosc_pxs / self.px_na_metr  # px/s -> m/s
        predkosc_kmh = predkosc_ms * 3600 / 1000  # m/s -> km/h
        if DEBUG_MODE:
            print(f"[DEBUG] Konwersja prędkości: {predkosc_pxs} px/s -> {predkosc_kmh} km/h")
        return predkosc_kmh

    def ms2_na_pxs2(self, przyspieszenie_ms2: float) -> float:
        """Konwertuje przyspieszenie z m/s² na px/s²."""
        przyspieszenie_pxs2 = przyspieszenie_ms2 * self.px_na_metr  # m/s² -> px/s²
        if DEBUG_MODE:
            print(f"[DEBUG] Konwersja przyspieszenia: {przyspieszenie_ms2} m/s² -> {przyspieszenie_pxs2} px/s²")
        return przyspieszenie_pxs2

    def pxs2_na_ms2(self, przyspieszenie_pxs2: float) -> float:
        """Konwertuje przyspieszenie z px/s² na m/s²."""
        przyspieszenie_ms2 = przyspieszenie_pxs2 / self.px_na_metr  # px/s² -> m/s²
        if DEBUG_MODE:
            print(f"[DEBUG] Konwersja przyspieszenia: {przyspieszenie_pxs2} px/s² -> {przyspieszenie_ms2} m/s²")
        return przyspieszenie_ms2

    def siatka_na_ekran(self, x_siatka: int, y_siatka: int) -> tuple[float, float]:
        """Konwertuje współrzędne kafelka w siatce na środkowy punkt w pikselach"""
        x_px = (x_siatka + 0.5) * self.rozmiar_kafelka_px
        y_px = (y_siatka + 0.5) * self.rozmiar_kafelka_px
        if DEBUG_MODE:
            print(f"[DEBUG] Konwersja współrzędnych: ({x_siatka}, {y_siatka}) -> ({x_px}, {y_px}) px")
        return x_px, y_px


class ConfigLoader:
    """
    Klasa odpowiedzialna za wczytywanie i sprawdzanie konfiguracji symulatora z pliku JSON.
    """
    def __init__(self, sciezka: str = "sim_config.json"):
        self.sciezka_konfiguracji = sciezka
        self.surowe_dane = {}
        self.scaler = None
        self.pociagi = []
        self.stacje = []
        self.semafory = []
        self.tory = []
        self.wspolczynnik_czasu = 1.0
        self.ustawienia_symulacji = {}
        self.zwrotnice = []
        

    def wczytaj_konfiguracje(self) -> bool:
        """Wczytuje konfigurację z pliku JSON i sprawdza jej poprawność."""
        if not os.path.exists(self.sciezka_konfiguracji):
            print(f"[ERROR] Plik konfiguracyjny '{self.sciezka_konfiguracji}' nie istnieje.")
            return False

        with open(self.sciezka_konfiguracji, 'r', encoding='utf-8') as f:
            try:
                self.surowe_dane = json.load(f)
                global DEBUG_MODE
                DEBUG_MODE = self.surowe_dane.get("ustawienia_symulacji", {}).get("tryb_debugowania", False)
                if DEBUG_MODE:
                    print(f"[DEBUG] Wczytano konfigurację: {self.surowe_dane}")
            except json.JSONDecodeError as e:
                print(f"[ERROR] Błąd dekodowania JSON: {e}")
                return False

        # Sprawdzenie obecności wymaganych sekcji
        for sekcja in ["ustawienia_symulacji", "pociagi", "stacje", "semafory", "zwrotnice", "tory"]:
            if sekcja not in self.surowe_dane:
                print(f"[ERROR] Brak sekcji '{sekcja}' w pliku konfiguracyjnym.")
                return False

        # Inicjalizacja Skalera
        self.ustawienia_symulacji = self.surowe_dane["ustawienia_symulacji"]
        self.scaler = Skaler(
            skala_w_metrach=self.ustawienia_symulacji.get("skala_w_metrach", 10.0),
            rozmiar_kafelka_px=self.ustawienia_symulacji.get("rozmiar_kafelka_px", 48)
        )

        self.wspolczynnik_czasu = self.ustawienia_symulacji.get("wspolczynnik_czasu", 1.0)
        self.pociagi = self.surowe_dane.get("pociagi", [])
        self.stacje = self.surowe_dane.get("stacje", [])
        self.semafory = self.surowe_dane.get("semafory", [])
        self.tory = self.surowe_dane.get("tory", [])
        self.zwrotnice = self.surowe_dane.get("zwrotnice", [])

        return True
