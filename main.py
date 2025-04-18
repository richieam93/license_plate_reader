import cv2
import easyocr
import imutils
import numpy as np
import paho.mqtt.client as mqtt
import os
from flask import Flask, Response, render_template

# MQTT configuration
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(os.getenv('MQTT_USERNAME'), os.getenv('MQTT_PASSWORD'))
mqtt_client.connect(os.getenv('MQTT_BROKER_URL'), int(os.getenv('MQTT_BROKER_PORT')))
mqtt_client.loop_start()

# Flask app for web server
app = Flask(__name__)

# Global variable to store the latest license plate
latest_license_plate = ""

@app.route('/')
def index():
    return render_template('index.html', license_plate=latest_license_plate)

def gen_frames():
    rtsp_url = os.getenv('RTSP_STREAM_URL')
    cap = cv2.VideoCapture(rtsp_url)

    reader = easyocr.Reader(['en'])

    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            bfilter = cv2.bilateralFilter(gray, 11, 17, 17)
            edged = cv2.Canny(bfilter, 30, 200)
            keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            contours = imutils.grab_contours(keypoints)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

            location = None
            for contour in contours:
                approx = cv2.approxPolyDP(contour, 10, True)
                if len(approx) == 4:
                    location = approx
                    break

            if location is not None:
                mask = np.zeros(gray.shape, np.uint8)
                new_image = cv2.drawContours(mask, [location], 0, 255, -1)
                new_image = cv2.bitwise_and(frame, frame, mask=mask)
                (x, y) = np.where(mask == 255)
                (x1, y1) = (np.min(x), np.min(y))
                (x2, y2) = (np.max(x), np.max(y))
                cropped_image = gray[x1:x2 + 1, y1:y2 + 1]

                result = reader.readtext(cropped_image)
                if result:
                    text = result[0][-2]
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    frame = cv2.putText(frame, text=text, org=(location[0][0][0], location[1][0][1] + 60), fontFace=font, fontScale=1, color=(0, 255, 0), thickness=2, lineType=cv2.LINE_AA)
                    frame = cv2.rectangle(frame, tuple(location[0][0]), tuple(location[2][0]), (0, 255, 0), 3)
                    latest_license_plate = text
                    mqtt_client.publish("homeassistant/license_plate", text)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)