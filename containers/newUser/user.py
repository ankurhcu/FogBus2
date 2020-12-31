import logging
import sys

from broker import Broker
from apps import FaceDetection, FaceAndEyeDetection, ColorTracking

if __name__ == "__main__":

    appID = int(sys.argv[1])
    videoPath = sys.argv[2] if len(sys.argv) > 2 else None

    if appID == 1:
        broker = Broker(
            host='127.0.0.1',
            port=5000,
            appIDs=[1],
            logLevel=logging.DEBUG)
        app = FaceDetection(1, broker, videoPath)
        app.run()
    elif appID == 2:
        broker = Broker(
            host='127.0.0.1',
            port=5000,
            appIDs=[1, 2],
            logLevel=logging.DEBUG)
        app = FaceAndEyeDetection(2, broker, videoPath)
        app.run()
    elif appID == 3:

        broker = Broker(
            host='127.0.0.1',
            port=5000,
            appIDs=[3],
            logLevel=logging.DEBUG)
        app = ColorTracking(3, broker, videoPath)
        app.run()
