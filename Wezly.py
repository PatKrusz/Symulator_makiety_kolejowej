# Infrastruktura i graf szlakowy

from enum import Enum
from typing import Dict, Optional, Tuple, List
import config

class Sygnal(Enum):
    CZERWONY = "CZERWONY"
    ZOLTY = "ZOLTY"
    ZIELONY = "ZIELONY"
    SZ = "SZ" # Sygnał zastępczy/awaryjny

class Zwrot(Enum):
    PLUS = "PLUS" # Na wprost
    MINUS = "MINUS" # W lewo lub w prawo, w zależności od konstrukcji zwrotnicy 

class Kierunek(Enum):
    POLNOC = "POLNOC"
    POLUDNIE = "POLUDNIE"
    WSCHOD = "WSCHOD"
    ZACHOD = "ZACHOD"
    POLNOC_WSCHOD = "POLNOC_WSCHOD"
    POLNOC_ZACHOD = "POLNOC_ZACHOD"
    POLUDNIE_WSCHOD = "POLUDNIE_WSCHOD"
    POLUDNIE_ZACHOD = "POLUDNIE_ZACHOD"


def kierunek_przeciwny(kierunek: Kierunek) -> Optional[Kierunek]:
    przeciwne = {
        Kierunek.POLNOC: Kierunek.POLUDNIE,
        Kierunek.POLUDNIE: Kierunek.POLNOC,
        Kierunek.WSCHOD: Kierunek.ZACHOD,
        Kierunek.ZACHOD: Kierunek.WSCHOD,
        Kierunek.POLNOC_WSCHOD: Kierunek.POLUDNIE_ZACHOD,
        Kierunek.POLUDNIE_ZACHOD: Kierunek.POLNOC_WSCHOD,
        Kierunek.POLNOC_ZACHOD: Kierunek.POLUDNIE_WSCHOD,
        Kierunek.POLUDNIE_WSCHOD: Kierunek.POLNOC_ZACHOD,
    }
    return przeciwne.get(kierunek)

class WezelGrafu:
    """ Podstawowa klasa węzła grafu reprezentująca pojedynczy kafelek toru"""
    def __init__(self, id_wezel: str, x_siatka: int, y_siatka: int):
        self.id_wezel = id_wezel
        self.x = x_siatka
        self.y = y_siatka

        # Zajętość węzła (czy jest zajęty przez pociąg)
        self.zajety = False
        self.pociag_id: Optional[str] = None  # ID pociągu zajmującego węzeł, jeśli jest zajęty

        # Słownik sąsiadów węzła, gdzie kluczem jest kierunek z którego można dojść do węzła, a wartością jest docelowy węzeł i kierunek wejścia do niego
        self.polaczenia: Dict[Kierunek, Tuple[str, Kierunek]] = {}

    def dodaj_polaczenie(self, kierunek_wejscia: Kierunek, id_cel: str, kierunek_wejscia_cel: Kierunek) -> None:
        """Dodaje połączenie do sąsiedniego węzła grafu."""
        self.polaczenia[kierunek_wejscia] = (id_cel, kierunek_wejscia_cel)
        if config.DEBUG_MODE:
            print(f"[DEBUG] Dodano połączenie węzła '{self.id_wezel}': {kierunek_wejscia} -> {id_cel} ({kierunek_wejscia_cel})")

    def nastepny_wezel(self, kierunek_wejscia: Kierunek, raportuj_awarie: bool = True) -> Optional[Tuple[str, Kierunek]]:
        """Zwraca ID następnego węzła i kierunek wejścia do niego dla pociągu wjeżdżającego z podanego kierunku."""
        polaczenie = self.polaczenia.get(kierunek_wejscia)
        if polaczenie is not None:
            return polaczenie

        # Fallback dla łuków: jeśli klucze są zapisane tak, że kierunek "powrotny"
        # jest opisany stroną przeciwną, wybierz drugą gałąź jako kontynuację.
        if len(self.polaczenia) >= 2:
            przeciwny = kierunek_przeciwny(kierunek_wejscia)
            if przeciwny is not None and przeciwny in self.polaczenia:
                for kierunek_kandydujacy, pol_kandydujace in self.polaczenia.items():
                    if kierunek_kandydujacy != przeciwny:
                        return pol_kandydujace

        return None

