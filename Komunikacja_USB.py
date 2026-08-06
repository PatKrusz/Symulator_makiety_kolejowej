import importlib
from typing import Any, Dict, List, Optional, Tuple

import config
from Graf import MenedzerGrafu
from Menedzer_pociagow import MenedzerPociagow
from Wezly import Kierunek, Sygnal, Zwrot
from Zegar_symulacji import ZegarSymulacji

try:
    serial = importlib.import_module("serial")
    SerialException = getattr(serial, "SerialException", Exception)
except ModuleNotFoundError:
    serial = None
    SerialException = Exception


class MostKomunikacjiUSB:
    """
    Prosty most komunikacyjny USB<->symulator.

    Preferowany format ramki: tekst zakończony znakiem nowej linii, np:
    SYG:S01:ZIE\n

    Obsługiwany jest wyłącznie format tekstowy.
    """

    _MAPA_SYGNAL_TXT_DO_ENUM = {
        "CZE": "CZERWONY",
        "CZER": "CZERWONY",
        "CZERWONY": "CZERWONY",
        "ZOL": "ZOLTY",
        "ZOLTY": "ZOLTY",
        "ZIE": "ZIELONY",
        "ZIEL": "ZIELONY",
        "ZIELONY": "ZIELONY",
        "SZ": "SZ",
    }

    _MAPA_SYGNAL_ENUM_DO_TXT = {
        "CZERWONY": "CZE",
        "ZOLTY": "ZOL",
        "ZIELONY": "ZIE",
        "SZ": "SZ",
    }

    _MAPA_ZWROT_TXT_DO_ENUM = {
        "PLU": "PLUS",
        "PLUS": "PLUS",
        "P": "PLUS",
        "MIN": "MINUS",
        "MINUS": "MINUS",
        "M": "MINUS",
    }

    _MAPA_ZWROT_ENUM_DO_TXT = {
        "PLUS": "PLU",
        "MINUS": "MIN",
    }

    def __init__(
        self,
        graf: MenedzerGrafu,
        menedzer_pociagow: MenedzerPociagow,
        zegar: ZegarSymulacji,
        wlaczony: bool = False,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 0.0,
    ):
        self.graf = graf
        self.menedzer_pociagow = menedzer_pociagow
        self.zegar = zegar
        self.wlaczony = wlaczony
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None
        self._sekcje: Dict[str, Dict[str, Any]] = {}
        self._sekcja_dla_toru: Dict[str, str] = {}
        self._zajetosc_sekcji_pociagow: Dict[str, Dict[str, int]] = {}

        self._zbuduj_model_sekcji()

        if self.wlaczony:
            self._otworz_port()

    def _otworz_port(self) -> None:
        if serial is None:
            print("[WARN] Brak pakietu pyserial. Komunikacja USB jest wyłączona.")
            self.wlaczony = False
            return

        if not self.port:
            print("[WARN] Nie podano portu COM. Komunikacja USB jest wyłączona.")
            self.wlaczony = False
            return

        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"[INFO] Połączono z mikrokontrolerem na porcie {self.port} ({self.baudrate} bps).")
        except SerialException as e:
            print(f"[WARN] Nie udało się otworzyć portu {self.port}: {e}")
            self.wlaczony = False

    def zamknij(self) -> None:
        if self._serial:
            try:
                self._serial.close()
            except SerialException:
                pass
            self._serial = None

    def _wyslij_tekst(self, linia: str) -> None:
        if not self.wlaczony or not self._serial:
            return

        try:
            self._serial.write((linia + "\n").encode("utf-8"))
        except SerialException as e:
            print(f"[WARN] Błąd zapisu na USB: {e}")

    def _sygnal_do_kodu(self, sygnal: Sygnal) -> str:
        return self._MAPA_SYGNAL_ENUM_DO_TXT.get(sygnal.value, sygnal.value)

    def _zwrot_do_kodu(self, zwrot: Zwrot) -> str:
        return self._MAPA_ZWROT_ENUM_DO_TXT.get(zwrot.value, zwrot.value)

    def _odpowiedz_error_txt(self, kod_bledu: str) -> None:
        self._wyslij_tekst(f"ERR:{kod_bledu}")

    def _odpowiedz_ok_txt(self, *pola: str) -> None:
        self._wyslij_tekst("OK:" + ":".join(pola))

    def _odpowiedz_data_txt(self, *pola: str) -> None:
        self._wyslij_tekst("DAT:" + ":".join(pola))

    def _zbuduj_model_sekcji(self) -> None:
        self._sekcje.clear()
        self._sekcja_dla_toru.clear()

        max_kroki = max(1, len(self.graf.wezly) + 5)
        for semafor in self.graf.semafory.values():
            start_id = semafor.id_toru
            kierunek = semafor.kierunek_sem
            obecny_id = start_id
            obecny_kierunek = kierunek
            odwiedzone = set()
            tory_sekcji: List[str] = []
            id_koncowego_semafora = "END"

            for _ in range(max_kroki):
                wezel = self.graf.wezly.get(obecny_id)
                if not wezel:
                    break

                nastepny = wezel.nastepny_wezel(obecny_kierunek, raportuj_awarie=False)
                if not nastepny:
                    break

                nastepny_id, nastepny_kierunek = nastepny
                klucz = (nastepny_id, nastepny_kierunek)
                if klucz in odwiedzone:
                    break
                odwiedzone.add(klucz)

                semafor_na_nastepnym = self.graf.semafory_dla_wezlow.get((nastepny_id, nastepny_kierunek))
                if semafor_na_nastepnym:
                    id_koncowego_semafora = semafor_na_nastepnym.id_semafora
                    break

                tory_sekcji.append(nastepny_id)
                obecny_id, obecny_kierunek = nastepny_id, nastepny_kierunek

            id_sekcji = f"SEC:{semafor.id_semafora}->{id_koncowego_semafora}:{kierunek.value}"
            self._sekcje[id_sekcji] = {
                "id": id_sekcji,
                "start_semafor": semafor.id_semafora,
                "koniec_semafor": id_koncowego_semafora,
                "kierunek": kierunek.value,
                "tory": tory_sekcji,
            }

            for id_toru in tory_sekcji:
                self._sekcja_dla_toru.setdefault(id_toru, id_sekcji)

    def _sekcja_dla_pociagu(self, pociag_id: str) -> str:
        pociag = self.menedzer_pociagow.pociagi.get(pociag_id)
        if not pociag or not pociag.id_zajetych_kafelkow:
            return "-"
        id_czola = pociag.id_zajetych_kafelkow[-1]
        return self._sekcja_dla_toru.get(id_czola, "-")

    def _nastepna_stacja_pociagu(self, pociag_id: str) -> Tuple[str, str, str]:
        sledzenie = self.menedzer_pociagow.sledzenie_rozkladow.get(pociag_id)
        if not sledzenie or not sledzenie.rozklad:
            return "-", "-", "-"

        przystanek = sledzenie.rozklad.aktualny_przystanek()
        if not przystanek:
            return "-", "-", "-"

        return (
            przystanek.id_stacji,
            str(przystanek.czas_przyjazdu or "-"),
            str(przystanek.czas_odjazdu or "-"),
        )

    def _typ_pociagu_kod(self, typ: str) -> str:
        typ_up = typ.strip().upper()
        if typ_up in {"OSOBOWY", "OSO"}:
            return "OSO"
        if typ_up in {"TOWAROWY", "TOW"}:
            return "TOW"
        if typ_up in {"POSPIESZNY", "POS"}:
            return "POS"
        if typ_up in {"TECHNICZNY", "TECH"}:
            return "TEC"
        return typ_up

    def _aktualizuj_i_raportuj_sekcje(self, zdarzenie: Dict[str, Any], czas_symulacji: str) -> None:
        typ = zdarzenie.get("typ")
        if typ not in {"tor_zajety", "tor_zwolniony"}:
            return

        id_pociagu = str(zdarzenie.get("pociag_id", ""))
        id_toru = str(zdarzenie.get("tor_id", ""))
        id_sekcji = self._sekcja_dla_toru.get(id_toru)
        if not id_pociagu or not id_sekcji:
            return

        licznik = self._zajetosc_sekcji_pociagow.setdefault(id_pociagu, {})
        stan = int(licznik.get(id_sekcji, 0))

        if typ == "tor_zajety":
            stan += 1
            licznik[id_sekcji] = stan
            if stan == 1:
                self._wyslij_tekst(f"EVT:SEC_IN:{id_pociagu}:{id_sekcji}:{czas_symulacji}")
            return

        if stan <= 1:
            licznik.pop(id_sekcji, None)
            self._wyslij_tekst(f"EVT:SEC_OUT:{id_pociagu}:{id_sekcji}:{czas_symulacji}")
        else:
            licznik[id_sekcji] = stan - 1

    def wyslij_zdarzenie(self, typ: str, payload: Dict[str, Any]) -> None:
        czas = self.zegar.obecna_data()

        if typ == "zwrotnica_rozpruta":
            self._wyslij_tekst(
                f"EVT:AWR:{payload.get('zwrotnica_id', '-')}:"
                f"{payload.get('pociag_id', '-')}:{czas}"
            )
            return

        if typ == "semafor_zmieniony":
            self._wyslij_tekst(
                f"EVT:SYG:{payload.get('semafor_id', '-')}:"
                f"{self._MAPA_SYGNAL_ENUM_DO_TXT.get(str(payload.get('sygnal', '')).upper(), payload.get('sygnal', '-'))}:{czas}"
            )
            return

        if typ == "zwrotnica_przestawiona":
            self._wyslij_tekst(
                f"EVT:ZWR:{payload.get('zwrotnica_id', '-')}:"
                f"{self._MAPA_ZWROT_ENUM_DO_TXT.get(str(payload.get('pozycja', '')).upper(), payload.get('pozycja', '-'))}:{czas}"
            )
            return

        if typ == "pociag_zmienil_kierunek":
            self._wyslij_tekst(
                f"EVT:KIR:{payload.get('pociag_id', '-')}:{payload.get('kierunek', '-') }:{czas}"
            )
            return

        if typ == "awaryjne_hamowanie":
            self._wyslij_tekst(
                f"EVT:EST:{'ON' if bool(payload.get('aktywny', False)) else 'OFF'}:{czas}"
            )
            return

        self._wyslij_tekst(f"EVT:UNK:{typ}:{czas}")

    def wyslij_zdarzenia_symulacji(self, zdarzenia: List[Dict[str, Any]], czas_symulacji: str) -> None:
        zdarzenia_posortowane = sorted(
            zdarzenia,
            key=lambda z: 0 if z.get("typ") == "zwrotnica_rozpruta" else 1,
        )

        for zdarzenie in zdarzenia_posortowane:
            typ = zdarzenie.get("typ", "nieznane")
            self._aktualizuj_i_raportuj_sekcje(zdarzenie, czas_symulacji)
            if typ == "zwrotnica_rozpruta":
                self._wyslij_tekst(
                    f"EVT:AWR:{zdarzenie.get('zwrotnica_id', '-')}:{zdarzenie.get('pociag_id', '-')}:{czas_symulacji}"
                )
            elif typ == "tor_zajety":
                self._wyslij_tekst(
                    f"EVT:ZAJ:{zdarzenie.get('pociag_id', '-')}:{zdarzenie.get('tor_id', '-')}:{czas_symulacji}"
                )
            elif typ == "tor_zwolniony":
                self._wyslij_tekst(
                    f"EVT:ZWO:{zdarzenie.get('pociag_id', '-')}:{zdarzenie.get('tor_id', '-')}:{czas_symulacji}"
                )
            elif typ == "pociag_zatrzymal_sie_na_stacji":
                self._wyslij_tekst(
                    f"EVT:STP:{zdarzenie.get('pociag_id', '-')}:{zdarzenie.get('stacja_id', '-')}:{czas_symulacji}"
                )
            elif typ == "pociag_odjechal_ze_stacji":
                self._wyslij_tekst(
                    f"EVT:ODJ:{zdarzenie.get('pociag_id', '-')}:{zdarzenie.get('stacja_id', '-')}:{czas_symulacji}"
                )
            elif typ == "przejazd_na_czerwonym":
                self._wyslij_tekst(
                    f"EVT:RED:{zdarzenie.get('pociag_id', '-')}:{zdarzenie.get('semafor_id', '-')}:{czas_symulacji}"
                )
            else:
                self._wyslij_tekst(f"EVT:UNK:{typ}:{czas_symulacji}")

    def _zparsuj_komende(self, linia: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Zwraca: (komenda, kod_bledu).
        """
        czesci = [c.strip() for c in linia.split(":")]
        if not czesci or not czesci[0]:
            return None, "brak_cmd"

        cmd = czesci[0].upper().rstrip("?")

        if cmd in {"PNG", "PING"}:
            return {"cmd": "ping"}, None

        if cmd == "SYG":
            if len(czesci) == 2:
                return {"cmd": "get_signal", "id": czesci[1]}, None
            if len(czesci) >= 3:
                return {
                    "cmd": "set_signal",
                    "id": czesci[1],
                    "signal": czesci[2],
                    "force": len(czesci) >= 4 and czesci[3].upper() in {"F", "FORCE", "W"},
                }, None
            return None, "bledna_komenda_syg"

        if cmd == "ZWR":
            if len(czesci) == 2:
                return {"cmd": "get_switch", "id": czesci[1]}, None
            if len(czesci) >= 3:
                return {
                    "cmd": "set_switch",
                    "id": czesci[1],
                    "position": czesci[2],
                    "force": len(czesci) >= 4 and czesci[3].upper() in {"F", "FORCE", "W"},
                }, None
            return None, "bledna_komenda_zwr"

        if cmd == "TOR":
            if len(czesci) < 2:
                return None, "bledna_komenda_tor"
            return {
                "cmd": "get_track",
                "id": czesci[1],
            }, None

        if cmd == "POC":
            if len(czesci) < 2:
                return None, "bledna_komenda_poc"
            return {
                "cmd": "get_train",
                "id": czesci[1],
            }, None

        if cmd == "KIR":
            if len(czesci) < 3:
                return None, "bledna_komenda_kir"
            return {
                "cmd": "set_train_direction",
                "id": czesci[1],
                "direction": czesci[2],
            }, None

        if cmd == "LIM":
            if len(czesci) < 3:
                return None, "bledna_komenda_lim"
            return {
                "cmd": "set_train_limit",
                "id": czesci[1],
                "value": czesci[2],
            }, None

        if cmd in {"EST", "ESTOP"}:
            if len(czesci) < 2:
                return None, "bledna_komenda_estop"
            return {
                "cmd": "set_emergency_stop",
                "active": czesci[1],
            }, None

        if cmd == "SEC":
            if len(czesci) < 2:
                return None, "bledna_komenda_sec"
            return {
                "cmd": "get_section",
                "id": czesci[1],
            }, None

        if cmd == "ROZ":
            if len(czesci) < 2:
                return None, "bledna_komenda_roz"
            return {
                "cmd": "get_train_schedule",
                "id": czesci[1],
            }, None

        if cmd == "ZGD":
            if len(czesci) < 2:
                return None, "bledna_komenda_zgd"
            return {
                "cmd": "allow_after_red",
                "id": czesci[1],
            }, None

        if cmd == "WOL":
            if len(czesci) < 3:
                return None, "bledna_komenda_wol"

            komenda = {
                "cmd": "get_free_space",
                "track_id": czesci[1],
                "direction": czesci[2],
                "max_steps": 20,
            }

            if len(czesci) >= 4 and czesci[3]:
                try:
                    komenda["max_steps"] = int(czesci[3])
                except ValueError:
                    return None, "niepoprawne_max_steps"

            return komenda, None

        if cmd in {"SNP", "SNAP"}:
            return {"cmd": "snapshot"}, None

        return None, "nieznana_komenda"

    def obsluz_wejscie(self) -> None:
        if not self.wlaczony or not self._serial:
            return

        try:
            while self._serial.in_waiting > 0:
                linia = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if not linia:
                    continue

                komenda, blad = self._zparsuj_komende(linia)
                if blad:
                    self._odpowiedz_error_txt(blad)
                    continue

                self._wykonaj_komende(komenda)
        except SerialException as e:
            print(f"[WARN] Błąd odczytu z USB: {e}")

    def _wykonaj_komende(self, komenda: Dict[str, Any]) -> None:
        cmd = komenda.get("cmd")

        def odpowiedz_error(kod_bledu: str) -> None:
            self._odpowiedz_error_txt(kod_bledu)

        if not cmd:
            odpowiedz_error("brak_cmd")
            return

        if cmd == "ping":
            self._odpowiedz_ok_txt("PNG", self.zegar.obecna_data())
            return

        if cmd == "set_switch":
            id_zwrotnicy = komenda.get("id")
            pozycja_str = str(komenda.get("position", "")).upper()
            wymuszenie = bool(komenda.get("force", False))

            zwrotnica = self.graf.zwrotnice.get(id_zwrotnicy)
            if not zwrotnica:
                odpowiedz_error("nieznana_zwrotnica")
                return

            pozycja_enum = self._MAPA_ZWROT_TXT_DO_ENUM.get(pozycja_str, pozycja_str)
            try:
                nowa_pozycja = Zwrot[pozycja_enum]
            except KeyError:
                odpowiedz_error("nieznana_pozycja")
                return

            ok = zwrotnica.ustaw_pozycje(nowa_pozycja, wymuszenie=wymuszenie)
            if not ok:
                odpowiedz_error("zwrotnica_zablokowana")
                return

            payload = {
                "zwrotnica_id": id_zwrotnicy,
                "pozycja": zwrotnica.pozycja.value,
            }
            self._odpowiedz_ok_txt("ZWR", id_zwrotnicy, self._zwrot_do_kodu(zwrotnica.pozycja))
            self.wyslij_zdarzenie("zwrotnica_przestawiona", payload)
            return

        if cmd == "get_switch":
            id_zwrotnicy = komenda.get("id")
            zwrotnica = self.graf.zwrotnice.get(id_zwrotnicy)
            if not zwrotnica:
                odpowiedz_error("nieznana_zwrotnica")
                return
            self._odpowiedz_data_txt(
                "ZWR",
                str(id_zwrotnicy),
                self._zwrot_do_kodu(zwrotnica.pozycja),
                "1" if zwrotnica.stan_awaryjny else "0",
            )
            return

        if cmd == "set_signal":
            id_semafora = komenda.get("id")
            sygnal_str = str(komenda.get("signal", "")).upper()
            semafor = self.graf.semafory.get(id_semafora)
            if not semafor:
                odpowiedz_error("nieznany_semafor")
                return

            sygnal_enum = self._MAPA_SYGNAL_TXT_DO_ENUM.get(sygnal_str, sygnal_str)
            try:
                nowy_sygnal = Sygnal[sygnal_enum]
            except KeyError:
                odpowiedz_error("nieznany_sygnal")
                return

            semafor.ustaw_sygnal(nowy_sygnal)
            payload = {
                "semafor_id": id_semafora,
                "sygnal": semafor.sygnal.value,
            }
            self._odpowiedz_ok_txt("SYG", id_semafora, self._sygnal_do_kodu(semafor.sygnal))
            self.wyslij_zdarzenie("semafor_zmieniony", payload)
            return

        if cmd == "get_signal":
            id_semafora = komenda.get("id")
            semafor = self.graf.semafory.get(id_semafora)
            if not semafor:
                odpowiedz_error("nieznany_semafor")
                return
            self._odpowiedz_data_txt(
                "SYG",
                str(id_semafora),
                self._sygnal_do_kodu(semafor.sygnal),
                semafor.id_toru,
                semafor.kierunek_sem.value,
            )
            return

        if cmd == "get_track":
            id_toru = komenda.get("id")
            wezel = self.graf.wezly.get(id_toru)
            if not wezel:
                odpowiedz_error("nieznany_tor")
                return

            self._odpowiedz_data_txt(
                "TOR",
                str(id_toru),
                "1" if wezel.zajety else "0",
                str(wezel.pociag_id if wezel.pociag_id else "-"),
            )
            return

        if cmd == "get_train":
            id_pociagu = komenda.get("id")
            pociag = self.menedzer_pociagow.pociagi.get(id_pociagu)
            if not pociag:
                odpowiedz_error("nieznany_pociag")
                return

            id_czola = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else "-"
            id_ogona = pociag.id_zajetych_kafelkow[0] if pociag.id_zajetych_kafelkow else "-"
            predkosc_kmh = pociag.skaler.pxs_na_kmh(pociag.predkosc_aktualna_pxs)
            id_sekcji = self._sekcja_dla_pociagu(pociag.id_pociagu)
            stacja_nast, czas_przyj, czas_odj = self._nastepna_stacja_pociagu(pociag.id_pociagu)
            status_czerwony = self.menedzer_pociagow.status_blokady_po_czerwonym(pociag.id_pociagu)
            self._odpowiedz_data_txt(
                "POC",
                pociag.id_pociagu,
                f"{pociag.predkosc_aktualna_pxs:.3f}",
                f"{pociag.predkosc_docelowa_pxs:.3f}",
                f"{predkosc_kmh:.2f}",
                self._typ_pociagu_kod(pociag.typ_pociagu),
                pociag.aktualny_kierunek.value,
                str(id_czola),
                str(id_ogona),
                id_sekcji,
                stacja_nast,
                czas_przyj,
                czas_odj,
                "1" if status_czerwony["aktywna"] else "0",
                str(status_czerwony["semafor_id"]),
            )
            return

        if cmd == "get_train_schedule":
            id_pociagu = komenda.get("id")
            pociag = self.menedzer_pociagow.pociagi.get(id_pociagu)
            if not pociag:
                odpowiedz_error("nieznany_pociag")
                return
            stacja_nast, czas_przyj, czas_odj = self._nastepna_stacja_pociagu(id_pociagu)
            self._odpowiedz_data_txt("ROZ", id_pociagu, stacja_nast, czas_przyj, czas_odj)
            return

        if cmd == "set_train_direction":
            id_pociagu = komenda.get("id")
            kierunek_str = str(komenda.get("direction", "")).upper()
            try:
                kierunek = Kierunek[kierunek_str]
            except KeyError:
                odpowiedz_error("nieznany_kierunek")
                return

            ok = self.menedzer_pociagow.ustaw_kierunek_pociagu(str(id_pociagu), kierunek, sprawdz_przejazd=True)
            if not ok:
                odpowiedz_error("brak_przejazdu_w_kierunku")
                return

            self._odpowiedz_ok_txt("KIR", str(id_pociagu), kierunek.value)
            self._wyslij_tekst(f"EVT:KIR:{id_pociagu}:{kierunek.value}:{self.zegar.obecna_data()}")
            return

        if cmd == "set_train_limit":
            id_pociagu = str(komenda.get("id"))
            wartosc = str(komenda.get("value", "")).upper()

            if wartosc in {"OFF", "BRAK", "NONE", "-"}:
                ok = self.menedzer_pociagow.ustaw_limit_predkosci_pociagu(id_pociagu, None)
                if not ok:
                    odpowiedz_error("nieznany_pociag")
                    return
                self._odpowiedz_ok_txt("LIM", id_pociagu, "OFF")
                return

            try:
                limit_kmh = float(wartosc.replace(",", "."))
            except ValueError:
                odpowiedz_error("niepoprawny_limit")
                return

            pociag = self.menedzer_pociagow.pociagi.get(id_pociagu)
            if not pociag:
                odpowiedz_error("nieznany_pociag")
                return

            limit_pxs = pociag.skaler.kmh_na_pxs(limit_kmh)
            self.menedzer_pociagow.ustaw_limit_predkosci_pociagu(id_pociagu, limit_pxs)
            self._odpowiedz_ok_txt("LIM", id_pociagu, f"{limit_kmh:.1f}")
            return

        if cmd == "set_emergency_stop":
            aktywne_str = str(komenda.get("active", "")).upper()
            aktywne = aktywne_str in {"1", "ON", "TRUE", "STOP", "ESTOP"}
            self.menedzer_pociagow.ustaw_awaryjne_hamowanie_globalne(aktywne)
            self._odpowiedz_ok_txt("EST", "ON" if aktywne else "OFF")
            self._wyslij_tekst(f"EVT:EST:{'ON' if aktywne else 'OFF'}:{self.zegar.obecna_data()}")
            return

        if cmd == "allow_after_red":
            id_pociagu = str(komenda.get("id"))
            ok = self.menedzer_pociagow.zezwol_na_jazde_po_czerwonym(id_pociagu)
            if not ok:
                odpowiedz_error("brak_awarii_czerwonego")
                return
            self._odpowiedz_ok_txt("ZGD", id_pociagu)
            self._wyslij_tekst(f"EVT:ZGD:{id_pociagu}:{self.zegar.obecna_data()}")
            return

        if cmd == "get_section":
            id_pociagu = str(komenda.get("id"))
            pociag = self.menedzer_pociagow.pociagi.get(id_pociagu)
            if not pociag:
                odpowiedz_error("nieznany_pociag")
                return

            id_czola = pociag.id_zajetych_kafelkow[-1] if pociag.id_zajetych_kafelkow else "-"
            id_ogona = pociag.id_zajetych_kafelkow[0] if pociag.id_zajetych_kafelkow else "-"
            sekcja_czola = self._sekcja_dla_toru.get(str(id_czola), "-")
            sekcja_ogona = self._sekcja_dla_toru.get(str(id_ogona), "-")
            self._odpowiedz_data_txt("SEC", id_pociagu, sekcja_czola, sekcja_ogona)
            return

        if cmd == "get_free_space":
            id_toru = komenda.get("track_id")
            kierunek_str = str(komenda.get("direction", "")).upper()
            try:
                max_kroki = int(komenda.get("max_steps", 20))
            except (TypeError, ValueError):
                odpowiedz_error("niepoprawne_max_steps")
                return

            try:
                kierunek = Kierunek[kierunek_str]
            except KeyError:
                odpowiedz_error("nieznany_kierunek")
                return

            wolne, powod = self.graf.znajdz_wolna_przestrzen(id_toru, kierunek, max_kroki)

            self._odpowiedz_data_txt(
                "WOL",
                str(id_toru),
                kierunek.value,
                str(wolne),
                str(powod),
            )
            return

        if cmd == "snapshot":
            zrzut = self._zrzut_stanu()
            self._odpowiedz_data_txt(
                "SNP",
                zrzut["czas_symulacji"],
                str(len(zrzut["pociagi"])),
                str(len(zrzut["semafory"])),
                str(len(zrzut["zwrotnice"])),
            )
            return

        odpowiedz_error("nieznana_komenda")

    def _zrzut_stanu(self) -> Dict[str, Any]:
        pociagi = []
        for pociag in self.menedzer_pociagow.pociagi.values():
            pociagi.append(
                {
                    "id": pociag.id_pociagu,
                    "predkosc_aktualna_pxs": pociag.predkosc_aktualna_pxs,
                    "predkosc_docelowa_pxs": pociag.predkosc_docelowa_pxs,
                    "zajete_tory": list(pociag.id_zajetych_kafelkow),
                }
            )

        semafory = {
            semafor_id: semafor.sygnal.value
            for semafor_id, semafor in self.graf.semafory.items()
        }
        zwrotnice = {
            zwrotnica_id: {
                "pozycja": zwrotnica.pozycja.value,
                "stan_awaryjny": zwrotnica.stan_awaryjny,
                "licznik_rozpruc": zwrotnica.licznik_rozpruc,
            }
            for zwrotnica_id, zwrotnica in self.graf.zwrotnice.items()
        }

        sekcje = {
            sekcja_id: {
                "start_semafor": dane["start_semafor"],
                "koniec_semafor": dane["koniec_semafor"],
                "kierunek": dane["kierunek"],
                "tory": list(dane["tory"]),
            }
            for sekcja_id, dane in self._sekcje.items()
        }

        return {
            "czas_symulacji": self.zegar.obecna_data(),
            "pociagi": pociagi,
            "semafory": semafory,
            "zwrotnice": zwrotnice,
            "sekcje": sekcje,
        }