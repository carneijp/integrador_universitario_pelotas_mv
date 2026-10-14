from datetime import datetime
import time
from threading import Thread
import requests
from Utils import Constant as C
from Services.BaseIntegrationService import BaseIntegrationService

class HealthMonitorClient:
    def __init__(self, implementedServices: set[BaseIntegrationService]):
        self.last_hour_count = dict()
        self.implementedServices = implementedServices
        self.__clockWorker = Thread(target= self.__clockMonitorLoop, daemon= True)
        self.__clockWorker.start()

    def __processHealthStatus(self, date: datetime):
        report = dict()
        report['hospital_token'] = C.HOSPITAL_KEY
        report['year'] = date.year
        report['month'] = date.month
        report['day'] = date.day
        report['hour'] = date.hour
        report['services_status'] = [{"service": service.service_name, "status" : service.get_processing_thread_status()} for service in self.implementedServices]

        header = {'Authorization':C.HOSPITAL_KEY}
        requests.post(url= f"{C.BOT_BASE_URL}/health_report",json= report,headers= header, verify= False)

    def __clockMonitorLoop(self):
        """Will Be always monitoring the minute so it can give a trigger to run the report generation"""
        while True:
            now = datetime.now()
            process_data_thread = Thread(target= self.__processHealthStatus, args= (now, ))
            process_data_thread.start()
            time.sleep(60)