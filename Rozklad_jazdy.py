# Rozkład jazdy dla pociągów

import datetime
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
    nazwa_stacji: str
    czas_postoju: float = 30 # Czas postoju w sekundach symulacji
    czas_przyjazdu: Optional[str] = None
    czas_odjazdu: Optional[str] = None

    @property
    def id_stacji(self) -> str:
        # Zgodność wsteczna: starszy kod mógł czytać id_stacji.
        return self.nazwa_stacji

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

    @staticmethod
    def _czas_hhmmss(czas_txt: str) -> Optional[datetime.time]:
        txt = str(czas_txt or "").strip()
        if not txt:
            return None

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.datetime.strptime(txt, fmt).time()
            except ValueError:
                continue
        return None

    def _czy_minal_czas_odjazdu(
        self,
        obecny_czas_symulacji: Optional[datetime.datetime],
        planowany_odjazd: Optional[str],
    ) -> bool:
        if not planowany_odjazd:
            return True
        if obecny_czas_symulacji is None:
            # Brak zegara symulacji: zachowaj stare zachowanie (tylko czas postoju).
            return True

        czas_docelowy = self._czas_hhmmss(planowany_odjazd)
        if czas_docelowy is None:
            return True

        return obecny_czas_symulacji.time() >= czas_docelowy

    def nazwa_docelowej_stacji(self) -> Optional[str]:
        """Zwraca nazwę bieżącej stacji docelowej z rozkładu lub None."""
        if not self.rozklad or self.rozklad.czy_koniec():
            return None

        przystanek = self.rozklad.aktualny_przystanek()
        return przystanek.nazwa_stacji if przystanek else None

    def id_docelowej_stacji(self) -> Optional[str]:
        # Zgodność wsteczna: stare API zwracało "id", teraz zwracamy nazwę stacji.
        return self.nazwa_docelowej_stacji()

    def aktualizuj_stan_postoju(
        self,
        delta_czasu_symulacji: float,
        pociag: Pociag,
        czy_na_stacji_docelowej: bool,
        czy_na_koncu_stacji_docelowej: bool = False,
        obecny_czas_symulacji: Optional[datetime.datetime] = None,
    ) -> Optional[float]:
        """
        Aktualizuje stan rozkładu niezależnie od logiki "patrzenia w przód".

        Zwraca:
        - 0.0 / predkosc_max_pxs gdy rozkład wymusza konkretną prędkość,
        - None gdy decyzja o prędkości ma zostać podjęta przez logikę szlakową.
        """
        if not self.rozklad or self.rozklad.czy_koniec():
            self.stan_pociagu = StanPociagu.KONIEC_TRASY
            return pociag.predkosc_max_pxs

        obecny_przystanek = self.rozklad.aktualny_przystanek()
        if not obecny_przystanek:
            self.stan_pociagu = StanPociagu.JAZDA
            return pociag.predkosc_max_pxs

        # Trwający postój na stacji.
        if self.stan_pociagu == StanPociagu.POSTOJ:
            self.zegar_postoju += delta_czasu_symulacji

            postoj_zakonczony = self.zegar_postoju >= obecny_przystanek.czas_postoju
            odjazd_dozwolony_czasowo = self._czy_minal_czas_odjazdu(
                obecny_czas_symulacji,
                obecny_przystanek.czas_odjazdu,
            )

            if postoj_zakonczony and odjazd_dozwolony_czasowo:
                if config.DEBUG_MODE:
                    print(f"[DEBUG] Odjazd ze stacji {obecny_przystanek.nazwa_stacji}")
                self.zegar_postoju = 0.0
                self.rozklad.nastepny_przystanek()
                self.stan_pociagu = StanPociagu.JAZDA
                return pociag.predkosc_max_pxs
            return 0.0

        # Czoło pociągu już znajduje się na stacji docelowej.
        if czy_na_stacji_docelowej:
            if not czy_na_koncu_stacji_docelowej:
                self.stan_pociagu = StanPociagu.HAMOWANIE
                return None

            if pociag.predkosc_aktualna_pxs == 0.0:
                self.stan_pociagu = StanPociagu.POSTOJ
                self.zegar_postoju = 0.0
                return 0.0

            self.stan_pociagu = StanPociagu.HAMOWANIE
            return 0.0

        self.stan_pociagu = StanPociagu.JAZDA
        return None

    def aktualizuj_logike_rozkladu(
        self, delta_czasu_symulacji: float, pociag: Pociag, graf: MenedzerGrafu) -> float:
        """Zachowana kompatybilność starego API. Logika szlakowa jest w MenedzerPociagow."""
        nazwa_docelowej_stacji = self.nazwa_docelowej_stacji()
        stacja_docelowa = next(
            (s for s in graf.stacje.values() if s.nazwa_stacji == nazwa_docelowej_stacji),
            None,
        ) if nazwa_docelowej_stacji else None
        id_przodu = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else None
        czy_na_stacji_docelowej = bool(stacja_docelowa and id_przodu in stacja_docelowa.id_torow)

        wynik = self.aktualizuj_stan_postoju(
            delta_czasu_symulacji,
            pociag,
            czy_na_stacji_docelowej,
            czy_na_koncu_stacji_docelowej=czy_na_stacji_docelowej,
        )
        return pociag.predkosc_max_pxs if wynik is None else wynik

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

    stop = Przystanek("Stacja Główna", 3.0)
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