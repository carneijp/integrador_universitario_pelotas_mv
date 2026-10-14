import tkinter as tk
import threading
import tkinter.messagebox as mb
import socket
import customtkinter
from customtkinter import CTkToplevel
import math
from Integrator import Integrator
from Utils import dataRequest
customtkinter.set_appearance_mode("Light")  # Modes: "System" (standard), "Dark", "Light"
customtkinter.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

def text_truncated(text: str, font: customtkinter.CTkFont, max_width: int) -> str:
    text = text.replace("\n", "")
    text = text.replace("\t", "")
    measure = font.measure(text= text) 
    if  measure < (max_width):
        return text
    else:
        return text[:(math.floor(len(text)*((max_width)/measure)) -3)] + '...'

class Data_row(customtkinter.CTkFrame):
    def __init__(self, parent, date_text, nr_prescr_text, id_qualis_prescr, status_sended_text, resposta_envio_text, app):
        super().__init__(master= parent, width= 1000, height= 50, fg_color= "#ffffff", bg_color= "#ffffff")
        self.app = app
        self.font = customtkinter.CTkFont(family= 'Arial', size= 12)#, weight= 'bold')
        self.grid(row=0, column=0, sticky = "nswe")
        self.grid_columnconfigure(8, weight= 1)
        self.prescr = None
        self.detail_window = None
        self.latest_id = None

        self.data = customtkinter.CTkLabel(self, width= 120, font= self.font, text= text_truncated(date_text, self.font, 120) if date_text is not None else " - ")
        self.data.grid(row= 0, column= 0, padx= 8, pady= 4, sticky= 'nswe')

        barra_vertical_1 = customtkinter.CTkFrame(self, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_1.grid(row=0 , column= 1, sticky= 'nswe')

        self.nr_prescricao = customtkinter.CTkLabel(self, width= 82, font= self.font, text= text_truncated(nr_prescr_text, self.font, max_width= 81) if nr_prescr_text is not None else " - ")
        self.nr_prescricao.grid(row= 0, column= 2, padx= 8, pady= 4, sticky = "nswe")

        barra_vertical_2 = customtkinter.CTkFrame(self, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_2.grid(row=0 , column= 3, sticky = "nswe")

        self.id_qualis = customtkinter.CTkLabel(self, width= 80, font= self.font, text= text_truncated(id_qualis_prescr, self.font, max_width= 80) if id_qualis_prescr is not None else " - ")
        self.id_qualis.grid(row= 0, column= 4, padx= 8, pady= 4, sticky = "nswe")

        barra_vertical_3 = customtkinter.CTkFrame(self, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_3.grid(row=0 , column= 5, sticky = "nswe")

        self.status_envio = customtkinter.CTkLabel(self, width= 80, font= self.font, text= text_truncated(status_sended_text, self.font, max_width= 80) if status_sended_text is not None else " - ")
        self.status_envio.grid(row= 0, column= 6, padx= 8, pady= 4, sticky = "nswe")

        barra_vertical_4 = customtkinter.CTkFrame(self, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_4.grid(row=0 , column= 7, sticky = "nswe")

        self.sobre_envio = customtkinter.CTkLabel(self, anchor= 'w', font= self.font, text= text_truncated(resposta_envio_text, self.font, max_width= 600) if resposta_envio_text is not None else " - ")
        self.sobre_envio.grid(row= 0, column= 8, padx= 8, pady= 4, sticky= 'w')

        barra_vertical_5 = customtkinter.CTkFrame(self, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_5.grid(row=0 , column= 9, sticky = "nswe")
        
        self.detalhes = customtkinter.CTkButton(self, width=80, corner_radius= 12, text= "Detalhes",command = self.open_new_details_window)
        self.detalhes.grid(row= 0, column= 10, padx= 8, pady= 4, sticky = "nswe")
    
    def open_new_details_window(self):
        if self.detail_window is None or not self.detail_window.winfo_exists():
            self.detail_window = Details(parent= self)
            self.detail_window.focus()
        else:
            self.detail_window.prescr = self.prescr
            self.detail_window.update_new_data()
            self.detail_window.focus()

class Details(CTkToplevel):
    def __init__(self, parent: Data_row, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent
        self.prescr_id = parent.prescr['prescr_id'] if parent.prescr is not None else "Nenhuma prescrição selecionada"
        self.prescr = parent.prescr 
        self.title(f"Detalhes da Prescrição: {self.prescr_id}")
        self.geometry("1000x600")

        self.grid_columnconfigure(0, weight= 1)
        self.grid_rowconfigure(1, weight= 1)

        self.font = customtkinter.CTkFont(family= 'Arial', size= 12)

        self.row1_details_prescr = self.basic_info_patient()
        self.row1_details_prescr.grid(row=0, column=0, sticky= 'nswe')

        self.row_2_main_information = self.main_information()
        self.row_2_main_information.grid(row=1, column=0, sticky= 'nswe')

        self.row_3_action = self.action_options()
        self.row_3_action.grid(row= 2, column= 0, sticky= 'nswe')

    def basic_info_patient(self):
        frame = customtkinter.CTkFrame(master= self, width= 850, height= 100, corner_radius= 0)
        frame.grid_columnconfigure((0,1,2), weight= 1)
        
        prescr_id_details_text = f'Id de prescrição: {self.prescr['prescr_id'] if self.prescr['prescr_id']  is not None else ' - '}' if self.prescr is not None else 'Id de prescrição:  - '
        self.prescr_id_details = customtkinter.CTkLabel(frame, text= prescr_id_details_text, font= self.font)
        self.prescr_id_details.grid(row= 0, column= 0, padx= 20, pady= 10, sticky= 'nsw')

        prescr_id_qualis_text = f'Id de prescrição na Qualis: {self.prescr['prescr_id_on_qualis'] if self.prescr['prescr_id_on_qualis'] is not None else ' - '}' if self.prescr is not None else 'Id de prescrição na Qualis:  - '
        self.prescr_id_qualis = customtkinter.CTkLabel(frame, text= prescr_id_qualis_text, font= self.font)
        self.prescr_id_qualis.grid(row= 1, column= 0, padx= 20, pady= (0, 10), sticky= 'nsw')

        prescr_data_liberacao_text = f'Data de liberação: {self.prescr['dt_liberacao'] if self.prescr['dt_liberacao'] is not None else ' - '}' if self.prescr is not None else 'Data de liberação:  - '
        self.data_liberacao = customtkinter.CTkLabel(frame, text= prescr_data_liberacao_text, font= self.font)
        self.data_liberacao.grid(row= 0, column= 1, padx= 20, pady= 10, sticky= 'nsw')

        prescr_codigo_paciente_text = f'Código do paciente: {self.prescr['patient_hospital_id'] if self.prescr['patient_hospital_id'] is not None else ' - '}' if self.prescr is not None else 'Codigo do paciente:  - '
        self.codigo_paciente = customtkinter.CTkLabel(frame, text= prescr_codigo_paciente_text, font= self.font)
        self.codigo_paciente.grid(row= 1, column= 1, padx= 20, pady= (0, 10), sticky= 'nsw')

        prescr_infection_name_text = text_truncated(text= f'Nome infecção: {self.prescr['infection_name'] if self.prescr['infection_name'] is not None else ' - '}', font= self.font, max_width= 300) if self.prescr is not None else 'Nome infecção:  - '
        self.infection_name = customtkinter.CTkLabel(frame, text= prescr_infection_name_text, font= self.font)
        self.infection_name.grid(row= 0, column= 2, padx= 20, pady= 10, sticky= 'nsw')

        prescr_codigo_medico_text = f'Código do médico prescritor: {self.prescr['cd_medico'] if self.prescr['cd_medico'] is not None else ' - '}' if self.prescr is not None else 'Codigo do medico:  - '
        self.codigo_medico = customtkinter.CTkLabel(frame, text= prescr_codigo_medico_text, font= self.font)
        self.codigo_medico.grid(row= 1, column= 2, padx= 20, pady= (0, 10), sticky= 'nsw')

        return frame
    
    def main_information(self):
        frame = customtkinter.CTkFrame(master= self, width= 850, height= 100, corner_radius= 0)
        frame.grid_columnconfigure((0,1), weight= 1)
        frame.grid_rowconfigure(1, weight= 1)

        label_font = customtkinter.CTkFont(family= 'Arial', size= 16, weight= 'bold')
        
        body_label = customtkinter.CTkLabel(frame, text= "Body enviado para Qualis", font= label_font)
        body_label.grid(row= 0, column= 0, padx= 20, pady= 10, sticky= 'nswe')

        prescr_body_sended_text = (self.prescr['body_sended'] if self.prescr['body_sended'] is not None else 'Body ainda não gerado, ou houve falha ao salvar o body.' if self.prescr['prescr_sended_status'] != '0' else '') if self.prescr is not None else ''
        self.body_sended = customtkinter.CTkTextbox(frame)
        self.body_sended.grid(row= 1, column= 0, padx= 20, pady= (0, 10), sticky= 'nswe')
        self.body_sended.insert("0.0", prescr_body_sended_text)

        message_result_label = customtkinter.CTkLabel(frame, text= "Retorno do envio para Qualis", font= label_font)
        message_result_label.grid(row= 0, column= 1, padx= 20, pady= 10, sticky= 'nswe')
        
        prescr_messafe_result_sended_text = (self.prescr['prescr_sended_message'] if self.prescr['prescr_sended_message'] is not None else 'Ainda sem retorno de um medico da qualis' if self.prescr['prescr_sended_status'] == '1' else 'Falha ao capturar o erro'  if self.prescr['prescr_sended_status'] != '0' else '') if self.prescr is not None else '' 
        self.message_result_sended = customtkinter.CTkTextbox(frame)
        self.message_result_sended.grid(row= 1, column= 1, padx= 20, pady= (0,10), sticky= 'nswe')
        self.message_result_sended.insert("0.0", prescr_messafe_result_sended_text)
        
        return frame
    
    def action_options(self):
        frame = customtkinter.CTkFrame(master= self, width= 850, height= 100, corner_radius= 0)
        frame.grid_columnconfigure(0, weight= 1)

        self.command_result = customtkinter.CTkLabel(frame, text= f'', font= self.font)
        self.command_result.grid(row= 0, column= 0, padx= 20, pady = 10, sticky= 'nswe')

        button_text = (f'Reenviar' if self.prescr['prescr_sended_status'] in ['-1', '-2', '-3'] else 'Enviar' if self.prescr['prescr_sended_status'] == '0' else 'Buscar resposta' if self.prescr['prescr_status'] == '0' else 'Fechar') if self.prescr is not None else 'Fechar'
        self.button_details = customtkinter.CTkButton(frame, text= button_text, command= self.button_operation_decision)
        self.button_details.grid(row= 0, column= 1, padx= (0,20), pady= 10, sticky= 'nswe')

        return frame

    def button_operation_decision(self):
        if self.prescr is not None:
            prescr_id = self.prescr['prescr_id']
            if self.prescr['prescr_sended_status'] in ['-1', '-2', '-3', '0']:
                self.command_result.configure(text= "Enviando a prescrição novamente o sistema irá parecer travado, levará 10 segundos.")
                self.parent.app.integrator.prescriptionIntegrator.try_send_prescription(self.prescr)
                query = f"""
                    SELECT *
                    FROM DBAMV.prescription_qualis
                    WHERE prescr_id = '{prescr_id}'
                """
                df = dataRequest.get_data(queryText= query)
                if df is not None:
                    if len(df) > 0:
                        self.prescr = df.iloc[0]
                        self.update_new_data()
                        self.command_result.configure(text= "Prescrição enviada")
                        return
                self.command_result.configure(text= "Falha ao enviar a prescrição")
            else:
                if self.prescr['prescr_status'] == '0':
                    self.parent.app.integrator.prescriptionIntegrator.try_get_doctor_answer_for_prescription(self.prescr)
                    query = f"""
                        SELECT *
                        FROM DBAMV.prescription_qualis
                        WHERE prescr_id = '{prescr_id}'
                    """
                    df = dataRequest.get_data(queryText= query)
                    if df is not None:
                        if len(df) > 0:
                            self.prescr = df.iloc[0]
                            self.update_new_data()
                            if self.prescr['prescr_status'] != 0:
                                self.command_result.configure(text= "Prescrição respondida")
                            else:
                                self.command_result.configure(text= "Prescrição ainda não respondida")
                            return
                    self.command_result.configure(text= "Falha ao enviar ao buscar resposta")
                else:
                    self.on_closing()
        else:
            self.on_closing()    

    def update_new_data(self):
        prescr_id_text = f'Id de prescrição: {self.prescr['prescr_id'] if self.prescr['prescr_id']  is not None else ' - '}' if self.prescr is not None else 'Id de prescrição:  - '
        self.prescr_id_details.configure(text= prescr_id_text)

        prescr_id_qualis_text = f'Id de prescrição na Qualis: {self.prescr['prescr_id_on_qualis'] if self.prescr['prescr_id_on_qualis'] is not None else ' - '}' if self.prescr is not None else 'Id de prescrição na Qualis:  - '
        self.prescr_id_qualis.configure(text= prescr_id_qualis_text)

        prescr_data_liberacao_text = f'Data de liberação: {self.prescr['dt_liberacao'] if self.prescr['dt_liberacao'] is not None else ' - '}' if self.prescr is not None else 'Data de liberação:  - '
        self.data_liberacao.configure(text= prescr_data_liberacao_text)

        prescr_codigo_paciente_text = f'Codigo do paciente: {self.prescr['patient_hospital_id'] if self.prescr['patient_hospital_id'] is not None else ' - '}' if self.prescr is not None else 'Codigo do paciente:  - '
        self.codigo_paciente.configure(text= prescr_codigo_paciente_text)

        prescr_infection_name_text = text_truncated(text= f'Nome infecção: {self.prescr['infection_name'] if self.prescr['infection_name'] is not None else ' - '}', font= self.font, max_width= 300) if self.prescr is not None else 'Nome infecção:  - '
        self.infection_name.configure(text= prescr_infection_name_text)

        prescr_codigo_medico_text = f'Codigo do medico prescritor: {self.prescr['cd_medico'] if self.prescr['cd_medico'] is not None else ' - '}' if self.prescr is not None else 'Codigo do medico:  - '
        self.codigo_medico.configure(text= prescr_codigo_medico_text)

        prescr_message_result_sended_text = (self.prescr['prescr_sended_message'] if self.prescr['prescr_sended_message'] is not None else 'Ainda sem retorno de um medico da qualis' if self.prescr['prescr_sended_status'] == '1' else 'Falha ao capturar o erro'  if self.prescr['prescr_sended_status'] != '0' else '') if self.prescr is not None else ''
        self.message_result_sended.delete("0.0", "end")
        self.message_result_sended.insert("0.0", prescr_message_result_sended_text)

        prescr_body_sended_text = (self.prescr['body_sended'] if self.prescr['body_sended'] is not None else 'Body ainda não gerado, ou houve falha ao salvar o body.' if self.prescr['prescr_sended_status'] != '0' else '') if self.prescr is not None else ''
        self.body_sended.delete("0.0", "end")
        self.body_sended.insert("0.0", prescr_body_sended_text)

        prescr_button_text = (f'Reenviar' if self.prescr['prescr_sended_status'] in ['-1', '-2', '-3'] else 'Enviar' if self.prescr['prescr_sended_status'] == '0' else 'Buscar resposta' if self.prescr['prescr_status'] == '0' else 'Fechar') if self.prescr is not None else 'Fechar'
        self.button_details.configure(text= prescr_button_text)

    def on_closing(self):
        self.destroy()

class App(customtkinter.CTk):
    _single_instance_socket = None
    _single_instance_port = 53421

    @classmethod
    def _acquire_single_instance_lock(cls) -> bool:
        if cls._single_instance_socket is not None:
            return True

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", cls._single_instance_port))
            sock.listen(1)
            cls._single_instance_socket = sock
            return True
        except OSError:
            sock.close()
            return False

    @classmethod
    def _release_single_instance_lock(cls):
        if cls._single_instance_socket is not None:
            cls._single_instance_socket.close()
            cls._single_instance_socket = None

    @staticmethod
    def _show_single_instance_warning():
        temp_root = tk.Tk()
        temp_root.withdraw()
        mb.showwarning("Integrador Qualis", "O aplicativo ja esta em execucao.")
        temp_root.destroy()

    def __init__(self):
        if not self._acquire_single_instance_lock():
            self._show_single_instance_warning()
            raise SystemExit(0)

        super().__init__()
        self.close_already_requested = False

        self.second_stop_flag = threading.Event()
        self.second_thread_runing = False
        self.second_thread = None

        self.total_sended = 0
        self.integrator = None
        
        self.prescriptions = None
        self.actual_page = 1
        self.total_page = 1
        try:
            self.integrator = Integrator()
            query = """
                SELECT COUNT(*)
                FROM DBAMV.prescription_qualis
                WHERE prescr_sended_status = '1'
            """
            print("Buscando contagem previa de prescrições enviadas...")
            df = dataRequest.get_data(queryText= query)
            count = df.iloc[0,0]
            self.total_sended = count
        except Exception as e:
            print(e)
            print("Não consegui pegar a contagem previa de enviadas")

        self.title("Integrador Qualis")
        self.geometry("1200x680")

        self.view = self.make_view()
        self.view.pack()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def make_view(self):
        view = customtkinter.CTkFrame(self, width= 1200, height= 800)
        view.grid_columnconfigure(1, weight = 1)
        view.grid_rowconfigure(0, weight=1)
 
        self.sideBar = self.make_side_bar(view)
        self.sideBar.grid(row = 0, column = 0, sticky = "nswe")

        self.mainFrame = self.make_main_frame(view)
        self.mainFrame.grid(row = 0, column = 1, sticky = "nswe")
        return view
    

    def make_side_bar(self, master):
        sidebar_frame = customtkinter.CTkFrame(master, width = 200, corner_radius= 0)#, fg_color= "#ffffff", bg_color= "#ffffff")
        sidebar_frame.grid_rowconfigure(8, weight= 1)

        logo_label = customtkinter.CTkLabel(sidebar_frame, text="Qualis", font=customtkinter.CTkFont(family= 'Arial', size=20, weight="bold"))
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # TODO: Local para comentar para gerar o client version, não o server version.
        self.on_off_button = customtkinter.CTkButton(sidebar_frame, text= "Ligar integrador", command= self.liga_desliga_intgrador)
        self.on_off_button.grid(row= 1, column= 0, padx=20, pady= 10)
        
        sidebar_status = customtkinter.CTkFrame(sidebar_frame, width=200)#, fg_color= "#ffffff", bg_color= "#ffffff")
        sidebar_status.grid(row=2, column= 0)

        # TODO: Local para modificar o texto para o client version
        self.status_integrador = customtkinter.CTkLabel(sidebar_status, text= "Integrador desligado", text_color= "#ff0000", font=customtkinter.CTkFont(size=10, weight="bold"))
        self.status_integrador.grid(row= 0, column= 0, pady=10, padx= 20)

        self.contador = customtkinter.CTkLabel(sidebar_status, text= f"Total enviadas: {self.total_sended}", font=customtkinter.CTkFont(size=10, weight="bold"))
        self.contador.grid(row= 1, column= 0, pady= 10, padx= 20)
        
        prescription_label = customtkinter.CTkLabel(sidebar_frame, text= "Prescrição:", font=customtkinter.CTkFont(family= 'Arial', size=20, weight="bold"))
        prescription_label.grid(row= 3, column= 0, padx= 20, pady= 10)

        sidebar_button_1 = customtkinter.CTkButton(sidebar_frame, text= "Não enviadas", command=self.get_all_not_sended_prescription)
        sidebar_button_1.grid(row=4, column=0, padx=20, pady=10)

        sidebar_button_1 = customtkinter.CTkButton(sidebar_frame, text= "Enviadas com sucesso", command=self.get_all_sended_success)
        sidebar_button_1.grid(row=5, column=0, padx=20, pady=10)
 
        sidebar_button_2 = customtkinter.CTkButton(sidebar_frame, text= "Com erro no envio", command=self.get_all_prescription_that_failed)
        sidebar_button_2.grid(row=6, column=0, padx=20, pady=10)

        sidebar_button_3 = customtkinter.CTkButton(sidebar_frame, text= "Sem antibiotico", command=self.get_all_prescriptions_without_antibioc)
        sidebar_button_3.grid(row=7, column=0, padx=20, pady=10)

        return sidebar_frame


    def make_main_frame(self, master):
        mainFrame = customtkinter.CTkFrame(master, width= 1000, height= 800, fg_color= "#ffffff", bg_color= "#ffffff")
        mainFrame.grid_rowconfigure(22, weight= 1)
        mainFrame.grid_columnconfigure(0, weight= 1)
        
        self.topBar = self.make_top_bar(mainFrame)

        line_horizontal_1 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_1.grid(row= 1, column= 0, sticky= 'n')

        self.row_1 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_1.grid(row=2, column= 0, sticky= 'nswe')

        line_horizontal_2 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_2.grid(row= 3, column= 0, sticky= 'n')

        self.row_2 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_2.grid(row=4, column= 0, sticky= 'nswe')

        line_horizontal_3 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_3.grid(row= 5, column= 0, sticky= 'n')

        self.row_3 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_3.grid(row=6, column= 0, sticky= 'nswe')

        line_horizontal_4 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_4.grid(row= 7, column= 0, sticky= 'n')

        self.row_4 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_4.grid(row=8, column= 0, sticky= 'nswe')

        line_horizontal_5 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_5.grid(row= 9, column= 0, sticky= 'n')


        self.row_5 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_5.grid(row=10, column= 0, sticky= 'nswe')

        line_horizontal_6 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_6.grid(row= 11, column= 0, sticky= 'n')


        self.row_6 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_6.grid(row=12, column= 0, sticky= 'nswe')

        line_horizontal_7 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_7.grid(row= 13, column= 0, sticky= 'n')


        self.row_7 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_7.grid(row= 14, column= 0, sticky= 'nswe')

        line_horizontal_8 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_8.grid(row= 15, column= 0, sticky= 'n')

        self.row_8 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_8.grid(row= 16, column= 0, sticky= 'nswe')

        line_horizontal_9 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_9.grid(row= 17, column= 0, sticky= 'n')

        self.row_9 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_9.grid(row= 18, column= 0, sticky= 'nswe')

        line_horizontal_10 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_10.grid(row= 19, column= 0, sticky= 'n')

        self.row_10 = Data_row(parent= mainFrame, date_text= None, nr_prescr_text= None, id_qualis_prescr= None, status_sended_text= None, resposta_envio_text= None, app= self)
        self.row_10.grid(row= 20, column= 0, sticky= 'nswe')

        line_horizontal_11 = customtkinter.CTkFrame(mainFrame,width= 1200, height= 1, fg_color= "#000000", bg_color= "#000000") 
        line_horizontal_11.grid(row= 21, column= 0, sticky= 'n')

        self.bottomBar = self.make_bottom_bar(mainFrame)

        return mainFrame


    def make_bottom_bar(self, frame):
        bottom_frame = customtkinter.CTkFrame(frame, width= 1000, height= 140, corner_radius= 0)#, fg_color= "#ffffff", bg_color= "#ffffff")
        bottom_frame.grid(row= 22, column= 0, sticky = "nswe")
        # Linha zero cresce empurrando a outra linha para baixo
        bottom_frame. grid_rowconfigure(0, weight= 1)
        # Coluna um cresce empurrando as duas colunas para os lados 
        bottom_frame.grid_columnconfigure(1, weight= 1)

        self.sending_with_error_status = customtkinter.CTkLabel(bottom_frame, text= "")
        self.sending_with_error_status.grid(row= 0, column= 1)

        previous_buttom = customtkinter.CTkButton(bottom_frame, text= "Anterior", command= self.previous_page)
        previous_buttom.grid(row= 1, column= 0, padx= 20, pady= (10, 20))

        self.page_control = customtkinter.CTkLabel(bottom_frame, text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
        self.page_control.grid(row= 1, column= 1, padx= 20, pady= (10,20))

        next_button = customtkinter.CTkButton(bottom_frame, text= "Próxima", command= self.next_page)
        next_button.grid(row=1, column=2, padx= 20, pady= (10,20))
        return bottom_frame


    def make_top_bar(self, frame):
        top_frame = customtkinter.CTkFrame(frame, width= 1000, height= 50, fg_color= "#ffffff", bg_color= "#ffffff")
        top_frame.grid(row=0, column=0, sticky = "nswe")
        top_frame.grid_columnconfigure(8, weight= 1)

        font = customtkinter.CTkFont(family= 'Arial', size= 12, weight= 'bold')

        data = customtkinter.CTkLabel(top_frame, font= font, width= 120, text= "Data da liberação")
        data.grid(row= 0, column= 0, padx= 8, pady= 10)

        barra_vertical_1 = customtkinter.CTkFrame(top_frame, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_1.grid(row=0 , column= 1)

        nr_prescricao = customtkinter.CTkLabel(top_frame, font= font, width= 80, text= "NR Prescrição")
        nr_prescricao.grid(row= 0, column= 2, padx= 8, pady= 10)

        barra_vertical_2 = customtkinter.CTkFrame(top_frame, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_2.grid(row=0 , column= 3)

        id_qualis = customtkinter.CTkLabel(top_frame, font= font, width= 80, text= "ID Qualis")
        id_qualis.grid(row= 0, column= 4, padx= 8, pady= 10)

        barra_vertical_3 = customtkinter.CTkFrame(top_frame, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_3.grid(row=0 , column= 5)

        status_envio = customtkinter.CTkLabel(top_frame, font= font, width= 80, text= "Status envio")
        status_envio.grid(row= 0, column= 6, padx= 8, pady= 10)

        barra_vertical_4 = customtkinter.CTkFrame(top_frame, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_4.grid(row=0 , column= 7)

        sobre_envio = customtkinter.CTkLabel(top_frame, font= font, text= "Resposta do envio",anchor= 'w')
        sobre_envio.grid(row= 0, column= 8, padx= 8, pady= 10, sticky= 'w')

        barra_vertical_5 = customtkinter.CTkFrame(top_frame, corner_radius= 0, width= 1, height= 50, fg_color= "#000000", bg_color= "#000000")
        barra_vertical_5.grid(row=0 , column= 9)
        
        detalhes = customtkinter.CTkLabel(top_frame, font= font, width= 80, text= "Detalhes")
        detalhes.grid(row= 0, column= 10, padx= 8, pady= 10)

        return top_frame


    def show_data_current_page(self):
        for i in range(((self.actual_page-1)*10), (self.actual_page*10) , +1):
            dados = None
            dt_liberacao = None
            prescr_id = None
            prescr_id_on_qualis = None
            prescr_sended_message = None
            status_envio = None
            if i < len(self.prescriptions):
                dados = self.prescriptions.iloc[i]
                dt_liberacao = dados['dt_liberacao']
                prescr_id = dados['prescr_id']
                prescr_id_on_qualis = dados['prescr_id_on_qualis']
                prescr_sended_message = dados['prescr_sended_message']
                status = dados['prescr_sended_status']# PRESCR_SENDED_STATUS
                status_envio = "Não enviado" if status == '0' else "Falta de\nantibiotico" if status == '-3' else "Erro no envio" if status == '-1' else 'Sucesso no\nenvio' if status == '1' else None
            font = customtkinter.CTkFont(family= "Arial", size= 12)
            resto = i %10
            match resto:
                case 0:
                    self.row_1.prescr = dados
                    self.row_1.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_1.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_1.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_1.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_1.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE

                case 1:
                    self.row_2.prescr = dados
                    self.row_2.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_2.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_2.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_2.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_2.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 2:
                    self.row_3.prescr = dados
                    self.row_3.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_3.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_3.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_3.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_3.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 3:
                    self.row_4.prescr = dados
                    self.row_4.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_4.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_4.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_4.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_4.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 4:
                    self.row_5.prescr = dados
                    self.row_5.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_5.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_5.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_5.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_5.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 5:
                    self.row_6.prescr = dados
                    self.row_6.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_6.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_6.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_6.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_6.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 6:
                    self.row_7.prescr = dados
                    self.row_7.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_7.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_7.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_7.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_7.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 7:
                    self.row_8.prescr = dados
                    self.row_8.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_8.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_8.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_8.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_8.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 8:
                    self.row_9.prescr = dados
                    self.row_9.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_9.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_9.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_9.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_9.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case 9:
                    self.row_10.prescr = dados
                    self.row_10.data.configure(text= dt_liberacao if dt_liberacao is not None else " - ")# DT_LIBERACAO
                    self.row_10.nr_prescricao.configure(text= prescr_id if prescr_id is not None else " - ")# PRESCR_ID
                    self.row_10.id_qualis.configure(text= prescr_id_on_qualis if prescr_id_on_qualis is not None else " - ") # PRESCR_ID_ON_QUALIS
                    self.row_10.status_envio.configure(text= status_envio if status_envio is not None else " - ")# variavel capturada lá em cima -3, 0, -1
                    self.row_10.sobre_envio.configure(text= text_truncated(text= prescr_sended_message, font= font, max_width= 600) if prescr_sended_message is not None else " - ")# PRESCR_SENDED_MESSAGE
                    
                case _:
                    pass
    
    def next_page(self):
        if self.actual_page+1 <= self.total_page:
            self.actual_page += 1
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()

    def previous_page(self):
        if self.actual_page - 1 >= 1:
            self.actual_page -= 1
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()

    def get_all_not_sended_prescription(self):
        try:
            self.prescriptions = self.integrator.prescriptionIntegrator.get_all_not_sended_prescription() if self.integrator is not None else []
            self.actual_page = 1
            self.total_page = math.ceil(len(self.prescriptions)/10) if math.ceil(len(self.prescriptions)/10) > 0 else 1 
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()
        except Exception as e:
            print(e)

    def get_all_prescription_that_failed(self):
        try: 
            self.prescriptions = self.integrator.prescriptionIntegrator.get_all_prescription_that_failed()  if self.integrator is not None else []
            self.actual_page = 1
            self.total_page = math.ceil(len(self.prescriptions)/10) if math.ceil(len(self.prescriptions)/10) > 0 else 1
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()
        except Exception as e:
            print(e)
    
    def get_all_prescriptions_without_antibioc(self):
        try:
            self.prescriptions = self.integrator.prescriptionIntegrator.get_all_prescriptions_without_antibioc() if self.integrator is not None else []
            self.actual_page = 1
            self.total_page = math.ceil(len(self.prescriptions)/10) if math.ceil(len(self.prescriptions)/10) > 0 else 1
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()
        except Exception as e:
            print(e)

    def get_all_sended_success(self):
        try:
            self.prescriptions = self.integrator.prescriptionIntegrator.get_all_prescription_success() if self.integrator is not None else []
            self.actual_page = 1
            self.total_page = math.ceil(len(self.prescriptions)/10) if math.ceil(len(self.prescriptions)/10) > 0 else 1
            self.page_control.configure(text= f"{self.actual_page} / {self.total_page}\n{"Páginas" if self.total_page > 1 else "Página"}")
            self.show_data_current_page()
        except Exception as e:
            print(e)

    def liga_desliga_intgrador(self):
        if not self.second_thread_runing:
            self.on_off_button.configure(text= "Desligar Intergrador")
            self.status_integrador.configure(text= "Integrador rodando", text_color= "#008000")
            if self.integrator is not None:
                self.integrator.start_all_implemented_services()
            self.second_thread_runing =  True
        else:
            self.on_off_button.configure(text= "Ligar Integrador")
            self.status_integrador.configure(text= "Integrador desligado", text_color= "#ff0000")
            if self.integrator is not None:
                self.integrator.stop_all_implemented_services()
            self.second_thread_runing = False
    
    def on_closing(self):
        if self.second_thread_runing:
            if mb.askyesno("Sair", "Se Você fechar irá DESLIGAR o integrador\ndeseja proceder com a operação?"):
                print("desligando")
                self.close_already_requested = True
                self.on_off_button.configure(text= "Ligar Integrador")
                self.status_integrador.configure(text= "Integrador desligado")
                if self.integrator is not None:
                    self.integrator.stop_all_implemented_services()
                self.second_thread_runing = False
                self._release_single_instance_lock()
                self.destroy()
        elif not self.close_already_requested:
            self._release_single_instance_lock()
            self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()