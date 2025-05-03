Detaillierte Erklärung des Projekts: Nummernschilderkennung mit Home Assistant-Integration
Überblick
Dieses Projekt realisiert ein automatisiertes System zur Erkennung von Nummernschildern, das über eine RTSP-Kamera mit Bewegungserkennung Bilder aufnimmt, die Nummernschilder extrahiert und die Ergebnisse in Home Assistant anzeigt. Die Lösung besteht aus mehreren Komponenten, die nahtlos zusammenarbeiten:

Kamera und Bewegungserkennung (via Kerberos.io-Container)
Bildverarbeitung und OCR (Python-Skript mit OpenCV und Tesseract)
Datenbank und Webinterface (Flask mit SQLite)
Integration in Home Assistant (ohne MQTT)

Komponenten des Projekts

Kerberos.io-Container (Bewegungserkennung)

Zweck: Erfasst RTSP-Videoströme und löst bei Bewegungserkennung Fotos aus.

Funktionsweise:

Der Container überwacht einen RTSP-Stream (z. B. rtsp://user:pass@camera_ip:554/stream).
Bei erkannter Bewegung schneidet Kerberos ein Bild aus dem Video und speichert es im Ordner /capture (z. B. als latest.jpg).

Die Bilder werden an den License Plate Reader (Python-Skript) weitergegeben.

License Plate Reader (Python-Skript)

Zweck: Verarbeitet die von Kerberos gelieferten Bilder, extrahiert Nummernschilder und speichert sie in Home Assistant.

Kernelemente:

Bildverarbeitung:

Umwandlung des Bildes in Graustufen.
Kantenerkennung mit Canny-Algorithmus.
Konturenfilterung zur Identifizierung des Nummernschild-Rahmens.
OCR mit Tesseract zur Textextraktion.

Datenbank: Speichert erkannte Nummernschilder mit Zeitstempel und Bilddateipfad in einer SQLite-Datenbank (license_plates.db).

Webserver: Liefert die neuesten Ergebnisse über eine REST-API und hostet das Webinterface.

Bildspeicherung: Verarbeitete Bilder werden im Ordner /processed_images mit Datum/Uhrzeit strukturiert archiviert.


Home Assistant-Integration

Zweck: Anzeige des letzten erkannten Nummernschildes und dessen Bild in der Home Assistant-Oberfläche.


Komponenten:
Generic Camera: Zeigt das letzte erkannte Bild an.
REST Sensor: Ruft das letzte Nummernschild über die Flask-API ab.


Datenfluss und Funktionsweise
Bildaufnahme durch Kerberos
RTSP-Stream: Kerberos überwacht kontinuierlich den Videoinput (z. B. einer Überwachungskamera).
Bewegungserkennung: Bei erkannter Bewegung im Sichtfeld speichert Kerberos ein Bild im Ordner /capture.
Dateiname: Das Bild wird als latest.jpg gespeichert (kann konfiguriert werden).

Bildverarbeitung durch Python-Skript
Dateiüberwachung:
Ein Thread überwacht den Ordner /capture auf neue Dateien.
Bei Änderung wird die Funktion detect_number_plate(file_path) aufgerufen.

Bildverarbeitung:
Das Bild wird auf Schärfe und Stabilität geprüft. Graustufen- und Kantenerkennung filtern irrelevante Bildinhalte. Konturen werden analysiert, um den Nummernschild-Rahmen zu lokalisieren.
Tesseract OCR extrahiert den Text aus dem ausgeschnittenen Bereich.

Speicherung:
Erkannte Nummernschilder werden in der SQLite-Datenbank (license_plates.db) gespeichert.
Das verarbeitete Bild wird im Ordner /processed_images archiviert. Das letzte erkannte Bild wird als latest.jpg aktualisiert.

Integration in Home Assistant
Generic Camera:

Zeigt das letzte erkannte Bild (latest.jpg) in der Home Assistant-Oberfläche an.

Beispielkonfiguration:
camera:
  - platform: generic
    name: "Nummernschild-Kamera"
    still_image_url: "http://<IP_DES_CONTAINERS>:8087/static/latest.jpg"
    refresh_interval: 10


REST Sensor:
Ruft das letzte erkannte Nummernschild über die Flask-API ab.


Beispielkonfiguration:
sensor.rest:
  - name: "Letztes Nummernschild"
    resource: "http://<IP_DES_CONTAINERS>:8087/api/latest_plate"
    value_template: "{{ value_json.plate_number }}"
    scan_interval: 10

    
Zusätzliche Funktionen

Automatische Bereinigung alter Bilder

Zweck: Löscht Bilder, die älter als 10 Tage sind, um Speicherplatz zu sparen.

Implementierung:
Ein Hintergrundthread führt täglich die Funktion cleanup_old_images() aus. Bilder werden nach dem Änderungsdatum (os.path.getmtime) gefiltert. Leere Verzeichnisse werden automatisch entfernt.

Manueller Löschen-Button
Zweck: Ermöglicht das manuelle Löschen aller Bilder und Daten über die Web-Oberfläche.

Funktionsweise:
Ein Button in index.html ruft die Flask-Rest-API /api/delete_images auf.

Löscht:
Alle Bilder in /processed_images. Das letzte erkannte Bild (latest.jpg). Alle Einträge aus der Datenbank.

Webinterface (index.html)

Hauptfunktionen

Anzeige des letzten Bildes:

Zeigt latest.jpg mit dynamischer Cache-Busting-URL (?timestamp) an.

Anzeige des letzten Nummernschildes:
Wird aus der Flask-API /api/latest_plate geladen.

Historie der letzten 10 Erkennungen:
Tabelle mit Nummernschild und Zeitstempel.


Löschen-Button:
Ruft die DELETE-API auf und aktualisiert die Oberfläche nach Bestätigung.


Vorteile und Anwendung

Echtzeit-Erkennung: Sofortige Erfassung von Nummernschildern bei Bewegung. Automatisierung: Kein manueller Eingriff erforderlich.
Datenarchivierung: Erkannte Schilder werden langfristig gespeichert. Integration in Home Assistant: Einfache Verbindung zu Smart-Home-Automationen (z. B. Torsteuerung bei bekanntem Nummernschild).
Skalierbarkeit: Erweiterbar auf mehrere Kameras oder andere OCR-Objekte.


Anwendungsszenarien
Garagentor-Steuerung: Öffnen des Tores bei Erkennung eines autorisierten Nummernschildes. Besuchserfassung: Automatische Log-Einträge bei Anfahrt.
Sicherheitsüberwachung: Identifizierung von Fahrzeugen bei verdächtigen Aktivitäten.

Technische Details
Docker-Container
Kerberos.io: Für Videoaufnahme und Bewegungserkennung.
License Plate Reader: Python-Skript mit Flask, OpenCV, Tesseract.
Home Assistant: Integration über REST- und Generic-Kamera-Komponenten.


Ordnerstruktur
/capture                  # Bilder von Kerberos
/processed_images         # Archivierte Bilder mit Datum/Uhrzeit
/static/latest.jpg        # Letztes erkanntes Bild
/license_plates.db        # SQLite-Datenbank
/data/license_plates.txt  # Textdatei mit Erkennungen


API-Endpunkte
/api/latest_plate: Gibt das letzte Nummernschild und Bild-URL zurück.
/api/plates: Liste der letzten 10 Erkennungen.
/api/delete_images: Löscht alle Bilder und Daten (DELETE-Request).
