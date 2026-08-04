import pygame as py
import math
from typing import Dict
import config
from Graf import MenedzerGrafu
from Menedzer_pociagow import MenedzerPociagow
from Loader import Skaler
from Wezly import WezelSemafora, WezelZwrotnicy, Sygnal, Zwrot

# Kolory
KOLORY = {
    "TLO": (30, 30, 30),
    "SIATKA": (50, 50, 50),
    "TOR": (150, 150, 150),
    "TOR_AKTYWNY": (50, 220, 100),       # Jasnozielony dla aktywnego toru zwrotnicy
    "TOR_NIEAKTYWNY": (80, 80, 80),      # Przyciemniony dla odgałęzienia nieaktywnego
    "POCIAG": (50, 150, 255),
    "STACJA": (100, 100, 200, 100),       # Z kanałem alpha
    "TEKST": (255, 255, 255),
    Sygnal.CZERWONY: (255, 50, 50),
    Sygnal.ZIELONY: (50, 255, 50),
    Sygnal.ZOLTY: (255, 255, 50),
    Sygnal.SZ: (250, 250, 250)
}

class SilnikGraficzny:
    """Klasa odpowiedzialna za rysowanie makiety i pociągów przy użyciu Pygame"""

    def __init__(self, szerokosc: int, wysokosc: int, skaler: Skaler):
        py.init()
        self.ekran = py.display.set_mode((szerokosc, wysokosc))
        py.display.set_caption("Symulator Makiety Kolejowej")

        self.skaler = skaler
        self.czcionka = py.font.SysFont("arial", 12)
        self.czcionka_duza = py.font.SysFont("arial", 16, bold=True)

        self.powierzchnia_alfa = py.Surface((szerokosc, wysokosc), py.SRCALPHA)

    def rysuj_siatke(self, szerokosc: int, wysokosc: int) -> None:
        """Rysuje siatkę dzielącą przestrzeń na kafelki"""
        rozmiar = self.skaler.rozmiar_kafelka_px
        for x in range(0, szerokosc, rozmiar):
            py.draw.line(self.ekran, KOLORY["SIATKA"], (x, 0), (x, wysokosc))
        for y in range(0, wysokosc, rozmiar):
            py.draw.line(self.ekran, KOLORY["SIATKA"], (0, y), (szerokosc, y))

    def _wyciagnij_wezel_cel(self, element, graf: MenedzerGrafu):
        """Pomocnicza metoda bezpiecznie odczytująca węzeł docelowy."""
        if element is None:
            return None

        if isinstance(element, (tuple, list)) and len(element) > 0:
            element = element[0]

        if isinstance(element, str):
            return graf.wezly.get(element)

        if isinstance(element, dict):
            id_cel = element.get("id_cel") or element.get("cel") or element.get("id")
            return graf.wezly.get(id_cel) if id_cel else None

        for attr in ["id_cel", "cel", "id_wezel", "id"]:
            if hasattr(element, attr):
                val = getattr(element, attr)
                if isinstance(val, str):
                    return graf.wezly.get(val)

        if hasattr(element, "x") and hasattr(element, "y"):
            return element

        return None

    def _wyciagnij_aktywny_cel_zwrotnicy(self, wezel: WezelZwrotnicy, graf: MenedzerGrafu):
        """Określa, który węzeł docelowy odpowiada aktualnemu ustawieniu zwrotnicy."""
        # 1. Sprawdzanie bezpośredniego atrybutu aktywnego celu
        for attr in ["aktywne_id_cel", "aktywny_cel", "id_cel_aktywny"]:
            if hasattr(wezel, attr):
                val = getattr(wezel, attr)
                res = self._wyciagnij_wezel_cel(val, graf)
                if res:
                    return res

        # 2. Sprawdzanie relacji Zwrot -> polaczenie
        zwrot = getattr(wezel, "pozycja", getattr(wezel, "zwrot", getattr(wezel, "stan", None)))
        galezie = getattr(wezel, "polaczenia_zwrotnicy", getattr(wezel, "zwroty", getattr(wezel, "galezie", None)))

        if zwrot is not None and isinstance(galezie, dict):
            cel = galezie.get(zwrot)
            res = self._wyciagnij_wezel_cel(cel, graf)
            if res:
                return res

        # 3. Metody zwrotnicy
        for method_name in ["pobierz_aktywne_polaczenie", "pobierz_aktywny_wezel"]:
            if hasattr(wezel, method_name):
                try:
                    res = self._wyciagnij_wezel_cel(getattr(wezel, method_name)(), graf)
                    if res:
                        return res
                except TypeError:
                    pass

        return None

    def rysuj_infrastrukture(self, graf: MenedzerGrafu) -> None:
        """Rysuje tory, zwrotnice, perony i semafory."""
        rozmiar = self.skaler.rozmiar_kafelka_px
        self.powierzchnia_alfa.fill((0, 0, 0, 0))

        # 1. Stacje (tło)
        for stacja in graf.stacje.values():
            for id_toru in stacja.id_torow:
                wezel = graf.wezly.get(id_toru)
                if wezel:
                    x_px = wezel.x * rozmiar
                    y_px = wezel.y * rozmiar
                    py.draw.rect(self.powierzchnia_alfa, KOLORY["STACJA"], (x_px, y_px, rozmiar, rozmiar))
        self.ekran.blit(self.powierzchnia_alfa, (0, 0))

        # 2. Tory i Zwrotnice
        for wezel in graf.wezly.values():
            x_srodek, y_srodek = self.skaler.siatka_na_ekran(wezel.x, wezel.y)

            if isinstance(wezel, WezelZwrotnicy):
                # Odczytanie aktualnego stanu zwrotnicy z pola self.pozycja
                stan = getattr(wezel, "pozycja", getattr(wezel, "zwrot", getattr(wezel, "stan", Zwrot.PLUS)))
                stan_str = str(stan.name if hasattr(stan, "name") else stan).upper()
                czy_plus_aktywny = "MINUS" not in stan_str

                # --- 2A. Połączenia w stanie PLUS ---
                polaczenia_plus = getattr(wezel, "polaczenia_plus", {})
                for p in polaczenia_plus.values():
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel, y_cel = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        self._rysuj_strzalke(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR_AKTYWNY"] if czy_plus_aktywny else KOLORY["TOR_NIEAKTYWNY"],
                            rozmiar_grotu=10 if czy_plus_aktywny else 6,
                            grubosc=3 if czy_plus_aktywny else 1
                        )

                # --- 2B. Połączenia w stanie MINUS ---
                polaczenia_minus = getattr(wezel, "polaczenia_minus", {})
                for p in polaczenia_minus.values():
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel, y_cel = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        czy_aktywny = not czy_plus_aktywny
                        self._rysuj_strzalke(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR_AKTYWNY"] if czy_aktywny else KOLORY["TOR_NIEAKTYWNY"],
                            rozmiar_grotu=10 if czy_aktywny else 6,
                            grubosc=3 if czy_aktywny else 1
                        )

                # Wyróżnienie środka zwrotnicy fioletowym pierścieniem
                py.draw.circle(self.ekran, (200, 100, 200), (int(x_srodek), int(y_srodek)), 6, 2)

            else:
                # --- 2C. Zwykły tor ---
                polaczenia = getattr(wezel, "polaczenia", {})
                kolekcja = polaczenia.values() if isinstance(polaczenia, dict) else (
                    polaczenia if isinstance(polaczenia, (list, tuple, set)) else []
                )

                for p in kolekcja:
                    wezel_cel = self._wyciagnij_wezel_cel(p, graf)
                    if wezel_cel:
                        x_cel, y_cel = self.skaler.siatka_na_ekran(wezel_cel.x, wezel_cel.y)
                        self._rysuj_strzalke(
                            start=(x_srodek, y_srodek),
                            cel=(x_cel, y_cel),
                            kolor=KOLORY["TOR"],
                            rozmiar_grotu=8,
                            grubosc=2
                        )

            # Debugowe etykiety ID
            if config.DEBUG_MODE:
                id_txt = getattr(wezel, "id_wezel", getattr(wezel, "id", ""))
                tekst = self.czcionka.render(str(id_txt), True, KOLORY["TEKST"])
                self.ekran.blit(tekst, (x_srodek - 10, y_srodek - 15))

        # 3. Semafory
        for semafor in graf.semafory.values():
            wezel_toru = graf.wezly.get(semafor.id_toru)
            if wezel_toru:
                x, y = self.skaler.siatka_na_ekran(wezel_toru.x, wezel_toru.y)
                kolor = KOLORY.get(semafor.sygnal, KOLORY["TEKST"])
                py.draw.circle(self.ekran, kolor, (int(x + 10), int(y - 10)), 6)
                py.draw.circle(self.ekran, (0, 0, 0), (int(x + 10), int(y - 10)), 6, 1)

    def rysuj_pociagi(self, menedzer_pociagow: MenedzerPociagow) -> None:
        """Rysuje pociągi na makiecie."""
        rozmiar = self.skaler.rozmiar_kafelka_px

        for pociag in menedzer_pociagow.pociagi.values():
            if not pociag.id_zajetych_kafelkow:
                continue

            for i, id_kafelka in enumerate(pociag.id_zajetych_kafelkow):
                wezel = menedzer_pociagow.graf.wezly.get(id_kafelka)
                if wezel:
                    x, y = self.skaler.siatka_na_ekran(wezel.x, wezel.y)

                    jest_poczatkiem = (i == len(pociag.id_zajetych_kafelkow) - 1)
                    kolor = KOLORY["POCIAG"] if jest_poczatkiem else (30, 100, 200)

                    szer, wys = rozmiar * 0.6, rozmiar * 0.6
                    prostokat = py.Rect(0, 0, szer, wys)
                    prostokat.center = (x, y)

                    py.draw.rect(self.ekran, kolor, prostokat)
                    py.draw.rect(self.ekran, (0, 0, 0), prostokat, 2)

                    if jest_poczatkiem:
                        tekst = self.czcionka_duza.render(pociag.id_pociagu, True, KOLORY["TEKST"])
                        self.ekran.blit(tekst, (x - 12, y - 8))

    def renderuj_klatke(self, graf: MenedzerGrafu, menedzer_pociagow: MenedzerPociagow, czas_symulacji: str) -> None:
        """Funkcja wywoływana co klatkę w pętli."""
        self.ekran.fill(KOLORY["TLO"])

        szerokosc = self.ekran.get_width()
        wysokosc = self.ekran.get_height()

        self.rysuj_siatke(szerokosc, wysokosc)
        self.rysuj_infrastrukture(graf)
        self.rysuj_pociagi(menedzer_pociagow)

        tekst_czasu = self.czcionka_duza.render(f"Czas: {czas_symulacji}", True, KOLORY["TEKST"])
        self.ekran.blit(tekst_czasu, (10, 10))

        py.display.flip()

    def zamknij(self) -> None:
        py.quit()

    def _rysuj_strzalke(self, start, cel, kolor, rozmiar_grotu=8, margines=12, grubosc=2):
        """Rysuje linię ze strzałką od punktu start do cel."""
        x1, y1 = start
        x2, y2 = cel

        dx = x2 - x1
        dy = y2 - y1
        dlugosc = math.hypot(dx, dy)

        if dlugosc == 0:
            return

        if dlugosc <= margines:
            margines = dlugosc * 0.3

        udx = dx / dlugosc
        udy = dy / dlugosc

        koniec_x = x2 - udx * margines
        koniec_y = y2 - udy * margines

        # 1. Główna linia toru
        py.draw.line(self.ekran, kolor, (int(x1), int(y1)), (int(koniec_x), int(koniec_y)), grubosc)

        # 2. Grot strzałki
        kat = math.atan2(dy, dx)
        kat_skrzydla = math.radians(25)

        p1 = (
            int(koniec_x - rozmiar_grotu * math.cos(kat - kat_skrzydla)),
            int(koniec_y - rozmiar_grotu * math.sin(kat - kat_skrzydla))
        )
        p2 = (
            int(koniec_x - rozmiar_grotu * math.cos(kat + kat_skrzydla)),
            int(koniec_y - rozmiar_grotu * math.sin(kat + kat_skrzydla))
        )
        p_koniec = (int(koniec_x), int(koniec_y))

        py.draw.polygon(self.ekran, kolor, [p_koniec, p1, p2])