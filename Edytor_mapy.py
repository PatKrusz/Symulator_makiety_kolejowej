import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pygame as py

from Graf import MenedzerGrafu
from Loader import Skaler
from Wezly import Kierunek, ObszarStacji, Sygnal, WezelGrafu, WezelSemafora, WezelZwrotnicy, Zwrot


PANEL_SZEROKOSC = 420
TOOLBAR_WYSOKOSC = 34
WIERSZ_WYSOKOSC = 24
ROZKLAD_WIDOCZNE_WIERSZE = 4
WLASCIWOSCI_SCROLL_KROK = 28
NAPIS_KOLOR = (245, 245, 245)
TLO_PANELU = (16, 18, 24)
TLO_SEKCJI = (28, 32, 42)
TLO_POLE = (44, 48, 62)
TLO_POLE_AKTYWNE = (72, 84, 112)
AKCENT = (255, 192, 92)
AKCENT_2 = (100, 210, 255)


@dataclass
class EdytorKomunikat:
    tresc: str = ""
    licznik_klatek: int = 0


@dataclass
class PoleFormularza:
    klucz: str
    etykieta: str
    typ: str
    wartosc: str
    opcje: List[str] = field(default_factory=list)


class EdytorMapy:
    """Wewnętrzny edytor mapy z panelem bocznym i prostą edycją właściwości."""

    def __init__(self, projekt: Optional[Dict[str, Any]] = None, sciezka_zapisu: str = "sim_config_edytor.json"):
        self.aktywny: bool = False
        self.tryb: str = "select"
        self.branch_mode: str = "PLUS"
        self.branch_mode_docelowy: str = "PLUS"
        self.wybrany_rodzaj: Optional[str] = None
        self.wybrany_id: Optional[str] = None
        self.wybrany_pociag_id: Optional[int] = None
        self._licznik_nowych_wezlow = 1
        self._licznik_nowych_semaforow = 1
        self._licznik_nowych_stacji = 1
        self._licznik_nowych_pociagow = 1
        self._drag_start_node: Optional[str] = None
        self._szybkie_laczenie_start: Optional[str] = None
        self.wybrany_rozklad_wiersz: int = 0

        self.projekt: Dict[str, Any] = copy.deepcopy(projekt) if projekt else {}
        self.projekt.setdefault("ustawienia_symulacji", {})
        self.projekt.setdefault("pociagi", [])
        self.projekt.setdefault("infrastruktura", {})

        self.sciezka_zapisu = Path(sciezka_zapisu)
        self.komunikat = EdytorKomunikat()
        self.formularz: List[PoleFormularza] = []
        self.aktywne_pole: int = -1
        self.bufor_tekstu: str = ""

        self._toolbar_rects: Dict[str, py.Rect] = {}
        self._lista_rects: List[Tuple[str, str, int, py.Rect]] = []
        self._pole_rects: List[py.Rect] = []
        self._przycisk_rects: Dict[str, py.Rect] = {}
        self._rozklad_wiersze_rects: List[Tuple[int, py.Rect]] = []
        self._rozklad_widok_rect: Optional[py.Rect] = None
        self._rozklad_scroll: int = 0
        self._wlasciwosci_widok_rect: Optional[py.Rect] = None
        self._wlasciwosci_scroll: int = 0
        self._wlasciwosci_wysokosc_tresci: int = 0
        self._lista_scroll: int = 0
        self._lista_widok_rect: Optional[py.Rect] = None
        self._wersja_zmian: int = 0

        self.draft_station_tracks: List[str] = []

    def przelacz(self) -> bool:
        self.aktywny = not self.aktywny
        self.tryb = "select"
        self.wybrany_rodzaj = None
        self.wybrany_id = None
        self.wybrany_pociag_id = None
        self.formularz = []
        self.aktywne_pole = -1
        self.bufor_tekstu = ""
        self.wybrany_rozklad_wiersz = 0
        self._rozklad_scroll = 0
        self._wlasciwosci_scroll = 0
        self._szybkie_laczenie_start = None
        self.ustaw_komunikat(f"Tryb edycji: {'wlaczony' if self.aktywny else 'wylaczony'}")
        return self.aktywny

    def _przewin_wlasciwosci(self, delta: int) -> bool:
        if self._wlasciwosci_widok_rect is None:
            return False

        widoczna_wysokosc = max(1, self._wlasciwosci_widok_rect.height)
        max_scroll = max(0, self._wlasciwosci_wysokosc_tresci - widoczna_wysokosc)
        poprzedni = self._wlasciwosci_scroll
        self._wlasciwosci_scroll = max(0, min(max_scroll, self._wlasciwosci_scroll + delta))
        return self._wlasciwosci_scroll != poprzedni

    def ustaw_komunikat(self, tresc: str, czas_zycia: int = 180) -> None:
        self.komunikat = EdytorKomunikat(tresc=tresc, licznik_klatek=czas_zycia)

    def _oznacz_zmiane(self) -> None:
        self._wersja_zmian += 1

    @property
    def wersja_zmian(self) -> int:
        return self._wersja_zmian

    def _spadek_komunikatu(self) -> None:
        if self.komunikat.licznik_klatek > 0:
            self.komunikat.licznik_klatek -= 1
            if self.komunikat.licznik_klatek <= 0:
                self.komunikat.tresc = ""

    def _graniczny_projekt(self) -> None:
        self.projekt.setdefault("ustawienia_symulacji", {})
        self.projekt.setdefault("pociagi", [])
        self.projekt.setdefault("infrastruktura", {})

    def _klik_na_siatce(self, pos: Tuple[int, int], skaler: Skaler) -> Tuple[int, int]:
        x, y = pos
        return int(x // skaler.rozmiar_kafelka_px), int(y // skaler.rozmiar_kafelka_px)

    def _pozycja_swiata(
        self,
        pos: Tuple[int, int],
        ekran_na_swiat: Optional[Callable[[float, float], Tuple[float, float]]],
    ) -> Tuple[int, int]:
        if ekran_na_swiat is None:
            return pos
        x_swiat, y_swiat = ekran_na_swiat(float(pos[0]), float(pos[1]))
        return int(x_swiat), int(y_swiat)

    def _mapuj_kierunek(self, dx: int, dy: int) -> Optional[Kierunek]:
        if dx == 1 and dy == 0:
            return Kierunek.ZACHOD
        if dx == -1 and dy == 0:
            return Kierunek.WSCHOD
        if dx == 0 and dy == 1:
            return Kierunek.POLNOC
        if dx == 0 and dy == -1:
            return Kierunek.POLUDNIE
        if dx == 1 and dy == 1:
            return Kierunek.POLNOC_ZACHOD
        if dx == 1 and dy == -1:
            return Kierunek.POLUDNIE_ZACHOD
        if dx == -1 and dy == 1:
            return Kierunek.POLNOC_WSCHOD
        if dx == -1 and dy == -1:
            return Kierunek.POLUDNIE_WSCHOD
        return None

    def _nastepne_id(self, prefix: str, istniejące: List[str]) -> str:
        licznik = 1
        while True:
            kandydat = f"{prefix}{licznik:02d}"
            if kandydat not in istniejące:
                return kandydat
            licznik += 1

    def _wezel_pod_wskaznikiem(
        self,
        pos: Tuple[int, int],
        skaler: Skaler,
        graf: MenedzerGrafu,
        ekran_na_swiat: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> Optional[WezelGrafu]:
        pos_swiata = self._pozycja_swiata(pos, ekran_na_swiat)
        x_siatka, y_siatka = self._klik_na_siatce(pos_swiata, skaler)
        return graf.znajdz_wezel_po_wspolrzednych(x_siatka, y_siatka)

    def _dodaj_lub_przeformuj_wezel(self, graf: MenedzerGrafu, x_siatka: int, y_siatka: int, jako_zwrotnica: bool) -> WezelGrafu:
        istniejący = graf.znajdz_wezel_po_wspolrzednych(x_siatka, y_siatka)
        if istniejący and not jako_zwrotnica:
            return istniejący

        if istniejący and jako_zwrotnica:
            nowa = WezelZwrotnicy(istniejący.id_wezel, x_siatka, y_siatka)
            nowa.polaczenia_plus = dict(istniejący.polaczenia)
            self._przelicz_geometrie_zwrotnicy_z_polaczen(nowa)
            graf.usun_wezel(istniejący.id_wezel)
            graf.dodaj_wezel(nowa)
            self._oznacz_zmiane()
            return nowa

        if jako_zwrotnica:
            nowy_id = self._nastepne_id("Z", list(graf.wezly.keys()))
            nowa = WezelZwrotnicy(nowy_id, x_siatka, y_siatka)
            graf.dodaj_wezel(nowa)
            self._oznacz_zmiane()
            return nowa

        nowy_id = self._nastepne_id("T", list(graf.wezly.keys()))
        nowa = WezelGrafu(nowy_id, x_siatka, y_siatka)
        graf.dodaj_wezel(nowa)
        self._oznacz_zmiane()
        return nowa

    def _dodaj_pelny_semafor(self, graf: MenedzerGrafu, tor_id: str) -> WezelSemafora:
        istniejące = list(graf.semafory.keys())
        nowy_id = self._nastepne_id("S", istniejące)
        semafor = WezelSemafora(nowy_id, tor_id, Kierunek.ZACHOD)
        semafor.ustaw_sygnal(Sygnal.CZERWONY)
        graf.dodaj_semafor(semafor)
        self._oznacz_zmiane()
        return semafor

    def _dodaj_lub_aktualizuj_stacje(self, graf: MenedzerGrafu) -> Optional[str]:
        if not self.draft_station_tracks:
            return "Nie wybrano torow dla peronu/stacji."

        nowa_nazwa = f"Peron {self._licznik_nowych_stacji:02d}"
        if self.wybrany_rodzaj == "stacja" and self.wybrany_id and self.wybrany_id in graf.stacje:
            stacja = graf.stacje[self.wybrany_id]
            stacja.id_torow = list(self.draft_station_tracks)
            self._oznacz_zmiane()
            if self.formularz:
                self._wypelnij_formularz_dla_aktualnego(graf)
            return None

        nowy_id = self._nastepne_id("ST", list(graf.stacje.keys()))
        stacja = ObszarStacji(nowy_id, nowa_nazwa, list(self.draft_station_tracks))
        graf.dodaj_stacje(stacja)
        self._licznik_nowych_stacji += 1
        self._oznacz_zmiane()
        return None

    def _dodaj_pociag_do_projektu(self, x_siatka: int, y_siatka: int) -> Dict[str, Any]:
        nowy_id = self._nastepne_id("P", [p.get("id", "") for p in self.projekt["pociagi"]])
        pociag = {
            "id": nowy_id,
            "typ": "OSOBOWY",
            "max_predkosc_kmh": 80.0,
            "przyspieszenie_bazowe": 0.8,
            "hamowanie_bazowe": 0.8,
            "masa": 1.0,
            "dlugosc": 2,
            "pozycja_startowa": {"x": x_siatka, "y": y_siatka},
            "kierunek_startowy": Kierunek.ZACHOD.name,
            "rozklad": [],
        }
        self.projekt["pociagi"].append(pociag)
        self._licznik_nowych_pociagow += 1
        self._oznacz_zmiane()
        return pociag

    def _znajdz_pociag_index(self) -> Optional[int]:
        if self.wybrany_rodzaj != "pociag" or self.wybrany_pociag_id is None:
            return None
        if 0 <= self.wybrany_pociag_id < len(self.projekt["pociagi"]):
            return self.wybrany_pociag_id
        return None

    def _aktualny_obiekt(self, graf: MenedzerGrafu) -> Optional[Any]:
        if self.wybrany_rodzaj in {"wezel", "zwrotnica"} and self.wybrany_id:
            return graf.wezly.get(self.wybrany_id)
        if self.wybrany_rodzaj == "semafor" and self.wybrany_id:
            return graf.semafory.get(self.wybrany_id)
        if self.wybrany_rodzaj == "stacja" and self.wybrany_id:
            return graf.stacje.get(self.wybrany_id)
        if self.wybrany_rodzaj == "pociag":
            idx = self._znajdz_pociag_index()
            if idx is not None:
                return self.projekt["pociagi"][idx]
        return None

    def _wybierz_obiekt(self, kind: str, ident: Any, graf: MenedzerGrafu) -> None:
        self.wybrany_rodzaj = kind
        self.wybrany_id = ident if isinstance(ident, str) else None
        self.wybrany_pociag_id = ident if kind == "pociag" and isinstance(ident, int) else None
        self._wypelnij_formularz_dla_aktualnego(graf, reset_scroll=True)

    def _wypelnij_formularz_dla_aktualnego(self, graf: MenedzerGrafu, reset_scroll: bool = False) -> None:
        obiekt = self._aktualny_obiekt(graf)
        self.formularz = []
        self.aktywne_pole = -1
        self.bufor_tekstu = ""
        if reset_scroll:
            self._wlasciwosci_scroll = 0

        if obiekt is None:
            return

        if isinstance(obiekt, WezelZwrotnicy):
            self.wybrany_rodzaj = "zwrotnica"
            opcje_kierunkow = ["-"] + [e.name for e in Kierunek]
            self.formularz = [
                PoleFormularza("id", "ID", "text", obiekt.id_wezel),
                PoleFormularza("x", "X", "int", str(obiekt.x)),
                PoleFormularza("y", "Y", "int", str(obiekt.y)),
                PoleFormularza("pozycja", "Pozycja", "choice", obiekt.pozycja.name, [e.name for e in Zwrot]),
                PoleFormularza("kierunek_glowny", "Kier. glowny", "choice", obiekt.kierunek_glowny.name if obiekt.kierunek_glowny else "-", opcje_kierunkow),
                PoleFormularza("kierunek_zwrotny_plus", "Zwrotny PLUS", "choice", obiekt.kierunek_zwrotny_plus.name if obiekt.kierunek_zwrotny_plus else "-", opcje_kierunkow),
                PoleFormularza("kierunek_zwrotny_minus", "Zwrotny MINUS", "choice", obiekt.kierunek_zwrotny_minus.name if obiekt.kierunek_zwrotny_minus else "-", opcje_kierunkow),
                PoleFormularza("stan_awaryjny", "Awaria", "choice", "TAK" if obiekt.stan_awaryjny else "NIE", ["NIE", "TAK"]),
            ]
            return

        if isinstance(obiekt, WezelGrafu):
            self.wybrany_rodzaj = "wezel"
            self.formularz = [
                PoleFormularza("id", "ID", "text", obiekt.id_wezel),
                PoleFormularza("x", "X", "int", str(obiekt.x)),
                PoleFormularza("y", "Y", "int", str(obiekt.y)),
            ]
            return

        if isinstance(obiekt, WezelSemafora):
            self.wybrany_rodzaj = "semafor"
            self.formularz = [
                PoleFormularza("id", "ID", "text", obiekt.id_semafora),
                PoleFormularza("id_toru", "Tor", "text", obiekt.id_toru),
                PoleFormularza("kierunek_sem", "Kierunek", "choice", obiekt.kierunek_sem.name, [e.name for e in Kierunek]),
                PoleFormularza("sygnal", "Sygnał", "choice", obiekt.sygnal.name, [e.name for e in Sygnal]),
            ]
            return

        if isinstance(obiekt, ObszarStacji):
            self.wybrany_rodzaj = "stacja"
            self.formularz = [
                PoleFormularza("id", "ID", "text", obiekt.id_stacji),
                PoleFormularza("nazwa", "Nazwa", "text", obiekt.nazwa_stacji),
                PoleFormularza("id_torow", "Tory", "text", ",".join(obiekt.id_torow)),
            ]
            return

        if isinstance(obiekt, dict) and "pozycja_startowa" in obiekt:
            self.wybrany_rodzaj = "pociag"
            self.formularz = [
                PoleFormularza("id", "ID", "text", str(obiekt.get("id", ""))),
                PoleFormularza("typ", "Typ", "text", str(obiekt.get("typ", ""))),
                PoleFormularza("masa", "Masa", "float", str(obiekt.get("masa", 1.0))),
                PoleFormularza("max_predkosc_kmh", "V max [km/h]", "float", str(obiekt.get("max_predkosc_kmh", 80.0))),
                PoleFormularza("przyspieszenie_bazowe", "Przysp. [m/s2]", "float", str(obiekt.get("przyspieszenie_bazowe", 0.8))),
                PoleFormularza("hamowanie_bazowe", "Ham. [m/s2]", "float", str(obiekt.get("hamowanie_bazowe", 0.8))),
                PoleFormularza("dlugosc", "Dlugosc", "int", str(obiekt.get("dlugosc", 2))),
                PoleFormularza("start_x", "Start X", "int", str(obiekt.get("pozycja_startowa", {}).get("x", 0))),
                PoleFormularza("start_y", "Start Y", "int", str(obiekt.get("pozycja_startowa", {}).get("y", 0))),
                PoleFormularza("kierunek_startowy", "Kier. start", "choice", str(obiekt.get("kierunek_startowy", Kierunek.ZACHOD.name)), [e.name for e in Kierunek]),
            ]
            self._odswiez_pola_rozkladu(graf, obiekt)

    @staticmethod
    def _normalizuj_wiersz_rozkladu(wiersz: Dict[str, Any]) -> Dict[str, Any]:
        nazwa_stacji = str(wiersz.get("nazwa_stacji") or wiersz.get("id_stacji") or "").strip()
        czas_postoju = float(wiersz.get("czas_postoju", 30.0))
        przyjazd = str(wiersz.get("przyjazd") or "").strip() or None
        odjazd = str(wiersz.get("odjazd") or "").strip() or None
        return {
            "nazwa_stacji": nazwa_stacji,
            # Klucz utrzymany dla kompatybilności ze starszym formatem.
            "id_stacji": nazwa_stacji,
            "czas_postoju": czas_postoju,
            "przyjazd": przyjazd,
            "odjazd": odjazd,
        }

    def _normalizuj_rozklad_pociagu(self, obiekt: Dict[str, Any]) -> List[Dict[str, Any]]:
        surowy = obiekt.get("rozklad", [])
        wynik: List[Dict[str, Any]] = []
        for wiersz in surowy if isinstance(surowy, list) else []:
            if isinstance(wiersz, dict):
                wynik.append(self._normalizuj_wiersz_rozkladu(wiersz))
        obiekt["rozklad"] = wynik
        return wynik

    def _nazwy_stacji(self, graf: MenedzerGrafu) -> List[str]:
        nazwy = sorted({stacja.nazwa_stacji.strip() for stacja in graf.stacje.values() if stacja.nazwa_stacji.strip()})
        if nazwy:
            return nazwy
        return sorted({stacja.id_stacji.strip() for stacja in graf.stacje.values() if stacja.id_stacji.strip()})

    def _odswiez_pola_rozkladu(self, graf: MenedzerGrafu, obiekt: Dict[str, Any]) -> None:
        klucze_rozkladu = {"rk_stacja", "rk_postoj", "rk_przyjazd", "rk_odjazd"}
        self.formularz = [pole for pole in self.formularz if pole.klucz not in klucze_rozkladu]

        rozklad = self._normalizuj_rozklad_pociagu(obiekt)
        if not rozklad:
            self.wybrany_rozklad_wiersz = 0
            self._rozklad_scroll = 0
            return

        self.wybrany_rozklad_wiersz = max(0, min(self.wybrany_rozklad_wiersz, len(rozklad) - 1))
        max_scroll = max(0, len(rozklad) - ROZKLAD_WIDOCZNE_WIERSZE)
        self._rozklad_scroll = max(0, min(self._rozklad_scroll, max_scroll))
        aktywny = rozklad[self.wybrany_rozklad_wiersz]
        nazwy_stacji = self._nazwy_stacji(graf)
        if aktywny["nazwa_stacji"] and aktywny["nazwa_stacji"] not in nazwy_stacji:
            nazwy_stacji.append(aktywny["nazwa_stacji"])

        self.formularz.extend(
            [
                PoleFormularza("rk_stacja", "Stacja", "choice", str(aktywny.get("nazwa_stacji", "")), nazwy_stacji),
                PoleFormularza("rk_postoj", "Postoj [s]", "float", str(aktywny.get("czas_postoju", 30.0))),
                PoleFormularza("rk_przyjazd", "Przyjazd", "text", str(aktywny.get("przyjazd") or "")),
                PoleFormularza("rk_odjazd", "Odjazd", "text", str(aktywny.get("odjazd") or "")),
            ]
        )

    def _ustaw_wartosc_pola(self, graf: MenedzerGrafu, pole: PoleFormularza, wartosc: str) -> Optional[str]:
        obiekt = self._aktualny_obiekt(graf)
        if obiekt is None:
            return "Brak wybranego elementu."

        try:
            if pole.klucz == "id":
                nowa_id = wartosc.strip()
                if not nowa_id:
                    return "ID nie moze byc puste."
                if self.wybrany_rodzaj in {"wezel", "zwrotnica"}:
                    if nowa_id != getattr(obiekt, "id_wezel", nowa_id) and nowa_id in graf.wezly:
                        return "Takie ID juz istnieje."
                    stary_id = obiekt.id_wezel
                    obiekt.id_wezel = nowa_id
                    if stary_id != nowa_id:
                        graf.wezly[nowa_id] = graf.wezly.pop(stary_id)
                        if isinstance(obiekt, WezelZwrotnicy):
                            graf.zwrotnice[nowa_id] = graf.zwrotnice.pop(stary_id)
                        for inny in graf.wezly.values():
                            if hasattr(inny, "polaczenia"):
                                inny.polaczenia = {
                                    k: ((nowa_id if v[0] == stary_id else v[0]), v[1])
                                    for k, v in inny.polaczenia.items()
                                }
                            if isinstance(inny, WezelZwrotnicy):
                                inny.polaczenia_plus = {k: ((nowa_id if v[0] == stary_id else v[0]), v[1]) for k, v in inny.polaczenia_plus.items()}
                                inny.polaczenia_minus = {k: ((nowa_id if v[0] == stary_id else v[0]), v[1]) for k, v in inny.polaczenia_minus.items()}
                        for semafor in graf.semafory.values():
                            if semafor.id_toru == stary_id:
                                semafor.id_toru = nowa_id
                        for stacja in graf.stacje.values():
                            stacja.id_torow = [nowa_id if t == stary_id else t for t in stacja.id_torow]
                    self._oznacz_zmiane()
                elif self.wybrany_rodzaj == "semafor":
                    if nowa_id != obiekt.id_semafora and nowa_id in graf.semafory:
                        return "Takie ID juz istnieje."
                    stary_id = obiekt.id_semafora
                    obiekt.id_semafora = nowa_id
                    graf.semafory[nowa_id] = graf.semafory.pop(stary_id)
                    for klucz, semafor in list(graf.semafory_dla_wezlow.items()):
                        if semafor.id_semafora == stary_id:
                            graf.semafory_dla_wezlow[klucz] = obiekt
                    self._oznacz_zmiane()
                elif self.wybrany_rodzaj == "stacja":
                    if nowa_id != obiekt.id_stacji and nowa_id in graf.stacje:
                        return "Takie ID juz istnieje."
                    stary_id = obiekt.id_stacji
                    obiekt.id_stacji = nowa_id
                    graf.stacje[nowa_id] = graf.stacje.pop(stary_id)
                    self._oznacz_zmiane()
                elif self.wybrany_rodzaj == "pociag":
                    idx = self._znajdz_pociag_index()
                    if idx is None:
                        return "Brak wybranego pociagu."
                    obiekt["id"] = nowa_id
                    self._oznacz_zmiane()
                return None

            if pole.klucz in {"x", "y", "start_x", "start_y"}:
                wartosc_int = int(wartosc)
                if self.wybrany_rodzaj in {"wezel", "zwrotnica"}:
                    setattr(obiekt, pole.klucz, wartosc_int)
                    self._oznacz_zmiane()
                elif self.wybrany_rodzaj == "pociag":
                    if pole.klucz == "start_x":
                        obiekt["pozycja_startowa"]["x"] = wartosc_int
                    else:
                        obiekt["pozycja_startowa"]["y"] = wartosc_int
                    self._oznacz_zmiane()
                return None

            if pole.klucz in {"masa", "max_predkosc_kmh", "przyspieszenie_bazowe", "hamowanie_bazowe"}:
                wartosc_float = float(wartosc)
                if self.wybrany_rodzaj == "pociag":
                    obiekt[pole.klucz] = wartosc_float
                    self._oznacz_zmiane()
                return None

            if pole.klucz == "dlugosc" and self.wybrany_rodzaj == "pociag":
                obiekt["dlugosc"] = int(wartosc)
                self._oznacz_zmiane()
                return None

            if self.wybrany_rodzaj == "zwrotnica" and pole.klucz == "pozycja":
                obiekt.ustaw_pozycje(Zwrot[wartosc])
                self._oznacz_zmiane()
                return None

            if self.wybrany_rodzaj == "zwrotnica" and pole.klucz in {"kierunek_glowny", "kierunek_zwrotny_plus", "kierunek_zwrotny_minus"}:
                kierunek_val = None if wartosc == "-" else Kierunek[wartosc]
                setattr(obiekt, pole.klucz, kierunek_val)
                self._oznacz_zmiane()
                return None

            if self.wybrany_rodzaj == "zwrotnica" and pole.klucz == "stan_awaryjny":
                obiekt.stan_awaryjny = wartosc == "TAK"
                self._oznacz_zmiane()
                return None

            if self.wybrany_rodzaj == "semafor":
                if pole.klucz == "id_toru":
                    obiekt.id_toru = wartosc.strip()
                    self._oznacz_zmiane()
                    return None
                if pole.klucz == "kierunek_sem":
                    obiekt.kierunek_sem = Kierunek[wartosc]
                    self._oznacz_zmiane()
                    return None
                if pole.klucz == "sygnal":
                    obiekt.ustaw_sygnal(Sygnal[wartosc])
                    self._oznacz_zmiane()
                    return None

            if self.wybrany_rodzaj == "stacja":
                if pole.klucz == "nazwa":
                    obiekt.nazwa_stacji = wartosc.strip()
                    self._oznacz_zmiane()
                    return None
                if pole.klucz == "id_torow":
                    obiekt.id_torow = [element.strip() for element in wartosc.split(",") if element.strip()]
                    self._oznacz_zmiane()
                    return None

            if self.wybrany_rodzaj == "pociag":
                if pole.klucz in {"rk_stacja", "rk_postoj", "rk_przyjazd", "rk_odjazd"}:
                    rozklad = self._normalizuj_rozklad_pociagu(obiekt)
                    if not rozklad:
                        return "Rozklad jest pusty. Dodaj pierwszy przystanek przyciskiem '+ Dodaj wiersz'."
                    idx = max(0, min(self.wybrany_rozklad_wiersz, len(rozklad) - 1))
                    wiersz = rozklad[idx]
                    if pole.klucz == "rk_stacja":
                        nazwa = wartosc.strip()
                        wiersz["nazwa_stacji"] = nazwa
                        wiersz["id_stacji"] = nazwa
                    elif pole.klucz == "rk_postoj":
                        wiersz["czas_postoju"] = float(wartosc)
                    elif pole.klucz == "rk_przyjazd":
                        txt = wartosc.strip()
                        wiersz["przyjazd"] = txt if txt else None
                    elif pole.klucz == "rk_odjazd":
                        txt = wartosc.strip()
                        wiersz["odjazd"] = txt if txt else None
                    self._odswiez_pola_rozkladu(graf, obiekt)
                    self._oznacz_zmiane()
                    return None
                obiekt[pole.klucz] = wartosc.strip()
                self._oznacz_zmiane()
                return None

        except Exception as exc:
            return f"Blad zapisu pola {pole.etykieta}: {exc}"

        return None

    def _aktywny_pole(self) -> Optional[PoleFormularza]:
        if 0 <= self.aktywne_pole < len(self.formularz):
            return self.formularz[self.aktywne_pole]
        return None

    def _sciezka_rzeczywistego_obiektu(self, graf: MenedzerGrafu) -> Optional[Any]:
        return self._aktualny_obiekt(graf)

    def _klik_toolbar(self, pos: Tuple[int, int]) -> Optional[str]:
        for nazwa, rect in self._toolbar_rects.items():
            if rect.collidepoint(pos):
                return nazwa
        return None

    def _klik_liste(self, pos: Tuple[int, int]) -> Optional[Tuple[str, Any]]:
        for kind, ident, _, rect in self._lista_rects:
            if rect.collidepoint(pos):
                return kind, ident
        return None

    def _klik_pole(self, pos: Tuple[int, int]) -> Optional[int]:
        for idx, rect in enumerate(self._pole_rects):
            if rect.collidepoint(pos):
                return idx
        return None

    def _klik_w_panelu(self, pos: Tuple[int, int]) -> bool:
        if not self._toolbar_rects:
            return False
        panel_x = min(rect.x for rect in self._toolbar_rects.values())
        return pos[0] >= panel_x

    def _wybierz_wiersz_rozkladu_po_kliknieciu(self, pos: Tuple[int, int], graf: MenedzerGrafu) -> bool:
        if self.wybrany_rodzaj != "pociag":
            return False
        for idx, rect in self._rozklad_wiersze_rects:
            if rect.collidepoint(pos):
                self.wybrany_rozklad_wiersz = idx
                obiekt = self._aktualny_obiekt(graf)
                if isinstance(obiekt, dict):
                    self._wypelnij_formularz_dla_aktualnego(graf, reset_scroll=False)
                return True
        return False

    def _przewin_rozklad(self, graf: MenedzerGrafu, delta: int) -> bool:
        obiekt = self._aktualny_obiekt(graf)
        if not isinstance(obiekt, dict):
            return False

        rozklad = self._normalizuj_rozklad_pociagu(obiekt)
        max_scroll = max(0, len(rozklad) - ROZKLAD_WIDOCZNE_WIERSZE)
        poprzedni = self._rozklad_scroll
        self._rozklad_scroll = max(0, min(max_scroll, self._rozklad_scroll + delta))
        return self._rozklad_scroll != poprzedni

    def _dodaj_wiersz_rozkladu(self, graf: MenedzerGrafu) -> Optional[str]:
        obiekt = self._aktualny_obiekt(graf)
        if not isinstance(obiekt, dict):
            return "Brak wybranego pociagu."
        rozklad = self._normalizuj_rozklad_pociagu(obiekt)
        nazwy_stacji = self._nazwy_stacji(graf)
        domyslna_nazwa = nazwy_stacji[0] if nazwy_stacji else ""
        rozklad.append(
            {
                "nazwa_stacji": domyslna_nazwa,
                "id_stacji": domyslna_nazwa,
                "czas_postoju": 30.0,
                "przyjazd": None,
                "odjazd": None,
            }
        )
        self.wybrany_rozklad_wiersz = len(rozklad) - 1
        self._rozklad_scroll = max(0, len(rozklad) - ROZKLAD_WIDOCZNE_WIERSZE)
        self._wypelnij_formularz_dla_aktualnego(graf, reset_scroll=False)
        self._oznacz_zmiane()
        return None

    def _usun_wiersz_rozkladu(self, graf: MenedzerGrafu) -> Optional[str]:
        obiekt = self._aktualny_obiekt(graf)
        if not isinstance(obiekt, dict):
            return "Brak wybranego pociagu."
        rozklad = self._normalizuj_rozklad_pociagu(obiekt)
        if not rozklad:
            return "Rozklad jest pusty."
        idx = max(0, min(self.wybrany_rozklad_wiersz, len(rozklad) - 1))
        rozklad.pop(idx)
        if not rozklad:
            self.wybrany_rozklad_wiersz = 0
            self._rozklad_scroll = 0
        else:
            self.wybrany_rozklad_wiersz = min(idx, len(rozklad) - 1)
            self._rozklad_scroll = min(self._rozklad_scroll, max(0, len(rozklad) - ROZKLAD_WIDOCZNE_WIERSZE))
        self._wypelnij_formularz_dla_aktualnego(graf, reset_scroll=False)
        self._oznacz_zmiane()
        return None

    def _przewin_liste(self, graf: MenedzerGrafu, delta: int) -> bool:
        elementy = self._lista_elementow(graf)
        if not elementy:
            return False

        max_widoczne = 5
        max_scroll = max(0, len(elementy) - max_widoczne)
        poprzedni = self._lista_scroll
        self._lista_scroll = max(0, min(max_scroll, self._lista_scroll + delta))
        return self._lista_scroll != poprzedni

    def _zastosuj_obiekt_terenowy(
        self,
        graf: MenedzerGrafu,
        pos: Tuple[int, int],
        skaler: Skaler,
        ekran_na_swiat: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> bool:
        pos_swiata = self._pozycja_swiata(pos, ekran_na_swiat)
        x_siatka, y_siatka = self._klik_na_siatce(pos_swiata, skaler)
        istniejący = graf.znajdz_wezel_po_wspolrzednych(x_siatka, y_siatka)

        if self.tryb == "node":
            if istniejący:
                self._wybierz_obiekt("wezel", istniejący.id_wezel, graf)
            else:
                nowy = self._dodaj_lub_przeformuj_wezel(graf, x_siatka, y_siatka, False)
                self._wybierz_obiekt("wezel", nowy.id_wezel, graf)
            self.ustaw_komunikat(f"Tor gotowy na ({x_siatka}, {y_siatka})")
            return True

        if self.tryb == "switch":
            if istniejący and isinstance(istniejący, WezelZwrotnicy):
                self._wybierz_obiekt("zwrotnica", istniejący.id_wezel, graf)
            else:
                nowy = self._dodaj_lub_przeformuj_wezel(graf, x_siatka, y_siatka, True)
                self._wybierz_obiekt("zwrotnica", nowy.id_wezel, graf)
            self.ustaw_komunikat("Zwrotnica ustawiona")
            return True

        if self.tryb == "signal":
            if not istniejący:
                self.ustaw_komunikat("Semafor musi byc przypiety do istniejacego toru")
                return True

            for (id_toru, _), semafor in graf.semafory_dla_wezlow.items():
                if id_toru == istniejący.id_wezel:
                    self._wybierz_obiekt("semafor", semafor.id_semafora, graf)
                    self.ustaw_komunikat(f"Wybrano semafor {semafor.id_semafora}")
                    return True

            semafor = self._dodaj_pelny_semafor(graf, istniejący.id_wezel)
            self._wybierz_obiekt("semafor", semafor.id_semafora, graf)
            self.ustaw_komunikat(f"Dodano semafor {semafor.id_semafora}")
            return True

        if self.tryb == "station":
            if not istniejący:
                self.ustaw_komunikat("Peron wymaga istniejacego toru")
                return True
            if istniejący.id_wezel in self.draft_station_tracks:
                self.draft_station_tracks.remove(istniejący.id_wezel)
                self.ustaw_komunikat(f"Usunieto {istniejący.id_wezel} ze szkicu peronu")
            else:
                self.draft_station_tracks.append(istniejący.id_wezel)
                self.ustaw_komunikat(f"Dodano {istniejący.id_wezel} do szkicu peronu")
            return True

        if self.tryb == "train":
            if not istniejący:
                self.ustaw_komunikat("Pociag musi startowac z istniejacego toru")
                return True
            pociag = self._dodaj_pociag_do_projektu(istniejący.x, istniejący.y)
            idx = len(self.projekt["pociagi"]) - 1
            self._wybierz_obiekt("pociag", idx, graf)
            self.ustaw_komunikat(f"Dodano pociag {pociag['id']} na {istniejący.id_wezel}")
            return True

        if self.tryb == "connect":
            if not istniejący:
                self.ustaw_komunikat("Polaczenia tworzy sie miedzy istniejacymi torami")
                return True
            if self._drag_start_node is None:
                self._drag_start_node = istniejący.id_wezel
                self.ustaw_komunikat(f"Wybrano poczatek polaczenia: {istniejący.id_wezel}")
            else:
                start = graf.wezly.get(self._drag_start_node)
                koniec = graf.wezly.get(istniejący.id_wezel)
                if start and koniec:
                    blad = self._utworz_polaczenie(start, koniec, graf)
                    if blad:
                        self.ustaw_komunikat(blad)
                    else:
                        self.ustaw_komunikat(f"Polaczono {start.id_wezel} z {koniec.id_wezel}")
                self._drag_start_node = None
            return True

        if self.tryb == "select" and istniejący:
            if isinstance(istniejący, WezelZwrotnicy):
                self._wybierz_obiekt("zwrotnica", istniejący.id_wezel, graf)
            else:
                self._wybierz_obiekt("wezel", istniejący.id_wezel, graf)
            self.ustaw_komunikat(f"Wybrano {istniejący.id_wezel}")
            return True

        return False

    def _obsluz_szybkie_laczenie(
        self,
        graf: MenedzerGrafu,
        pos: Tuple[int, int],
        skaler: Skaler,
        ekran_na_swiat: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> bool:
        if not (py.key.get_mods() & py.KMOD_SHIFT):
            self._szybkie_laczenie_start = None
            return False

        wezel = self._wezel_pod_wskaznikiem(pos, skaler, graf, ekran_na_swiat)
        if not wezel:
            return False

        if self._szybkie_laczenie_start is None:
            self._szybkie_laczenie_start = wezel.id_wezel
            self.ustaw_komunikat(f"Szybkie laczenie: start {wezel.id_wezel}")
            return True

        if self._szybkie_laczenie_start == wezel.id_wezel:
            return True

        start = graf.wezly.get(self._szybkie_laczenie_start)
        if not start:
            self._szybkie_laczenie_start = wezel.id_wezel
            self.ustaw_komunikat(f"Szybkie laczenie: nowy start {wezel.id_wezel}")
            return True

        blad = self._utworz_polaczenie(start, wezel, graf)
        if blad:
            self.ustaw_komunikat(blad)
        else:
            self.ustaw_komunikat(f"Polaczono {start.id_wezel} -> {wezel.id_wezel}")
            self._szybkie_laczenie_start = wezel.id_wezel
        return True

    def _utworz_polaczenie(self, wezel_a: WezelGrafu, wezel_b: WezelGrafu, graf: MenedzerGrafu) -> Optional[str]:
        dx = wezel_b.x - wezel_a.x
        dy = wezel_b.y - wezel_a.y
        if max(abs(dx), abs(dy)) != 1 or (dx == 0 and dy == 0):
            return "Polaczenie mozliwe tylko miedzy sasiednimi polami"

        kierunek_a = self._mapuj_kierunek(dx, dy)
        kierunek_b = self._mapuj_kierunek(-dx, -dy)
        if not kierunek_a or not kierunek_b:
            return "Nie udalo sie okreslic kierunku polaczenia"

        galaz_a = self.branch_mode
        galaz_b = self.branch_mode_docelowy

        if isinstance(wezel_a, WezelZwrotnicy):
            if galaz_a == "PLUS":
                wezel_a.polaczenia_plus[kierunek_a] = (wezel_b.id_wezel, kierunek_a)
            else:
                wezel_a.polaczenia_minus[kierunek_a] = (wezel_b.id_wezel, kierunek_a)
            self._aktualizuj_geometrie_zwrotnicy(wezel_a, kierunek_a, (wezel_b.id_wezel, kierunek_a))
        else:
            wezel_a.dodaj_polaczenie(kierunek_a, wezel_b.id_wezel, kierunek_a)

        if isinstance(wezel_b, WezelZwrotnicy):
            if galaz_b == "PLUS":
                wezel_b.polaczenia_plus[kierunek_b] = (wezel_a.id_wezel, kierunek_b)
            else:
                wezel_b.polaczenia_minus[kierunek_b] = (wezel_a.id_wezel, kierunek_b)
            self._aktualizuj_geometrie_zwrotnicy(wezel_b, kierunek_b, (wezel_a.id_wezel, kierunek_b))
        else:
            wezel_b.dodaj_polaczenie(kierunek_b, wezel_a.id_wezel, kierunek_b)

        return None

    def _aktualizuj_geometrie_zwrotnicy(
        self,
        zwrotnica: WezelZwrotnicy,
        kierunek_wejscia: Kierunek,
        polaczenie: Tuple[str, Kierunek],
    ) -> None:
        # Parametry zostawione dla kompatybilności wywołań; geometria jest
        # liczona całościowo z map PLUS/MINUS, żeby konfiguracja była intuicyjna.
        _ = kierunek_wejscia
        _ = polaczenie
        self._przelicz_geometrie_zwrotnicy_z_polaczen(zwrotnica)

    def _przelicz_geometrie_zwrotnicy_z_polaczen(self, zwrotnica: WezelZwrotnicy) -> None:
        plus = dict(zwrotnica.polaczenia_plus)
        minus = dict(zwrotnica.polaczenia_minus)

        if not plus and not minus:
            zwrotnica.kierunek_glowny = None
            zwrotnica.kierunek_zwrotny_plus = None
            zwrotnica.kierunek_zwrotny_minus = None
            zwrotnica.polaczenie_glowne = None
            zwrotnica.polaczenie_zwrotne_plus = None
            zwrotnica.polaczenie_zwrotne_minus = None
            return

        wspolne_kierunki = [k for k in plus.keys() if k in minus]
        kierunek_glowny = wspolne_kierunki[0] if wspolne_kierunki else None

        if kierunek_glowny is None:
            # Fallback dla niepełnej konfiguracji: zachowujemy poprzedni główny
            # jeśli pasuje, inaczej bierzemy pierwszy dostępny kierunek.
            kandydaci = list(plus.keys()) + [k for k in minus.keys() if k not in plus]
            if zwrotnica.kierunek_glowny in kandydaci:
                kierunek_glowny = zwrotnica.kierunek_glowny
            elif kandydaci:
                kierunek_glowny = kandydaci[0]

        zwrotnica.kierunek_glowny = kierunek_glowny

        zwrotnica.polaczenie_zwrotne_plus = plus.get(kierunek_glowny) if kierunek_glowny else None
        zwrotnica.polaczenie_zwrotne_minus = minus.get(kierunek_glowny) if kierunek_glowny else None

        kierunek_plus_unikalny = next((k for k in plus.keys() if k != kierunek_glowny), None)
        kierunek_minus_unikalny = next((k for k in minus.keys() if k != kierunek_glowny), None)
        zwrotnica.kierunek_zwrotny_plus = kierunek_plus_unikalny
        zwrotnica.kierunek_zwrotny_minus = kierunek_minus_unikalny

        # Połączenie do kierunku głównego (przy wjeździe od strony zwrotnej).
        pol_glowne_plus = plus.get(kierunek_plus_unikalny) if kierunek_plus_unikalny else None
        pol_glowne_minus = minus.get(kierunek_minus_unikalny) if kierunek_minus_unikalny else None
        zwrotnica.polaczenie_glowne = pol_glowne_plus or pol_glowne_minus

    def _usun_referencje_do_wezla_w_zwrotnicy(self, zwrotnica: WezelZwrotnicy, id_wezla: str) -> None:
        zwrotnica.polaczenia_plus = {k: v for k, v in zwrotnica.polaczenia_plus.items() if v[0] != id_wezla}
        zwrotnica.polaczenia_minus = {k: v for k, v in zwrotnica.polaczenia_minus.items() if v[0] != id_wezla}

        if zwrotnica.polaczenie_glowne and zwrotnica.polaczenie_glowne[0] == id_wezla:
            zwrotnica.polaczenie_glowne = None
        if zwrotnica.polaczenie_zwrotne_plus and zwrotnica.polaczenie_zwrotne_plus[0] == id_wezla:
            zwrotnica.polaczenie_zwrotne_plus = None
        if zwrotnica.polaczenie_zwrotne_minus and zwrotnica.polaczenie_zwrotne_minus[0] == id_wezla:
            zwrotnica.polaczenie_zwrotne_minus = None

        self._przelicz_geometrie_zwrotnicy_z_polaczen(zwrotnica)

    def _usun_wszystkie_polaczenia_wezla(self, graf: MenedzerGrafu, id_wezla: str) -> bool:
        wezel = graf.wezly.get(id_wezla)
        if not wezel:
            return False

        # Usuń połączenia wychodzące wskazanego węzła.
        if isinstance(wezel, WezelZwrotnicy):
            wezel.polaczenia_plus.clear()
            wezel.polaczenia_minus.clear()
            wezel.polaczenie_glowne = None
            wezel.polaczenie_zwrotne_plus = None
            wezel.polaczenie_zwrotne_minus = None
            self._przelicz_geometrie_zwrotnicy_z_polaczen(wezel)
        else:
            wezel.polaczenia.clear()

        self._oznacz_zmiane()

        # Usuń połączenia przychodzące z innych węzłów.
        for inny in graf.wezly.values():
            if isinstance(inny, WezelZwrotnicy):
                self._usun_referencje_do_wezla_w_zwrotnicy(inny, id_wezla)
            else:
                inny.polaczenia = {
                    kierunek: pol
                    for kierunek, pol in inny.polaczenia.items()
                    if pol[0] != id_wezla
                }

        return True

    def _usun_wybrany(self, graf: MenedzerGrafu) -> bool:
        if self.wybrany_rodzaj in {"wezel", "zwrotnica"} and self.wybrany_id:
            graf.usun_wezel(self.wybrany_id)
            self.wybrany_id = None
            self.wybrany_rodzaj = None
            self.formularz = []
            self._oznacz_zmiane()
            return True

        if self.wybrany_rodzaj == "semafor" and self.wybrany_id:
            graf.semafory.pop(self.wybrany_id, None)
            for klucz, semafor in list(graf.semafory_dla_wezlow.items()):
                if semafor.id_semafora == self.wybrany_id:
                    graf.semafory_dla_wezlow.pop(klucz, None)
            self.wybrany_id = None
            self.wybrany_rodzaj = None
            self.formularz = []
            self._oznacz_zmiane()
            return True

        if self.wybrany_rodzaj == "stacja" and self.wybrany_id:
            graf.stacje.pop(self.wybrany_id, None)
            self.wybrany_id = None
            self.wybrany_rodzaj = None
            self.formularz = []
            self._oznacz_zmiane()
            return True

        if self.wybrany_rodzaj == "pociag" and self.wybrany_pociag_id is not None:
            if 0 <= self.wybrany_pociag_id < len(self.projekt["pociagi"]):
                self.projekt["pociagi"].pop(self.wybrany_pociag_id)
            self.wybrany_pociag_id = None
            self.wybrany_rodzaj = None
            self.formularz = []
            self._oznacz_zmiane()
            return True

        return False

    def obsluz_zdarzenie(
        self,
        zdarzenie: py.event.Event,
        graf: MenedzerGrafu,
        skaler: Skaler,
        ekran_na_swiat: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> bool:
        if not self.aktywny:
            return False

        if zdarzenie.type == py.MOUSEBUTTONDOWN:
            if zdarzenie.button == 1:
                if self._obsluz_toolbar(zdarzenie.pos, graf):
                    return True

                klik_liste = self._klik_liste(zdarzenie.pos)
                if klik_liste:
                    kind, ident = klik_liste
                    if kind == "pociag":
                        self.wybrany_pociag_id = int(ident)
                        self.wybrany_rodzaj = "pociag"
                        self.wybrany_id = None
                    else:
                        self.wybrany_rodzaj = kind
                        self.wybrany_id = str(ident)
                        self.wybrany_pociag_id = None
                    self._wypelnij_formularz_dla_aktualnego(graf)
                    return True

                if self.wybrany_rodzaj == "pociag":
                    if "rozklad_add" in self._przycisk_rects and self._przycisk_rects["rozklad_add"].collidepoint(zdarzenie.pos):
                        blad = self._dodaj_wiersz_rozkladu(graf)
                        self.ustaw_komunikat(blad or "Dodano przystanek do rozkladu")
                        return True
                    if "rozklad_del" in self._przycisk_rects and self._przycisk_rects["rozklad_del"].collidepoint(zdarzenie.pos):
                        blad = self._usun_wiersz_rozkladu(graf)
                        self.ustaw_komunikat(blad or "Usunieto przystanek z rozkladu")
                        return True
                    if self._wybierz_wiersz_rozkladu_po_kliknieciu(zdarzenie.pos, graf):
                        self.ustaw_komunikat(f"Wybrano wiersz rozkladu #{self.wybrany_rozklad_wiersz + 1}")
                        return True

                if self._klik_pole(zdarzenie.pos) is not None:
                    idx = self._klik_pole(zdarzenie.pos)
                    if idx is not None:
                        self.aktywne_pole = idx
                        self.bufor_tekstu = self.formularz[idx].wartosc
                    return True

                if self._klik_w_panelu(zdarzenie.pos):
                    return True

                if self._obsluz_szybkie_laczenie(graf, zdarzenie.pos, skaler, ekran_na_swiat):
                    return True

                return self._zastosuj_obiekt_terenowy(graf, zdarzenie.pos, skaler, ekran_na_swiat)

            if zdarzenie.button in {4, 5}:
                if self._lista_widok_rect and self._lista_widok_rect.collidepoint(zdarzenie.pos):
                    self._przewin_liste(graf, -1 if zdarzenie.button == 4 else 1)
                    return True
                if self._wlasciwosci_widok_rect and self._wlasciwosci_widok_rect.collidepoint(zdarzenie.pos):
                    if self._przewin_wlasciwosci(-WLASCIWOSCI_SCROLL_KROK if zdarzenie.button == 4 else WLASCIWOSCI_SCROLL_KROK):
                        return True
                    return True
                if self._rozklad_widok_rect and self._rozklad_widok_rect.collidepoint(zdarzenie.pos):
                    if self._przewin_rozklad(graf, -1 if zdarzenie.button == 4 else 1):
                        return True
                    return True

            if zdarzenie.button == 3:
                if self.tryb == "connect":
                    if not self._klik_w_panelu(zdarzenie.pos):
                        wskazany = self._wezel_pod_wskaznikiem(zdarzenie.pos, skaler, graf, ekran_na_swiat)
                        if wskazany and self._usun_wszystkie_polaczenia_wezla(graf, wskazany.id_wezel):
                            self._drag_start_node = None
                            self._szybkie_laczenie_start = None
                            self.ustaw_komunikat(f"Usunieto polaczenia wezla {wskazany.id_wezel}")
                            return True
                    self._drag_start_node = None
                    self._szybkie_laczenie_start = None
                    self.ustaw_komunikat("Anulowano polaczenie")
                    return True
                if self._usun_wybrany(graf):
                    self.ustaw_komunikat("Usunieto wybrany element")
                return True

        if zdarzenie.type == py.MOUSEWHEEL:
            pozycja_myszy = py.mouse.get_pos()
            if self._lista_widok_rect and self._lista_widok_rect.collidepoint(pozycja_myszy):
                if self._przewin_liste(graf, -zdarzenie.y):
                    return True
                return True
            if self._wlasciwosci_widok_rect and self._wlasciwosci_widok_rect.collidepoint(pozycja_myszy):
                if self._przewin_wlasciwosci(-zdarzenie.y * WLASCIWOSCI_SCROLL_KROK):
                    return True
                return True
            if self._rozklad_widok_rect and self._rozklad_widok_rect.collidepoint(pozycja_myszy):
                if self._przewin_rozklad(graf, -zdarzenie.y):
                    return True
                return True

        if zdarzenie.type == py.KEYDOWN:
            czy_edytuje_pole = self.aktywne_pole >= 0 and self.aktywne_pole < len(self.formularz)

            if czy_edytuje_pole:
                pole = self.formularz[self.aktywne_pole]

                if zdarzenie.key == py.K_ESCAPE:
                    self.aktywne_pole = -1
                    self.bufor_tekstu = ""
                    self.ustaw_komunikat("Anulowano edycje pola")
                    return True

                if zdarzenie.key == py.K_TAB and self.formularz:
                    self.aktywne_pole = (self.aktywne_pole + 1) % len(self.formularz)
                    self.bufor_tekstu = self.formularz[self.aktywne_pole].wartosc
                    return True

                if zdarzenie.key == py.K_RETURN:
                    blad = self._ustaw_wartosc_pola(graf, self.formularz[self.aktywne_pole], self.bufor_tekstu)
                    if blad:
                        self.ustaw_komunikat(blad)
                    else:
                        self.formularz[self.aktywne_pole].wartosc = self.bufor_tekstu
                        self.ustaw_komunikat("Zapisano pole")
                    return True

                if zdarzenie.key == py.K_BACKSPACE:
                    self.bufor_tekstu = self.bufor_tekstu[:-1]
                    return True

                if pole.typ == "choice":
                    if zdarzenie.key in {py.K_LEFT, py.K_RIGHT} and pole.opcje:
                        idx = pole.opcje.index(self.bufor_tekstu) if self.bufor_tekstu in pole.opcje else 0
                        if zdarzenie.key == py.K_RIGHT:
                            idx = (idx + 1) % len(pole.opcje)
                        else:
                            idx = (idx - 1) % len(pole.opcje)
                        self.bufor_tekstu = pole.opcje[idx]
                        return True
                    return True

                znak = zdarzenie.unicode
                if znak:
                    if pole.typ in {"int", "float"}:
                        if znak.isdigit() or znak in {"-", "."}:
                            self.bufor_tekstu += znak
                            return True
                    elif znak.isprintable():
                        self.bufor_tekstu += znak
                        return True

                # Gdy pole jest aktywne, globalne skróty edytora są zablokowane.
                return True

            if zdarzenie.key == py.K_ESCAPE:
                self._drag_start_node = None
                self._szybkie_laczenie_start = None
                self.aktywne_pole = -1
                self.bufor_tekstu = ""
                self.ustaw_komunikat("Anulowano")
                return True

            if zdarzenie.key == py.K_TAB and self.formularz:
                self.aktywne_pole = (self.aktywne_pole + 1) % len(self.formularz)
                self.bufor_tekstu = self.formularz[self.aktywne_pole].wartosc
                return True

            if zdarzenie.key == py.K_RETURN:
                if self.aktywne_pole >= 0 and self.aktywne_pole < len(self.formularz):
                    blad = self._ustaw_wartosc_pola(graf, self.formularz[self.aktywne_pole], self.bufor_tekstu)
                    if blad:
                        self.ustaw_komunikat(blad)
                    else:
                        self.formularz[self.aktywne_pole].wartosc = self.bufor_tekstu
                        self.ustaw_komunikat("Zapisano pole")
                    return True

                if self.tryb == "station":
                    blad = self._dodaj_lub_aktualizuj_stacje(graf)
                    if blad:
                        self.ustaw_komunikat(blad)
                    else:
                        self.ustaw_komunikat("Zapisano peron/stacje")
                    return True

            if zdarzenie.key == py.K_BACKSPACE and self.aktywne_pole >= 0:
                self.bufor_tekstu = self.bufor_tekstu[:-1]
                return True

            if zdarzenie.key == py.K_DELETE:
                if self._usun_wybrany(graf):
                    self.ustaw_komunikat("Usunieto element")
                return True

            if zdarzenie.key == py.K_s and (zdarzenie.mod & py.KMOD_CTRL):
                self.zapisz_do_pliku(graf)
                return True

            if zdarzenie.key == py.K_1:
                self.tryb = "select"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: wybieranie")
                return True
            if zdarzenie.key == py.K_2:
                self.tryb = "node"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: tor")
                return True
            if zdarzenie.key == py.K_3:
                self.tryb = "switch"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: zwrotnica")
                return True
            if zdarzenie.key == py.K_4:
                self.tryb = "signal"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: semafor")
                return True
            if zdarzenie.key == py.K_5:
                self.tryb = "station"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: peron")
                return True
            if zdarzenie.key == py.K_6:
                self.tryb = "train"
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: pociag")
                return True
            if zdarzenie.key == py.K_7:
                self.tryb = "connect"
                self._drag_start_node = None
                self._szybkie_laczenie_start = None
                self.ustaw_komunikat("Tryb: laczenie")
                return True
            if zdarzenie.key == py.K_b:
                self.branch_mode = "MINUS" if self.branch_mode == "PLUS" else "PLUS"
                self.ustaw_komunikat(f"Gałąź startowej zwrotnicy: {self.branch_mode}")
                return True
            if zdarzenie.key == py.K_n:
                self.branch_mode_docelowy = "MINUS" if self.branch_mode_docelowy == "PLUS" else "PLUS"
                self.ustaw_komunikat(f"Gałąź docelowej zwrotnicy: {self.branch_mode_docelowy}")
                return True

        return False

    def _obsluz_toolbar(self, pos: Tuple[int, int], graf: MenedzerGrafu) -> bool:
        for nazwa, rect in self._toolbar_rects.items():
            if rect.collidepoint(pos):
                if nazwa == "save":
                    self.zapisz_do_pliku(graf)
                    return True
                self.tryb = nazwa
                self._drag_start_node = None
                self.ustaw_komunikat(f"Tryb: {nazwa}")
                return True

        if "draft_station_save" in self._przycisk_rects and self._przycisk_rects["draft_station_save"].collidepoint(pos):
            blad = self._dodaj_lub_aktualizuj_stacje(graf)
            if blad:
                self.ustaw_komunikat(blad)
            else:
                self.ustaw_komunikat("Zapisano peron/stacje")
            return True

        if "draft_station_clear" in self._przycisk_rects and self._przycisk_rects["draft_station_clear"].collidepoint(pos):
            self.draft_station_tracks = []
            self.ustaw_komunikat("Wyczyszczono szkic peronu")
            return True

        return False

    def zapisz_do_pliku(self, graf: MenedzerGrafu) -> None:
        self._graniczny_projekt()
        dane = copy.deepcopy(self.projekt)
        dane["infrastruktura"] = graf.eksportuj_do_slownika()
        with self.sciezka_zapisu.open("w", encoding="utf-8") as plik:
            json.dump(dane, plik, ensure_ascii=False, indent=2)
        self.ustaw_komunikat(f"Zapisano do {self.sciezka_zapisu.name}")

    def _rysuj_przycisk(self, ekran: py.Surface, rect: py.Rect, tekst: str, aktywny: bool, font: py.font.Font) -> None:
        kolor = TLO_POLE_AKTYWNE if aktywny else TLO_POLE
        py.draw.rect(ekran, kolor, rect, border_radius=6)
        py.draw.rect(ekran, AKCENT if aktywny else (90, 98, 120), rect, 1, border_radius=6)
        napis = font.render(tekst, True, NAPIS_KOLOR)
        ekran.blit(napis, (rect.x + 8, rect.y + 7))

    def _lista_elementow(self, graf: MenedzerGrafu) -> List[Tuple[str, Any, str]]:
        elementy: List[Tuple[str, Any, str]] = []
        if self.tryb in {"select", "node", "switch", "connect"}:
            for wezel in graf.wezly.values():
                if isinstance(wezel, WezelZwrotnicy):
                    elementy.append(("zwrotnica", wezel.id_wezel, f"{wezel.id_wezel} ({wezel.x},{wezel.y})"))
                else:
                    elementy.append(("wezel", wezel.id_wezel, f"{wezel.id_wezel} ({wezel.x},{wezel.y})"))

        if self.tryb == "signal":
            for semafor in graf.semafory.values():
                elementy.append(("semafor", semafor.id_semafora, f"{semafor.id_semafora} -> {semafor.id_toru}"))

        if self.tryb == "station":
            for stacja in graf.stacje.values():
                elementy.append(("stacja", stacja.id_stacji, f"{stacja.id_stacji} [{len(stacja.id_torow)} torow]"))

        if self.tryb == "train":
            for idx, pociag in enumerate(self.projekt["pociagi"]):
                elementy.append(("pociag", idx, f"{pociag.get('id', f'P{idx}')} @ {pociag.get('pozycja_startowa', {}).get('x', '?')},{pociag.get('pozycja_startowa', {}).get('y', '?')}"))

        return elementy

    def _przyciski_draft_station(self) -> Dict[str, py.Rect]:
        return self._przycisk_rects

    @staticmethod
    def _wektor_kierunku(kierunek: Kierunek) -> Tuple[float, float]:
        mapa = {
            Kierunek.POLNOC: (0.0, -1.0),
            Kierunek.POLUDNIE: (0.0, 1.0),
            Kierunek.WSCHOD: (1.0, 0.0),
            Kierunek.ZACHOD: (-1.0, 0.0),
            Kierunek.POLNOC_WSCHOD: (0.7, -0.7),
            Kierunek.POLNOC_ZACHOD: (-0.7, -0.7),
            Kierunek.POLUDNIE_WSCHOD: (0.7, 0.7),
            Kierunek.POLUDNIE_ZACHOD: (-0.7, 0.7),
        }
        return mapa.get(kierunek, (0.0, -1.0))

    def _podswietl_wybrany_na_mapie(
        self,
        ekran: py.Surface,
        graf: MenedzerGrafu,
        skaler: Skaler,
        zoom: float = 1.0,
        swiat_na_ekran: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> None:
        def _mapuj(x: float, y: float) -> Tuple[float, float]:
            if swiat_na_ekran is None:
                return x, y
            return swiat_na_ekran(x, y)

        if self.wybrany_rodzaj in {"wezel", "zwrotnica"} and self.wybrany_id:
            wezel = graf.wezly.get(self.wybrany_id)
            if wezel:
                x_w, y_w = skaler.siatka_na_ekran(wezel.x, wezel.y)
                x, y = _mapuj(x_w, y_w)
                py.draw.circle(ekran, AKCENT, (int(x), int(y)), 14, 2)
            return

        if self.wybrany_rodzaj == "semafor" and self.wybrany_id:
            semafor = graf.semafory.get(self.wybrany_id)
            if semafor and semafor.id_toru in graf.wezly:
                tor = graf.wezly[semafor.id_toru]
                x_w, y_w = skaler.siatka_na_ekran(tor.x, tor.y)
                x, y = _mapuj(x_w, y_w)
                przes = max(6, int(round(10 * zoom)))
                promien = max(4, int(round(6 * zoom)))
                wx, wy = self._wektor_kierunku(semafor.kierunek_sem)
                x_sem = x + wx * przes
                y_sem = y + wy * przes
                py.draw.circle(ekran, AKCENT, (int(x_sem), int(y_sem)), promien, 2)
            return

        if self.wybrany_rodzaj == "pociag" and self.wybrany_pociag_id is not None:
            if 0 <= self.wybrany_pociag_id < len(self.projekt["pociagi"]):
                pociag = self.projekt["pociagi"][self.wybrany_pociag_id]
                sx = int(pociag.get("pozycja_startowa", {}).get("x", -9999))
                sy = int(pociag.get("pozycja_startowa", {}).get("y", -9999))
                wezel = graf.znajdz_wezel_po_wspolrzednych(sx, sy)
                if wezel:
                    x_w, y_w = skaler.siatka_na_ekran(wezel.x, wezel.y)
                    x, y = _mapuj(x_w, y_w)
                    py.draw.circle(ekran, AKCENT, (int(x), int(y)), 14, 2)
            return

        if self.wybrany_rodzaj == "stacja" and self.wybrany_id and self.wybrany_id in graf.stacje:
            stacja = graf.stacje[self.wybrany_id]
            for id_toru in stacja.id_torow:
                wezel = graf.wezly.get(id_toru)
                if wezel:
                    x_w, y_w = skaler.siatka_na_ekran(wezel.x, wezel.y)
                    x, y = _mapuj(x_w, y_w)
                    py.draw.circle(ekran, AKCENT, (int(x), int(y)), 10, 2)

    def rysuj_nakladke(
        self,
        ekran: py.Surface,
        graf: MenedzerGrafu,
        skaler: Skaler,
        czcionka: py.font.Font,
        czcionka_duza: py.font.Font,
        zoom: float = 1.0,
        swiat_na_ekran: Optional[Callable[[float, float], Tuple[float, float]]] = None,
    ) -> None:
        if not self.aktywny:
            self._spadek_komunikatu()
            return

        self._podswietl_wybrany_na_mapie(ekran, graf, skaler, zoom, swiat_na_ekran)

        szer, wys = ekran.get_size()
        panel_x = max(0, szer - PANEL_SZEROKOSC)
        panel = py.Surface((PANEL_SZEROKOSC, wys), py.SRCALPHA)
        panel.fill((*TLO_PANELU, 235))
        ekran.blit(panel, (panel_x, 0))

        self._toolbar_rects = {}
        self._lista_rects = []
        self._pole_rects = []
        self._przycisk_rects = {}
        self._rozklad_wiersze_rects = []
        self._rozklad_widok_rect = None
        self._wlasciwosci_widok_rect = None

        toolbar = [
            ("select", "Wybierz"),
            ("node", "Tor"),
            ("switch", "Zwrotnica"),
            ("signal", "Semafor"),
            ("station", "Peron"),
            ("train", "Pociag"),
            ("connect", "Lacz"),
            ("save", "Zapisz"),
        ]

        x = panel_x + 8
        y = 8
        for klucz, etykieta in toolbar:
            rect = py.Rect(x, y, 96, TOOLBAR_WYSOKOSC)
            self._toolbar_rects[klucz] = rect
            self._rysuj_przycisk(ekran, rect, etykieta, self.tryb == klucz, czcionka)
            x += 100
            if x + 96 > szer:
                x = panel_x + 8
                y += 40

        y += 48
        naglowek = czcionka_duza.render(f"Tryb: {dict(toolbar).get(self.tryb, '').upper()}", True, AKCENT)
        ekran.blit(naglowek, (panel_x + 12, y))
        y += 24
        instrukcja = [
            "LPM: tworzenie/wybor",
            "PPM: usun / anuluj laczenie",
            "1-7: szybka zmiana trybu",
            "B: galaz startowej zwrotnicy",
            "N: galaz docelowej zwrotnicy",
            "Enter: zapis pola / peronu",
            "Tab: nastepne pole",
            "Ctrl+S: zapis projektu",
        ]
        for linia in instrukcja:
            ekran.blit(czcionka.render(linia, True, NAPIS_KOLOR), (panel_x + 12, y))
            y += 18

        if self.tryb == "station":
            y += 6
            py.draw.rect(ekran, TLO_SEKCJI, py.Rect(panel_x + 8, y, PANEL_SZEROKOSC - 16, 74), border_radius=6)
            ekran.blit(czcionka_duza.render("Szkic peronu", True, AKCENT_2), (panel_x + 16, y + 6))
            tory_txt = ", ".join(self.draft_station_tracks) if self.draft_station_tracks else "-"
            ekran.blit(czcionka.render(f"Tory: {tory_txt}", True, NAPIS_KOLOR), (panel_x + 16, y + 30))
            btn_save = py.Rect(panel_x + 16, y + 50, 156, 22)
            btn_clear = py.Rect(panel_x + 180, y + 50, 156, 22)
            self._przycisk_rects["draft_station_save"] = btn_save
            self._przycisk_rects["draft_station_clear"] = btn_clear
            self._rysuj_przycisk(ekran, btn_save, "Utworz / aktualizuj", False, czcionka)
            self._rysuj_przycisk(ekran, btn_clear, "Wyczysc", False, czcionka)
            y += 86

        y += 8
        sekcja = py.Rect(panel_x + 8, y, PANEL_SZEROKOSC - 16, 180)
        py.draw.rect(ekran, TLO_SEKCJI, sekcja, border_radius=8)
        ekran.blit(czcionka_duza.render("Obiekty", True, AKCENT_2), (panel_x + 16, y + 6))
        y_lista = y + 30
        wysokosc_listy = 140
        self._lista_widok_rect = py.Rect(panel_x + 12, y_lista - 2, PANEL_SZEROKOSC - 24, wysokosc_listy)
        py.draw.rect(ekran, (18, 22, 30), self._lista_widok_rect, border_radius=4)
        self._lista_rects = []
        elementy = self._lista_elementow(graf)
        max_widoczne = max(1, wysokosc_listy // 26)
        max_scroll = max(0, len(elementy) - max_widoczne)
        self._lista_scroll = max(0, min(self._lista_scroll, max_scroll))
        widoczne = elementy[self._lista_scroll:self._lista_scroll + max_widoczne]

        for lokalny_idx, (kind, ident, opis) in enumerate(widoczne):
            idx = self._lista_scroll + lokalny_idx
            rect = py.Rect(panel_x + 14, y_lista, PANEL_SZEROKOSC - 28, 22)
            self._lista_rects.append((kind, ident, idx, rect))
            aktywny = (kind == self.wybrany_rodzaj and ((kind == "pociag" and ident == self.wybrany_pociag_id) or (kind != "pociag" and str(ident) == str(self.wybrany_id))))
            py.draw.rect(ekran, TLO_POLE_AKTYWNE if aktywny else TLO_POLE, rect, border_radius=4)
            tekst = czcionka.render(opis, True, NAPIS_KOLOR)
            ekran.blit(tekst, (rect.x + 6, rect.y + 4))
            y_lista += 26

        if len(elementy) > max_widoczne:
            info = czcionka.render(f"{self._lista_scroll + 1}-{self._lista_scroll + len(widoczne)} / {len(elementy)}", True, NAPIS_KOLOR)
            ekran.blit(info, (panel_x + 16, y + 172))

        y += 188
        sekcja = py.Rect(panel_x + 8, y, PANEL_SZEROKOSC - 16, wys - y - 88)
        py.draw.rect(ekran, TLO_SEKCJI, sekcja, border_radius=8)
        ekran.blit(czcionka_duza.render("Wlasciwosci", True, AKCENT_2), (panel_x + 16, y + 6))

        self._wlasciwosci_widok_rect = py.Rect(sekcja.x + 8, sekcja.y + 30, sekcja.width - 16, sekcja.height - 38)
        py.draw.rect(ekran, (18, 22, 30), self._wlasciwosci_widok_rect, border_radius=6)

        clip_poprzedni = ekran.get_clip()
        ekran.set_clip(self._wlasciwosci_widok_rect)

        baza_y = self._wlasciwosci_widok_rect.y + 8
        fy = baza_y - self._wlasciwosci_scroll
        self._pole_rects = []

        def _widoczny(rect: py.Rect) -> bool:
            return self._wlasciwosci_widok_rect is not None and rect.colliderect(self._wlasciwosci_widok_rect)

        if not self.formularz:
            ekran.blit(czcionka.render("Wybierz element lub dodaj go na planszy.", True, NAPIS_KOLOR), (panel_x + 16, fy))
            fy += 24
        else:
            for idx, pole in enumerate(self.formularz):
                etykieta = czcionka.render(f"{pole.etykieta}", True, NAPIS_KOLOR)
                ekran.blit(etykieta, (panel_x + 16, fy))
                rect = py.Rect(panel_x + 132, fy - 2, PANEL_SZEROKOSC - 148, WIERSZ_WYSOKOSC)
                self._pole_rects.append(rect)
                py.draw.rect(ekran, TLO_POLE_AKTYWNE if idx == self.aktywne_pole else TLO_POLE, rect, border_radius=4)
                wartosc = self.bufor_tekstu if idx == self.aktywne_pole else pole.wartosc
                if pole.typ == "choice" and wartosc not in pole.opcje and pole.opcje:
                    wartosc = pole.opcje[0]
                ekran.blit(czcionka.render(str(wartosc), True, NAPIS_KOLOR), (rect.x + 6, rect.y + 4))
                fy += 28

        if self.wybrany_rodzaj == "zwrotnica" and self.wybrany_id and self.wybrany_id in graf.zwrotnice:
            zwrotnica = graf.zwrotnice[self.wybrany_id]
            fy += 8
            info = czcionka.render(
                f"Galaz laczenia: start {self.branch_mode}, cel {self.branch_mode_docelowy}",
                True,
                AKCENT,
            )
            ekran.blit(info, (panel_x + 16, fy))
            fy += 20
            plus_txt = ", ".join(f"{k.name}->{v[0]}" for k, v in zwrotnica.polaczenia_plus.items()) or "-"
            minus_txt = ", ".join(f"{k.name}->{v[0]}" for k, v in zwrotnica.polaczenia_minus.items()) or "-"
            ekran.blit(czcionka.render(f"PLUS: {plus_txt}", True, NAPIS_KOLOR), (panel_x + 16, fy))
            fy += 18
            ekran.blit(czcionka.render(f"MINUS: {minus_txt}", True, NAPIS_KOLOR), (panel_x + 16, fy))
            fy += 18

        if self.wybrany_rodzaj == "station" and self.wybrany_id and self.wybrany_id in graf.stacje:
            fy += 20
            stacja = graf.stacje[self.wybrany_id]
            ekran.blit(czcionka.render(f"Wybrane tory: {', '.join(stacja.id_torow) or '-'}", True, NAPIS_KOLOR), (panel_x + 16, fy))
            fy += 20

        if self.wybrany_rodzaj == "pociag" and self.wybrany_pociag_id is not None and 0 <= self.wybrany_pociag_id < len(self.projekt["pociagi"]):
            fy += 20
            train = self.projekt["pociagi"][self.wybrany_pociag_id]
            ekran.blit(czcionka.render(f"Start: {train.get('pozycja_startowa', {}).get('x', '?')},{train.get('pozycja_startowa', {}).get('y', '?')}", True, NAPIS_KOLOR), (panel_x + 16, fy))
            fy += 18

            rozklad = self._normalizuj_rozklad_pociagu(train)
            tabela_x = panel_x + 16
            tabela_w = PANEL_SZEROKOSC - 32
            kolumny = [
                ("Stacja", 124),
                ("Postoj[s]", 82),
                ("Przyjazd", 82),
                ("Odjazd", 82),
            ]

            py.draw.rect(ekran, (18, 22, 30), py.Rect(tabela_x, fy, tabela_w, 24), border_radius=4)
            kx = tabela_x + 6
            for naglowek, szer in kolumny:
                ekran.blit(czcionka.render(naglowek, True, AKCENT_2), (kx, fy + 4))
                kx += szer

            y_wiersza = fy + 26
            max_wiersze = ROZKLAD_WIDOCZNE_WIERSZE
            max_scroll = max(0, len(rozklad) - max_wiersze)
            self._rozklad_scroll = max(0, min(self._rozklad_scroll, max_scroll))
            widoczne = rozklad[self._rozklad_scroll:self._rozklad_scroll + max_wiersze]
            self._rozklad_widok_rect = py.Rect(tabela_x, y_wiersza - 1, tabela_w, max_wiersze * 24)

            for lokalny_idx, przystanek in enumerate(widoczne):
                idx = self._rozklad_scroll + lokalny_idx
                rect = py.Rect(tabela_x, y_wiersza, tabela_w, 22)
                aktywny = idx == self.wybrany_rozklad_wiersz
                py.draw.rect(ekran, TLO_POLE_AKTYWNE if aktywny else TLO_POLE, rect, border_radius=4)
                if _widoczny(rect):
                    self._rozklad_wiersze_rects.append((idx, rect))

                dane = self._normalizuj_wiersz_rozkladu(przystanek)
                wartosci = [
                    str(dane.get("nazwa_stacji") or "-"),
                    str(dane.get("czas_postoju", 30.0)),
                    str(dane.get("przyjazd") or "-"),
                    str(dane.get("odjazd") or "-"),
                ]
                kx = tabela_x + 6
                for (wartosc, (_, szer)) in zip(wartosci, kolumny):
                    ekran.blit(czcionka.render(wartosc, True, NAPIS_KOLOR), (kx, y_wiersza + 4))
                    kx += szer

                y_wiersza += 24

            if len(rozklad) > max_wiersze:
                start = self._rozklad_scroll + 1
                stop = self._rozklad_scroll + len(widoczne)
                ekran.blit(czcionka.render(f"Wiersze {start}-{stop} / {len(rozklad)}", True, NAPIS_KOLOR), (tabela_x, y_wiersza + 2))
                y_wiersza += 16
            elif not rozklad:
                ekran.blit(czcionka.render("Rozklad pusty - dodaj pierwszy przystanek", True, NAPIS_KOLOR), (tabela_x, y_wiersza + 2))
                y_wiersza += 16

            btn_add = py.Rect(tabela_x, y_wiersza + 4, 150, 22)
            btn_del = py.Rect(tabela_x + 160, y_wiersza + 4, 150, 22)
            if _widoczny(btn_add):
                self._przycisk_rects["rozklad_add"] = btn_add
            if _widoczny(btn_del):
                self._przycisk_rects["rozklad_del"] = btn_del
            self._rysuj_przycisk(ekran, btn_add, "+ Dodaj wiersz", False, czcionka)
            self._rysuj_przycisk(ekran, btn_del, "- Usun wiersz", False, czcionka)
            fy = y_wiersza + 30

        ekran.set_clip(clip_poprzedni)

        self._wlasciwosci_wysokosc_tresci = max(0, int(fy - baza_y) + self._wlasciwosci_scroll + 12)
        if self._wlasciwosci_widok_rect is not None:
            max_scroll = max(0, self._wlasciwosci_wysokosc_tresci - self._wlasciwosci_widok_rect.height)
            self._wlasciwosci_scroll = max(0, min(self._wlasciwosci_scroll, max_scroll))

            if max_scroll > 0:
                pasek_tla = py.Rect(self._wlasciwosci_widok_rect.right - 6, self._wlasciwosci_widok_rect.y + 3, 4, self._wlasciwosci_widok_rect.height - 6)
                py.draw.rect(ekran, (46, 50, 62), pasek_tla, border_radius=2)
                uchwyt_h = max(18, int(pasek_tla.height * (self._wlasciwosci_widok_rect.height / max(self._wlasciwosci_wysokosc_tresci, 1))))
                zakres = max(1, pasek_tla.height - uchwyt_h)
                uchwyt_y = pasek_tla.y + int((self._wlasciwosci_scroll / max_scroll) * zakres)
                py.draw.rect(ekran, (130, 138, 165), py.Rect(pasek_tla.x, uchwyt_y, pasek_tla.width, uchwyt_h), border_radius=2)

        if self.komunikat.tresc:
            pasek = py.Rect(panel_x + 8, wys - 44, PANEL_SZEROKOSC - 16, 36)
            py.draw.rect(ekran, (10, 14, 20), pasek, border_radius=8)
            ekran.blit(czcionka.render(self.komunikat.tresc, True, AKCENT), (panel_x + 14, wys - 34))

        self._spadek_komunikatu()
