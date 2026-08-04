# Zegar symulacji

import datetime
from typing import Callable
import config

class Wydarzenie:
    """
    Klasa reprezentuje pojedyncze wydarzenie w symulacji zaplanowane na konkretny czas symulacji
    """
    def __init__(self, czas_symulacji: datetime.datetime, akcja: Callable, nazwa: str = ""):
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
        if config.DEBUG_MODE:
            print(f"[DEBUG] Ustawiono współczynnik czasu na: {self.wspolczynnik_czasu}")

    def przelacz_pauze(self) -> bool:
        """Przełącza stan pauzy symulacji."""
        self.pauza = not self.pauza
        if config.DEBUG_MODE:
            print(f"[DEBUG] Pauza symulacji: {'Włączona' if self.pauza else 'Wyłączona'}")
        return self.pauza

    def aktualizuj_czas(self, delta_czasu_rzeczywistego: float) -> float:
        """Aktualizuje czas symulacji na podstawie upływu czasu rzeczywistego i współczynnika przyspieszenia."""
        if self.pauza:
            #if config.DEBUG_MODE:
            #    print("[DEBUG] Symulacja w pauzie, czas nie jest aktualizowany.")
            return 0.0

        delta_czasu_symulacji = delta_czasu_rzeczywistego * self.wspolczynnik_czasu
        self.czas_symulacji += datetime.timedelta(seconds=delta_czasu_symulacji)

        #if config.DEBUG_MODE:
        #    print(f"[DEBUG] Aktualizacja czasu symulacji: +{delta_czasu_symulacji:.2f}s, nowy czas: {self.czas_symulacji.time()}")

        self._wykonaj_wydarzenia()
        return delta_czasu_symulacji

    def dodaj_wydarzenie(self, czas_wywolania: datetime.datetime, akcja: Callable, nazwa: str = "") -> None:
        """Dodaje wydarzenie do harmonogramu symulacji. Na konkretną wirtualną godzinę symulacji."""
        wydarzenie = Wydarzenie(czas_wywolania, akcja, nazwa)
        self._zaplanowane_wydarzenia.append(wydarzenie)

    def _wykonaj_wydarzenia(self) -> None:
        """Wykonuje wszystkie wydarzenia, których czas symulacji został osiągnięty lub przekroczony."""
        for wydarzenie in self._zaplanowane_wydarzenia:
            if not wydarzenie.wykonane and self.czas_symulacji >= wydarzenie.czas_symulacji:
                if config.DEBUG_MODE:
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