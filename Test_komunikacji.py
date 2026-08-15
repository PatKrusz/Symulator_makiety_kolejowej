import serial
import time

PORT = 'COM3'
BAUD_RATE = 115200

def run_test():
    try:
        print(f"Łączenie z ESP32 na porcie {PORT}...")
        ser = serial.Serial(PORT, BAUD_RATE, timeout=0)
        
        # Otwarcie portu zazwyczaj resetuje ESP32 (linie DTR/RTS)
        # Odczekujemy 2 sekundy, aż ESP32 w pełni się uruchomi
        time.sleep(2)
        ser.reset_input_buffer()

        # Przygotowanie wiadomości (musi kończyć się \n)
        msg_to_send = "Cześć ESP32, tu Python!\n"
        
        print(f"[PC] Wysyłam: {msg_to_send.strip()}")
        ser.write(msg_to_send.encode('utf-8'))
        time.sleep(0.5)  # Czekamy chwilę na odpowiedź
        # Odczyt odpowiedzi z ESP32
        response = ser.readline().decode('utf-8').strip()

        if response:
            print(f"[ESP32] Odpowiedź: {response}")
            print("\n✅ Test komunikacji zakończony sukcesem!")
        else:
            print("\n⚠️ Brak odpowiedzi (timeout). Sprawdź port i kod na ESP32.")

        ser.close()

    except serial.SerialException as e:
        print(f"\n❌ Błąd portu szeregowego: {e}")
        print("Upewnij się, że zamknąłeś Monitor Szeregowy w Arduino IDE!")

if __name__ == '__main__':
    run_test()