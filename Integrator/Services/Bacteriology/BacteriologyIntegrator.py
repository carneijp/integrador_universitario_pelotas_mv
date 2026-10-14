import traceback
import threading
import numpy as np
import pandas as pd
import datetime
import requests
import json
import time
import warnings
from typing import Literal, Optional
from Services.BaseIntegrationService import BaseIntegrationService, ServiceOptionsEnum
from Utils.Authenticator.Authenticator import Authenticator
from Utils import dataRequest
from Utils import Constant as C
warnings.filterwarnings("ignore")

class BacteriologyIntegrator(BaseIntegrationService):
    def __init__(self, authenticator: Authenticator):
        super().__init__(ServiceOptionsEnum.BACTERIOLOGY, authenticator)

    def __get_doctor_id(self, bacteriology) -> str | None:
        """Retorna o id do médico solicitante do exame sendo analisado, caso não seja localizado retorna por default o usuário do dr. Rodrigo Pires dos Santos, responsável pela Qualis"""
        # TODO: Sempre modificar o código default do dr. Rodrigo conforme o sistema
        query = f"""
        select 
            coalesce(coalesce(a.cd_prestador_resp, a.cd_prestador), 831) as cd_prestador
        from (
            SELECT                                 
                cd_prestador,
                cd_prestador_resp
            FROM DBAMV.PED_LAB e
            WHERE e.CD_PED_LAB = {bacteriology['cd_ped_lab']}
        ) a
        """
        df = dataRequest.get_data(queryText= query)
        return str(df.iloc[0]['cd_prestador']) if len(df) > 0 else None

    def __get_all_pending_to_send(self) -> pd.DataFrame:
        """Pega a lista de bacteriologias ainda não enviadas para a Qualis"""
        query = """
            SELECT 
                * 
            FROM DBAMV.BACTERIOLOGY_QUALIS b
            WHERE b.BACTERIOLOGY_SENDED_STATUS = '0'
        """
        return dataRequest.get_data(queryText= query)

    def __get_all_peding_update(self) -> pd.DataFrame:
        """Retorna a lista de todos os exames que precisam ser atualizados dentro do sistema da Qualis"""
        query = """
            SELECT 
                *
            FROM DBAMV.BACTERIOLOGY_QUALIS B
            WHERE B.BACTERIOLOGY_SENDED_STATUS = '2'
        """
        return dataRequest.get_data(queryText= query)

    def __get_all_that_failed_before(self):
        """Retorna a lista de todos os exames que tiveram erro ao integrar no sistema da Qualis"""
        query = """
            SELECT 
                *
            FROM DBAMV.BACTERIOLOGY_QUALIS B
            WHERE B.BACTERIOLOGY_SENDED_STATUS = '-1'
        """
        return dataRequest.get_data(queryText= query)

    def __update_bacteriology_qualis_status(self, bacteriologyQualis, sended: bool, messageSended: str, messageResponse: str, isUpdate: bool):
        """Atualiza o status de envio dado o processamento da tentativa de envio"""
        if messageSended is None or messageResponse is None:
            raise Exception("Não é permitido messagem ser vazia!")
        
        update = f"""
            UPDATE DBAMV.BACTERIOLOGY_QUALIS b
            SET 
                b.ID_BACTERIOLOGY_QUALIS = :id_bacteriology_qualis,
                b.BACTERIOLOGY_SENDED_STATUS = :sended_status,
                b.BODY_SENDED = :body_sended,
                b.RESPONSE_RECIEVED = :response_recieved
            WHERE b.CD_PED_LAB = :cd_ped_lab and b.CD_EXA_LAB = :cd_exa_lab AND b.CD_ITPED_LAB = :cd_itped_lab
        """
        payload = {
            "cd_ped_lab" : int(bacteriologyQualis['cd_ped_lab']),
            "cd_exa_lab" : int(bacteriologyQualis['cd_exa_lab']),
            "cd_itped_lab" : int(bacteriologyQualis['cd_itped_lab']),
            "body_sended" : str(messageSended)[:3999],
            "response_recieved" : str(messageResponse)[:3999],
            "id_bacteriology_qualis" : None
        }
        if not sended:
            payload["sended_status"] = "-1" if not isUpdate else "-2"
        else:
            payload["id_bacteriology_qualis"] = str(bacteriologyQualis['id_bacteriology_qualis'])
            payload["sended_status"] = '1'
        
        try:
            dataRequest.execute(update, payload)
        except Exception as e:
            payload["body_sended"] = 'Erro ao salvar com os objetos'
            payload["response_recieved"] = e
            payload["sended_status"] = "-1" if not isUpdate else "-2"
            dataRequest.execute(update, payload)

    def __get_all_materials(self, bacteriology):
        """Retorna a lista de germes/materiais realizados para o exame, já na estrutura necessária para o sistema."""
        def get_all_antibiotic_for_material(material):
            """Retorna a lista de todos os antibioticos testados e ainda não testados para um material"""
            allAntibiotics = []
            query = f"""
                SELECT 
                    cd_antimicrob,
                    tp_resultado
                FROM DBAMV.ITCULTURA ic
                WHERE ic.CD_PED_LAB = {material['cd_ped_lab']} 
                    AND ic.CD_EXA_LAB = {material['cd_exa_lab']} 
                    AND ic.CD_ITPED_LAB = {material['cd_itped_lab']} 
                    AND ic.CD_GERMES = {material['cd_germes']}
            """
            foundedAntibiotics = dataRequest.get_data(queryText= query)
            for i in range(len(foundedAntibiotics)):
                localAntibiotic = foundedAntibiotics.iloc[i]
                sensibility = str(localAntibiotic['tp_resultado']).upper()
                if sensibility == 'N':
                    continue
                antibiotic = {
                    "id": None,
                    "hospitalAntibioticIdentifier": localAntibiotic['cd_antimicrob'], 
                    "sensibility": 'S' if sensibility in ['S', 'E'] else ('R' if sensibility == 'R' else ('I' if sensibility in ['I', 'M'] else None)) 
                }
                allAntibiotics.append(antibiotic.copy())
            
            return allAntibiotics

        def get_sitio(cd_ped_lab: str, cd_exa_lab: str, cd_itped_lab: str) -> str | None:
            """Retorna o sitio da coleta do pedido de exame"""
            query = f"""
                SELECT 
                    M.ds_material 
                FROM cultura C
                INNER JOIN MATERIAL M
                    ON M.CD_MATERIAL = C.CD_MATERIAL 
                WHERE C.CD_PED_LAB = {cd_ped_lab} AND C.CD_EXA_LAB = {cd_exa_lab} AND C.CD_ITPED_LAB = {cd_itped_lab}
            """
            df = dataRequest.get_data(queryText= query)
            return df.iloc[0]['ds_material'] if len(df) > 0 else None

        def get_mic(antibiotico: Literal["vancomicina", "imipenem", "meropenem", "polimixina"], cd_germe, bacteriology) -> Optional[str]:
            """Retorna o valor de MIC para um dos possíveis antibióticos."""
            # TODO: SEMPRE MUDAR AQUI PARA O VALOR CORRETO DO ANTIMICROB DE CADA HOSPITAL
            antibioticID = None
            if antibiotico == "vancomicina":
                antibioticID = "(119)"
            elif antibiotico == "imipenem":
                antibioticID = "(58, 232)"
            elif antibiotico == "meropenem":
                antibioticID = "(67)"
            elif antibiotico == "polimixina":
                antibioticID = "(87, 291)"
            else:
                return None
            
            queryMic = f"""
                SELECT 
                    nr_mic
                FROM DBAMV.ITCULTURA IC
                WHERE IC.CD_PED_LAB = {bacteriology['cd_ped_lab']} 
                    AND IC.CD_EXA_LAB = {bacteriology['cd_exa_lab']} 
                    AND IC.CD_ITPED_LAB = {bacteriology['cd_itped_lab']}
                    AND IC.CD_ANTIMICROB in {antibioticID}
                    AND IC.CD_GERMES = {cd_germe}
                    AND IC.NR_MIC IS NOT NULL
            """
            df = dataRequest.get_data(queryText= queryMic)
            mic = df.iloc[0]['nr_mic'] if len(df) > 0 else None
            return str(mic) if mic != np.nan and mic is not None else None

        allMaterials = []
        query = f"""
            SELECT 
                *
            FROM DBAMV.GERMES_CULTURA gc
            WHERE gc.CD_PED_LAB = {bacteriology['cd_ped_lab']} AND gc.CD_EXA_LAB = {bacteriology['cd_exa_lab']} AND gc.CD_ITPED_LAB = {bacteriology['cd_itped_lab']}
        """
        foundedMaterials = dataRequest.get_data(queryText= query)

        cd_material = bacteriology['cd_material'] if not pd.isna(bacteriology['cd_material']) else -1
        if cd_material == -1:
            print("Material de coleta da cultura não foi identificado.")
        
        sitio = get_sitio(cd_ped_lab= bacteriology['cd_ped_lab'], cd_exa_lab= bacteriology['cd_exa_lab'], cd_itped_lab= bacteriology['cd_itped_lab'])
        
        for i in range(len(foundedMaterials)):
            locatedMaterial = foundedMaterials.iloc[i]
            antibioticsForMaterial = get_all_antibiotic_for_material(material= locatedMaterial)
            vancomicinaMIC = get_mic("vancomicina", locatedMaterial['cd_germes'], bacteriology)
            meropenemMIC = get_mic("meropenem", locatedMaterial['cd_germes'], bacteriology)
            imipenemMIC = get_mic("imipenem", locatedMaterial['cd_germes'], bacteriology)
            polimixinaMIC = get_mic("polimixina", locatedMaterial['cd_germes'], bacteriology)
            
            material = {
                "id": None, 
                "sitio": sitio,
                "esbl": None, # Enum('U', 'P', 'N')
                "vancomicina": vancomicinaMIC, 
                "meropenem": meropenemMIC,
                "imipenem": imipenemMIC,
                "polimixina": polimixinaMIC,
                "obs": locatedMaterial['ds_colonia'] if locatedMaterial['ds_colonia'] != np.nan else None,
                "germHospitalIdentifier": int(locatedMaterial['cd_germes']) if locatedMaterial['cd_germes'] != np.nan else None,
                "hospitalMaterialIdentifier": int(cd_material), 
                "antibiotics": antibioticsForMaterial
            }
            allMaterials.append(material.copy())

        return allMaterials

    def __get_dt_exam(self, bacteriology: pd.Series) -> Optional[str]:
        """Retorna a data da coleta/realização do exame"""
        query = f"""
            SELECT
                dt_exame
            FROM DBAMV.PED_LAB
            WHERE CD_PED_LAB = {bacteriology['cd_ped_lab']}
        """
        df = dataRequest.get_data(queryText= query)
        return pd.to_datetime(df.iloc[0]['dt_exame']).to_pydatetime().strftime("%Y-%m-%dT%H:%M:%S") if len(df) > 0 else None
    
    def __get_patient(self, bacteriology: pd.Series) -> Optional[pd.DataFrame]:
        """Retorna os dados existentes sobre o paciente na tabela onde ficam armazenados os principais dados do paciente dentro do RP"""
        query = f"""
            SELECT 
                DISTINCT P.* 
            FROM DBAMV.PED_LAB PL
            INNER JOIN DBAMV.ATENDIME A
                ON A.CD_ATENDIMENTO = PL.CD_ATENDIMENTO 
            INNER JOIN DBAMV.PACIENTE P
                ON A.CD_PACIENTE = P.CD_PACIENTE
            WHERE PL.CD_PED_LAB = {bacteriology['cd_ped_lab']}
        """
        df = dataRequest.get_data(queryText= query)
        return df if len(df) > 0 else None
    
    def __get_atendimento(self, bacteriology: pd.Series) -> Optional[pd.DataFrame]:
        """Retorna todos os dados do atendimento de dentro da tabela onde ficam armazenado as principais informações sobre o atendimento dentro do RP"""
        query = f"""
            SELECT 
                A.*,
                COALESCE(TO_CHAR(PM.cd_unid_int), CASE WHEN PL.CD_SETOR IS NOT NULL THEN 'setor_' || TO_CHAR(pl.cd_setor) ELSE NULL END) AS cd_unid_int
            FROM DBAMV.PED_LAB PL
            LEFT JOIN DBAMV.PRE_MED PM
                ON PL.CD_PRE_MED = PM.CD_PRE_MED 
            INNER JOIN DBAMV.ATENDIME A
                ON A.CD_ATENDIMENTO = PL.CD_ATENDIMENTO 
            WHERE PL.CD_PED_LAB = {bacteriology['cd_ped_lab']}
        """
        df = dataRequest.get_data(queryText= query)
        return df if len(df) > 0 else None
    
    def __get_leito(self, cd_leito: int|str) -> Optional[str]:
        """Retorna o nome do leito dado o codigo de leito onde o paciente estava na hora do exame"""
        if cd_leito is None:
            return None
        
        query = f"""
            SELECT 
                ds_leito
            FROM DBAMV.LEITO
            WHERE CD_LEITO = {cd_leito}
        """
        df = dataRequest.get_data(queryText= query)
        return str(df.iloc[0]['ds_leito']) if len(df) > 0 else None
    
    def __calculate_patient_age_in_hours(self, birthDate: str|datetime.datetime) -> int:
        """Calculates the age of a patient in hours based on their birth date."""
        birthDate = pd.to_datetime(birthDate)
        birthDate = datetime.datetime(year= birthDate.year, month= birthDate.month, day= birthDate.day)
        current_time = datetime.datetime.now()
        age_in_hours = (current_time - birthDate).total_seconds() // 3600
        return int(age_in_hours)

    def __get_bacteriology(self, cd_ped_lab: str, cd_exa_lab: str, cd_itped_lab: str) -> Optional[pd.Series]:
        """Retorna a bacteriologia/cultura para aquele exame sendo processado"""
        query = f"""
            SELECT 
                *
            FROM DBAMV.CULTURA C 
            WHERE C.CD_PED_LAB = {cd_ped_lab} AND C.CD_EXA_LAB = {cd_exa_lab} AND C.CD_ITPED_LAB = {cd_itped_lab}
        """
        df = dataRequest.get_data(queryText= query)
        return df.iloc[0] if len(df) else None

    def __try_send_bacteriology(self, bacteriologyQualis):
        """Função que unifica o processamento para envio a qualis tanto de criação como atualização de uma bacteriologia"""
        bacteriology = self.__get_bacteriology(bacteriologyQualis['cd_ped_lab'], bacteriologyQualis['cd_exa_lab'], bacteriologyQualis['cd_itped_lab']) 
        if bacteriology is None:
            print("Sem cultura localizada para essa prescrição")
            return
        
        doctor_id = self.__get_doctor_id(bacteriology)
        token = None
        if doctor_id is not None:
            token = self._authenticator.get_Token_for_cd_medico(doctor_id)

        materials = self.__get_all_materials(bacteriology)
        dtExam = self.__get_dt_exam(bacteriology)
        idOnQualis = bacteriologyQualis['id_bacteriology_qualis'] if bacteriologyQualis['id_bacteriology_qualis'] != np.nan else None
        isUpdate = idOnQualis is not None and (bacteriologyQualis['bacteriology_sended_status'] in ['-2', '2'])

        # Todos os dados do paciente estão sendo iniciados como vazios Assim reduz a quantidade de ternário que faz as validações
        body = {
            "id": int(idOnQualis) if idOnQualis is not None else None,
            "patientHospitalIdentifier": None,
            "patientWeight": None, # Peso do paciente em kilos
            "patientHeight": None, # Altura em centimetros
            "patientAge": None, # Idade do paciente em horas
            "patientName": None,
            "patientGender": None, # Enum('M', 'F')
            "patientRace": None, # Enum('O', 'B')
            "patientDocument": None, # CPF ou CNPJ
            "hospitalUnityIdentifier": "-1",
            "dateBacteriology": None, 
            "dateAdmission": None, 
            "dateExam": str(dtExam) if dtExam is not None else None,
            "room": None,
            "obs": bacteriology['ds_observacao'],
            "materials": materials # Lista de germes/materiais
        }

        patient = self.__get_patient(bacteriology)
        if patient is not None:
            atendimento = self.__get_atendimento(bacteriology)
            body["patientAge"] = self.__calculate_patient_age_in_hours(patient['dt_nascimento'].values[0])
            body["patientName"] = patient['nm_paciente'].values[0]
            body["patientGender"] = "M" if str(patient['tp_sexo'].values[0]).upper() == "M" else "F"
            body["patientRace"] = 'B' if str(patient['tp_cor'].values[0]).upper() == "P" else 'O'
            body["patientHospitalIdentifier"] = str(patient['cd_paciente'].values[0])
            body["patientDocument"] = str(patient["nr_cpf"].values[0])

            if atendimento is not None:
                body["hospitalUnityIdentifier"] = (str(atendimento['cd_unid_int'].values[0]) if atendimento['cd_unid_int'].values[0] is not None else "-1") if atendimento['cd_unid_int'].values[0] != np.nan else "-1"
                body["room"] = self.__get_leito(atendimento['cd_leito'].values[0])
                body["dateAdmission"] = str(atendimento['hr_atendimento'].values[0])
        
        body_sended = body
        response = None
        if isUpdate:
            response = requests.put(f"{C.API_BASE_URL}bacteriology", headers= {'Authorization': token, 'hospital-key': C.HOSPITAL_KEY}, json= body_sended, verify= False, timeout= 20)
        else:
            response = requests.post(f"{C.API_BASE_URL}bacteriology", headers= {'Authorization': token, 'hospital-key': C.HOSPITAL_KEY}, json= body_sended, verify= False, timeout= 20)
        
        if body_sended is None or response is None: 
            return
        
        body_sended = json.dumps(body_sended)
        body_recieved = response.json()
        code = body_recieved['code']
        message = None
        error_message = None
        sended = False

        if code == '0':
            sended = True
            bacteriologyQualis['id_bacteriology_qualis'] = body_recieved['results'][0]['id']
            message = "Sucesso ao inserir bacteriologia."
        else:
            message = body_recieved['message']
            message_list = list(filter(None, body_recieved['results']))
            final_list = []
            for dc in message_list:
                sendedList = json.dumps(dc)
                sendedList.replace("'", '"')
                final_list.append(sendedList)
            error_message = str("; ".join(final_list))
            message = message + ";" + error_message
            self.solve_prescription_sended_error(doctor_id, body, body_recieved)
        
        self.__update_bacteriology_qualis_status(bacteriologyQualis= bacteriologyQualis, sended= sended, messageSended= body_sended, messageResponse= message, isUpdate= isUpdate)
        
    def solve_prescription_sended_error(self, cd_prestador, body, response):
        """Dado o body enviado e a resposta do servidor para a bacteriologia, valida se existe alguma formula pré definida que possibilite a solução doe rro"""
        message = None
        doctorInternalCode = cd_prestador
        

        germs = []
        materials = []
        antibiotics = []
        for material in  body['materials']:
            germs.append(material['germHospitalIdentifier'])
            materials.append(material['hospitalMaterialIdentifier'])
            for atb in material['antibiotics']:
                antibiotics.append(atb['hospitalAntibioticIdentifier'])

        error = response['results'][0]
        if 'Full authentication is required to access this resource' in error:
            if self.prescritorsReported.get(doctorInternalCode) is not None:
                return
            else:
                self.prescritorsReported[doctorInternalCode] = True

            query = f"""
                select 
                    p.nr_cpf_cgc as cpf,
                    p.nm_prestador as nome,
                    p.ds_email as email,
                    p.ds_codigo_conselho as crm,
                    coalesce(p.nr_fone_contato, p.nr_fone_comercial) as telefone,
                    tp.nm_tip_presta as categoria_profissional
                from dbamv.prestador p
                inner join dbamv.tip_presta tp
                    on p.cd_tip_presta = tp.cd_tip_presta
                where p.cd_prestador {f"= {doctorInternalCode}" if doctorInternalCode is not None and str(doctorInternalCode) != 'None' else "is null"}
            """
            df = dataRequest.get_data(queryText= query)
            
            if len(df) > 0 :
                doctor = df.iloc[0]
                message = f"!Cultural!\n"
                message += f"Error: {response['message']}\n"
                message += f"Medico com cd_medico {doctorInternalCode} não possui cadastro dados para cadastro:\n"
                message += f"Codigo interno do hospital: {doctorInternalCode}\n"
                message += f"Nome completo: {doctor['nome'] if (str(doctor['nome']).lower() != 'nan' and doctor['nome'] is not None) else ''}\n"
                message += f"CPF: {doctor['cpf'] if (str(doctor['cpf']).lower() != 'nan' and doctor['cpf'] is not None) else ''}\n"
                message += f"CRM: {doctor['crm'] if (str(doctor['crm']).lower() != 'nan' and doctor['crm'] is not None) else ''}\n"
                message += f"Email: {doctor['email'] if (str(doctor['email']).lower() != 'nan' and doctor['email'] is not None) else ''}\n"
                message += f"Telefone: {doctor['telefone'] if (str(doctor['telefone']).lower() != 'nan' and doctor['telefone'] is not None) else ''}\n"
                message += f"Categoria profissional: {doctor['categoria_profissional'] if (str(doctor['categoria_profissional']).lower() != 'nan' and doctor['categoria_profissional'] is not None) else ''}\n"
                message += f"Hospital: {C.HOSPITAL_NAME}"
            else:
                message = f"Medico com cd_medico {doctorInternalCode} não possui cadastro. Falha ao buscar dados do médico de forma automática para o cadastro"
        
        elif 'HospitalUnity não pode ser nulo' in error:
            id = body["hospitalUnityIdentifier"]

            if 'setor_' in id:
                query = f"""
                    select
                        distinct
                        s.cd_setor as codigo,
                        s.nm_setor as descricao
                    from dbamv.setor s
                    where to_char(s.cd_setor) = '{id.strip("setor_") if isinstance(id, str) else "null"}'
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Setor do exame não cadastrado:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um ou mais desses setor(es) não está cadastrado na Qualis. Cadastre-o como unidade hospitalar na Qualis.\n"
                    message += f"Observação: esses são os setor(es) do hospital caso não exista o seu tipo você deve cria-lo ou solicitar a equipe de TI da Qualis.\n"
                    message += f"Favor validar os setor(es) com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
            else:
                query = f"""
                    select
                        distinct
                        ui.cd_unid_int as codigo,
                        ui.ds_unid_int as descricao
                    from dbamv.unid_int ui
                    where to_char(ui.cd_unid_int) = '{id if isinstance(id, str) else "null"}'
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Unidade(s) hospitalar do exame não cadastrado:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um ou mais dessas unidade(s) não está cadastrado na Qualis. Cadastre-o como unidade hospitalar na Qualis.\n"
                    message += f"Observação: essas são as unidade(s) do hospital caso não exista o seu tipo você deve cria-lo ou solicitar a equipe de TI da Qualis.\n"
                    message += f"Favor validar os unidade(s) com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"

        elif isinstance(error, dict):
            if 'germHospitalIdentifier' in error['field'] and 'NOT ABLE TO PARSE THE INFORMATION FOR LOCAL OBJECT' in error['message']:
                ids = ""
                for germId in germs:
                    ids += f"'{germId}', "
                
                query = f"""
                    select
                        distinct
                        g.cd_germes as codigo,
                        g.ds_germe as descricao
                    from dbamv.germes g
                    where to_char(g.cd_germes) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Microorganismo(s) não encontrados os microorganismo(s) presentes no exame:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um ou mais desses microorganismo(s) não está cadastrado na Qualis. \n"
                    message += f"Observação: esses são os microorganismos do hospital caso não exista nem o seu proprio tipo você deve cria-lo.\n"
                    message += f"Favor validar os microorganismo(s) com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
        
            elif 'hospitalAntibioticIdentifier' in error['field'] and 'NOT ABLE TO PARSE THE INFORMATION FOR LOCAL OBJECT' in error['message']:
                ids = ""
                for antibioticId in antibiotics:
                    ids += f"'{antibioticId}', "
                
                query = f"""
                    select
                        distinct
                        ab.cd_antimicrob as codigo,
                        ab.nm_antimicrob as descricao
                    from dbamv.antimicrob ab
                    where to_char(ab.cd_antimicrob) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Antibiotico(s) de culturas não encontrados os antibiotico(s) de culturas presentes no exame:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um ou mais desses antibiotico(s) de culturas não está cadastrado na Qualis. \n"
                    message += f"Observação: esses são os antibiotico(s) de culturas do hospital, caso não exista o seu proprio tipo de antibiotico você deve cria-lo.\n"
                    message += f"Favor validar os antibiotico(s) de culturas com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
            
            elif 'hospitalMaterialIdentifier' in error['field'] and 'NOT ABLE TO PARSE THE INFORMATION FOR LOCAL OBJECT' in error['message']:
                ids = ""
                for materialId in materials:
                    ids += f"'{materialId}', "
                
                query = f"""
                    select
                        distinct
                        m.cd_material as codigo,
                        m.ds_material as descricao
                    from dbamv.material m
                    where to_char(m.cd_material) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Material não encontrados os materiais presentes no exame:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um ou mais desses materiais de sitio de coleta do exame não está cadastrado na Qualis. \n"
                    message += f"Favor validar os materiais com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
        
        if message is None:
            message = f"Erro: {response['message']}\n"
            message += f"Error variable: {error}\n"
            message += f"Erro sem solucao predefinida, solicite auxilio para a equipe de desenvolvimento da qualis, necessario debug para solucionar:\n"
            message += f"Detalhes: {response}\n"
            message += f"Body enviado para a api: {json.dumps(body)}\n"
        
        subject = "Erro na integração da prescrição"
        self._send_email(message, subject)
    
    # Envia todas as bacteriologias que houveram falha anteriormente
    def send_all_failed_before(self):
        if (not self.thread_erros_runing):
            self.prescritorsReported = dict()
            self.thread_erros_runing = True
            previous_failed = self.__get_all_that_failed_before()
            for index_previous_failed in previous_failed.index:
                if self._stop_event.is_set():
                    break
                bacteriology_failed = previous_failed.iloc[index_previous_failed]
                self.__try_send_bacteriology(bacteriology_failed)
            self.thread_erros_runing = False
        else:
            print("Ainda processando ultima requisição de envio de bacteriologias com falhas anteriores.")

    def _monitor_loop(self, retryCounter: int = 0):
        """Função de loop infinito para processamento das bacteriologias pendentes"""
        print("Iniciando monitoramento da bacteriologia")
        try:
            contador = 0
            intervalRetry = 60
            while not self._stop_event.is_set():
                self._report_progress()
                df_bacteriology = self.__get_all_pending_to_send()
                print(f"Retornado lista de pendentes de envio com: {len(df_bacteriology)} unidades")
                for i in range(len(df_bacteriology)):
                    if self._stop_event.is_set():
                        break
                    self._report_progress()
                    bacteriology = df_bacteriology.iloc[i]
                    try:
                        self.__try_send_bacteriology(bacteriology)
                    except Exception as e:
                        self.__update_bacteriology_qualis_status(bacteriologyQualis= bacteriology, sended= False, messageSended="", messageResponse= str(e), isUpdate= False)
                        print(f"Error enviando uma bacteriologia, error: {e}")

                df_bacteriology_to_update = self.__get_all_peding_update()   
                print(f"Retornado lista de pendentes de atualização com: {len(df_bacteriology_to_update)} unidades")
                for i in range(len(df_bacteriology_to_update)):
                    if self._stop_event.is_set():
                        break
                    self._report_progress()
                    bacteriology = df_bacteriology_to_update.iloc[i]
                    try:
                        self.__try_send_bacteriology(bacteriology)
                    except Exception as e:
                        self.__update_bacteriology_qualis_status(bacteriologyQualis= bacteriology, sended= False, messageSended="", messageResponse= str(e), isUpdate= True)
                        print(f"Error enviando uma atualização de uma bacteriologia, error: {e}")

                if contador%intervalRetry == 0:
                    job = threading.Thread(target= self.send_all_failed_before)
                    job.start()
                
                contador += 1

                if contador%intervalRetry == (intervalRetry-1):  
                    contador = 0
                
                if self._stop_event.wait(timeout=60):
                    break
                self._report_progress()
        except Exception as e:
            if self._stop_event.is_set():
                return
            errorCompleto = traceback.format_exc()
            self._send_email(f"Error em {C.HOSPITAL_NAME}, reporte a equipe de desenvolvimento sobre: {errorCompleto}", f"Error grave durante execução do integrador, retry number: {retryCounter}")
            print(e, f"Reiniciando monitoramento da bacteriologia, tentativa: {retryCounter}")
            self._report_progress()
            self._monitor_loop(retryCounter+1)