class WezelZwrotnicy(WezelGrafu):
    """ Klasa reprezentująca zwrotnicę. Przełącza połączenia w zależności od ustawienia zwrotnicy (PLUS lub MINUS) """
    def __init__(self, id_wezel: str, x_siatka: int, y_siatka: int):
        super().__init__(id_wezel, x_siatka, y_siatka)
        self.pozycja = Zwrot.PLUS  # Domyślne ustawienie zwrotnicy
        self.blokada = False  # Flaga blokady dla ryglowania przez sterownik

        self.polaczenia_plus: Dict[Kierunek, Tuple[str, Kierunek]] = {}
        self.polaczenia_minus: Dict[Kierunek, Tuple[str, Kierunek]] = {}

        # Nowy model geometrii zwrotnicy.
        self.kierunek_glowny: Optional[Kierunek] = None
        self.kierunek_zwrotny_plus: Optional[Kierunek] = None
        self.kierunek_zwrotny_minus: Optional[Kierunek] = None
        self.polaczenie_glowne: Optional[Tuple[str, Kierunek]] = None
        self.polaczenie_zwrotne_plus: Optional[Tuple[str, Kierunek]] = None
        self.polaczenie_zwrotne_minus: Optional[Tuple[str, Kierunek]] = None

        self.stan_awaryjny: bool = False
        self.licznik_rozpruc: int = 0
        self._awaria_do_raportu: bool = False

    def ustaw_pozycje(self, nowa_pozycja: Zwrot, wymuszenie: bool = False) -> bool:
        """Ustawia pozycję zwrotnicy. Jeśli wymuszenie jest True, ignoruje blokadę. Zwraca True jeśli ustawienie się powiodło, False jeśli nie (np. z powodu blokady)."""
        if self.blokada and not wymuszenie:
            if config.DEBUG_MODE:
                print(f"[DEBUG] Próba ustawienia zwrotnicy '{self.id_wezel}' na {nowa_pozycja}, ale jest zablokowana.")
            return False  # Nie można zmienić ustawienia, zwrotnica jest zablokowana

        self.pozycja = nowa_pozycja
        if config.DEBUG_MODE:
            print(f"[DEBUG] Zwrotnica '{self.id_wezel}' ustawiona na {self.pozycja.value}.")
        return True

    def wyczysc_awarie(self) -> None:
        self.stan_awaryjny = False

    def pobierz_i_wyczysc_flage_awarii(self) -> bool:
        if self._awaria_do_raportu:
            self._awaria_do_raportu = False
            return True
        return False

    def ustaw_geometrie(
        self,
        kierunek_glowny: Optional[Kierunek],
        kierunek_zwrotny_plus: Optional[Kierunek],
        kierunek_zwrotny_minus: Optional[Kierunek],
        polaczenie_glowne: Optional[Tuple[str, Kierunek]],
        polaczenie_zwrotne_plus: Optional[Tuple[str, Kierunek]],
        polaczenie_zwrotne_minus: Optional[Tuple[str, Kierunek]],
    ) -> None:
        self.kierunek_glowny = kierunek_glowny
        self.kierunek_zwrotny_plus = kierunek_zwrotny_plus
        self.kierunek_zwrotny_minus = kierunek_zwrotny_minus
        self.polaczenie_glowne = polaczenie_glowne
        self.polaczenie_zwrotne_plus = polaczenie_zwrotne_plus
        self.polaczenie_zwrotne_minus = polaczenie_zwrotne_minus

    def _zbuduj_geometrie_legacy(self) -> None:
        if self.kierunek_glowny is not None:
            return

        if self.polaczenia_plus:
            self.kierunek_glowny, self.polaczenie_zwrotne_plus = next(iter(self.polaczenia_plus.items()))

        if self.polaczenia_minus:
            kandydat_kier, kandydat_pol = next(iter(self.polaczenia_minus.items()))
            if self.kierunek_glowny is None:
                self.kierunek_glowny = kandydat_kier
                self.polaczenie_zwrotne_minus = kandydat_pol
            elif kandydat_kier == self.kierunek_glowny:
                self.polaczenie_zwrotne_minus = kandydat_pol
            else:
                self.kierunek_zwrotny_minus = kandydat_kier
                self.polaczenie_glowne = kandydat_pol

        if self.kierunek_glowny is not None:
            self.kierunek_zwrotny_plus = self.kierunek_zwrotny_plus or self.kierunek_glowny
            self.kierunek_zwrotny_minus = self.kierunek_zwrotny_minus or self.kierunek_glowny
            if self.polaczenie_zwrotne_plus is None and self.polaczenie_zwrotne_minus is not None:
                self.polaczenie_zwrotne_plus = self.polaczenie_zwrotne_minus
            if self.polaczenie_zwrotne_minus is None and self.polaczenie_zwrotne_plus is not None:
                self.polaczenie_zwrotne_minus = self.polaczenie_zwrotne_plus

        if self.polaczenie_glowne is None:
            for kierunek, polaczenie in self.polaczenia_plus.items():
                if self.kierunek_glowny is not None and kierunek != self.kierunek_glowny:
                    self.kierunek_zwrotny_plus = kierunek
                    self.polaczenie_glowne = polaczenie
                    break
            if self.polaczenie_glowne is None:
                for kierunek, polaczenie in self.polaczenia_minus.items():
                    if self.kierunek_glowny is not None and kierunek != self.kierunek_glowny:
                        self.kierunek_zwrotny_minus = kierunek
                        self.polaczenie_glowne = polaczenie
                        break

    @staticmethod
    def _kierunek_przeciwny(kierunek: Kierunek) -> Optional[Kierunek]:
        return kierunek_przeciwny(kierunek)

    def _oznacz_rozprucie(self, kierunek_wejscia: Kierunek, raportuj_awarie: bool) -> None:
        if not raportuj_awarie:
            return
        self.stan_awaryjny = True
        self._awaria_do_raportu = True
        self.licznik_rozpruc += 1
        if config.DEBUG_MODE:
            print(f"[DEBUG] Rozprucie zwrotnicy '{self.id_wezel}' przy wjezdzie z {kierunek_wejscia.name}.")

    def nastepny_wezel(self, kierunek_wejscia: Kierunek, raportuj_awarie: bool = True) -> Optional[Tuple[str, Kierunek]]:
        """Przeciaża metodę z klasy bazowej, aby zwracać połączenia w zależności od ustawienia zwrotnicy."""
        self._zbuduj_geometrie_legacy()

        # Format edytora: klucze połączeń opisują kierunki wyjścia ze zwrotnicy.
        # Kierunek pociągu na wejściu opisuje więc stronę przeciwną.
        strona_wejscia = self._kierunek_przeciwny(kierunek_wejscia)
        wspolne_kierunki = [k for k in self.polaczenia_plus if k in self.polaczenia_minus]
        kierunek_wspolny = wspolne_kierunki[0] if wspolne_kierunki else None
        kierunek_plus_unikalny = next((k for k in self.polaczenia_plus if k != kierunek_wspolny), None)
        kierunek_minus_unikalny = next((k for k in self.polaczenia_minus if k != kierunek_wspolny), None)

        if strona_wejscia is not None and kierunek_wspolny is not None:
            # Wjazd od strony wspólnej: wybór toru zależy od nastawy, bez rozprucia.
            if strona_wejscia == kierunek_wspolny:
                if self.pozycja == Zwrot.PLUS and kierunek_plus_unikalny is not None:
                    return self.polaczenia_plus.get(kierunek_plus_unikalny)
                if self.pozycja == Zwrot.MINUS and kierunek_minus_unikalny is not None:
                    return self.polaczenia_minus.get(kierunek_minus_unikalny)

            # Wjazd od gałęzi PLUS: wyjście na wspólną; rozprucie przy nastawie MINUS.
            if strona_wejscia == kierunek_plus_unikalny:
                if self.pozycja != Zwrot.PLUS:
                    self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
                return self.polaczenia_plus.get(kierunek_wspolny) or self.polaczenia_minus.get(kierunek_wspolny)

            # Wjazd od gałęzi MINUS: wyjście na wspólną; rozprucie przy nastawie PLUS.
            if strona_wejscia == kierunek_minus_unikalny:
                if self.pozycja != Zwrot.MINUS:
                    self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
                return self.polaczenia_minus.get(kierunek_wspolny) or self.polaczenia_plus.get(kierunek_wspolny)

        # Fallback: gdy konfiguracja jest niepełna, użyj bezpośredniego dopasowania klucza.
        pol_plus = self.polaczenia_plus.get(kierunek_wejscia)
        pol_minus = self.polaczenia_minus.get(kierunek_wejscia)
        if pol_plus is not None and pol_minus is not None:
            return pol_plus if self.pozycja == Zwrot.PLUS else pol_minus
        if pol_plus is not None:
            if self.pozycja != Zwrot.PLUS:
                self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
            return pol_plus
        if pol_minus is not None:
            if self.pozycja != Zwrot.MINUS:
                self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
            return pol_minus

        if self.kierunek_glowny is not None:
            if kierunek_wejscia == self.kierunek_glowny:
                if self.pozycja == Zwrot.PLUS:
                    return self.polaczenie_zwrotne_plus or self.polaczenie_zwrotne_minus
                return self.polaczenie_zwrotne_minus or self.polaczenie_zwrotne_plus

            if kierunek_wejscia == self.kierunek_zwrotny_plus and self.kierunek_zwrotny_plus is not None:
                self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
                return self.polaczenia_plus.get(kierunek_wejscia) or self.polaczenie_glowne

            if kierunek_wejscia == self.kierunek_zwrotny_minus and self.kierunek_zwrotny_minus is not None:
                self._oznacz_rozprucie(kierunek_wejscia, raportuj_awarie)
                return self.polaczenia_minus.get(kierunek_wejscia) or self.polaczenie_glowne

        # Fallback kompatybilności ze starszym modelem.
        if self.pozycja == Zwrot.PLUS:
            return self.polaczenia_plus.get(kierunek_wejscia, None)
        return self.polaczenia_minus.get(kierunek_wejscia, None)

