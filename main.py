import cv2
import imutils
import pytesseract
import os
import time
import logging
import traceback
import json
from datetime import datetime, timezone, timedelta
import pytz
from flask import Flask, render_template, jsonify, send_from_directory, request
from flask_sqlalchemy import SQLAlchemy
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Thread
from contextlib import contextmanager

# Logging konfigurieren
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Flask-App initialisieren
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/license_plates.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Globale Variable für das letzte verarbeitete Bild
latest_image = '/app/static/latest.jpg'
processed_images_dir = '/app/processed_images'
text_file_path = '/app/data/license_plates.txt'

# Zeitzone
local_tz = pytz.timezone('Europe/Zurich')

# Datenbank-Modell
class LicensePlate(db.Model):
    __tablename__ = 'license_plates'
    id = db.Column(db.Integer, primary_key=True)
    plate_number = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(255), nullable=False)

# Kontextmanager für Application Context
@contextmanager
def app_context():
    ctx = app.app_context()
    ctx.push()
    try:
        yield
    finally:
        ctx.pop()

# Hilfsfunktion: Warte, bis die Datei stabil ist
def wait_for_file_stable(path, timeout=10, check_interval=1):
    if not os.path.exists(path):
        logger.debug(f"Datei existiert nicht: {path}")
        return False

    initial_size = os.path.getsize(path)
    start_time = time.time()

    while time.time() - start_time < timeout:
        time.sleep(check_interval)
        current_size = os.path.getsize(path)
        if current_size == initial_size:
            logger.debug(f"Datei {path} stabil nach {time.time() - start_time:.2f}s")
            return True
        initial_size = current_size

    logger.debug(f"Datei {path} ist stabil geblieben")
    return True

# Automatische Bereinigung alter Bilder
def cleanup_old_images():
    logger.info("Starte Bereinigung alter Bilder")
    
    try:
        now = datetime.now(local_tz)
        cutoff_date = now - timedelta(days=10)
        
        for root, dirs, files in os.walk(processed_images_dir):
            for file in files:
                if file.endswith((".jpg", ".jpeg", ".png")):
                    file_path = os.path.join(root, file)
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path), local_tz)
                    
                    if file_mtime < cutoff_date:
                        try:
                            os.remove(file_path)
                            logger.info(f"Alte Datei gelöscht: {file_path}")
                        except Exception as e:
                            logger.error(f"Kann Datei {file_path} nicht löschen: {str(e)}")
        
        # Leere Verzeichnisse löschen
        for root, dirs, files in os.walk(processed_images_dir, topdown=False):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    if not os.listdir(dir_path):  # Verzeichnis leer?
                        os.rmdir(dir_path)
                        logger.info(f"Leeres Verzeichnis gelöscht: {dir_path}")
                except Exception as e:
                    logger.error(f"Kann Verzeichnis {dir_path} nicht löschen: {str(e)}")
        
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung: {str(e)}")
        logger.error(traceback.format_exc())

def start_cleanup_thread():
    while True:
        try:
            cleanup_old_images()
            # Alle 24 Stunden ausführen
            time.sleep(86400)
        except Exception as e:
            logger.error(f"Fehler im Bereinigungs-Thread: {str(e)}")
            time.sleep(3600)

# Bild speichern mit Zeitschema
def save_processed_image(image, base_name):
    now = datetime.now(local_tz)
    date_dir = now.strftime("%Y-%m-%d")
    hour_dir = now.strftime("%H")
    
    target_dir = os.path.join(processed_images_dir, date_dir, hour_dir)
    os.makedirs(target_dir, exist_ok=True)
    
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{base_name}.jpeg"
    target_path = os.path.join(target_dir, filename)
    
    cv2.imwrite(target_path, image)
    return target_path

# Textdatei aktualisieren
def append_to_text_file(plate_number):
    try:
        with open(text_file_path, 'a') as f:
            now = datetime.now(local_tz)
            f.write(f"{now.isoformat()},{plate_number}\n")
        logger.debug(f"Nummernschild in Textdatei gespeichert: {plate_number}")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben in Textdatei: {str(e)}")

