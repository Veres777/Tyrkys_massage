from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from fpdf import FPDF
from zipfile import ZipFile
from dotenv import load_dotenv
from flask_mail import Mail, Message
import stripe
import csv
import os
import re

load_dotenv()

app = Flask(__name__)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_ADDRESS')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')

mail = Mail(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH')


# Vytvoření potřebných složek
os.makedirs('faktury', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/rezervace', methods=['POST'])
def rezervace():
    jmeno = request.form['jmeno']
    telefon = request.form['telefon']
    email = request.form['email']
    adresa = request.form['adresa']
    typ = request.form['typ']
    delka = request.form['delka']
    cena = request.form['cena']
    datum = request.form['datum']
    cas = request.form['cas']
    zprava = request.form['zprava']

    # Formátování data a času
    try:
        datumcas = datetime.strptime(f"{datum} {cas}", "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return jsonify({'error': 'Neplatný formát data nebo času'}), 400

    # Uložení rezervace do CSV
    with open('rezervace.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([
            jmeno, telefon, email, adresa,
            typ, delka, cena,
            datumcas, zprava,
            "nezaplaceno", ""
        ])

    return jsonify({'success': True}), 200

@app.route('/create-payment-intent', methods=['POST'])
def create_payment():
    data = request.get_json()
    amount = int(data['cena']) * 100  # cena в Kč, Stripe принимает в haléřích

    intent = stripe.PaymentIntent.create(
        amount=amount,
        currency='czk',
        automatic_payment_methods={'enabled': True},
        metadata={
            'jmeno': data['jmeno'],
            'telefon': data['telefon'],
            'email': data['email'],
            'typ': data['typ'],
            'delka': data['delka'],
            'datum': data['datum'],
            'cas': data['cas']
        }
    )
    return jsonify({'clientSecret': intent.client_secret})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['user'] = username
            flash('Přihlášení bylo úspěšné.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Nesprávné přihlašovací údaje.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Byli jste odhlášeni.', 'info')
    return redirect(url_for('login'))


@app.route('/admin')
def admin():
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'warning')
        return redirect(url_for('login'))

    rezervace = []
    faktury = []
    hledany = request.args.get('hledat', '').lower()

    if os.path.exists('rezervace.csv'):
        with open('rezervace.csv', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            rezervace = list(reader)
            if hledany:
                rezervace = [r for r in rezervace if any(hledany in pole.lower() for pole in r)]

    if os.path.exists('faktury'):
        faktury = [f for f in os.listdir('faktury') if f.endswith('.pdf')]

    # Výpočet statistik
    celkem = len(rezervace)
    zaplaceno = sum(1 for r in rezervace if len(r) > 9 and r[9] == "zaplaceno")
    nezaplaceno = celkem - zaplaceno

    prijem = 0
    masaze = []
    for r in rezervace:
        if len(r) >= 7 and r[6].isdigit():
            cena = int(r[6])
            if len(r) > 9 and r[9] == "zaplaceno":
                prijem += cena
            masaze.append(r[4])

    nejcastejsi = max(set(masaze), key=masaze.count) if masaze else "N/A"

    statistiky = {
        "celkem": celkem,
        "zaplaceno": zaplaceno,
        "nezaplaceno": nezaplaceno,
        "prijem": prijem,
        "nejcastejsi": nejcastejsi
    }

    return render_template('admin.html', rezervace=rezervace, faktury=faktury, statistiky=statistiky)


@app.route('/vytvor_fakturu', methods=['POST'])
def vytvor_fakturu():
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    jmeno = request.form['jmeno']
    telefon = request.form['telefon']
    email = request.form['email']
    adresa = request.form['adresa']
    typ = request.form['typ']
    delka = request.form['delka']
    cena = request.form['cena']
    datumcas = request.form['datumcas']
    zprava = request.form['zprava']

    datum_vystaveni = datetime.now().strftime("%d.%m.%Y")
    aktualni_rok = datetime.now().year

    cislo_soubor = f"faktury/faktura_cislo_{aktualni_rok}.txt"
    poradi = 1
    if os.path.exists(cislo_soubor):
        with open(cislo_soubor, 'r') as f:
            poradi = int(f.read().strip()) + 1
    with open(cislo_soubor, 'w') as f:
        f.write(str(poradi))

    cislo_faktury = f"{aktualni_rok}{str(poradi).zfill(6)}"

    # Popis služby podle typu
    popisy = {
        "klasicka": "Klasická relaxační masáž",
        "lymfaticka": "Lymfatická masáž",
        "sportovni": "Sportovní masáž",
        "lavove": "Masáž lávovými kameny",
        "bankova": "Baňková masáž",
        "medova": "Medová masáž",
        "hlava": "Masáž hlavy a dekoltu",
        "anticelulitidova": "Anticelulitidová masáž",
        "kokos": "Relaxační masáž s kokosovým olejem",
        "regeneracni": "Regenerační masáž"
    }

    popis_sluzby = popisy.get(typ, "Masáž")
    cena_int = int(cena)

    # Bezpečné jméno pro soubor
    bezpecne_jmeno = re.sub(r'[^a-zA-Z0-9]', '_', jmeno)
    bezpecny_datum = re.sub(r'[^0-9]', '', datumcas)
    soubor = f"faktury/faktura_{bezpecne_jmeno}_{bezpecny_datum}.pdf"

    pdf = FPDF()
    pdf.add_page()

    # Přidání fontů (předpokládáme, že máte fonty v systému)
    try:
        pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
        pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)
    except:
        # Fallback pokud fonty nejsou k dispozici
        pdf.add_font("Arial", style="", fname="arial.ttf")
        pdf.add_font("Arial", style="B", fname="arialbd.ttf")

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, f"Faktura {cislo_faktury}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(90, 8, "DODAVATEL:", 0, 0)
    pdf.cell(0, 8, "ODBĚRATEL:", 0, 1)
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(90, 8, "Ivanna Lukovets", 0, 0)
    pdf.cell(0, 8, jmeno, 0, 1)
    pdf.cell(90, 8, "K Horoměřicům 1185/55", 0, 0)
    pdf.cell(0, 8, adresa, 0, 1)
    pdf.cell(90, 8, "Praha 6 – Suchdol", 0, 0)
    pdf.cell(0, 8, telefon, 0, 1)
    pdf.cell(90, 8, "IČO: 19111592", 0, 0)
    pdf.cell(0, 8, email, 0, 1)
    pdf.cell(90, 8, "Tel: +420 608 639 637", 0, 0)
    pdf.cell(0, 8, "", 0, 1)
    pdf.cell(90, 8, "E-mail: ivannalukovets1987@gmail.com", 0, 1)
    pdf.ln(5)
    pdf.cell(0, 10, "Fakturuji Vám za provedené služby", ln=True)
    pdf.ln(5)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(100, 8, "Název položky", 1)
    pdf.cell(20, 8, "Množ.", 1)
    pdf.cell(30, 8, "Jedn.", 1)
    pdf.cell(0, 8, "Cena", 1, ln=True)
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(100, 8, f"{popis_sluzby} ({delka} min)", 1)
    pdf.cell(20, 8, "1", 1)
    pdf.cell(30, 8, "ks", 1)
    pdf.cell(0, 8, f"{cena_int} Kč", 1, ln=True)
    pdf.ln(5)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(150, 8, "Celkem (včetně DPH):", 0)
    pdf.cell(0, 8, f"{cena_int} Kč", 0, ln=True)
    pdf.ln(10)
    pdf.set_font("DejaVu", "", 12)
    pdf.cell(0, 8, f"Datum vystavení: {datum_vystaveni}", ln=True)
    pdf.cell(0, 8, "Způsob platby: Hotově", ln=True)
    pdf.ln(15)
    pdf.cell(0, 8, "S úctou,", ln=True)
    pdf.cell(0, 8, "Ivanna Lukovets", ln=True)

    pdf.output(soubor)

    flash(f"Faktura č. {cislo_faktury} byla vygenerována.", 'success')
    return redirect(url_for('admin'))


@app.route('/zaplaceno/<int:index>', methods=['POST'])
def zaplaceno(index):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    rezervace = []
    with open('rezervace.csv', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        rezervace = list(reader)

    if 0 <= index < len(rezervace):
        if len(rezervace[index]) < 11:
            # Rozšíření na potřebný počet sloupců
            rezervace[index] = rezervace[index] + [''] * (11 - len(rezervace[index]))

        rezervace[index][9] = 'zaplaceno'

        with open('rezervace.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rezervace)

        # Vygeneruj fakturu
        jmeno = rezervace[index][0]
        telefon = rezervace[index][1]
        email = rezervace[index][2]
        adresa = rezervace[index][3]
        typ = rezervace[index][4]
        delka = rezervace[index][5]
        cena = rezervace[index][6]
        datumcas = rezervace[index][7]
        zprava = rezervace[index][8]

        # Vytvoření faktury
        vygeneruj_fakturu(jmeno, telefon, email, adresa, typ, delka, cena, datumcas, zprava)
        soubor = najdi_fakturu(jmeno, datumcas)
        if soubor:
            odesli_fakturu(email, soubor)

        flash('Rezervace označena jako zaplacená. Faktura byla vytvořena a odeslána e-mailem.', 'success')

    return redirect(url_for('admin'))


def najdi_fakturu(jmeno, datumcas):
    bezpecne_jmeno = re.sub(r'[^a-zA-Z0-9]', '_', jmeno)
    bezpecny_datum = re.sub(r'[^0-9]', '', datumcas)
    pattern = f"faktura_{bezpecne_jmeno}_{bezpecny_datum}.*\.pdf"

    for soubor in os.listdir('faktury'):
        if re.match(pattern, soubor):
            return soubor
    return None


def odesli_fakturu(email, soubor):
    cesta = os.path.join("faktury", soubor)

    try:
        msg = Message(
            subject="Faktura za masáž – Tyrkys masáže",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email],
            body="Dobrý den,\n\nv příloze naleznete fakturu za masáž. Děkujeme za zaplacení.\n\nS pozdravem,\nTyrkys masáže"
        )

        with open(cesta, 'rb') as f:
            msg.attach(soubor, "application/pdf", f.read())

        mail.send(msg)
        return True
    except Exception as e:
        print(f"Chyba při odesílání e-mailu: {e}")
        return False



@app.route('/uloz_poznamku/<int:index>', methods=['POST'])
def uloz_poznamku(index):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    nova_poznamka = request.form.get('nova_poznamka', '')
    rezervace = []

    if os.path.exists('rezervace.csv'):
        with open('rezervace.csv', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            rezervace = list(reader)

    if 0 <= index < len(rezervace):
        # Rozšíření na 11 sloupců pokud je potřeba
        if len(rezervace[index]) < 11:
            rezervace[index] = rezervace[index] + [''] * (11 - len(rezervace[index]))

        rezervace[index][10] = nova_poznamka

        with open('rezervace.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rezervace)

        flash('Poznámka byla uložena.', 'success')
    else:
        flash('Neplatný index rezervace.', 'danger')

    return redirect(url_for('admin'))


@app.route('/faktury/<path:nazev>')
def stahnout_fakturu(nazev):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    return send_from_directory('faktury', nazev, as_attachment=True)


@app.route('/smaz_fakturu/<nazev>', methods=['POST'])
def smaz_fakturu(nazev):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    cesta = os.path.join('faktury', nazev)
    if os.path.exists(cesta):
        os.remove(cesta)
        flash(f"Faktura {nazev} byla smazána.", 'info')
    else:
        flash("Soubor neexistuje.", 'warning')

    return redirect(url_for('admin'))


@app.route('/admin_rezervace', methods=['POST'])
def admin_rezervace():
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    jmeno = request.form['jmeno']
    telefon = request.form['telefon']
    email = request.form['email']
    adresa = request.form['adresa']
    typ = request.form['typ']
    delka = request.form['delka']
    cena = request.form['cena']
    datum = request.form['datum']
    cas = request.form['cas']
    zprava = request.form['zprava']

    try:
        datumcas = datetime.strptime(f"{datum} {cas}", "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        flash('Neplatný formát data nebo času', 'danger')
        return redirect(url_for('admin'))

    with open('rezervace.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([
            jmeno, telefon, email, adresa,
            typ, delka, cena,
            datumcas, zprava,
            "nezaplaceno", ""
        ])

    # Automaticky vytvořit fakturu
    vygeneruj_fakturu(jmeno, telefon, email, adresa, typ, delka, cena, datumcas, zprava)

    flash('Rezervace i faktura byly úspěšně vytvořeny.', 'success')
    return redirect(url_for('admin'))


def vygeneruj_fakturu(jmeno, telefon, email, adresa, typ, delka, cena, datumcas, zprava):
    datum_vystaveni = datetime.now().strftime("%d.%m.%Y")
    aktualni_rok = datetime.now().year

    cislo_soubor = f"faktury/faktura_cislo_{aktualni_rok}.txt"
    poradi = 1
    if os.path.exists(cislo_soubor):
        with open(cislo_soubor, 'r') as f:
            poradi = int(f.read().strip()) + 1
    with open(cislo_soubor, 'w') as f:
        f.write(str(poradi))

    cislo_faktury = f"{aktualni_rok}{str(poradi).zfill(6)}"

    popisy = {
        "klasicka": "Klasická relaxační masáž",
        "lymfaticka": "Lymfatická masáž",
        "sportovni": "Sportovní masáž",
        "lavove": "Masáž lávovými kameny",
        "bankova": "Baňková masáž",
        "medova": "Medová masáž",
        "hlava": "Masáž hlavy a dekoltu",
        "anticelulitidova": "Anticelulitidová masáž",
        "kokos": "Relaxační masáž s kokosovým olejem",
        "regeneracni": "Regenerační masáž"
    }

    popis_sluzby = popisy.get(typ, "Masáž")
    cena_int = int(cena)

    bezpecne_jmeno = re.sub(r'[^a-zA-Z0-9]', '_', jmeno)
    bezpecny_datum = re.sub(r'[^0-9]', '', datumcas)
    soubor = f"faktury/faktura_{bezpecne_jmeno}_{bezpecny_datum}.pdf"

    pdf = FPDF()
    pdf.add_page()

    try:
        pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
        pdf.add_font("DejaVu", "B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", uni=True)
        font_family = "DejaVu"
    except:
        pdf.add_font("Arial", style="", fname="arial.ttf")
        pdf.add_font("Arial", style="B", fname="arialbd.ttf")
        font_family = "Arial"

    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 10, f"Faktura {cislo_faktury}", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font(font_family, "B", 12)
    pdf.cell(90, 8, "DODAVATEL:", 0, 0)
    pdf.cell(0, 8, "ODBĚRATEL:", 0, 1)
    pdf.set_font(font_family, "", 12)
    pdf.cell(90, 8, "Ivanna Lukovets", 0, 0)
    pdf.cell(0, 8, jmeno, 0, 1)
    pdf.cell(90, 8, "K Horoměřicům 1185/55", 0, 0)
    pdf.cell(0, 8, adresa, 0, 1)
    pdf.cell(90, 8, "Praha 6 – Suchdol", 0, 0)
    pdf.cell(0, 8, telefon, 0, 1)
    pdf.cell(90, 8, "IČO: 19111592", 0, 0)
    pdf.cell(0, 8, email, 0, 1)
    pdf.cell(90, 8, "Tel: +420 608 639 637", 0, 0)
    pdf.cell(0, 8, "", 0, 1)
    pdf.cell(90, 8, "E-mail: ivannalukovets01071987@gmail.com", 0, 1)
    pdf.ln(5)
    pdf.cell(0, 10, "Fakturuji Vám za provedené služby", ln=True)
    pdf.ln(5)
    pdf.set_font(font_family, "B", 12)
    pdf.cell(100, 8, "Název položky", 1)
    pdf.cell(20, 8, "Množ.", 1)
    pdf.cell(30, 8, "Jedn.", 1)
    pdf.cell(0, 8, "Cena", 1, ln=True)
    pdf.set_font(font_family, "", 12)
    pdf.cell(100, 8, f"{popis_sluzby} ({delka} min)", 1)
    pdf.cell(20, 8, "1", 1)
    pdf.cell(30, 8, "ks", 1)
    pdf.cell(0, 8, f"{cena_int} Kč", 1, ln=True)
    pdf.ln(5)
    pdf.set_font(font_family, "B", 12)
    pdf.cell(150, 8, "Celkem (včetně DPH):", 0)
    pdf.cell(0, 8, f"{cena_int} Kč", 0, ln=True)
    pdf.ln(10)
    pdf.set_font(font_family, "", 12)
    pdf.cell(0, 8, f"Datum vystavení: {datum_vystaveni}", ln=True)
    pdf.cell(0, 8, "Způsob platby: Hotově", ln=True)
    pdf.ln(15)
    pdf.cell(0, 8, "S úctou,", ln=True)
    pdf.cell(0, 8, "Ivanna Lukovets", ln=True)

    pdf.output(soubor)


@app.route('/volne-casy', methods=['POST'])
def volne_casy():
    from datetime import datetime, timedelta

    data = request.get_json()
    zvolene_datum = data.get("datum")
    delka = int(data.get("delka", 60))  # длительность массажа

    if not zvolene_datum or not delka:
        return jsonify({"cas": []})

    pause = 15  # мин пауза
    vsechny_starty = [
        "09:00", "09:30", "10:00", "10:30",
        "11:00", "11:30", "12:00", "12:30",
        "13:00", "13:30", "14:00", "14:30",
        "15:00", "15:30", "16:00", "16:30"
    ]

    # собрать все занятые интервалы
    obsazene_intervaly = []
    if os.path.exists("rezervace.csv"):
        with open("rezervace.csv", newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) >= 8:
                    try:
                        datumcas = row[7]
                        start = datetime.strptime(datumcas, "%d.%m.%Y %H:%M")
                        konec = start + timedelta(minutes=int(row[5]) + pause)
                        if start.strftime("%Y-%m-%d") == zvolene_datum:
                            obsazene_intervaly.append((start.time(), konec.time()))
                    except Exception:
                        continue

    # проверка, перекрывается ли интервал
    def je_volne(start_str):
        start = datetime.strptime(start_str, "%H:%M")
        end = start + timedelta(minutes=delka + pause)
        for obs_start, obs_end in obsazene_intervaly:
            # перекрытие: start < obs_end and end > obs_start
            if start.time() < obs_end and end.time() > obs_start:
                return False
        return True

    volne_casy = [cas for cas in vsechny_starty if je_volne(cas)]

    return jsonify({"cas": volne_casy})




@app.route('/stahnout_faktury_mesic', methods=['POST'])
def stahnout_faktury_mesic():
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    mesic = int(request.form['mesic'])
    rok = int(request.form['rok'])

    zip_jmeno = f"faktury_{rok}_{str(mesic).zfill(2)}.zip"
    zip_cesta = os.path.join("faktury", zip_jmeno)

    with ZipFile(zip_cesta, 'w') as zipf:
        for soubor in os.listdir('faktury'):
            if soubor.endswith('.pdf') and soubor.startswith('faktura_'):
                try:
                    # Extrahování data z názvu souboru
                    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', soubor)
                    if match:
                        den = int(match.group(1))
                        mesic_soubor = int(match.group(2))
                        rok_soubor = int(match.group(3))

                        if mesic_soubor == mesic and rok_soubor == rok:
                            zipf.write(os.path.join("faktury", soubor), arcname=soubor)
                except Exception as e:
                    print(f"Chyba při zpracování {soubor}: {e}")

    return send_from_directory('faktury', zip_jmeno, as_attachment=True)


@app.route('/smaz_rezervaci/<int:index>', methods=['POST'])
def smaz_rezervaci(index):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    rezervace = []
    if os.path.exists('rezervace.csv'):
        with open('rezervace.csv', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            rezervace = list(reader)

    if 0 <= index < len(rezervace):
        rezervace.pop(index)

        with open('rezervace.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerows(rezervace)

        flash('Rezervace byla smazána.', 'info')

    return redirect(url_for('admin'))


@app.route('/zobraz_fakturu/<path:nazev>')
def zobraz_fakturu(nazev):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    return send_from_directory('faktury', nazev)


@app.route('/vratit_fakturu/<int:index>', methods=['POST'])
def vratit_fakturu(index):
    if 'user' not in session or session['user'] != ADMIN_USERNAME:
        flash('Přístup odepřen.', 'danger')
        return redirect(url_for('login'))

    rezervace = []
    if os.path.exists('rezervace.csv'):
        with open('rezervace.csv', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            rezervace = list(reader)

    if 0 <= index < len(rezervace):
        jmeno = rezervace[index][0]
        telefon = rezervace[index][1]
        email = rezervace[index][2]
        adresa = rezervace[index][3]
        typ = rezervace[index][4]
        delka = rezervace[index][5]
        cena = rezervace[index][6]
        datumcas = rezervace[index][7]
        zprava = rezervace[index][8]

        vygeneruj_fakturu(jmeno, telefon, email, adresa, typ, delka, cena, datumcas, zprava)
        flash('Faktura byla znovu vytvořena.', 'success')

    return redirect(url_for('admin'))

def odesli_upozorneni_ivanovi(jmeno, telefon, email, typ, delka, datum, cas):
    zprava = f"""
Nová rezervace!

👤 Jméno: {jmeno}
📞 Telefon: {telefon}
✉️ E-mail: {email}
💆 Typ masáže: {typ}
⏱️ Délka: {delka} minut
📅 Datum: {datum}
🕒 Čas: {cas}
    """

    try:
        msg = Message(
            subject="Nová rezervace – Tyrkys masáže",
            sender=app.config['MAIL_USERNAME'],
            recipients=["ivannalukovets01071987@gmail.com"],  # или другой email для уведомлений
            body=zprava
        )
        mail.send(msg)
    except Exception as e:
        print(f"Chyba při odesílání upozornění: {e}")



if __name__ == '__main__':
    app.run(debug=True, port=5001)