class WezelSemafora:
    """Klasa reprezentująca semafor. Jest powiązana z konkretnym kafelkiem toru i kierunkiem ruchu. Semafor może zmieniać sygnał (CZERWONY, ZOLTY, ZIELONY, SZ) i blokować ruch pociągów w zależności od sygnału."""
    def __init__(self, id_semafora: str, id_toru: str, kierunek_semafora: Kierunek):
        self.id_semafora = id_semafora
        self.id_toru = id_toru
        self.kierunek_sem = kierunek_semafora # Kierunek z którego nadjeżdża pociąg
        self.sygnal: Sygnal = Sygnal.CZERWONY  # Domyślny sygnał semafora

    def ustaw_sygnal(self, nowy_sygnal: Sygnal) -> None:
        """Ustawia sygnał semafora na nowy sygnał."""
        self.sygnal = nowy_sygnal
        if config.DEBUG_MODE:
            print(f"[DEBUG] Semafor '{self.id_semafora}' ustawiony na sygnał: {self.sygnal.value}")

class ObszarStacji:
    """Klasa reprezentująca obszar stacji. Jest powiązana z grupą kafelków"""
    def __init__(self, id_stacji: str, nazwa_stacji: str, id_torow: List[str]):
        self.id_stacji = id_stacji
        self.nazwa_stacji = nazwa_stacji
        self.id_torow = id_torow  # Lista ID torów wchodzących w skład peronu