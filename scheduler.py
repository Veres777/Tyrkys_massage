from apscheduler.schedulers.background import BackgroundScheduler
import csv
from datetime import datetime, timedelta
import pywhatkit
import os
import time

def spust_scheduler():
    scheduler = BackgroundScheduler()

    def odesli_pripominky():
        zitrek = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        if os.path.exists("rezervace.csv"):
            with open("rezervace.csv", newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    if len(row) >= 6:
                        jmeno = row[0]
                        telefon = row[1]
                        datumcas = row[5]
                        if datumcas.startswith(zitrek):
                            cas = datumcas.split()[1]
                            zprava = f"Dobrý den {jmeno}, připomínáme vaši masáž zítra v {cas} v Ivanna Care. Těšíme se na vás! 🌸"
                            cislo = "+420" + telefon.replace(" ", "")
                            h = datetime.now().hour
                            m = datetime.now().minute + 1
                            pywhatkit.sendwhatmsg(cislo, zprava, h, m, wait_time=20)
                            time.sleep(15)

    scheduler.add_job(odesli_pripominky, 'cron', hour=18, minute=0)
    scheduler.start()
