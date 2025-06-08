import pywhatkit
import csv
import os
from datetime import datetime, timedelta
import time

# Datum zítřka
zitrek = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")

# Načti rezervace
if os.path.exists("rezervace.csv"):
    with open("rezervace.csv", newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) >= 4:
                jmeno = row[0]
                telefon = row[1]
                datumcas = row[3]

                if datumcas.startswith(zitrek):
                    cas = datumcas.split()[1]
                    zprava = f"Dobrý den {jmeno}, připomínáme vaši masáž zítra v {cas} v Ivanna Care. Těšíme se na vás! 🌸"

                    # ✅ Na zkoušku nastavíme fixní číslo Ivany:
                    # Místo: cislo = "+420" + telefon.replace(" ", "")
                    cislo = "+420608639637"

                    h = datetime.now().hour
                    m = datetime.now().minute + 1

                    print(f"Posílám zprávu {jmeno} ({cislo})...")

                    pywhatkit.sendwhatmsg(cislo, zprava, h, m, wait_time=20)

                    # Pauza, aby se WhatsApp nezasekl
                    time.sleep(15)