# Bildverarbeitung mit Fehlerbehandlung
def detect_number_plate(file_path):
    try:
        logger.debug(f"Verarbeite neues Bild: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"Datei existiert nicht: {file_path}")
            return None

        if not wait_for_file_stable(file_path):
            logger.error(f"Datei {file_path} ist nicht stabil")
            os.remove(file_path)
            return None

        image = cv2.imread(file_path)
        if image is None:
            logger.error(f"Kann Bild nicht laden: {file_path}")
            os.remove(file_path)
            return None

        # Bild verarbeiten
        image = imutils.resize(image, width=500)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray, 170, 200)
        
        # Konturen finden
        cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:30]
        
        for c in cnts:
            perimeter = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * perimeter, True)
            if len(approx) == 4:
                x, y, w, h = cv2.boundingRect(c)
                crp_img = image[y:y+h, x:x+w]
                temp_path = '/tmp/number_plate.png'
                cv2.imwrite(temp_path, crp_img)
                
                # OCR durchführen
                text = pytesseract.image_to_string(temp_path, lang='deu')
                text = ''.join(e for e in text if e.isalnum())
                
                if text:
                    logger.debug(f"Nummernschild erkannt: {text}")
                    cv2.putText(image, text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cv2.imwrite(latest_image, image)
                    
                    processed_path = save_processed_image(image, text)
                    
                    with app_context():
                        new_plate = LicensePlate(plate_number=text, image_path=processed_path)
                        db.session.add(new_plate)
                        db.session.commit()
                    
                    # Textdatei aktualisieren
                    append_to_text_file(text)
                
                try:
                    os.remove(file_path)
                    logger.debug(f"Originalbild gelöscht: {file_path}")
                except Exception as e:
                    logger.error(f"Fehler beim Löschen des Originalbildes: {str(e)}")
                
                return text
        
        # Kein Nummernschild gefunden
        logger.debug("Kein Nummernschild gefunden")
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.debug(f"Bild ohne Nummernschild gelöscht: {file_path}")
            except Exception as e:
                logger.error(f"Fehler beim Löschen des leeren Bildes: {str(e)}")
                
        return None
        
    except Exception as e:
        logger.error(f"Fehler bei der Bildverarbeitung: {str(e)}")
        logger.error(traceback.format_exc())
        return None

# Flask-Routen
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/plates')
def get_plates():
    try:
        local_tz = pytz.timezone('Europe/Zurich')
        plates = LicensePlate.query.order_by(LicensePlate.timestamp.desc()).limit(10).all()
        return jsonify([{
            'plate_number': p.plate_number,
            'timestamp': p.timestamp.replace(tzinfo=timezone.utc).astimezone(local_tz).isoformat(),
            'image_path': p.image_path.replace('/app/', '')
        } for p in plates])
    except Exception as e:
        logger.error(f"Fehler bei API-Anfrage: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/latest_plate')
def get_latest_plate():
    try:
        local_tz = pytz.timezone('Europe/Zurich')
        plate = LicensePlate.query.order_by(LicensePlate.timestamp.desc()).first()
        if plate:
            return jsonify({
                'plate_number': plate.plate_number,
                'timestamp': plate.timestamp.replace(tzinfo=timezone.utc).astimezone(local_tz).isoformat(),
                'image_url': f"/static/latest.jpg?{int(time.time())}"
            })
        else:
            return jsonify({'plate_number': None, 'timestamp': None, 'image_url': '/static/placeholder.jpg'})
    except Exception as e:
        logger.error(f"Fehler bei API-Anfrage: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Neue Route für manuelles Löschen
@app.route('/api/delete_images', methods=['DELETE'])
def delete_images():
    try:
        # Dateien löschen
        for root, dirs, files in os.walk(processed_images_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Kann Datei {file_path} nicht löschen: {str(e)}")
        
        # Leere Verzeichnisse löschen
        for root, dirs, files in os.walk(processed_images_dir, topdown=False):
            for dir in dirs:
                dir_path = os.path.join(root, dir)
                try:
                    os.rmdir(dir_path)
                except Exception as e:
                    logger.error(f"Kann Verzeichnis {dir_path} nicht löschen: {str(e)}")
        
        # Letztes Bild zurücksetzen
        if os.path.exists(latest_image):
            os.remove(latest_image)
            cv2.imwrite(latest_image, 255 * np.ones((100, 400, 3), np.uint8))  # Leeres Bild
        
        # Datenbank leeren
        with app_context():
            db.session.query(LicensePlate).delete()
            db.session.commit()
        
        logger.info("Alle Bilder und Daten wurden gelöscht")
        return jsonify({"status": "success", "message": "Alle Bilder wurden gelöscht"})
    except Exception as e:
        logger.error(f"Fehler beim Löschen: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/images/<path:path>')
def send_image(path):
    return send_from_directory('/app', path)

def start_observer():
    while True:
        try:
            logger.debug("Starte Datei-Überwachung...")
            path = "/capture"
            
            if not os.path.exists(path):
                logger.error(f"Verzeichnis existiert nicht: {path}")
                time.sleep(5)
                continue
                
            event_handler = FileSystemEventHandler()
            event_handler.on_modified = lambda e: detect_number_plate(e.src_path) if e.src_path.endswith((".jpg", ".jpeg")) else None
            
            observer = Observer()
            observer.schedule(event_handler, path, recursive=False)
            observer.start()
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
            
            observer.join()
            
        except Exception as e:
            logger.error(f"Fehler in der Datei-Überwachung: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(5)

if __name__ == '__main__':
    os.makedirs(os.path.dirname(latest_image), exist_ok=True)
    os.makedirs(processed_images_dir, exist_ok=True)
    os.makedirs('/app/data', exist_ok=True)  # Für die Textdatei
    
    with app.app_context():
        try:
            db.create_all()
            logger.debug("Datenbanktabellen erstellt")
        except Exception as e:
            logger.error(f"Fehler bei Datenbankinitialisierung: {str(e)}")
    
    # Hintergrundthreads starten
    observer_thread = Thread(target=start_observer)
    observer_thread.daemon = True
    observer_thread.start()
    
    cleanup_thread = Thread(target=start_cleanup_thread)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    logger.debug("Starte Flask-Webserver auf Port 5000")
    app.run(host='0.0.0.0', port=5000)