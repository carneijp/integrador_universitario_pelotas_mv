import datetime
import cx_Oracle
import sys
import warnings
from typing import Set
from Services.Bacteriology.BacteriologyIntegrator import BacteriologyIntegrator
from Services.BaseIntegrationService import BaseIntegrationService
from Services.Prescription.PrescriptionIntegrator import PrescriptionIntegrator
from Utils.HealthMonitor.HealthMonitorClient import HealthMonitorClient
from Utils.Authenticator.Authenticator import Authenticator
warnings.filterwarnings("ignore")

class Integrator():
    def __init__(self) -> None:
        if sys.platform == 'win32':
            lib_dir=r"..\instantclient_21_14_windows"
            cx_Oracle.init_oracle_client(lib_dir= lib_dir)
        else:
            if sys.platform == 'linux' or sys.platform == 'linux2':
                lib_dir=r"..\instantclient_21_14_linux"
                cx_Oracle.init_oracle_client(lib_dir= lib_dir)
            else:
                Exception("Esse OS NÃO É suportado para o integrador.")
        
        self.__authenticator = Authenticator()
        # self.bacteriologyIntegrator = BacteriologyIntegrator(self.__authenticator)
        self.prescriptionIntegrator = PrescriptionIntegrator(self.__authenticator)
        
        self.implementedServices: Set[BaseIntegrationService] = set([
            # self.bacteriologyIntegrator,
            self.prescriptionIntegrator
        ])
        self.healthMonitor = HealthMonitorClient(self.implementedServices)

        print(f"Iniciando sistema de integração com Qualis, data: {datetime.datetime.now()}")

    def start_all_implemented_services(self):
        """Inicia as threads de todos os serviços implementados."""
        for service in self.implementedServices:
            service._start()

    def stop_all_implemented_services(self):
        """Solicita parada das threads de todos os serviços implementados."""
        for service in self.implementedServices:
            service._stop()