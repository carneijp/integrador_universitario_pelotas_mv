from abc import ABC, abstractmethod
from threading import Event, Thread
from Utils.Authenticator.Authenticator import Authenticator
from Utils import Constant as C
from enum import Enum
import time
import requests

class ServiceOptionsEnum(Enum):
    PRESCRIPTION = "prescription"
    BACTERIOLOGY = "bacteriology"

    def __str__(self) -> str:
        return self.value

class BaseIntegrationService(ABC):
    def __init__(self, service_name: ServiceOptionsEnum, authenticator: Authenticator):
        self.service_name = str(service_name)
        self._authenticator = authenticator
        self._worker: Thread | None = None
        self._stop_event = Event()
        self._last_progress_at = 0.0
        self._stale_after_seconds = 300

        self.prescritorsReported = dict()
        self.thread_erros_runing = False

    def _report_progress(self):
        self._last_progress_at = time.time()

    def _start(self):
        if self._worker is None or not self._worker.is_alive():
            self._stop_event.clear()
            self._report_progress()
            self._worker = Thread(target=self._monitor_loop, daemon=True)
            self._worker.start()

    def _stop(self):
        if self._worker is None:
            return

        self._stop_event.set()
        # Services sleep in 60s windows; give enough time for graceful exit.
        self._worker.join(timeout=65)
        if self._worker is not None and not self._worker.is_alive():
            self._worker = None

    def get_processing_thread_status(self) -> bool:
        is_alive = self._worker is not None and self._worker.is_alive()
        if not is_alive:
            return False

        seconds_without_progress = time.time() - self._last_progress_at
        return seconds_without_progress <= self._stale_after_seconds
    
    def _send_email(self, message: str, subject: str, email_destination: str = "suporte@portalqualis.com.br"):
        emailBody = {
            "mensagem": message,
            "subject": subject,
            "email_destination": email_destination
        }        
        header = {'Authorization': C.HOSPITAL_KEY}
        requests.post(
            url= f"{C.BOT_BASE_URL}/send_email", 
            json= emailBody, 
            headers= header, 
            verify= False
        )

    @abstractmethod
    def _monitor_loop(self):
        pass