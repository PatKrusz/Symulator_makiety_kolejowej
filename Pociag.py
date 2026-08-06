# Pociąg

from collections import deque
from typing import List, Optional, Tuple
import config
from Wezly import WezelGrafu, WezelZwrotnicy, Kierunek, Sygnal
from Graf import MenedzerGrafu
from Loader import Skaler

class Pociag:
    """
    Klasa reprezentująca autonomiczny skład pociągu w symulacji.
    Posiada własną fizykę (ruch oraz masę), oraz zarządza zajmowanymi kafelkami (rozmiar)
    """
    def __init__(self, id_pociagu: str, typ_pociagu: str, masa: float, predkosc_max_kmh: float, przyspieszenie_ms2: float, hamowanie_ms2: float, dlugosc_w_kafelkach: int, skaler: Skaler):
        self.id_pociagu: str = id_pociagu
        self.typ_pociagu: str = typ_pociagu
        if masa <= 0.0:
            raise ValueError("Masa pociagu musi byc dodatnia.")
        self.masa: float = masa  # mnożnik fizyczny, może wpływać na przyspieszenie i hamowanie
        self.predkosc_max_kmh: float = predkosc_max_kmh
        self.przyspieszenie_ms2: float = przyspieszenie_ms2
        self.hamowanie_ms2: float = hamowanie_ms2
        self.dlugosc_w_kafelkach: int = dlugosc_w_kafelkach  # liczba kafelków zajmowanych przez pociąg

        # Prędkość i przyspieszenie w pikselach na sekundę i pikselach na sekundę kwadratową
        self.skaler: Skaler = skaler
        self.predkosc_max_pxs: float = skaler.kmh_na_pxs(predkosc_max_kmh)
        self.przyspieszenie_pxs2: float = skaler.ms2_na_pxs2(przyspieszenie_ms2)
        self.hamowanie_pxs2: float = skaler.ms2_na_pxs2(hamowanie_ms2)

        # Aktualny stan pociągu
        self.predkosc_aktualna_pxs: float = 0.0  # aktualna prędkość w px/s
        self.predkosc_docelowa_pxs: float = 0.0  # prędkość docelowa w px/s, do której pociąg dąży
        self.narzucona_predkosc_max_pxs: Optional[float] = None  # limit narzucony przez sterownik

        # Efektywne przyspieszenie i hamowanie, uwzględniające masę pociągu
        self.efektywne_przyspieszenie_pxs2: float = self.przyspieszenie_pxs2 / self.masa
        self.efektywne_hamowanie_pxs2: float = self.hamowanie_pxs2 / self.masa

        # Pozycja pociągu w grafie (ID węzła i kierunek wejścia)
        # zajete_kafelki działa jak kolejka FIFO
        self.id_zajetych_kafelkow: deque[Tuple[str, Kierunek]] = deque()
        self.aktualny_kierunek: Kierunek = Kierunek.ZACHOD  # Kierunek, w którym pociąg się porusza

        # Dystans w obrębie aktualnego kafelka w pikselach
        self.dystans_w_kafelku_px: float = 0.0  # odległość od początku kafelka w pikselach

        # Flagi stanu pociągu
        self.sprawny: bool = True  # czy pociąg jest sprawny
        self.uszkodzony: bool = False  # czy pociąg jest uszkodzony
        self.wymuszony_postoj: bool = False  # zatrzymanie ręczne w trybie symulacji
        self.zatrzymaj_na_koncu_biezacego_kafelka: bool = False  # precyzyjny postój na końcu toru/stacji

    def utworz_pociag(self, id_pierwszego_kafelka: str, kierunek_wejscia: Kierunek, graf: MenedzerGrafu) -> None:
        """Umieszcza pociąg na podanym kafelku makiety"""
        self.aktualny_kierunek = kierunek_wejscia
        self.id_zajetych_kafelkow.append(id_pierwszego_kafelka)

        # Oznacz węzeł jako zajęty przez pociąg
        if id_pierwszego_kafelka in graf.wezly:
            wezel = graf.wezly[id_pierwszego_kafelka]
            wezel.zajety = True
            wezel.pociag_id = self.id_pociagu
            if config.DEBUG_MODE:
                print(f"[DEBUG] Pociąg {self.id_pociagu} utworzony na kafelku {id_pierwszego_kafelka} w kierunku {kierunek_wejscia}.")
        else:
            raise ValueError(f"Kafelek o ID '{id_pierwszego_kafelka}' nie istnieje w grafie.")

    def _czy_zatrzymac_na_koncu_biezacego_kafelka(self, graf: MenedzerGrafu) -> bool:
        if self.zatrzymaj_na_koncu_biezacego_kafelka:
            return True

        if not self.id_zajetych_kafelkow:
            return False

        id_kafelka_przodu = self.id_zajetych_kafelkow[-1]
        semafor = graf.semafory_dla_wezlow.get((id_kafelka_przodu, self.aktualny_kierunek))
        if not semafor:
            return False

        if semafor.sygnal == Sygnal.CZERWONY:
            return self._czy_moze_wyhamowac_na_biezacym_kafelku()

        if semafor.sygnal == Sygnal.SZ:
            if self.typ_pociagu.strip().upper() in {"TECHNICZNY", "TECH", "RATOWNICZY"}:
                return False
            return self._czy_moze_wyhamowac_na_biezacym_kafelku()

        return False

    def _czy_moze_wyhamowac_na_biezacym_kafelku(self) -> bool:
        pozostaly_dystans_px = max(0.0, self.skaler.rozmiar_kafelka_px - self.dystans_w_kafelku_px)
        if self.efektywne_hamowanie_pxs2 <= 0.0:
            return False
        droga_hamowania_px = (self.predkosc_aktualna_pxs ** 2) / (2.0 * self.efektywne_hamowanie_pxs2)
        return droga_hamowania_px <= pozostaly_dystans_px + 0.001

    def ustaw_kierunek_ruchu(self, nowy_kierunek: Kierunek, graf: MenedzerGrafu, sprawdz_przejazd: bool = True) -> bool:
        """Ustawia kierunek ruchu pociągu; opcjonalnie sprawdza, czy istnieje przejazd z czoła pociągu."""
        if sprawdz_przejazd and self.id_zajetych_kafelkow:
            id_kafelka_przodu = self.id_zajetych_kafelkow[-1]
            kafelek_przodu = graf.wezly.get(id_kafelka_przodu)
            if not kafelek_przodu:
                return False
            if not kafelek_przodu.nastepny_wezel(nowy_kierunek, raportuj_awarie=False):
                return False

        self.aktualny_kierunek = nowy_kierunek
        return True

    def aktualizuj_fizyke(self, delta_czasu_symulacji: float, graf: MenedzerGrafu) -> List[Tuple[str, str]]:
        """Aktualizuje prędkość i pozycję pociągu w symulacji na podstawie upływu czasu symulacji. Zwraca listę zdarzeń związanych z infrastrukturą (np. zajęcie lub zwolnienie kafelków)."""
        zdarzenia = []
        
        if delta_czasu_symulacji <= 0 or not self.sprawny:
            return zdarzenia

        # Zmiana prędkości
        if self.predkosc_aktualna_pxs < self.predkosc_docelowa_pxs:
            self.predkosc_aktualna_pxs += self.efektywne_przyspieszenie_pxs2 * delta_czasu_symulacji
            if self.predkosc_aktualna_pxs > self.predkosc_docelowa_pxs:
                self.predkosc_aktualna_pxs = self.predkosc_docelowa_pxs
        elif self.predkosc_aktualna_pxs > self.predkosc_docelowa_pxs:
            self.predkosc_aktualna_pxs -= self.efektywne_hamowanie_pxs2 * delta_czasu_symulacji
            if self.predkosc_aktualna_pxs < self.predkosc_docelowa_pxs:
                self.predkosc_aktualna_pxs = self.predkosc_docelowa_pxs

        # Jeśli pociąg stoi w miejscu, nie przeliczamy pozycji
        if self.predkosc_aktualna_pxs == 0.0:
            return []

        # Obliczanie przemieszczenia w pikselach dla aktualnej klatki symulacji
        przemieszczenie_px = self.predkosc_aktualna_pxs * delta_czasu_symulacji
        self.dystans_w_kafelku_px += przemieszczenie_px

        # Sprawdzenie, czy pociąg przesunął się do następnego kafelka
        rozmiar_kafelka_px = self.skaler.rozmiar_kafelka_px
        if self.dystans_w_kafelku_px >= rozmiar_kafelka_px:
            id_kafelka_przodu = self.id_zajetych_kafelkow[-1] if self.id_zajetych_kafelkow else None
            semafor_na_przodzie = None
            if id_kafelka_przodu:
                semafor_na_przodzie = graf.semafory_dla_wezlow.get((id_kafelka_przodu, self.aktualny_kierunek))

            if semafor_na_przodzie and semafor_na_przodzie.sygnal == Sygnal.CZERWONY and not self._czy_moze_wyhamowac_na_biezacym_kafelku():
                zdarzenia.append(("przejazd_na_czerwonym", semafor_na_przodzie.id_semafora))

            if self._czy_zatrzymac_na_koncu_biezacego_kafelka(graf):
                self.dystans_w_kafelku_px = rozmiar_kafelka_px - 0.001
                if self.predkosc_docelowa_pxs <= 0.0:
                    self.predkosc_aktualna_pxs = 0.0
                return zdarzenia

            self.dystans_w_kafelku_px -= rozmiar_kafelka_px

            # pobieramy kafelek z przodu pociągu
            id_kafelka_przodu = self.id_zajetych_kafelkow[-1]
            kafelek_przodu = graf.wezly.get(id_kafelka_przodu)
            if kafelek_przodu:
                nastepny = kafelek_przodu.nastepny_wezel(self.aktualny_kierunek)
                if nastepny:
                    id_nastepnego_kafelka, kierunek_nastepnego = nastepny

                    self.id_zajetych_kafelkow.append(id_nastepnego_kafelka)
                    self.aktualny_kierunek = kierunek_nastepnego

                    # Oznacz nowy węzeł jako zajęty przez pociąg
                    nowy_wezel = graf.wezly[id_nastepnego_kafelka]
                    if nowy_wezel:
                        nowy_wezel.zajety = True
                        nowy_wezel.pociag_id = self.id_pociagu
                    zdarzenia.append(("zajety", id_nastepnego_kafelka))

                    # Zwolnij węzeł z tyłu pociągu, jeśli pociąg przesunął się o pełen kafelek
                    if len(self.id_zajetych_kafelkow) > self.dlugosc_w_kafelkach:
                        id_kafelka_tylu = self.id_zajetych_kafelkow.popleft()
                        wezel_tylu = graf.wezly[id_kafelka_tylu]
                        if wezel_tylu:
                            wezel_tylu.zajety = False
                            wezel_tylu.pociag_id = None
                        zdarzenia.append(("zwolniony", id_kafelka_tylu))

                    if isinstance(kafelek_przodu, WezelZwrotnicy) and kafelek_przodu.pobierz_i_wyczysc_flage_awarii():
                        zdarzenia.append(("zwrotnica_rozpruta", kafelek_przodu.id_wezel))
                else:
                    # Brak następnego węzła - koniec toru lub brak połączenia
                    if config.DEBUG_MODE:
                        print(f"[DEBUG] Pociąg {self.id_pociagu} osiągnął koniec toru na kafelku {id_kafelka_przodu}.")

        return zdarzenia

