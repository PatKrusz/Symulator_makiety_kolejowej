## Symulator ruchu pociągów na makiecie kolejowej 

# Inicjalizacja bibliotek
import pygame as pg
import os
import json
import datetime
import time

# globalna flaga trybu debugowania
DEBUG_MODE = True

# Wczytywanie ustawień symulatora z pliku konfiguracyjnego
class Scaler:
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

        # Inicjalizacja Scalera
        self.ustawienia_symulacji = self.surowe_dane["ustawienia_symulacji"]
        self.scaler = Scaler(
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

# Zegar symulacji
class Wydarzenie:
    """
    Klasa reprezentuje pojedyncze wydarzenie w symulacji zaplanowane na konkretny czas symulacji
    """
    def __init__(self, czas_symulacji: datetime.datetime, akcja: callable, nazwa: str = ""):
        self.czas_symulacji = czas_symulacji
        self.akcja = akcja
        self.nazwa = nazwa
        self.wykonane = False

class ZegarSymulacji:
    """
    Klasa odpowiedzialna za zarządzanie czasem symulacji i harmonogramem wydarzeń. Obsługuje przyspieszenie czasu w symulacji, przeliczanie czasu rzeczywistego na czas symulacji, oraz pauze
    """
    def __init__(self, czas_startu: datetime.datetime = None, wspolczynnik_czasu: float = 1.0):
        if czas_startu is None:
            teraz = datetime.datetime.now()
            czas_startu = teraz.replace(hour=10, minute=0, second=0, microsecond=0)  # Domyślnie 10:00:00
        
        self.czas_symulacji = czas_startu
        self.wspolczynnik_czasu = wspolczynnik_czasu
        self._zaplanowane_wydarzenia = []
        self.pauza = False

    def ustaw_wspolczynnik_czasu(self, wspolczynnik: float) -> None:
        """Ustawia współczynnik przyspieszenia czasu symulacji."""
        self.wspolczynnik_czasu = wspolczynnik
        if DEBUG_MODE:
            print(f"[DEBUG] Ustawiono współczynnik czasu na: {self.wspolczynnik_czasu}")

    def przelacz_pauze(self) -> bool:
        """Przełącza stan pauzy symulacji."""
        self.pauza = not self.pauza
        if DEBUG_MODE:
            print(f"[DEBUG] Pauza symulacji: {'Włączona' if self.pauza else 'Wyłączona'}")
        return self.pauza

    def aktualizuj_czas(self, delta_czasu_rzeczywistego: float) -> float:
        """Aktualizuje czas symulacji na podstawie upływu czasu rzeczywistego i współczynnika przyspieszenia."""
        if self.pauza:
            if DEBUG_MODE:
                print("[DEBUG] Symulacja w pauzie, czas nie jest aktualizowany.")
            return 0.0

        delta_czasu_symulacji = delta_czasu_rzeczywistego * self.wspolczynnik_czasu
        self.czas_symulacji += datetime.timedelta(seconds=delta_czasu_symulacji)

        if DEBUG_MODE:
            print(f"[DEBUG] Aktualizacja czasu symulacji: +{delta_czasu_symulacji:.2f}s, nowy czas: {self.czas_symulacji.time()}")

        self._wykonaj_wydarzenia()
        return delta_czasu_symulacji

    def dodaj_wydarzenie(self, czas_wywolania: datetime.datetime, akcja: callable, nazwa: str = "") -> None:
        """Dodaje wydarzenie do harmonogramu symulacji. Na konkretną wirtualną godzinę symulacji."""
        wydarzenie = Wydarzenie(czas_wywolania, akcja, nazwa)
        self._zaplanowane_wydarzenia.append(wydarzenie)

    def _wykonaj_wydarzenia(self) -> None:
        """Wykonuje wszystkie wydarzenia, których czas symulacji został osiągnięty lub przekroczony."""
        for wydarzenie in self._zaplanowane_wydarzenia:
            if not wydarzenie.wykonane and self.czas_symulacji >= wydarzenie.czas_symulacji:
                if DEBUG_MODE:
                    print(f"[DEBUG] Wykonywanie wydarzenia: {wydarzenie.nazwa} o czasie symulacji: {wydarzenie.czas_symulacji.time()}")
                try:
                    wydarzenie.akcja()
                    wydarzenie.wykonane = True
                except Exception as e:
                    print(f"[ERROR] Błąd podczas wykonywania wydarzenia '{wydarzenie.nazwa}': {e}")
        
        self._zaplanowane_wydarzenia = [w for w in self._zaplanowane_wydarzenia if not w.wykonane]

    def obecny_czas(self) -> str:
        """Zwraca aktualny czas symulacji."""
        return self.czas_symulacji.strftime("%H:%M:%S")

    def obecna_data(self) -> str:
        """Zwraca aktualną datę i godzinę symulacji w formacie YYYY-MM-DD HH:MM:SS."""
        return self.czas_symulacji.strftime("%Y-%m-%d %H:%M:%S")

