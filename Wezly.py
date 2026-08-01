from enum import Enum
from typing import Dict, Optional, Tuple, List

global DEBUG_MODE

# Infrastruktura i graf szlakowy

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
        if DEBUG_MODE:
            print(f"[DEBUG] Dodano połączenie węzła '{self.id_wezel}': {kierunek_wejscia} -> {id_cel} ({kierunek_wejscia_cel})")

    def nastepny_wezel(self, kierunek_wejscia: Kierunek) -> Optional[Tuple[str, Kierunek]]:
        """Zwraca ID następnego węzła i kierunek wejścia do niego dla pociągu wjeżdżającego z podanego kierunku."""
        return self.polaczenia.get(kierunek_wejscia, None)

class WezelZwrotnicy(WezelGrafu):
    """ Klasa reprezentująca zwrotnicę. Przełącza połączenia w zależności od ustawienia zwrotnicy (PLUS lub MINUS) """
    def __init__(self, id_wezel: str, x_siatka: int, y_siatka: int):
        super().__init__(id_wezel, x_siatka, y_siatka)
        self.pozycja = Zwrot.PLUS  # Domyślne ustawienie zwrotnicy
        self.blokada = False  # Flaga blokady dla ryglowania przez sterownik

        self.polaczenia_plus: Dict[Kierunek, Tuple[str, Kierunek]] = {}
        self.polaczenia_minus: Dict[Kierunek, Tuple[str, Kierunek]] = {}

    def ustaw_pozycje(self, nowa_pozycja: Zwrot, wymuszenie: bool = False) -> bool:
        """Ustawia pozycję zwrotnicy. Jeśli wymuszenie jest True, ignoruje blokadę. Zwraca True jeśli ustawienie się powiodło, False jeśli nie (np. z powodu blokady)."""
        if self.blokada and not wymuszenie:
            if DEBUG_MODE:
                print(f"[DEBUG] Próba ustawienia zwrotnicy '{self.id_wezel}' na {nowa_pozycja}, ale jest zablokowana.")
            return False  # Nie można zmienić ustawienia, zwrotnica jest zablokowana

        self.pozycja = nowa_pozycja
        if DEBUG_MODE:
            print(f"[DEBUG] Zwrotnica '{self.id_wezel}' ustawiona na {self.pozycja.value}.")
        return True

    def nastepny_wezel(self, kierunek_wejscia: Kierunek) -> Optional[Tuple[str, Kierunek]]:
        """Przeciaża metodę z klasy bazowej, aby zwracać połączenia w zależności od ustawienia zwrotnicy."""
        if self.pozycja == Zwrot.PLUS:
            return self.polaczenia_plus.get(kierunek_wejscia, None)
        else:
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
        if DEBUG_MODE:
            print(f"[DEBUG] Semafor '{self.id_semafora}' ustawiony na sygnał: {self.sygnal.value}")

class ObszarStacji:
    """Klasa reprezentująca obszar stacji. Jest powiązana z grupą kafelków"""
    def __init__(self, id_stacji: str, nazwa_stacji: str, id_torow: List[str]):
        self.id_stacji = id_stacji
        self.nazwa_stacji = nazwa_stacji
        self.id_torow = id_torow  # Lista ID torów wchodzących w skład peronu