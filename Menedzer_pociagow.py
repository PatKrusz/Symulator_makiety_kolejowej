import datetime
import math
from typing import Dict, List, Optional
from Pociag import Pociag
from Rozklad_jazdy import SledzenieRozkladu, StanPociagu
from Graf import MenedzerGrafu
from Wezly import Kierunek, Sygnal
import config

class MenedzerPociagow:
    """Połączenie pociągów z grafiką i fizyką. Nadzoruje ruch, zapobiega kolizjom i aktualizuje rozkłady."""
    def __init__(self, graf: MenedzerGrafu, zasieg_widoku_kafelki: int = 5):
        self.graf: MenedzerGrafu = graf
        self.zasieg_widoku_kafelki: int = max(1, zasieg_widoku_kafelki)
        self.pociagi: Dict[str, Pociag] = {}
        self.sledzenie_rozkladow: Dict[str, SledzenieRozkladu] = {}
        self._poprzedni_stan_rozkladu: Dict[str, StanPociagu] = {}
        self._zolty_tryb: Dict[str, Dict[str, str]] = {}
        self.awaryjne_hamowanie_globalne: bool = False
        self._blokada_po_czerwonym: Dict[str, Dict[str, object]] = {}

    @staticmethod
    def _normalizuj_klucz_stacji(wartosc: Optional[str]) -> str:
        return str(wartosc or "").strip().upper()

    def _tory_stacji_docelowej(self, klucz_stacji: Optional[str]) -> set[str]:
        if not klucz_stacji:
            return set()

        klucz = self._normalizuj_klucz_stacji(klucz_stacji)
        tory: set[str] = set()
        for stacja in self.graf.stacje.values():
            nazwa = self._normalizuj_klucz_stacji(getattr(stacja, "nazwa_stacji", ""))
            ident = self._normalizuj_klucz_stacji(getattr(stacja, "id_stacji", ""))
            if klucz in {nazwa, ident}:
                tory.update(stacja.id_torow)
        return tory

    def _predkosc_bazowa_pociagu(self, pociag: Pociag) -> float:
        if pociag.narzucona_predkosc_max_pxs is None:
            return pociag.predkosc_max_pxs
        return max(0.0, min(pociag.predkosc_max_pxs, pociag.narzucona_predkosc_max_pxs))

    def _jest_pociag_techniczny(self, pociag: Pociag) -> bool:
        return pociag.typ_pociagu.strip().upper() in {"TECHNICZNY", "TECH", "RATOWNICZY"}

    def ustaw_kierunek_pociagu(self, id_pociagu: str, kierunek: Kierunek, sprawdz_przejazd: bool = True) -> bool:
        pociag = self.pociagi.get(id_pociagu)
        if not pociag:
            return False
        return pociag.ustaw_kierunek_ruchu(kierunek, self.graf, sprawdz_przejazd=sprawdz_przejazd)

    def ustaw_limit_predkosci_pociagu(self, id_pociagu: str, limit_pxs: Optional[float]) -> bool:
        pociag = self.pociagi.get(id_pociagu)
        if not pociag:
            return False
        if limit_pxs is None:
            pociag.narzucona_predkosc_max_pxs = None
            return True
        pociag.narzucona_predkosc_max_pxs = max(0.0, min(limit_pxs, pociag.predkosc_max_pxs))
        return True

    def ustaw_awaryjne_hamowanie_globalne(self, aktywne: bool) -> None:
        self.awaryjne_hamowanie_globalne = aktywne

    def zezwol_na_jazde_po_czerwonym(self, id_pociagu: str) -> bool:
        status = self._blokada_po_czerwonym.get(id_pociagu)
        if not status:
            return False
        status["zgoda_na_wznowienie"] = True
        return True

    def status_blokady_po_czerwonym(self, id_pociagu: str) -> Dict[str, object]:
        status = self._blokada_po_czerwonym.get(id_pociagu)
        if not status:
            return {"aktywna": False, "zgoda_na_wznowienie": False, "semafor_id": "-"}
        return {
            "aktywna": bool(status.get("aktywna", False)),
            "zgoda_na_wznowienie": bool(status.get("zgoda_na_wznowienie", False)),
            "semafor_id": str(status.get("semafor_id", "-")),
        }

    def _czy_koniec_stacji_docelowej(self, pociag: Pociag, tory_stacji_docelowej: set[str], id_kafelka_przod: Optional[str]) -> bool:
        if not tory_stacji_docelowej or not id_kafelka_przod or id_kafelka_przod not in tory_stacji_docelowej:
            return False

        obecny_wezel = self.graf.wezly.get(id_kafelka_przod)
        if not obecny_wezel:
            return True

        nastepny = obecny_wezel.nastepny_wezel(pociag.aktualny_kierunek, raportuj_awarie=False)
        if not nastepny:
            return True

        id_nastepnego, _ = nastepny
        return id_nastepnego not in tory_stacji_docelowej

    def _limit_predkosci_dla_dojazdu_do_konca_stacji(
        self,
        pociag: Pociag,
        tory_stacji_docelowej: set[str],
        id_start: Optional[str],
        kierunek_start: Kierunek,
    ) -> Optional[float]:
        if not tory_stacji_docelowej or not id_start:
            return None

        obecny_id = id_start
        obecny_kierunek = kierunek_start
        dystans_px = 0.0

        for _ in range(self.zasieg_widoku_kafelki + len(tory_stacji_docelowej) + 2):
            if obecny_id in tory_stacji_docelowej:
                nastepny_wezel = self.graf.wezly.get(obecny_id)
                if not nastepny_wezel:
                    break

                nastepny = nastepny_wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
                if not nastepny:
                    break

                id_nastepnego, kierunek_nastepnego = nastepny
                if id_nastepnego not in tory_stacji_docelowej:
                    return math.sqrt(max(0.0, 2.0 * pociag.efektywne_hamowanie_pxs2 * dystans_px))

                dystans_px += pociag.skaler.rozmiar_kafelka_px
                obecny_id, obecny_kierunek = id_nastepnego, kierunek_nastepnego
                continue

            obecny_wezel = self.graf.wezly.get(obecny_id)
            if not obecny_wezel:
                break

            nastepny = obecny_wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
            if not nastepny:
                break

            id_nastepnego, kierunek_nastepnego = nastepny
            dystans_px += pociag.skaler.rozmiar_kafelka_px
            obecny_id, obecny_kierunek = id_nastepnego, kierunek_nastepnego

        return None

    def _predkosc_bezpieczna_z_buforem(self, pociag: Pociag, dystans_do_semafora_px: float) -> float:
        bezpieczny_dystans_px = max(0.0, dystans_do_semafora_px - 0.5*pociag.skaler.rozmiar_kafelka_px)
        if pociag.efektywne_hamowanie_pxs2 <= 0.0 or bezpieczny_dystans_px <= 0.0:
            return 0.0
        return math.sqrt(max(0.0, 2.0 * pociag.efektywne_hamowanie_pxs2 * bezpieczny_dystans_px))

    def _wyznacz_predkosc_docelowa(
        self,
        delta_czasu_symulacji: float,
        pociag: Pociag,
        sledzenie: Optional[SledzenieRozkladu],
        obecny_czas_symulacji: Optional[datetime.datetime] = None,
    ) -> float:
        """
        Jedno miejsce decyzyjne "patrzenia w przód": stacja docelowa + semafory.
        """
        if pociag.wymuszony_postoj:
            return 0.0

        if self.awaryjne_hamowanie_globalne:
            return 0.0

        status_czerwony = self._blokada_po_czerwonym.get(pociag.id_pociagu)
        if status_czerwony and bool(status_czerwony.get("aktywna", False)):
            if bool(status_czerwony.get("zgoda_na_wznowienie", False)) and pociag.predkosc_aktualna_pxs <= 0.0:
                self._blokada_po_czerwonym.pop(pociag.id_pociagu, None)
            else:
                return 0.0

        predkosc_bazowa = self._predkosc_bazowa_pociagu(pociag)
        predkosc_docelowa = predkosc_bazowa
        id_kafelka_przod = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else None
        if not id_kafelka_przod:
            return predkosc_docelowa

        # Ograniczenie po żółtym działa do kolejnego semafora.
        zolty_info = self._zolty_tryb.get(pociag.id_pociagu)
        if zolty_info:
            semafor_tutaj = pociag._znajdz_semafor_dla_kierunku(self.graf, id_kafelka_przod, pociag.aktualny_kierunek)
            if semafor_tutaj and semafor_tutaj.id_semafora != zolty_info.get("origin"):
                self._zolty_tryb.pop(pociag.id_pociagu, None)
            else:
                predkosc_docelowa = min(predkosc_docelowa, predkosc_bazowa * 0.5)

        tory_stacji_docelowej: set[str] = set()
        if sledzenie:
            nazwa_stacji_docelowej = sledzenie.nazwa_docelowej_stacji()
            tory_stacji_docelowej = self._tory_stacji_docelowej(nazwa_stacji_docelowej)

        czy_na_stacji_docelowej = bool(tory_stacji_docelowej and id_kafelka_przod in tory_stacji_docelowej)
        czy_na_koncu_stacji_docelowej = self._czy_koniec_stacji_docelowej(
            pociag,
            tory_stacji_docelowej,
            id_kafelka_przod,
        )
        predkosc_dokladnego_dociagniecia = math.sqrt(
            max(0.0, 2.0 * pociag.efektywne_hamowanie_pxs2 * pociag.skaler.rozmiar_kafelka_px)
        )
        limit_dojazdu_do_stacji = self._limit_predkosci_dla_dojazdu_do_konca_stacji(
            pociag,
            tory_stacji_docelowej,
            id_kafelka_przod,
            pociag.aktualny_kierunek,
        )

        if czy_na_stacji_docelowej and not czy_na_koncu_stacji_docelowej:
            if limit_dojazdu_do_stacji is not None:
                predkosc_docelowa = min(predkosc_docelowa, limit_dojazdu_do_stacji)
            else:
                predkosc_docelowa = min(predkosc_docelowa, predkosc_dokladnego_dociagniecia)

        # Rozkład zarządza tylko postojem/odjazdem oraz zatrzymaniem po wjechaniu na stację.
        if sledzenie:
            nadpisanie = sledzenie.aktualizuj_stan_postoju(
                delta_czasu_symulacji,
                pociag,
                czy_na_stacji_docelowej,
                czy_na_koncu_stacji_docelowej,
                obecny_czas_symulacji=obecny_czas_symulacji,
            )
            if nadpisanie is not None:
                predkosc_docelowa = min(predkosc_docelowa, nadpisanie)

        # Jeśli rozkład nie wymusił pełnego zatrzymania, skanuj tor do przodu.
        if predkosc_docelowa > 0.0:
            obecny_id = id_kafelka_przod
            obecny_kierunek = pociag.aktualny_kierunek

            for krok in range(self.zasieg_widoku_kafelki):
                if krok > 0:
                    wezel_na_trasie = self.graf.wezly.get(obecny_id)
                    if wezel_na_trasie and wezel_na_trasie.zajety and wezel_na_trasie.pociag_id != pociag.id_pociagu:
                        dystans_do_zajetego_px = (
                            max(0.0, pociag.skaler.rozmiar_kafelka_px - pociag.dystans_w_kafelku_px)
                            + (krok - 1) * pociag.skaler.rozmiar_kafelka_px
                        )
                        predkosc_docelowa = min(
                            predkosc_docelowa,
                            self._predkosc_bezpieczna_z_buforem(pociag, dystans_do_zajetego_px),
                        )
                        break

                if tory_stacji_docelowej and krok > 0 and obecny_id in tory_stacji_docelowej:
                    # Ograniczenie zależne od rzeczywistej odległości do końca stacji,
                    # zamiast stałego wczesnego spowalniania przy pierwszym wykryciu peronu.
                    if limit_dojazdu_do_stacji is not None:
                        predkosc_docelowa = min(predkosc_docelowa, limit_dojazdu_do_stacji)
                    else:
                        predkosc_docelowa = min(predkosc_docelowa, predkosc_dokladnego_dociagniecia)
                    break

                semafor = pociag._znajdz_semafor_dla_kierunku(self.graf, obecny_id, obecny_kierunek)
                if semafor:
                    if semafor.sygnal == Sygnal.CZERWONY:
                        if krok == 0:
                            dystans_do_semafora_px = max(
                                0.0,
                                pociag.skaler.rozmiar_kafelka_px - pociag.dystans_w_kafelku_px,
                            )
                        else:
                            dystans_do_semafora_px = krok * pociag.skaler.rozmiar_kafelka_px

                        if dystans_do_semafora_px > 0:
                            vmax_przed_czerwonym = self._predkosc_bezpieczna_z_buforem(pociag, dystans_do_semafora_px)
                            if krok == 0 and pociag.predkosc_aktualna_pxs <= vmax_przed_czerwonym + 0.001:
                                predkosc_docelowa = 0.0
                            else:
                                predkosc_docelowa = min(predkosc_docelowa, vmax_przed_czerwonym)
                        break
                    if semafor.sygnal == Sygnal.ZOLTY:
                        predkosc_docelowa = min(predkosc_docelowa, predkosc_bazowa * 0.5)
                        if pociag.id_pociagu not in self._zolty_tryb:
                            self._zolty_tryb[pociag.id_pociagu] = {"origin": semafor.id_semafora}
                    if semafor.sygnal == Sygnal.SZ:
                        if not self._jest_pociag_techniczny(pociag):
                            if krok == 0:
                                dystans_do_semafora_px = max(
                                    0.0,
                                    pociag.skaler.rozmiar_kafelka_px - pociag.dystans_w_kafelku_px,
                                )
                            else:
                                dystans_do_semafora_px = krok * pociag.skaler.rozmiar_kafelka_px

                            if dystans_do_semafora_px > 0:
                                vmax_przed_sz = self._predkosc_bezpieczna_z_buforem(pociag, dystans_do_semafora_px)
                                if krok == 0 and pociag.predkosc_aktualna_pxs <= vmax_przed_sz + 0.001:
                                    predkosc_docelowa = 0.0
                                else:
                                    predkosc_docelowa = min(predkosc_docelowa, vmax_przed_sz)
                            break
                        predkosc_sz = pociag.skaler.kmh_na_pxs(10.0)
                        predkosc_docelowa = min(predkosc_docelowa, predkosc_sz)

                obecny_wezel = self.graf.wezly.get(obecny_id)
                if not obecny_wezel:
                    break

                nastepny = obecny_wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
                if not nastepny:
                    break

                obecny_id, obecny_kierunek = nastepny

        return predkosc_docelowa

    def dodaj_pociag(self, pociag: Pociag, sledzenie_rozkladu: Optional[SledzenieRozkladu] = None) -> None:
        """Dodaje nowy pociąg do symulacji"""
        self.pociagi[pociag.id_pociagu] = pociag
        self._zolty_tryb.pop(pociag.id_pociagu, None)
        self._blokada_po_czerwonym.pop(pociag.id_pociagu, None)
        if sledzenie_rozkladu:
            self.sledzenie_rozkladow[pociag.id_pociagu] = sledzenie_rozkladu
            self._poprzedni_stan_rozkladu[pociag.id_pociagu] = sledzenie_rozkladu.stan_pociagu
        if config.DEBUG_MODE:
            print(f"[DEBUG] Zarejestrowano pociąg: {pociag.id_pociagu}")

    def aktualizuj(self, delta_czasu_symulacji: float, obecny_czas_symulacji: Optional[datetime.datetime] = None) -> List[dict]:
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
            sledzenie = self.sledzenie_rozkladow.get(id_pociagu)
            poprzedni_stan = self._poprzedni_stan_rozkladu.get(id_pociagu, StanPociagu.JAZDA)
            id_stacji_przed_aktualizacja = None

            if sledzenie:
                if sledzenie.rozklad and sledzenie.rozklad.aktualny_przystanek():
                    id_stacji_przed_aktualizacja = sledzenie.rozklad.aktualny_przystanek().nazwa_stacji

            # 2. WSPÓLNA LOGIKA PATRZENIA W PRZÓD (SEMAFORY + STACJA)
            predkosc_docelowa = self._wyznacz_predkosc_docelowa(
                delta_czasu_symulacji,
                pociag,
                sledzenie,
                obecny_czas_symulacji=obecny_czas_symulacji,
            )
            nowy_stan = sledzenie.stan_pociagu if sledzenie else StanPociagu.JAZDA

            if nowy_stan != poprzedni_stan:
                if nowy_stan == StanPociagu.POSTOJ and id_stacji_przed_aktualizacja:
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "pociag_zatrzymal_sie_na_stacji",
                            "pociag_id": id_pociagu,
                            "stacja_id": id_stacji_przed_aktualizacja,
                            "stacja_nazwa": id_stacji_przed_aktualizacja,
                        }
                    )
                elif poprzedni_stan == StanPociagu.POSTOJ and nowy_stan == StanPociagu.JAZDA and id_stacji_przed_aktualizacja:
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "pociag_odjechal_ze_stacji",
                            "pociag_id": id_pociagu,
                            "stacja_id": id_stacji_przed_aktualizacja,
                            "stacja_nazwa": id_stacji_przed_aktualizacja,
                        }
                    )

            self._poprzedni_stan_rozkladu[id_pociagu] = nowy_stan

            tory_stacji_docelowej_dla_flagi: set[str] = set()
            if sledzenie:
                nazwa_stacji_docelowej = sledzenie.nazwa_docelowej_stacji()
                tory_stacji_docelowej_dla_flagi = self._tory_stacji_docelowej(nazwa_stacji_docelowej)

            czy_na_koncu_stacji_docelowej = self._czy_koniec_stacji_docelowej(
                pociag,
                tory_stacji_docelowej_dla_flagi,
                id_kafelka_przod,
            )

            pociag.predkosc_docelowa_pxs = predkosc_docelowa
            pociag.zatrzymaj_na_koncu_biezacego_kafelka = bool(
                sledzenie
                and czy_na_koncu_stacji_docelowej
                and nowy_stan in {StanPociagu.HAMOWANIE, StanPociagu.POSTOJ}
            )

            # 3. AKTUALIZACJA FIZYKI
            zdarzenia_pociagu = pociag.aktualizuj_fizyke(delta_czasu_symulacji, self.graf)
            for typ_zdarzenia, id_toru in zdarzenia_pociagu:
                if typ_zdarzenia == "zajety":
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "tor_zajety",
                            "pociag_id": id_pociagu,
                            "tor_id": id_toru,
                        }
                    )
                elif typ_zdarzenia == "zwolniony":
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "tor_zwolniony",
                            "pociag_id": id_pociagu,
                            "tor_id": id_toru,
                        }
                    )
                elif typ_zdarzenia == "zwrotnica_rozpruta":
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "zwrotnica_rozpruta",
                            "pociag_id": id_pociagu,
                            "zwrotnica_id": id_toru,
                        }
                    )
                elif typ_zdarzenia == "przejazd_na_czerwonym":
                    poprzedni_status = self._blokada_po_czerwonym.get(id_pociagu)
                    if not poprzedni_status or not bool(poprzedni_status.get("aktywna", False)):
                        self._blokada_po_czerwonym[id_pociagu] = {
                            "aktywna": True,
                            "zgoda_na_wznowienie": False,
                            "semafor_id": id_toru,
                        }
                        wszystkie_zdarzenia.append(
                            {
                                "typ": "przejazd_na_czerwonym",
                                "pociag_id": id_pociagu,
                                "semafor_id": id_toru,
                            }
                        )
                elif typ_zdarzenia == "pociag_zatrzymal_sie_na_czerwonym":
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "pociag_zatrzymal_sie_na_czerwonym",
                            "pociag_id": id_pociagu,
                            "semafor_id": id_toru,
                        }
                    )
                elif typ_zdarzenia == "pociag_odjechal_z_czerwonego":
                    wszystkie_zdarzenia.append(
                        {
                            "typ": "pociag_odjechal_z_czerwonego",
                            "pociag_id": id_pociagu,
                            "semafor_id": id_toru,
                        }
                    )

            #if config.DEBUG_MODE:
                #print(f"[DEBUG] Prędkość docelowa pociągu {pociag.id_pociagu}: {pociag.predkosc_docelowa_pxs}")
                #print(f"[DEBUG] Prędkość aktualna pociągu {pociag.id_pociagu}: {pociag.predkosc_aktualna_pxs}")

        return wszystkie_zdarzenia