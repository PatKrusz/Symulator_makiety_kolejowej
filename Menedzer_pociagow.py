from typing import Dict, List, Optional
from Pociag import Pociag
from Rozklad_jazdy import SledzenieRozkladu
from Graf import MenedzerGrafu
from Wezly import Sygnal
import config

class MenedzerPociagow:
    """Połączenie pociągów z grafiką i fizyką. Nadzoruje ruch, zapobiega kolizjom i aktualizuje rozkłady."""
    def __init__(self, graf: MenedzerGrafu):
        self.graf: MenedzerGrafu = graf
        self.pociagi: Dict[str, Pociag] = {}
        self.sledzenie_rozkladow: Dict[str, SledzenieRozkladu] = {}

    def dodaj_pociag(self, pociag: Pociag, sledzenie_rozkladu: Optional[SledzenieRozkladu] = None) -> None:
        """Dodaje nowy pociąg do symulacji"""
        self.pociagi[pociag.id_pociagu] = pociag
        if sledzenie_rozkladu:
            self.sledzenie_rozkladow[pociag.id_pociagu] = sledzenie_rozkladu
        if config.DEBUG_MODE:
            print(f"[DEBUG] Zarejestrowano pociąg: {pociag.id_pociagu}")

    def aktualizuj(self, delta_czasu_symulacji: float) -> List[tuple]:
        """
        Główna funkcja aktualizująca dla wszystkich pociągów.
        Zwraca listę wszystkich zdarzeń infrastrukturalnych
        """
        wszystkie_zdarzenia = []

        for id_pociagu, pociag in self.pociagi.items():
            if not pociag.sprawny or pociag.uszkodzony:
                continue

            id_kafelka_przod = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else None
            if not id_kafelka_przod:
                continue

            # 1. ODCZYT Z ROZKŁADU JAZDY
            predkosc_docelowa = pociag.predkosc_max_pxs
            sledzenie = self.sledzenie_rozkladow.get(id_pociagu)

            if sledzenie:
                # Uwaga: Przekazujemy teraz obiekt pociąg zamiast samego ID
                predkosc_docelowa = sledzenie.aktualizuj_logike_rozkladu(
                    delta_czasu_symulacji, pociag, self.graf
                )

            # 2. REAKCJA NA SEMAFORY
            sygnal = self.graf.odczytaj_najblizszy_semafor(id_kafelka_przod, pociag.aktualny_kierunek)
            
            if sygnal == Sygnal.CZERWONY:
                # Wymuszamy zatrzymanie, ignorując rozkład
                predkosc_docelowa = 0.0
            elif sygnal == Sygnal.ZOLTY:
                # Ograniczenie prędkości
                predkosc_docelowa = min(predkosc_docelowa, pociag.predkosc_max_pxs * 0.5)
            
            pociag.predkosc_docelowa_pxs = predkosc_docelowa

            # 3. AKTUALIZACJA FIZYKI
            zdarzenia_pociagu = pociag.aktualizuj_fizyke(delta_czasu_symulacji, self.graf)
            wszystkie_zdarzenia.extend(zdarzenia_pociagu)

            if config.DEBUG_MODE:
                print(f"[DEBUG] Prędkość docelowa pociągu {pociag.id_pociagu}: {pociag.predkosc_docelowa_pxs}")
                print(f"[DEBUG] Prędkość aktualna pociągu {pociag.id_pociagu}: {pociag.predkosc_aktualna_pxs}")

        return wszystkie_zdarzenia