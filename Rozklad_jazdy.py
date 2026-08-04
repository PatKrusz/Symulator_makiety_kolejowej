# Rozkład jazdy dla pociągów

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from Graf import MenedzerGrafu
from Pociag import Pociag
import config

class StanPociagu(Enum):
    JAZDA = "JAZDA" # Normalna jazda
    HAMOWANIE = "HAMOWANIE" # Hamowanie przed stacją
    POSTOJ = "POSTOJ" # Postój na stacji
    KONIEC_TRASY = "KONIEC_TRASY" # Zrealizowano zaplanowaną trasę

@dataclass
class Przystanek:
    """Pojedyńczy przystanek w rozkładzie jazdy"""
    id_stacji: str
    czas_postoju: float = 30 # Czas postoju w sekundach symulacji
    czas_przyjazdu: Optional[str] = None
    czas_odjazdu: Optional[str] = None

class RozkladPociagu:
    """Zarządza sekwencją przystanków dla danego pociągu"""

    def __init__(self, id_rozkladu: str, przystanki: List[Przystanek]): 
        self.id_rozkladu: str = id_rozkladu
        self.przystanki: List[Przystanek] = przystanki
        self.id_obecnego_przystanku: int = 0

    def aktualny_przystanek(self) -> Optional[Przystanek]:
        """Zwraca aktualny lub najbliższy przystanek"""
        if 0 <= self.id_obecnego_przystanku < len(self.przystanki):
            return self.przystanki[self.id_obecnego_przystanku]
        return None

    def nastepny_przystanek(self) -> Optional[Przystanek]:
        """Przejście do kolejnego przystanku po zakończeniu postoju"""
        self.id_obecnego_przystanku += 1
        return self.aktualny_przystanek()

    def czy_koniec(self) -> bool:
        """Sprzawdzenie, czy dojechano do końca trasy"""
        return self.id_obecnego_przystanku >= len(self.przystanki)

class SledzenieRozkladu:
    """Klasa odpowiedzialna za realizację rozkładu jazdy na poziomie pociągu."""
    def __init__(self, rozklad: Optional[RozkladPociagu] = None):
        self.rozklad: Optional[RozkladPociagu] = rozklad
        self.stan_pociagu: StanPociagu = StanPociagu.JAZDA
        self.zegar_postoju: float = 0.0 # Obecny czas postoju na stacji

    def aktualizuj_logike_rozkladu(
        self, delta_czasu_symulacji: float, pociag: Pociag, graf: MenedzerGrafu) -> float:
        """Aktualizuje stan realizacji rozkładu. Zwraca rekomendowaną prędkość docelową"""
        if not self.rozklad or self.rozklad.czy_koniec():
            self.stan_pociagu = StanPociagu.KONIEC_TRASY
            return pociag.predkosc_max_pxs

        obecny_przystanek = self.rozklad.aktualny_przystanek()
        if not obecny_przystanek:
            self.stan_pociagu = StanPociagu.JAZDA
            return pociag.predkosc_max_pxs

        stacja_docelowa = graf.stacje.get(obecny_przystanek.id_stacji)
        id_przodu = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else None

        # 1. Trwający postój (pociąg stoi w miejscu i czeka)
        if self.stan_pociagu == StanPociagu.POSTOJ:
            self.zegar_postoju += delta_czasu_symulacji
            if self.zegar_postoju >= obecny_przystanek.czas_postoju:
                if config.DEBUG_MODE:
                    print(f"[DEBUG] Odjazd ze stacji {obecny_przystanek.id_stacji}")
                self.zegar_postoju = 0.0
                self.rozklad.nastepny_przystanek()
                self.stan_pociagu = StanPociagu.JAZDA
                return pociag.predkosc_max_pxs
            return 0.0

        # 2. Pociąg zbliża się lub wjechał na kafelek stacji
        if stacja_docelowa:
            # Jeśli czoło stoi już na stacji
            if id_przodu in stacja_docelowa.id_torow:
                if pociag.predkosc_aktualna_pxs == 0.0:
                    self.stan_pociagu = StanPociagu.POSTOJ
                    self.zegar_postoju = 0.0
                    return 0.0
                
                self.stan_pociagu = StanPociagu.HAMOWANIE
                return 0.0 # Wylecenie do zera na stacji

            # Sprawdzenie, czy następny kafelek to stacja (wczesne zwalnianie)
            kafelek_przodu = graf.wezly.get(id_przodu)
            if kafelek_przodu:
                nastepny = kafelek_przodu.nastepny_wezel(pociag.aktualny_kierunek)
                if nastepny and nastepny[0] in stacja_docelowa.id_torow:
                    self.stan_pociagu = StanPociagu.HAMOWANIE
                    # Zmniejszamy prędkość docelową do 30% przed wjechaniem na stację
                    return pociag.predkosc_max_pxs * 0.3

        # 3. Zwykła jazda szlakowa
        self.stan_pociagu = StanPociagu.JAZDA
        return pociag.predkosc_max_pxs

# Test jednostkowy

if __name__ == "__main__":

    from Wezly import ObszarStacji, WezelGrafu
    from Graf import MenedzerGrafu

    graf = MenedzerGrafu()
    t1 = WezelGrafu("T01",1,1)
    t2 = WezelGrafu("T02",2,1)
    t3 = WezelGrafu("T03",3,1)

    graf.dodaj_wezel(t1)
    graf.dodaj_wezel(t2)
    graf.dodaj_wezel(t3)

    stacja = ObszarStacji("ST01", "Stacja Główna", ["T02"])
    graf.dodaj_stacje(stacja)

    stop = Przystanek("ST01", 3.0)
    rozklad = RozkladPociagu("R01", [stop])
    sledzenie = SledzenieRozkladu(rozklad)

    max_predkosc = 100

    print("\n1. Pociąg jedzie na T01:")
    v_docelowe = sledzenie.aktualizuj_logike_rozkladu(0.5,"T01",graf,max_predkosc)
    print(f"   Stan: {sledzenie.stan_pociagu.value} | Zadana prędkość: {v_docelowe} px/s")

    print("\n2. Pociąg wjeżdża na T02 (Peron ST01):")
    v_docelowe = sledzenie.aktualizuj_logike_rozkladu(0.5, "T02", graf, max_predkosc)
    print(f"   Stan: {sledzenie.stan_pociagu.value} | Zadana prędkość: {v_docelowe} px/s")

    print("\n3. Postój trwa przez 2 sekundy:")
    for step in range(2):
        v_docelowe = sledzenie.aktualizuj_logike_rozkladu(1.0, "T02", graf, max_predkosc)
        print(f"   [t={step+1}s] Stan: {sledzenie.stan_pociagu.value} | Zadana prędkość: {v_docelowe} px/s")

    print("\n4. Upływa 3. sekunda postoju:")
    v_docelowe = sledzenie.aktualizuj_logike_rozkladu(1.0, "T02", graf, max_predkosc)
    print(f"   Stan: {sledzenie.stan_pociagu.value} | Zadana prędkość: {v_docelowe} px/s")