## Test jednostkowy dla klasy Pociag z fizyką i zajetością kafelków
if __name__ == "__main__":
    config.DEBUG_MODE = True

    skaler = Skaler(skala_w_metrach=10, rozmiar_kafelka_px=48)
    graf = MenedzerGrafu()

    for i in range(1, 5):
        id_wezel = f"T0{i}"
        graf.dodaj_wezel(WezelGrafu(id_wezel, x_siatka=i, y_siatka=0))

    graf.wezly["T01"].dodaj_polaczenie(Kierunek.ZACHOD, "T02", Kierunek.ZACHOD)
    graf.wezly["T02"].dodaj_polaczenie(Kierunek.ZACHOD, "T03", Kierunek.ZACHOD)
    graf.wezly["T03"].dodaj_polaczenie(Kierunek.ZACHOD, "T04", Kierunek.ZACHOD)

    pociag = Pociag(id_pociagu="P1", typ_pociagu="Towarowy", masa=2.5, predkosc_max_kmh=80, przyspieszenie_ms2=0.2, hamowanie_ms2=0.35, dlugosc_w_kafelkach=2, skaler=skaler)

    pociag.utworz_pociag(id_pierwszego_kafelka="T01", kierunek_wejscia=Kierunek.ZACHOD, graf=graf)
    pociag.predkosc_docelowa_pxs = skaler.kmh_na_pxs(40)

    print(f"Test jednostkowy: Pociąg {pociag.id_pociagu} utworzony na kafelku T01, docelowa prędkość: 40 km/h")

    for i in range(1,51):
        zdarzenia = pociag.aktualizuj_fizyke(delta_czasu_symulacji=0.5, graf=graf)
        szybkość_kmh = skaler.pxs_na_kmh(pociag.predkosc_aktualna_pxs)
        zajete_str = " -> ".join(pociag.id_zajetych_kafelkow)
        print(f"Symulacja {i}: Prędkość: {szybkość_kmh:.2f} km/h, Zajęte kafelki: {zajete_str}, Zdarzenia: {zdarzenia}")

    print(f"Koniec")