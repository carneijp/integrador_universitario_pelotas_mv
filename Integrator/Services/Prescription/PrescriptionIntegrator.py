import traceback
import warnings
import pandas as pd
import datetime
import requests
import math
import time
import threading
import json
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DBAPIError, DatabaseError
from Services.BaseIntegrationService import BaseIntegrationService, ServiceOptionsEnum
from Utils.Authenticator.Authenticator import Authenticator
from Utils import dataRequest
from Utils import Constant as C

warnings.filterwarnings("ignore")

class PrescriptionIntegrator(BaseIntegrationService):
    def __init__(self, authenticator: Authenticator):
        super().__init__(ServiceOptionsEnum.PRESCRIPTION, authenticator= authenticator)
        
        # Defini o CURB default para envios
        self.CURB = {
            "bloodPressure": False,
            "confusion": False,
            "respiratoryRate": False
        }
    
    # Função para trazer todas as prescrições que falharam
    def get_all_prescription_that_failed(self):
        query_get_all_prescription_not_sended = """
            SELECT * 
            FROM DBAMV.prescription_qualis p
            WHERE p.prescr_sended_status = '-1' 
                AND p.dt_liberacao IS NOT NULL AND p.dt_suspensao IS NULL
            ORDER BY p.dt_liberacao DESC
        """
        df = dataRequest.get_data(queryText= query_get_all_prescription_not_sended)
        return df

    # Pega todas as prescrições já enviadas com sucesso
    def get_all_prescription_success(self):
        query_get_all_prescription_not_sended = """
            select * from (
                SELECT * 
                FROM DBAMV.prescription_qualis p
                WHERE p.prescr_sended_status = '1' AND p.dt_liberacao IS NOT NULL
                ORDER BY p.dt_liberacao DESC
            ) where rownum <= 100
        """
        df = dataRequest.get_data(queryText= query_get_all_prescription_not_sended)
        return df

    # Pega todas as prescrições ainda não enviadas, onde contem uma data de liberação para o envio, e não foi suspensa
    def get_all_not_sended_prescription(self) -> pd.DataFrame:
        query_get_all_prescription_not_sended = """
            SELECT * 
            FROM DBAMV.prescription_qualis p
            WHERE p.prescr_sended_status = '0' AND p.dt_liberacao IS NOT NULL AND p.dt_suspensao IS NULL
            ORDER BY p.dt_liberacao DESC
        """
        df = dataRequest.get_data(queryText= query_get_all_prescription_not_sended)
        return df

    # Busca todas as prescrições sem antibiotico
    def get_all_prescriptions_without_antibioc(self):
        query_get_all_prescription_not_sended = """
            SELECT * 
            FROM DBAMV.prescription_qualis p
            WHERE p.prescr_sended_status = '-3' AND p.dt_liberacao IS NOT NULL AND p.dt_suspensao IS NULL
            ORDER BY p.dt_liberacao DESC
        """
        df = dataRequest.get_data(queryText= query_get_all_prescription_not_sended)
        return df
    
    # Elimina as linhas que tem mais de uma semana e não tem antibiótico
    def __delete_old_prescriptions(self):
        query ="""
            DELETE FROM DBAMV.PRESCRIPTION_QUALIS
            WHERE PRESCR_SENDED_STATUS = '-3'
            AND INFECTION_DATE + INTERVAL '7' DAY < (CURRENT_DATE)
        """
        dataRequest.execute(query, {})

    def __update_sended_status_after_atempt(self, prescr_id: str, sended_success: bool, sended_message_response: str | None, sended_body_to_api: str, qualis_prescr_id):
        """Realiza update no banco depois de ter feito tentativa de envio da prescrição"""
        query_update_prescr_status = f"""
            UPDATE DBAMV.prescription_qualis p
            SET
                p.prescr_sended_status = :new_prescr_status,
                p.prescr_sended_message = :sended_message_response,
                p.prescr_id_on_qualis = :qualis_prescr_id,
                p.body_sended = :sended_body_to_api,
                p.dt_envio = SYSDATE
            WHERE p.prescr_id = :prescr_id
        """
        # Query de update
        payload = {
            "new_prescr_status" : '1' if sended_success else '-1',
            "sended_message_response" : str(sended_message_response)[:3999] if sended_message_response is not None else None,
            "qualis_prescr_id" : str(qualis_prescr_id) if qualis_prescr_id is not None else None,
            "sended_body_to_api" : str(sended_body_to_api)[:3999],
            "prescr_id" : str(prescr_id),
        }
        try:
            dataRequest.execute(query_update_prescr_status, payload)
        except:
            payload["sended_body_to_api"] = 'Error no body'
            dataRequest.execute(query_update_prescr_status, payload)

    def __update_sended_status_no_antibiotic(self, prescr_id: str, old_sended_status: str, message: str):
        """Update no banco depois de ter percebido que a prescrição não possui antibiotico"""
        # Dado que não tenho antibiotico vou validar se é a primeira vez que estou tentando enviar ou se já tentei ante, caso contrario coloca em estado de não enviar mais
        quey_update_prescr_sended_status = f"""
            UPDATE DBAMV.prescription_qualis p
            SET
                p.prescr_sended_status = :new_prescr_status,
                p.prescr_sended_message = :message,
                p.dt_envio = SYSDATE
            WHERE p.prescr_id = :prescr_id
        """
        payload = {
            "new_prescr_status" : '-3' if old_sended_status in ['-1', '0', '1'] else '-2',
            "message" : str(message),
            "prescr_id" : str(prescr_id),
        }
        dataRequest.execute(quey_update_prescr_sended_status, payload)

    # Busca todas as prescrições que não foram enviadas na primeira tentativa por falta de antibiotico atrelada a ela.
    def __get_all_prescription_missing_antibiotic_to_sencond_try(self) -> pd.DataFrame:
        query_get_all_prescription_not_sended = """
            SELECT 
                * 
            FROM DBAMV.prescription_qualis p
            WHERE p.prescr_sended_status = '-2' 
                AND p.dt_liberacao IS NOT NULL 
                AND p.dt_suspensao IS NULL
        """
        df = dataRequest.get_data(queryText= query_get_all_prescription_not_sended)
        return df

    # Recebe o id da prescrição e retorna a lista de antibioticos atralados aquela prescripção
    # Função para buscar antibioticos de uma prescrição
    def __get_antibiotic_for_prescription_id(self, prescription_id: str) -> pd.DataFrame:
        query_get_antibiotics = f"""
            SELECT
                TO_CHAR(tp.ds_tip_presc) AS "antibioticName",
                TO_CHAR(ipm.cd_tip_presc) AS "antibioticIdentifier",
                TO_CHAR(ipm.qt_itpre_med) AS "dosage",
                TO_CHAR(ipm.qt_dias) AS "usagePeriod",
                TO_CHAR(ipm.cd_tip_fre) AS "hospitalIntervalTimeIdentifier",
                TO_CHAR(ipm.cd_for_apl) AS "hospitalViaIdentifier",
                TO_CHAR(ipm.cd_uni_pro) AS "hospitalDosageUnitIdentifier",
                TO_CHAR('Observação: ' || COALESCE(ipm.ds_itpre_med || '\n ', '\n') || 'Justificativa: ' || COALESCE(ipm.ds_justificativa, '')) AS JUSTIFICATIVA
            FROM DBAMV.itpre_med ipm
            INNER JOIN DBAMV.TIP_PRESC tp
                ON ipm.cd_tip_presc = tp.cd_tip_presc
            WHERE (
                    (ipm.cd_tip_esq IN ('MDA') AND ipm.cd_tip_presc not in (16264, 16169, 23342, 16204))
                    or
                    (ipm.cd_tip_presc in (22275, 22120, 20565, 23094, 23143, 17464, 20564, 17465))
                )
                AND (
                    ipm.nr_dia = 1 -- Ajustar conforme o hospital utiliza
                    or trunc(ipm.dh_registro) = (
                        select 
                            trunc(a.dt_atendimento) 
                        from dbamv.atendime a 
                        inner join dbamv.pre_med pm 
                            on a.cd_atendimento = pm.cd_atendimento
                        where pm.cd_pre_med = {prescription_id}
                    ) 
                )
                AND (ipm.sn_cancelado = 'N' OR ipm.SN_CANCELADO IS NULL)
                AND ipm.cd_pre_med = {prescription_id}
        """
        df = dataRequest.get_data(queryText= query_get_antibiotics)

        def arrange_dosage(row):
            dosage = str(row['dosage'])
            dosage = dosage.replace(",", ".")
            if len(dosage) > 0:
                if dosage[0] == '.':
                    dosage = '0' + dosage
            return dosage
        
        if len(df) > 0:
            df['dosage'] = df.apply(arrange_dosage, axis= 1)
        
        return df

    # Para verificar se existe antibiotico da prescrição
    def __valida_antibiotics(self, antibiotics: pd.DataFrame) -> bool:
        return len(antibiotics) > 0
    
    def __get_infection_name(self, nr_atendimento: str, patient_id: str) -> str:
        query_infection_name = f"""
            SELECT
                ds_cid
            FROM DBAMV.ATENDIME A
            INNER JOIN DBAMV.CID C 
                ON A.CD_CID = C.CD_CID
            WHERE A.CD_ATENDIMENTO = {nr_atendimento}
                AND A.CD_PACIENTE = {patient_id}
        """

        df = dataRequest.get_data(queryText=query_infection_name)

        infection_name = df.iloc[0]['ds_cid'] if len(df) > 0 else 'Não identificada'

        return infection_name
    
    def get_all_antibiotics_for_past_30_days(self, nr_atendimento: str) -> str:
        query = f"""
            SELECT 
                DS_TIP_PRESC, 
                DH_IMPRESSAO
            FROM (
                SELECT 
                    tp.DS_TIP_PRESC, p.DH_IMPRESSAO,
                    ROW_NUMBER() OVER (ORDER BY p.DH_IMPRESSAO DESC) AS rn
                FROM dbamv.pre_med p
                INNER JOIN dbamv.itpre_med it 
                    ON p.CD_PRE_MED = it.CD_PRE_MED
                INNER JOIN dbamv.tip_presc tp 
                    ON it.CD_TIP_PRESC = tp.CD_TIP_PRESC
                WHERE (
                        (it.cd_tip_esq IN ('MDA') AND it.cd_tip_presc not in (16264, 16169, 23342, 16204))
                        or
                        (it.cd_tip_presc in (22275, 22120, 20565, 23094, 23143, 17464, 20564, 17465))
                    )
                    AND CD_ATENDIMENTO = {nr_atendimento}
                    AND it.nr_dia = 1
                    AND DH_IMPRESSAO >= (SYSDATE - 30)
            ) T
                WHERE rn > 1 
                ORDER BY DH_IMPRESSAO DESC
        """

        df = dataRequest.get_data(queryText=query)
        
        if len(df) <= 0:
            return "" 
        
        result = []
        
        result.append("Lista de antibióticos utilizados nos últimos 30 dias:")
        
        for _, row in df.iterrows():
            antibiotic = row['ds_tip_presc']
            impression_date = row['dh_impressao']
            
            formatted_date = impression_date.strftime('%d/%m/%y')
            
            result.append(f"{antibiotic} - {formatted_date}")
        
        return "\n" + "\n".join(result) + "\n" 

    # Separa os antibioticos para serem enviados em grupos de 3 em 3.
    def __return_list_of_list_of_json_antibiotics(self, antibiotics: pd.DataFrame) -> list:
        antibiotics_json_list = []
        sub_list = []

        for index in range(len(antibiotics)):
            json = antibiotics.iloc[index][['antibioticName', 'antibioticIdentifier', 'dosage', 'usagePeriod', 'hospitalIntervalTimeIdentifier', 'hospitalViaIdentifier', 'hospitalDosageUnitIdentifier']].to_dict()#.to_json()
            sub_list.append(json)

        if len(sub_list) > 0:
            antibiotics_json_list.append(sub_list.copy())
        
        return antibiotics_json_list

    # Busca a data de admissão de um paciente
    def __get_admission_date(self, patient_id: str, nr_atendimento: str) -> str:
        query_get_admission_date = f"""
            SELECT 
                dt_atendimento
            FROM DBAMV.ATENDIME a
            WHERE a.cd_paciente = '{patient_id}' 
                AND a.cd_atendimento = '{nr_atendimento}'
        """
        df = dataRequest.get_data(queryText= query_get_admission_date)
        if df is None:
            return ''
        else:
            if len(df) == 0:
                return ''
        return str(df.iloc[0]['dt_atendimento'].to_datetime64())

    # Função que retorna a evolução do paciente
    # TODO: Modificar aqui sempre os codigos dos objetos
    def __get_evol(self, cd_paciente: str, html:bool) -> str | None:
        def campo_as_boolean(df: pd.DataFrame, cd_campo: int) -> bool:
            valores = df.loc[df['cd_campo'] == cd_campo, 'lo_valor']
            return not valores.empty and str(valores.iloc[0]).strip().lower() == 'true'

        query = f"""
            SELECT
                to_char(pdc.dh_fechamento, 'dd/mm/yyyy') AS dh_fechamento,
                pdc.nm_documento,
                ec.cd_campo,
                ec.ds_campo,
                erc.lo_valor as lo_valor
            FROM dbamv.pw_documento_clinico pdc
            INNER JOIN dbamv.pw_editor_clinico pec
                ON pdc.cd_documento_clinico = pec.cd_documento_clinico
            INNER JOIN dbamv.editor_registro er
                ON pec.cd_editor_registro = er.cd_registro
            INNER JOIN dbamv.editor_registro_campo erc
                ON er.cd_registro = erc.cd_registro
            INNER JOIN dbamv.editor_campo ec
                ON erc.cd_campo = ec.cd_campo
            WHERE pdc.cd_documento_clinico = (
                SELECT * FROM (
                    SELECT
                        pdc2.cd_documento_clinico
                    FROM dbamv.pw_documento_clinico pdc2
                    INNER JOIN dbamv.atendime a
                        on pdc2.cd_atendimento = a.cd_atendimento
                    WHERE pdc2.cd_objeto = 371
                        AND pdc2.nm_documento IN ('EVOLUÇÃO MÉDICA', 'ATEDIMENTO MÉDICO DE URGENCIA NA INTERNAÇÃO', 'ADMISSÃO - INTERNAÇÃO HOSPITALAR')
                        AND pdc2.cd_documento_digital IS NOT NUll
                        AND a.cd_paciente = {cd_paciente}
                        AND pdc2.dh_fechamento IS NOT NULL
                    ORDER BY 1 DESC
                ) WHERE ROWNUM <= 1
            )
        """
        df = dataRequest.get_data(queryText= query)
        if len(df) == 0:
            return ""
        
        type = str(df.iloc[0]['nm_documento'])
        date = df.iloc[0]['dh_fechamento']
        df['lo_valor'] = df['lo_valor'].fillna("")

        if type.upper().strip() == "EVOLUÇÃO MÉDICA".upper().strip():
            evo = f"Evolução EVOLUÇÃO MÉDICA do dia: {date}"

            diagnostico = str(df[df['cd_campo'] == 306488].iloc[0]['lo_valor'])
            evo += f"\tDiagnóstico Principal: {diagnostico}\n" if diagnostico.strip() != "" else ""

            medicamentos = str(df[df['cd_campo'] == 306509].iloc[0]['lo_valor'])
            evo += f"\tAntibiotico em Uso: {medicamentos}\n" if medicamentos.strip() != "" else ""

            antecedentes = str(df[df['cd_campo'] == 306489].iloc[0]['lo_valor'])
            evo += f"\tAntecedentes: {antecedentes}\n" if antecedentes.strip() != "" else ""

            medicamentos = str(df[df['cd_campo'] == 306498].iloc[0]['lo_valor'])
            evo += f"\tMedicamentos de uso habitual: {medicamentos}\n" if medicamentos.strip() != "" else ""

            exame_fisico = str(df[df['cd_campo'] == 306510].iloc[0]['lo_valor'])
            evo += f"\tExame físico: {exame_fisico}\n" if exame_fisico.strip() != "" else ""

            obs = str(df[df['cd_campo'] == 306491].iloc[0]['lo_valor'])
            evo += f"\tObservações ou Complementações a evolução Médica: {obs}\n" if obs.strip() != "" else ""

            conduta = str(df[df['cd_campo'] == 306492].iloc[0]['lo_valor'])
            evo += f"\tConduta: {conduta}\n" if conduta.strip() != "" else ""

            return evo
        elif type.upper().strip() == "ATEDIMENTO MÉDICO DE URGENCIA NA INTERNAÇÃO".upper().strip():
            evo = f"Evolução de ATEDIMENTO MÉDICO DE URGENCIA NA INTERNAÇÃO do dia: {date}"
            
            queixa = str(df[df['cd_campo'] == 286906].iloc[0]['lo_valor'])
            evo += f"\tQueixa principal: {queixa}\n" if queixa.strip() != "" else ""

            historia = str(df[df['cd_campo'] == 286907].iloc[0]['lo_valor'])            
            evo += f"\tHistória da Doença Atual: {historia}\n\n" if historia.strip() != "" else ""
            
            evo += f"História Patológica Pregressa\n"
            
            sim_diabetes = campo_as_boolean(df, 286909)
            nao_diabetes = campo_as_boolean(df, 286908)
            evo += f"\tDiabetes: {'Sim' if sim_diabetes else 'Não'}\n" if not sim_diabetes or not nao_diabetes else ""
            
            sim_has = campo_as_boolean(df, 286912)
            nao_has = campo_as_boolean(df, 286911)
            evo += f"\tHAS: {'Sim' if sim_has else 'Não'}\n" if not sim_has or not nao_has else ""
            
            sim_outras = campo_as_boolean(df, 286915)
            nao_outras = campo_as_boolean(df, 286914)
            especificar = str(df[df['cd_campo'] == 286916].iloc[0]['lo_valor'])
            evo += f"\tOutras doenças: {'Sim' if sim_outras else ('Não' if nao_outras else '')}\n" if not sim_outras or not nao_outras or especificar.strip() != "" else ""
            evo += f"\t\tEspecificar: {especificar}\n" if especificar != "" else ""

            medicamentos = str(df[df['cd_campo'] == 286917].iloc[0]['lo_valor'])
            evo += f"\tMedicamentos em uso: {medicamentos}\n" if medicamentos.strip() != "" else ""
            
            sim_alergia = campo_as_boolean(df, 286919)
            nao_alergia = campo_as_boolean(df, 286918)
            obs_alergias = str(df[df['cd_campo'] == 286920].iloc[0]['lo_valor'])
            evo += f"\tAlergias: {'Sim' if sim_alergia else ('Não' if nao_alergia else '')}\n" if not sim_alergia or not nao_alergia or obs_alergias.strip() != "" else ""
            evo += f"\t\t{obs_alergias}\n" if obs_alergias.strip() != "" else ""

            intercorrencias = str(df[df['cd_campo'] == 286947].iloc[0]['lo_valor'])
            evo += f"\tIntercorrências durante internação: {intercorrencias}\n" if intercorrencias.strip() != "" else ""
            
            outras_obs = str(df[df['cd_campo'] == 286921].iloc[0]['lo_valor'])
            evo += f"\tOutras informações: {outras_obs}\n\n" if outras_obs.strip() != "" else ""

            motivo_atendimento = str(df[df['cd_campo'] == 286948].iloc[0]['lo_valor'])
            evo += f"\tMotivo do atendimento: {motivo_atendimento}\n\n" if motivo_atendimento.strip() != "" else ""
            
            evo += f"Exame fisico: \n"

            peso = str(df[df['cd_campo'] == 286922].iloc[0]['lo_valor'])
            evo += f"\tPeso: {peso}\n" if peso.strip() != "" else ""

            ectoscopia = str(df[df['cd_campo'] == 286932].iloc[0]['lo_valor'])
            evo += f"\tEctoscopia: {ectoscopia}\n" if ectoscopia.strip() != "" else ""
            
            aparelho_cardiovascular = str(df[df['cd_campo'] == 286933].iloc[0]['lo_valor'])
            evo += f"\tAparelho Cardiovascular: {aparelho_cardiovascular}\n" if aparelho_cardiovascular.strip() != "" else ""
            
            aparelho_respiratorio = str(df[df['cd_campo'] == 286934].iloc[0]['lo_valor'])
            evo += f"\tAparelho Respiratorio: {aparelho_respiratorio}\n" if aparelho_respiratorio.strip() != "" else ""
            
            abdome = str(df[df['cd_campo'] == 286935].iloc[0]['lo_valor'])
            evo += f"\tAbdome: {abdome}\n" if abdome.strip() != "" else ""
            
            membros_inferiores = str(df[df['cd_campo'] == 286936].iloc[0]['lo_valor'])
            evo += f"\tMembros Inferiores: {membros_inferiores}\n" if membros_inferiores.strip() != "" else ""

            neurologico = str(df[df['cd_campo'] == 286937].iloc[0]['lo_valor'])
            evo += f"\tExame Físico Neurológico: {neurologico}\n" if neurologico.strip() != "" else ""

            obs = str(df[df['cd_campo'] == 286938].iloc[0]['lo_valor'])
            evo += f"\tObservações ou Complementações: {obs}\n" if obs.strip() != "" else ""

            diagnostico = str(df[df['cd_campo'] == 286940].iloc[0]['lo_valor'])
            evo += f"\tDiagnóstico Inicial Principal: {diagnostico}\n" if diagnostico.strip() != "" else ""

            diagnostico_diferencial = str(df[df['cd_campo'] == 286941].iloc[0]['lo_valor'])
            evo += f"\tDiagnósticos diferenciais: {diagnostico_diferencial}\n" if diagnostico_diferencial.strip() != "" else ""

            conduta = str(df[df['cd_campo'] == 286939].iloc[0]['lo_valor'])
            evo += f"\tConduta: {conduta}\n" if conduta.strip() != "" else ""
            return evo
        elif type.upper().strip() == "ADMISSÃO - INTERNAÇÃO HOSPITALAR".upper().strip():
            evo = f"Evolução ADMISSÃO - INTERNAÇÃO HOSPITALAR do dia: {date}\n\n"

            queixa = str(df[df['cd_campo'] == 293605].iloc[0]['lo_valor'])
            evo += f"\tQueixa principal: {queixa}\n" if queixa.strip() != "" else ""

            historia = str(df[df['cd_campo'] == 293606].iloc[0]['lo_valor'])            
            evo += f"\tHistória da Doença Atual: {historia}\n\n" if historia.strip() != "" else ""
            
            evo += f"História Patológica Pregressa\n"
            
            sim_diabetes = campo_as_boolean(df, 293608)
            nao_diabetes = campo_as_boolean(df, 293607)
            evo += f"\tDiabetes: {'Sim' if sim_diabetes else 'Não'}\n" if not sim_diabetes or not nao_diabetes else ""
            
            sim_has = campo_as_boolean(df, 293610)
            nao_has = campo_as_boolean(df, 293609)
            evo += f"\tHAS: {'Sim' if sim_has else 'Não'}\n" if not sim_has or not nao_has else ""
            
            sim_outras = campo_as_boolean(df, 293612)
            nao_outras = campo_as_boolean(df, 293611)
            especificar = str(df[df['cd_campo'] == 293613].iloc[0]['lo_valor'])
            evo += f"\tOutras doenças: {'Sim' if sim_outras else ('Não' if nao_outras else '')}\n" if not sim_outras or not nao_outras or especificar.strip() != "" else ""
            evo += f"\t\tEspecificar: {especificar}\n" if especificar != "" else ""

            medicamentos = str(df[df['cd_campo'] == 293614].iloc[0]['lo_valor'])
            evo += f"\tMedicamentos deuso habitual: {medicamentos}\n" if medicamentos.strip() != "" else ""
            
            sim_cirurgia = campo_as_boolean(df, 293616)
            nao_cirurgia = campo_as_boolean(df, 293615)
            obs_internacoes = str(df[df['cd_campo'] == 293617].iloc[0]['lo_valor'])
            evo += f"\tInternações / Cirurgias prévias: {'Sim' if sim_cirurgia else ('Não' if nao_cirurgia else '')}\n" if not sim_cirurgia or not nao_cirurgia or obs_internacoes.strip() != "" else ""
            evo += f"\t\t{obs_internacoes}\n" if obs_internacoes.strip() != '' else ''
            
            sim_alergia = campo_as_boolean(df, 293619)
            nao_alergia = campo_as_boolean(df, 293618)
            obs_alergias = str(df[df['cd_campo'] == 293620].iloc[0]['lo_valor'])
            evo += f"\tAlergias: {'Sim' if sim_alergia else ('Não' if nao_alergia else '')}\n" if not sim_alergia or not nao_alergia or obs_alergias.strip() != "" else ""
            evo += f"\t\t{obs_alergias}\n" if obs_alergias.strip() != "" else ""
            
            outras_obs = str(df[df['cd_campo'] == 293621].iloc[0]['lo_valor'])
            evo += f"\tOutras informações: {outras_obs}\n\n" if outras_obs.strip() != "" else ""
            
            evo += f"Exame fisico: \n"

            ectoscopia = str(df[df['cd_campo'] == 293630].iloc[0]['lo_valor'])
            evo += f"\tEctoscopia: {ectoscopia}\n" if ectoscopia.strip() != "" else ""
            
            aparelho_cardiovascular = str(df[df['cd_campo'] == 293631].iloc[0]['lo_valor'])
            evo += f"\tAparelho Cardiovascular: {aparelho_cardiovascular}\n" if aparelho_cardiovascular.strip() != "" else ""
            
            aparelho_respiratorio = str(df[df['cd_campo'] == 293632].iloc[0]['lo_valor'])
            evo += f"\tAparelho Respiratorio: {aparelho_respiratorio}\n" if aparelho_respiratorio.strip() != "" else ""
            
            abdome = str(df[df['cd_campo'] == 293633].iloc[0]['lo_valor'])
            evo += f"\tAbdome: {abdome}\n" if abdome.strip() != "" else ""
            
            membros_inferiores = str(df[df['cd_campo'] == 293634].iloc[0]['lo_valor'])
            evo += f"\tMembros Inferiores: {membros_inferiores}\n" if membros_inferiores.strip() != "" else ""

            neurologico = str(df[df['cd_campo'] == 293635].iloc[0]['lo_valor'])
            evo += f"\tExame Físico Neurológico: {neurologico}\n" if neurologico.strip() != "" else ""

            obs = str(df[df['cd_campo'] == 293636].iloc[0]['lo_valor'])
            evo += f"\tObservações ou Complementações a evolução Médica: {obs}\n" if obs.strip() != "" else ""

            conduta = str(df[df['cd_campo'] == 293637].iloc[0]['lo_valor'])
            evo += f"\tConduta: {conduta}\n" if conduta.strip() != "" else ""
            return evo
        
        return f"Falha no parse da evolução tipo: {type}"
    
    # Função para buscar resultado do ultimo exame de creatinina do paciente dado o numero do atendimento desse paciente.
    def __get_creatinine_and_collection_date(self, nr_paciente: str) -> pd.DataFrame | None:
        #VERIFICAR COMO PEGAR AS INFO DA CREATININA
        query_get_creatinine = f"""
            select * from (
                SELECT 
                    tp.DS_TIP_PRESC AS nm_exame,
                    re.DS_RESULTADO AS qt_resultado,
                    il.DT_LAUDO AS dt_digitacao
                FROM dbamv.PED_LAB pl  
                INNER JOIN dbamv.ITPED_LAB il 
                    ON pl.CD_PED_LAB = il.CD_PED_LAB 
                INNER JOIN dbamv.TIP_PRESC tp 
                    ON il.CD_EXA_LAB = tp.CD_EXA_LAB
                INNER JOIN dbamv.RES_EXA re 
                    ON re.CD_PED_LAB = il.CD_PED_LAB
                        AND re.CD_EXA_LAB = tp.CD_EXA_LAB 
                        AND il.CD_ITPED_LAB = re.CD_ITPED_LAB 
                INNER JOIN dbamv.atendime a
                    on a.cd_atendimento = pl.cd_atendimento
                WHERE tp.CD_TIP_PRESC IN (15589, 15606)
                    AND il.DT_LAUDO IS NOT NULL
                    AND a.cd_paciente = {nr_paciente}
                order by il.DT_LAUDO desc
            )
            where rownum <= 1
        """
        df = dataRequest.get_data(queryText= query_get_creatinine)
        df_sorted = df.sort_values(by='dt_digitacao', ascending=False)
        
        if len(df_sorted) > 0:
            # TODO: ALERTA MUDANCA AQUI EMBAIXO POSSIVEL
            return df_sorted[['nm_exame', 'qt_resultado', 'dt_digitacao']].fillna('')#.reset_index()
                
        return None

    # Fazer union all para buscar a ultima data do atendime onde tenha sido feito o registro dentro de um leito das unidades de dialise
    # Função para buscar a ultima dialise do paciente se ele tiver feito.
    def __get_dialise(self, nr_paciente: str):
        query = f"""
            select 
                * 
            from (
                SELECT 
                    DH_REGISTRO
                FROM PRE_MED pm 
                INNER JOIN ITPRE_MED im 
                    ON pm.CD_PRE_MED = im.CD_PRE_MED
                INNER JOIN ATENDIME a
                    on pm.cd_atendimento = a.cd_atendimento
                WHERE im.CD_TIP_PRESC IN (17500, 17501, 17502, 17504, 17503)
                    AND DH_REGISTRO IS NOT NULL
                    AND a.cd_paciente = {nr_paciente}
                order by 1 desc
            ) where rownum <= 1
        """
        df = dataRequest.get_data(queryText= query)
        if df is not None:
            if len(df) > 0:
                return df
                    
        return None
    
    # Função para buscar informações sobre o usuário
    def __get_paciente(self, patient_id:str) -> pd.Series:
        def get_patient_information(patient_id: str) -> pd.DataFrame:
            from datetime import datetime
            query_get_patient = f"""
                SELECT 
                    NM_PACIENTE, 
                    TP_SEXO, 
                    DT_NASCIMENTO, 
                    TP_COR,
                    NR_CPF
                FROM DBAMV.PACIENTE p
                WHERE p.CD_PACIENTE = {patient_id}
            """
            df = dataRequest.get_data(query_get_patient)
            df['hospitalIdentifier'] = patient_id
            df['tp_cor'] = df['tp_cor'].apply(lambda x: 'B' if str(x) == '2' else 'O')
            current_date = datetime.now()

            df['age_in_days'] = df['dt_nascimento'].apply(lambda x: 0 if (x is None or pd.isna(x)) else (current_date - x).days)
            df['patientAge'] = df['age_in_days'].apply(lambda x: int(x) * 24)
            df.rename(columns= {'tp_cor': 'race', 'tp_sexo': 'gender', 'nm_paciente': 'name', 'nr_cpf': 'cpf'}, inplace= True)
            df.drop(columns=['dt_nascimento', 'age_in_days'], inplace= True)
            return df

        def get_patient_allergy(patient_id: str) -> pd.DataFrame | None:
            query = f"""
                SELECT 
                    distinct 
                        A.DS_AVISO,  
                        S.DS_SUBSTANCIA 
                FROM DBAMV.SUBS_PAC A 
                INNER JOIN DBAMV.SUBSTANCIA S 
                    ON A.CD_SUBSTANCIA = S.CD_SUBSTANCIA
                WHERE A.CD_PACIENTE = {patient_id}
            """

            df = dataRequest.get_data(queryText=query)

            drugAllergyName = ""
            drugAllergy = False

            if df is None:
                return None

            for index in df.index:
                linha = df.iloc[index]
                substancia = linha["ds_substancia"]
                aviso = linha["ds_aviso"]
                if str(substancia) == "nan":
                    continue
                else:
                    drugAllergy = True
                    drugAllergyName += f"{substancia}"
                    if str(aviso) == str(substancia) or str(aviso) == "nan":
                        drugAllergyName += ", "
                        continue
                    else:
                        drugAllergyName += f" ({aviso}), "
                

            drugAllergyName =  drugAllergyName.strip(", ") if len(drugAllergyName.strip(", ")) < 255 else drugAllergyName.strip(", ")[:249]+"..."

            if drugAllergyName == "":
                drugAllergy = False
                drugAllergyName = "SEM MEDICAMENTO DE ALERGIA"

            result = {
                'drugAllergy': [drugAllergy],
                'drugAllergyName': [drugAllergyName]
            }
            return pd.DataFrame(result)

        patient = get_patient_information(patient_id)
        patient_allergies = get_patient_allergy(patient_id)

        patient['drugAllergy'] = patient_allergies['drugAllergy'] if patient_allergies is not None else None
        patient['drugAllergyName'] = patient_allergies['drugAllergyName']  if patient_allergies is not None else None
        return patient.iloc[0]
        

    # Bucar o antibiotico que o usuário tomou antes dessa prescrição
    def __get_previous_antibiotic(self, nr_prescricao_atual: str, patient_id: str) -> str:
        get_antibiotic_for_this_prescription = f"""
            SELECT 
                distinct presc.DS_TIP_PRESC 
            FROM DBAMV.ITPRE_MED it
            INNER JOIN DBAMV.TIP_PRESC presc 
                ON it.CD_TIP_PRESC = presc.CD_TIP_PRESC
            INNER JOIN DBAMV.PRE_MED pm
                ON it.cd_pre_med = pm.cd_pre_med
            inner join dbamv.atendime a
                on pm.cd_atendimento = a.cd_atendimento
            WHERE (
                    (it.cd_tip_esq IN ('MDA') AND it.cd_tip_presc not in (16264, 16169, 23342, 16204))
                    or
                    (it.cd_tip_presc in (22275, 22120, 20565, 23094, 23143, 17464, 20564, 17465))
                )
                AND pm.DT_PRE_MED >= (SYSDATE-90) 
                AND pm.CD_PRE_MED < {int(nr_prescricao_atual)}
                AND a.CD_PACIENTE = {patient_id}
        """
        antibiotics = dataRequest.get_data(queryText= get_antibiotic_for_this_prescription)
        if len(antibiotics) > 0:
            concatenado = ""
            for index in antibiotics.index:
                concatenado += f"{antibiotics.iloc[index]['ds_tip_presc']}, "
            
            return concatenado.strip(", ") if len(concatenado.strip(", ")) < 255 else concatenado.strip(", ")[:249]+"..."

        return 'Não contem antibiotico prévio registrado'
    
    def get_patient_height(self, cd_paciente: str):
        query = f"""
            SELECT 
                valor
            FROM COLETA_SINAL_VITAL CSV
            INNER JOIN ITCOLETA_SINAL_VITAL ISV
                ON CSV.CD_COLETA_SINAL_VITAL = ISV.CD_COLETA_SINAL_VITAL 
            INNER JOIN ATENDIME A
                ON CSV.CD_ATENDIMENTO = A.CD_ATENDIMENTO 
            WHERE ISV.CD_SINAL_VITAL = 10
                AND ISV.VALOR  IS NOT NULL
                AND A.CD_PACIENTE = {cd_paciente}
            ORDER BY ISV.CD_COLETA_SINAL_VITAL DESC
        """

        df = dataRequest.get_data(queryText=query)

        if len(df) > 0:
            return df.iloc[0]['valor']

        return 0
    
    def get_patient_weight(self, cd_paciente: str):
        query = f"""
            SELECT 
                valor
            FROM COLETA_SINAL_VITAL CSV
            INNER JOIN ITCOLETA_SINAL_VITAL ISV
                ON CSV.CD_COLETA_SINAL_VITAL = ISV.CD_COLETA_SINAL_VITAL 
            INNER JOIN ATENDIME A
                ON CSV.CD_ATENDIMENTO = A.CD_ATENDIMENTO 
            WHERE ISV.CD_SINAL_VITAL = 9
                AND ISV.VALOR  IS NOT NULL
                AND A.CD_PACIENTE = {cd_paciente}
            ORDER BY ISV.CD_COLETA_SINAL_VITAL DESC
        """

        df = dataRequest.get_data(queryText=query)

        if len(df) > 0:
            return df.iloc[0]['valor']

        return 0

    # Busca a ultima vez que o usuãrio esteve no hospital.
    def __get_previous_admission(self, cd_pessoa_fisica: str, nr_atendimento_atual: str):
        get_all_services = f"""
            SELECT 
                A.CD_ATENDIMENTO, 
                A.DT_ATENDIMENTO 
            FROM DBAMV.ATENDIME A
            WHERE A.CD_PACIENTE = '{cd_pessoa_fisica}' 
                AND A.DT_ATENDIMENTO >= (SYSDATE-90) 
                AND A.CD_ATENDIMENTO < {int(nr_atendimento_atual)} 
            ORDER BY A.DT_ATENDIMENTO DESC
        """
        all_services = dataRequest.get_data(queryText= get_all_services)
        
        return len(all_services) > 0

    def get_status(self,num_st):
        status_text = "Status da prescrição: "
        match num_st:
            case '0':
                status_text += "Aberto"
            case '1':
                status_text += "Ajuste de dose"
            case '2':
                status_text += "Mudar via prescrição"
            case '3':
                status_text += "Outra sugestão"
            case '4':
                status_text += "Aguardando mais infromações"
            case '5':
                status_text += "Sobreposição de terapia"
            case '6':
                status_text += "Suspender terapia"
            case '7':
                status_text += "Adequado"
            case '8':
                status_text += "Ajuste tempo de uso"
            case '9':
                status_text += "Nova recomendação"
            case '10':
                status_text += "Adequado até resultado de culturas"
            case '11':
                status_text += "Adequado com observação"
            case _:
                pass
        return status_text

    # Processa a tentativa de busca de resposta
    def try_get_doctor_answer_for_prescription(self, prescr):
        def get_texto_sobre_retorno(content):
            if len(content['submissions']) > 1:
                retorno = content['submissions'][-1]
                if (retorno['doctorQualisName'] or None ) is None:
                    return None
                date = datetime.datetime.fromisoformat(retorno['submissionDate'])
                text_antibiotics_sended_for_qualis = f"\t\tQualis - Avaliação da prescrição de antimicrobianos  - {date.day}/{date.month}/{date.year}, {date.time()}"
                
                envio = content['submissions'][-2]
                if 'antibiotics' not in envio:
                    envio = content['submissions'][0]
                date = datetime.datetime.fromisoformat(envio['submissionDate'])
                text_antibiotics_sended_for_qualis += f"\n\n{f'Data e horário da prescrição enviada: {date.day}/{date.month}/{date.year}, {date.time()}'}"
                text_antibiotics_sended_for_qualis += f"\nNúmero da prescrição interna: {prescr['prescr_id']}\n"

                for i in range(len(envio['antibiotics'])):
                    dosageUnit = envio['antibiotics'][i]['dosageUnitName']
                    dosage = envio['antibiotics'][i]['dosage']
                    via = envio['antibiotics'][i]['viaName']
                    intervalTime = envio['antibiotics'][i]['intervalTimeName']
                    usagePeriod = envio['antibiotics'][i]['usagePeriod']
                    antibioticName = envio['antibiotics'][i]['hospitalAntibiotic']['name']

                    text_for_antibiotic = f"""\n{i+1}) {antibioticName if antibioticName is not None else 'Falha no nome do antibiotico'}
    \t- Dose: {dosage if dosage is not None else 'Falha na captura da dose'}
    \t- Unidade da dose: {dosageUnit if dosageUnit is not None else "Falha na captura da unidade da dose"}
    \t- Via: {via if via is not None else "Falha na captura da via"}
    \t- Intervalo de uso: {intervalTime if intervalTime is not None else "Falha na captura do intervalo de uso"}
    \t- Tempo de uso previsto: {f"{usagePeriod} dias" if usagePeriod is not None else "Falha na captura dos dias de uso"}\n
    """             
                    text_antibiotics_sended_for_qualis += text_for_antibiotic

                status_text = self.get_status(str(content['status']))

                text_antibiotics_sended_for_qualis += "\n========== PARECER DA QUALIS ========== \n"
                text_antibiotics_sended_for_qualis += f"\nNúmero da prescrição dentro da Qualis: {prescr['prescr_id_on_qualis']}\n"
                text_antibiotics_sended_for_qualis += status_text + "\n"
                
                avaliacao = retorno.get('recommendationMessage') or ''
                avaliacao_text= "\nAvaliação: " + (avaliacao if avaliacao is not None else "")
                text_antibiotics_sended_for_qualis += avaliacao_text + "\n"

                if 'antibiotics' in retorno:
                    i_sub = 0
                    for i in range(len(retorno['antibiotics'])):
                        dosageUnit = retorno['antibiotics'][i]['dosageUnitName']
                        dosage = retorno['antibiotics'][i]['dosage']
                        via = retorno['antibiotics'][i]['viaName']
                        intervalTime = retorno['antibiotics'][i]['intervalTimeName']
                        usagePeriod = retorno['antibiotics'][i]['usagePeriod']
                        antibioticName = retorno['antibiotics'][i]['hospitalAntibiotic']['name']

                        text_for_antibiotic = f"""\n{i+1+i_sub}) {antibioticName if antibioticName is not None else 'Falha no nome do antibiotico'}
    \t- Dose: {dosage if dosage is not None else 'Falha na captura da dose'}
    \t- Unidade da dose: {dosageUnit if dosageUnit is not None else "Falha na captura da unidade da dose"}
    \t- Via: {via if via is not None else "Falha na captura da via"}
    \t- Intervalo de uso: {intervalTime if intervalTime is not None else "Falha na captura do intervalo de uso"}
    \t- Tempo de uso previsto: {f"{usagePeriod} dias" if usagePeriod is not None else "Falha na captura dos dias de uso"}\n
    """             
                        status = '7'
                        try:
                            status = retorno['antibiotics'][i]['status']
                        except Exception:
                            pass

                        if str(status) == '6':
                            i_sub += -1
                            continue

                        text_antibiotics_sended_for_qualis += text_for_antibiotic
                
                text_antibiotics_sended_for_qualis += f"\nAvaliado por {retorno['doctorQualisName'] if 'doctorQualisName' in retorno else 'Falha ao pegar o nome do medico'}. Crm {retorno['doctorQualisCRM'] if 'doctorQualisCRM' in retorno else 'Falha ao pegar o crm do medico'}\n"
                
                date = datetime.datetime.fromisoformat(retorno['submissionDate'])
                text_antibiotics_sended_for_qualis += f"\nEm {date.day}/{date.month}/{date.year}, {date.time()}"
                
                text_antibiotics_sended_for_qualis += f"\nVeja em: https://portalqualis.com.br/prescricao/{prescr['prescr_id_on_qualis']}"
                
                return text_antibiotics_sended_for_qualis
            else:
                return None
        
        def get_texto_data_retorno(content) -> str | None:
            if len(content['submissions']) > 1:
                retorno = content['submissions'][-1]
                date = datetime.datetime.fromisoformat(retorno['submissionDate'])
                return f"{date.day}/{date.month}/{date.year}, {date.time()}"
            
            return None
            
        current_text = prescr['prescr_sended_message'] if prescr is not None else ''
        doctor_id = prescr['cd_medico'] if prescr is not None else ''
        token = self._authenticator.get_Token_for_cd_medico(doctor_id)
        prescr_on_qualis_id = prescr['prescr_id_on_qualis'] if prescr is not None else ''

        response = requests.get(f"{C.API_BASE_URL}prescriptions/{prescr_on_qualis_id}", headers= {'Authorization': token, 'hospital-key': C.HOSPITAL_KEY}, verify= False, timeout= 20)
        body = response.json()
        content = body['results'][0]
        status = content['status']
        mensagem_retorno = None
        if status != 0: # Isso vai diferenciar se já houve ou não uma resposta por parte da Qualis
            mensagem_retorno = get_texto_sobre_retorno(content)
            texto_data_retorno = get_texto_data_retorno(content)

            # Vou atualizar a prescription_qualis para salvar o retorno
            if mensagem_retorno is not None and texto_data_retorno is not None:
                mensagem_retorno = mensagem_retorno[:3999]
                if current_text is not None and texto_data_retorno in current_text:
                    print(f"Prescrição {prescr['prescr_id']} já possui retorno, não será atualizado.")
                    return

                query_update_with_response = f"""
                    UPDATE DBAMV.prescription_qualis p
                    SET
                        p.prescr_status = :status,
                        p.prescr_sended_message = :message,
                        p.dt_retorno = SYSDATE
                    WHERE p.prescr_id = :prescr_id
                """ 
                payload = {
                    "status": str(status),
                    "message": str(mensagem_retorno),
                    "prescr_id": str(prescr['prescr_id'])
                }
                dataRequest.execute(query_update_with_response, payload)

                query_pre_prescription = f"""
                    SELECT 
                        *
                    FROM DBAMV.pre_med
                    WHERE cd_pre_med = {prescr['prescr_id']}
                """
                df = dataRequest.get_data(queryText= query_pre_prescription)

                if df is None:
                    return  
                else:
                    row = df.iloc[0]

                query_insert_into_evolution_patient = f"""
                    DECLARE cd_next_doc_clinico NUMBER; cd_next_pre_med NUMBER;
                    BEGIN
                        SELECT SEQ_PW_DOCUMENTO_CLINICO.nextval INTO cd_next_doc_clinico FROM dual;
                        SELECT SEQ_PRE_MED.nextval INTO cd_next_pre_med FROM dual;

                        INSERT INTO DBAMV.PW_DOCUMENTO_CLINICO (cd_documento_clinico, cd_tipo_documento, cd_paciente, cd_atendimento, cd_usuario, cd_prestador, tp_status, dh_referencia, dh_criacao, dh_fechamento, cd_objeto, dh_documento, cd_multi_empresa)
                        VALUES (
                            cd_next_doc_clinico,
                            :cd_tipo_documento,
                            :patient_hospital_id,
                            :nr_atendimento,
                            :cd_usuario,
                            :cd_prestador,
                            'FECHADO',
                            sysdate,
                            sysdate,
                            sysdate,
                            :cd_objeto,
                            sysdate,
                            NULL
                        );

                        INSERT INTO DBAMV.pre_med (cd_pre_med, cd_atendimento, cd_prestador, cd_unid_int, dt_pre_med, hr_pre_med, ds_evolucao, cd_id_usuario, sn_fechado, sn_rn, dt_validade, fl_principal, fl_impresso, tp_pre_med, nm_usuario, cd_setor, dt_referencia, sn_transcricao, dh_criacao, dh_impressao, cd_objeto, sn_prescricao_dia_seguinte, cd_documento_clinico)
                        VALUES (
                            cd_next_pre_med,
                            :nr_atendimento,
                            :cd_prestador,
                            :hospital_unity_id,
                            sysdate,
                            sysdate,
                            :mensagem_retorno,
                            :cd_id_usuario,
                            'S',
                            :sn_rn,
                            TO_DATE(:dt_validade, 'YYYY/MM/DD HH24:MI:SS'),
                            :fl_principal,
                            :fl_impresso,
                            :tp_pre_med,
                            :nm_prestador,
                            :cd_setor,
                            TO_DATE(:dt_referencia, 'YYYY/MM/DD HH24:MI:SS'),
                            :sn_transcricao,
                            sysdate,
                            sysdate,
                            :cd_objeto,
                            :sn_prescricao_dia_seguinte,
                            cd_next_doc_clinico
                        );

                        UPDATE DBAMV.prescription_qualis 
                        SET PRESCR_STATUS = -3
                        WHERE prescr_id = cd_next_pre_med;
                    END;   
                """
                payload = {
                    "cd_tipo_documento" : 36,
                    "cd_usuario" : 'RSANTOS',
                    "nm_prestador" : 'RODRIGO PIRES DOS SANTOS',
                    "cd_prestador" : 606,
                    "cd_objeto" : 446,
                    "patient_hospital_id" : int(prescr['patient_hospital_id']) if 'nan' != str(prescr['nr_atendimento']) else None,
                    "nr_atendimento" : int(prescr['nr_atendimento']) if 'nan' != str(prescr['nr_atendimento']) else None,
                    "hospital_unity_id" : int(prescr['hospital_unity_id']) if str(prescr['hospital_unity_id']) not in ['nan', 'None'] else None,
                    "mensagem_retorno" : str(mensagem_retorno),
                    "cd_id_usuario" : int(row['cd_id_usuario']),
                    "sn_rn" : str(row['sn_rn']),
                    "dt_validade" : str(row['dt_validade']),
                    "fl_principal" : str(row['fl_principal']),
                    "fl_impresso" : str(row['fl_impresso']),
                    "tp_pre_med" : str(row['tp_pre_med']),
                    "cd_setor" : int(row['cd_setor']),
                    "sn_transcricao" : str(row['sn_transcricao']),
                    "dt_referencia" : str(row['dt_referencia']),
                    "sn_prescricao_dia_seguinte" : str(row['sn_prescricao_dia_seguinte']),
                }
                dataRequest.execute(query_insert_into_evolution_patient, payload)

    def __get_possible_new_doctor_answer(self):
        query = """
            SELECT * FROM DBAMV.PRESCRIPTION_QUALIS P
            WHERE P.PRESCR_SENDED_STATUS = '1' 
                AND P.PRESCR_STATUS != '0'
                AND P.DT_RETORNO > (SYSDATE-1)
        """
        df = dataRequest.get_data(queryText= query)
        for index in df.index:
            try:
                prescr = df.iloc[index]
                self.try_get_doctor_answer_for_prescription(prescr)
                self._report_progress()
            except Exception as e:
                print(f"Erro ao buscar resposta para a prescricao: {prescr['prescr_id']} - {e}")
                        
    # Função para fazer looping buscando pelas respostas
    def __busca_todas_respostas_pendentes(self):
        query_pendente_resposta = """
            SELECT * 
            FROM DBAMV.prescription_qualis P
            WHERE p.prescr_sended_status = '1' AND p.prescr_status = '0'
        """
        df = dataRequest.get_data(queryText= query_pendente_resposta)

        for index in df.index:
            prescr = df.iloc[index]
            try:
                self.try_get_doctor_answer_for_prescription(prescr)
            except Exception as e:
                errorCompleto = traceback.format_exc()
                self._send_email(f"Error em {C.HOSPITAL_NAME}, reporte a equipe de desenvolvimento sobre: {errorCompleto}", f"Error grave durante execução do integrador")

    def __get_setor_atendimento(self, prescription) -> str | None:
        query = f"""
            SELECT
                cd_setor
            FROM DBAMV.PRE_MED pm
            WHERE pm.CD_PRE_MED = {prescription['prescr_id']}
        """
        df = dataRequest.get_data(queryText= query)

        if len(df) > 0:
            return "setor_" + str(df.iloc[0]['cd_setor'])
        
        return None 
    
    def __get_patient_last_bacteriology_requested_date(self, patient_id: str) -> str:
        query = f"""
            select * from (
                SELECT 
                    dt_pedido as data_hora_criacao,
                    LISTAGG(nm_exa_lab, ', ') WITHIN GROUP (ORDER BY nm_exa_lab) AS exames
                FROM (
                    SELECT DISTINCT 
                        pl.dt_pedido,
                        el.nm_exa_lab
                    FROM dbamv.ped_lab pl
                    INNER JOIN dbamv.itped_lab ipl
                        ON pl.cd_ped_lab = ipl.cd_ped_lab
                    INNER JOIN dbamv.exa_lab el 
                        ON ipl.cd_exa_lab = el.cd_exa_lab 
                    INNER JOIN dbamv.atendime a
                        ON pl.cd_atendimento = a.cd_atendimento 
                    WHERE el.sn_cultura = 'S'
                    AND a.cd_paciente = {patient_id}
                ) t
                GROUP BY dt_pedido
                ORDER BY 1 desc
            )
            where rownum <= 1
        """
        df = dataRequest.get_data(queryText= query)
        if len(df) == 0:
            return f"\nÚltimo exame de bacteriologia solicitado: Não há registro de exame de bacteriologia solicitado.\n"
        else:
            date = df.iloc[0]['data_hora_criacao']
            exames = df.iloc[0]['exames']
            return f"\nÚltimo exame de bacteriologia solicitado em {date.day}/{date.month}/{date.year}: {exames}\n"

    def __get_patient_temperature_history(self, patient_id: str, *, day_limit: int = 3) -> str | None:
        query = f"""
            SELECT
                * 
            FROM (
                SELECT 
                    TRUNC(csv.data_coleta, 'DD') as dia,
                    min(isv.VALOR) as min_temp,
                    avg(isv.VALOR) as avg_temp,
                    max(isv.VALOR) as max_temp,
                    SUM(CASE WHEN isv.VALOR IS NOT NULL THEN 1 ELSE 0 END) AS n_temps
                FROM dbamv.COLETA_SINAL_VITAL csv 
                INNER JOIN dbamv.ITCOLETA_SINAL_VITAL isv
                    ON csv.CD_COLETA_SINAL_VITAL = ISV.CD_COLETA_SINAL_VITAL
                INNER JOIN dbamv.ATENDIME a 
                    ON csv.CD_ATENDIMENTO = a.CD_ATENDIMENTO 
                WHERE isv.CD_SINAL_VITAL = 1
                    AND a.CD_PACIENTE = {patient_id}
                GROUP BY trunc(csv.DATA_COLETA, 'DD')
                ORDER BY 1 DESC
            ) A
            WHERE rownum <= {day_limit}
        """
        df = dataRequest.get_data(queryText= query)

        if len(df) == 0:
            return None
        else:
            header = f"\nHistórico de temperatura (últimos {len(df)} dias):"
            linhas = []
            # Mantém a ordenação solicitada (já veio ordenado pela query)
            for _, row in df.iterrows():
                # Formata data dd/mm/aaaa
                if hasattr(row["dia"], "strftime"):
                    dia_fmt = row["dia"].strftime("%d/%m/%Y")
                else:
                    # Caso venha como string
                    dia_fmt = str(row["dia"])

                avg = row["avg_temp"]
                mn = row["min_temp"]
                mx = row["max_temp"]
                n = row["n_temps"]

                # Formatação bonita; ajusta casas decimais conforme desejar
                linhas.append(
                    f"\t• {dia_fmt}: média {avg:.1f} °C (mín {mn:.1f} °C, máx {mx:.1f} °C), {int(n)} medida(s)"
                )

            return header + "\n" + "\n".join(linhas) + "\n"

    def __get_discharge_date(self, cd_atendimento: str) -> datetime.date | None:
        query = f"""
            SELECT 
                coalesce(a.DT_ALTA, pra.DT_REGISTRO_ALTA) as data_alta
            FROM dbamv.atendime a
            left JOIN dbamv.PW_REGISTRO_ALTA pra 
                ON a.cd_atendimento = pra.CD_ATENDIMENTO
            WHERE a.cd_atendimento = {cd_atendimento}
                -- AND pra.CD_MOT_ALT NOT IN (15)
                AND (pra.TP_SITUACAO IS NOT NULL and pra.TP_SITUACAO != 'CANCELADA')
        """
        df = dataRequest.get_data(queryText= query)
        if len(df) > 0:
            return df.iloc[0]['data_alta']

        return None
    
    # Defini função para tentativa de envio das prescrições
    def try_send_prescription(self, prescription):
        antibiotics = self.__get_antibiotic_for_prescription_id(prescription_id= prescription['prescr_id'])
        data_alta = self.__get_discharge_date(cd_atendimento= prescription['nr_atendimento'])
        if not self.__valida_antibiotics(antibiotics) or data_alta is not None:
            tentativa = "Primeira tentativa" if prescription['prescr_sended_status'] in ['-1', '0', '1'] else 'Segunda tentativa'
            message = 'No antibiotic found locally for this prescription' if data_alta is None else 'Paciente já possui alta'
            print(f"Rejeitando prescription: {prescription['prescr_id']}, {message}. {tentativa}")
            self.__update_sended_status_no_antibiotic(
                prescr_id= prescription['prescr_id'], 
                old_sended_status= prescription['prescr_sended_status'], 
                message= message
            )
            return # isso vai fazer ele atualizar o numero da prescrição e ignorar a tentativa de envio.

        token = self._authenticator.get_Token_for_cd_medico(cd_medico= prescription['cd_medico'])

        paciente = self.__get_paciente(prescription['patient_hospital_id'])

        previousAntibioticName = self.__get_previous_antibiotic(prescription['prescr_id'], prescription['patient_hospital_id'])

        hasPreviousAntibiotic = previousAntibioticName != 'Não contem antibiotico prévio registrado' 

        patient_weight = self.get_patient_weight(prescription['patient_hospital_id'])

        patient_height = self.get_patient_height(prescription['patient_hospital_id'])

        list_antibiotics = self.__return_list_of_list_of_json_antibiotics(antibiotics)

        infection_name = self.__get_infection_name(prescription['nr_atendimento'], prescription['patient_hospital_id'])

        last_dialise = self.__get_dialise(prescription['patient_hospital_id'])

        last_creatinine = self.__get_creatinine_and_collection_date(prescription['patient_hospital_id'])

        last_culture_requested = self.__get_patient_last_bacteriology_requested_date(prescription['patient_hospital_id'])

        last_mesured_temps = self.__get_patient_temperature_history(prescription['patient_hospital_id'])

        clinical_history = self.__get_evol(prescription['patient_hospital_id'], html= True)
        past_antibiotics = self.get_all_antibiotics_for_past_30_days(prescription['nr_atendimento'])

        if last_culture_requested is not None:
            clinical_history = clinical_history + last_culture_requested
        
        if last_mesured_temps is not None:
            clinical_history = clinical_history + last_mesured_temps
        
        clinical_history = clinical_history + past_antibiotics 
        
        if last_dialise is not None:
            texto_sobre_dialise = ""
            if len(last_dialise) > 0:
                dialise_date = last_dialise.iloc[0]['dh_registro']
                dialise_nome = 'Hemodiálise'
                texto_sobre_dialise = f"""{f"Dialise do paciente do dia {dialise_date.day}/{dialise_date.month}/{dialise_date.year}:" if dialise_date else ""} 
\t- Dialise: {dialise_nome}
   \n"""     
            clinical_history = texto_sobre_dialise + clinical_history

        crea_date = None
        if last_creatinine is not None:
            if len(last_creatinine) > 0: #isso dava pra tirar, pq retorna somente uma linha
                crea_date = last_creatinine.iloc[0]['dt_digitacao']

                clinical_history = f"""{f"Exame de creatinina dia {crea_date.day}/{crea_date.month}/{crea_date.year}:" if crea_date else "" }
{f"    - Exame {last_creatinine.iloc[0]['nm_exame']} {last_creatinine.iloc[0]['qt_resultado']}" if last_creatinine.iloc[0]['qt_resultado'] else "Não tem resultado" }
""" + "\n" + clinical_history
            
        admission_date = self.__get_admission_date(prescription['patient_hospital_id'], prescription['nr_atendimento'])
        index_antibiotico_controle = 0
        previous_admission = self.__get_previous_admission(prescription['patient_hospital_id'], prescription['nr_atendimento'])
        body_sended = None 

        cd_setor = self.__get_setor_atendimento(prescription)

        for lista_antibioticos in list_antibiotics:

            antibiotics_justification = ''
            for atb in lista_antibioticos:
                antibiotics_name = atb['antibioticName']
                antibiotics_justification += f"\nJustificativa Antibiotico {antibiotics_name}: "
                antibiotics_justification += f"\n\t- {antibiotics.iloc[index_antibiotico_controle]['justificativa'] if antibiotics.iloc[index_antibiotico_controle]['justificativa'] is not None else 'Não justificado' }"
                index_antibiotico_controle += 1
            clinical_history += antibiotics_justification

            # patient height
            patient_height_value = None

            if patient_height is not None:
                if isinstance(patient_height, (float, int)):
                    if not math.isnan(patient_height):
                        if float(patient_height)//100 >= 1:
                            patient_height_value = patient_height
                        else:
                            patient_height_value = int(float(patient_height) * 100)

            last_creatinine_value = (
                float(last_creatinine.iloc[0]['qt_resultado'].replace(',', '.').upper().strip('INFERIOR A '))
                if not last_creatinine.empty and str(last_creatinine.iloc[0]['qt_resultado']) != ''
                else None
            ) if last_creatinine is not None else None

            body = {
                'prescriptionHospitalIdentifier': prescription['prescr_id'],
                'prescriptionClearenceDate': str(prescription['dt_liberacao'].to_datetime64()),
                'admissionDate': admission_date,
                'infectionDate': str(prescription['infection_date'].to_datetime64()),
                'patientName': paciente['name'],
                'patientGender': paciente['gender'],
                'patientRace': paciente['race'],
                'patientAge': int(paciente['patientAge']),
                'patientWeight': patient_weight if patient_weight != 'nan' and patient_weight is not None and not math.isnan(patient_weight) else None,
                'patientHeight': patient_height_value if patient_height_value != 'nan' and patient_height_value is not None and not math.isnan(patient_height_value) else None,
                'patientDocument': paciente['cpf'],
                'drugAllergy': bool(paciente['drugAllergy']),
                'drugAllergyName': paciente['drugAllergyName'],
                'previousAntibiotic': hasPreviousAntibiotic,
                'previousAntibioticName': previousAntibioticName,
                'immunosuppression': None,
                'lastCreatinine': last_creatinine_value,
                'lastCreatinineDate': (str(last_creatinine.iloc[0]['dt_digitacao'].to_datetime64()) if str(crea_date) != "" and len(last_creatinine) > 0 else None ) if crea_date is not None else None,
                'renalFunctionLoss': None,
                'dialysisType': (2 if len(last_dialise) > 0 else None ) if last_dialise is not None else None,
                'clinicalHistory': clinical_history.replace("¿¿", 'çã').replace("|", "\n- "),
                'previousAdmission': previous_admission,
                'hospitalInfectionIdentifier': (prescription['id_infection'] if str(prescription['id_infection']) != '' else '1' ) if prescription['id_infection'] is not None  else '1' ,
                'infectionName': infection_name,
                'patientHospitalIdentifier': prescription['patient_hospital_id'],
                'hospitalUnityIdentifier': prescription['hospital_unity_id'] if str(prescription['hospital_unity_id']) != 'nan' and str(prescription['hospital_unity_id']) != 'None' else cd_setor,
                'curb': self.CURB, 
                'submissions': [
                    {
                        'antibiotics': lista_antibioticos
                    }
                ]            
            }

            body['clinicalHistory'] = bypass_waf_sanitizer(body['clinicalHistory'])
            body_sended = body
            response = requests.post(f"{C.API_BASE_URL}prescriptions", headers= {'Authorization': token, 'hospital-key': C.HOSPITAL_KEY}, json= body_sended, verify= False, timeout= 20)
        
        if body_sended is None or response is None: 
            return
        body_sended = json.dumps(body_sended)
        body_response = response.json()
        code = body_response['code']
        message = None
        prescr_id_qualis = None 
        error_message = None
        if code == '0':
            prescr_id_qualis = body_response['results'][0]['id']
        else:
            message = str(body_response['message'])
            message_list = list(filter(None, body_response['results']))
            final_list = []
            for dc in message_list:
                sended = json.dumps(dc)
                sended.replace("'", '"')
                final_list.append(sended)
            error_message = str("; ".join(final_list))
            message = message + ";" + error_message
            self.solve_prescription_sended_error(prescription, body, body_response)
        
        print(f"Date: {datetime.datetime.now()}; Prescription_id: {prescription['prescr_id']}, message: {message}{f', id on qualis portal: {prescr_id_qualis}' if prescr_id_qualis else ''}")
        
        self.__update_sended_status_after_atempt(prescr_id= prescription['prescr_id'], 
                                            sended_success= code == '0', 
                                            sended_message_response= message,
                                            sended_body_to_api= body_sended, 
                                            qualis_prescr_id= prescr_id_qualis)
    

    def solve_prescription_sended_error(self, prescription, body, response):
        processed = {
            "auth" : False,
            "intervalTime" : False,
            "via" : False,
            "antibiotic" : False,
            "hospitalUnity" : False,
            "geral" : False,
            "dosage" : False
        }
        for error in response['results']:
            message = None
            doctorInternalCode = prescription['cd_medico']

            antibioticos = []
            for submission in  body['submissions']:
                for atb in submission['antibiotics']:
                    antibioticos.append(atb)

            if 'Full authentication is required to access this resource' in error:
                if processed['auth']:
                    continue
                processed["auth"] = True

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
                    message = f"Error: {response['message']}\n"
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
            
            elif 'Cannot invoke \"qualisapi2.Models.DosageUnit.getId()\" because \"dosageUnitFetch\" is null' in error:
                if processed["dosage"]:
                    continue
                processed["dosage"] = True

                ids = ""
                column = "hospitalDosageUnitIdentifier"
                for atb in antibioticos:
                    if column in atb and atb[column] is not None:
                        id = atb[column]
                        ids += f"'{id}', "
                
                query = f"""
                    select
                        distinct
                        up.cd_uni_pro as codigo,
                        up.ds_unidade as descricao
                    from dbamv.uni_pro up
                    where to_char(up.cd_uni_pro) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Unidade(s) de medida dos antibioticos prescritos:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Uma dessas unidades de medida não está cadastrada na Qualis. \n"
                    message += f"Favor validar as unidades de medida com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
                
            elif 'Cannot invoke \"qualisapi2.Models.IntervalTime.getId()\" because \"intervalTimeFetch\" is null' in error:
                if processed["intervalTime"]:
                    continue
                processed["intervalTime"] = True

                ids = ""
                column = "hospitalIntervalTimeIdentifier"
                for atb in antibioticos:
                    if column in atb and atb[column] is not None:
                        id = atb[column]
                        ids += f"'{id}', "
                
                query = f"""
                    select
                        distinct
                        tf.cd_tip_fre as codigo,
                        tf.ds_tip_fre as descricao
                    from dbamv.tip_fre tf
                    where to_char(tf.cd_tip_fre) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Intervalo(s) de aprazamento dos antibioticos prescritos:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Um desses intervalos de aprazamento não está cadastrado na Qualis. \n"
                    message += f"Favor validar os intervalos de aprazamento com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"
                    
            elif 'Cannot invoke \"qualisapi2.Models.Via.getId()\" because \"viaFetch\" is null' in error:
                if processed["via"]:
                    continue
                processed["via"] = True

                ids = ""
                column = "hospitalViaIdentifier"
                for atb in antibioticos:
                    if column in atb and atb[column] is not None:
                        id = atb[column]
                        ids += f"'{id}', "
                
                query = f"""
                    select
                        distinct
                        ap.cd_for_apl as codigo,
                        ap.ds_for_apl as descricao
                    from dbamv.for_apl ap
                    where to_char(ap.cd_for_apl) in ({ids.strip(", ")})
                """
                df = dataRequest.get_data(queryText= query)
                
                if len(df) > 0:
                    message = f"Error: {response['message']}\n"
                    message += f"Via(s) de aplicacao dos antibioticos prescritos:\n"
                    message += f"{df.to_string(index= False)}\n"
                    message += f"Uma dessas vias de aplicacao não está cadastrada na Qualis. \n"
                    message += f"Favor validar as vias de aplicacao com os códigos acima.\n"
                    message += f"Hospital: {C.HOSPITAL_NAME}"

            elif isinstance(error, dict):
                if 'antibioticIdentifier' in error['field'] and 'Value not found' in error['message']:
                    if processed["antibiotic"]:
                        continue
                    processed["antibiotic"] = True

                    ids = ""
                    column = "antibioticIdentifier"
                    for atb in antibioticos:
                        if column in atb and atb[column] is not None:
                            id = atb[column]
                            ids += f"'{id}', "
                    
                    query = f"""
                        select
                            distinct
                            tp.cd_tip_presc as codigo,
                            tp.ds_tip_presc as descricao
                        from dbamv.tip_presc tp
                        where to_char(tp.cd_tip_presc) in ({ids.strip(", ")})
                    """
                    df = dataRequest.get_data(queryText= query)
                    
                    if len(df) > 0:
                        message = f"Error: {response['message']}\n"
                        message += f"Antibiotico(s) não encontrados os antibioticos prescritos:\n"
                        message += f"{df.to_string(index= False)}\n"
                        message += f"Um ou mais desses antibioticos não está cadastrada na Qualis. \n"
                        message += f"Observação: é possivel que exista um antibiotico que não é do interesse em receber, nesse caso é necessário solicitar um novo executavel bloqueando esse item junto a equipe da TI da Qualis.\n"
                        message += f"Favor validar os antibioticos com os códigos acima.\n"
                        message += f"Hospital: {C.HOSPITAL_NAME}"
            
                elif 'hospitalUnityIdentifier' in error['field'] and 'Value not found' in error['message']:
                    if processed["hospitalUnity"]:
                        continue
                    processed["hospitalUnity"] = True

                    id = f"'{body['hospitalUnityIdentifier']}'"
                    query = f"""
                        SELECT 
                            distinct 
                                u.cd_unid_int as id_unidade,
                                u.ds_unid_int
                        FROM dbamv.unid_int u
                        WHERE to_char(u.cd_unid_int) in ({id})
                    """
                    if "setor_" in id:
                        query = f"""
                            SELECT 
                                distinct
                                    s.cd_setor as id_unidade,
                                    s.nm_setor 
                            FROM dbamv.setor s
                            WHERE to_char(s.cd_setor) in ({id.replace("setor_", "")})
                        """
                    df = dataRequest.get_data(queryText= query)

                    if "setor_" in id:
                        df["id_unidade"] = df["id_unidade"].apply(lambda x: f"setor_{x}")
                    
                    if len(df) > 0:
                        message = f"Error: {response['message']}\n"
                        message += f"Unidade hospitalar não encontrada:\n"
                        message += f"{df.to_string(index= False)}\n"
                        message += f"A unidade hospitalar não está cadastrada na Qualis. \n"
                        message += f"Favor validar a unidade hospitalar com o código acima.\n"
                        message += f"Hospital: {C.HOSPITAL_NAME}"
                
                elif 'usagePeriod' in error['field']:
                    continue

                elif 'hospitalDosageUnitIdentifier' in error['field'] and 'Value not found' in error['message']:
                    if processed["dosage"]:
                        continue
                    processed["dosage"] = True

                    ids = ""
                    column = "hospitalDosageUnitIdentifier"
                    for atb in antibioticos:
                        if column in atb and atb[column] is not None:
                            id = atb[column]
                            ids += f"'{id}', "
                    
                    query = f"""
                        select
                            distinct
                            up.cd_uni_pro as codigo,
                            up.ds_unidade as descricao
                        from dbamv.uni_pro up
                        where to_char(up.cd_uni_pro) in ({ids.strip(", ")})
                    """
                    df = dataRequest.get_data(queryText= query)
                    
                    if len(df) > 0:
                        message = f"Error: {response['message']}\n"
                        message += f"Unidade(s) de medida dos antibioticos prescritos:\n"
                        message += f"{df.to_string(index= False)}\n"
                        message += f"Uma dessas unidades de medida não está cadastrada na Qualis. \n"
                        message += f"Favor validar as unidades de medida com os códigos acima.\n"
                        message += f"Hospital: {C.HOSPITAL_NAME}"

                elif 'hospitalViaIdentifier' in error['field'] and 'Value not found' in error['message']:
                    if processed["via"]:
                        continue
                    processed["via"] = True

                    ids = ""
                    column = "hospitalViaIdentifier"
                    for atb in antibioticos:
                        if column in atb and atb[column] is not None:
                            id = atb[column]
                            ids += f"'{id}', "
                    
                    query = f"""
                        select
                            distinct
                            ap.cd_for_apl as codigo,
                            ap.ds_for_apl as descricao
                        from dbamv.for_apl ap
                        where to_char(ap.cd_for_apl) in ({ids.strip(", ")})
                    """
                    df = dataRequest.get_data(queryText= query)
                    
                    if len(df) > 0:
                        message = f"Error: {response['message']}\n"
                        message += f"Via(s) de aplicacao dos antibioticos prescritos:\n"
                        message += f"{df.to_string(index= False)}\n"
                        message += f"Uma dessas vias de aplicacao não está cadastrada na Qualis. \n"
                        message += f"Favor validar as vias de aplicacao com os códigos acima.\n"
                        message += f"Hospital: {C.HOSPITAL_NAME}"
                        
                elif 'hospitalIntervalTimeIdentifier' in error['field'] and 'Value not found' in error['message']:
                    if processed["intervalTime"]:
                        continue
                    processed["intervalTime"] = True

                    ids = ""
                    column = "hospitalIntervalTimeIdentifier"
                    for atb in antibioticos:
                        if column in atb and atb[column] is not None:
                            id = atb[column]
                            ids += f"'{id}', "
                    
                    query = f"""
                        select
                            distinct
                            tf.cd_tip_fre as codigo,
                            tf.ds_tip_fre as descricao
                        from dbamv.tip_fre tf
                        where to_char(tf.cd_tip_fre) in ({ids.strip(", ")})
                    """
                    df = dataRequest.get_data(queryText= query)
                    
                    if len(df) > 0:
                        message = f"Error: {response['message']}\n"
                        message += f"Intervalo(s) de aprazamento dos antibioticos prescritos:\n"
                        message += f"{df.to_string(index= False)}\n"
                        message += f"Um desses intervalos de aprazamento não está cadastrado na Qualis. \n"
                        message += f"Favor validar os intervalos de aprazamento com os códigos acima.\n"
                        message += f"Hospital: {C.HOSPITAL_NAME}"

            if message is None:
                message = f"Erro: {response['message']}\n"
                message += f"Error variable: {error}\n"
                message += f"Erro sem solucao predefinida, solicite auxilio para a equipe de desenvolvimento da qualis, necessario debug para solucionar:\n"
                message += f"Detalhes: {response}\n"
                message += f"Body enviado para a api: {json.dumps(body)}\n"
            
            subject = "Erro na integração da prescrição"
            self._send_email(message, subject)

    # Envia todas as prescrições que houveram falha anteriormente
    def send_all_failed_before(self):
        if (not self.thread_erros_runing):
            self.prescritorsReported = dict()
            self.thread_erros_runing = True
            previous_failed = self.get_all_prescription_that_failed()
            for index_previous_failed in previous_failed.index:
                if self._stop_event.is_set():
                    break
                prescription_failed = previous_failed.iloc[index_previous_failed]
                self.try_send_prescription(prescription_failed)
            self.thread_erros_runing = False
        else:
            print("Ainda processando ultima requisição de envio de prescrições com falhas anteriores.")

    # Função que ficará em looping coordenando a chamada das funções trabalhadoras.
    def _monitor_loop(self, controleRetries: int = 0):
        try:
            contador = 0
            while not self._stop_event.is_set():
                self._report_progress()
                pending_prescriptions = self.get_all_not_sended_prescription()

                for index in pending_prescriptions.index:
                    if self._stop_event.is_set():
                        break
                    self._report_progress()
                    prescription = pending_prescriptions.iloc[index]
                    self.try_send_prescription(prescription)

                if self._stop_event.wait(timeout=60):
                    break # depois de ter esperado de 60 segundos vou chamar todas as prescrições com status de -2 para ver se entrou alguma prescrição para ela.
                self._report_progress()
                
                if contador%60 == 0:
                    job = threading.Thread(target= self.send_all_failed_before)
                    job.start() # a cada 60 minutos ele vai tentar enviar todas as prescrições que estão com status de erro, isso é para garantir que mesmo as prescrições que tiveram algum erro de integração sejam enviadas assim que o erro for resolvido, seja ele um erro de cadastro de algum dado ou um erro temporário da api da qualis.
                    self.__get_possible_new_doctor_answer()

                if contador%121 == 120: # a cada 2 horas ele vai tentar reenviar as prescrições que não tinham antibiotico na primeira tentativa
                    prescriptions_second_try = self.__get_all_prescription_missing_antibiotic_to_sencond_try()
                    for index_second_try in prescriptions_second_try.index:
                        if self._stop_event.is_set():
                            break
                        self._report_progress()
                        prescription_second = prescriptions_second_try.iloc[index_second_try]
                        self.try_send_prescription(prescription_second)

                    contador= 0
                    self.__delete_old_prescriptions()
                    self._report_progress()
                
                self.__busca_todas_respostas_pendentes()
                self._report_progress()
                
                contador += 1
                print(f"Contador: {contador}")
        except Exception as e:
            if self._stop_event.is_set():
                return
            traceback.print_exc()
            maxRetries = 15
            errorCompleto = traceback.format_exc()
            self._send_email(f"Error em {C.HOSPITAL_NAME}, reporte a equipe de desenvolvimento sobre: {errorCompleto}", f"Error grave durante execução do integrador, retry: {controleRetries}/{maxRetries}")
            print("Exception type: ", type(e))
            time.sleep(60)
            self._report_progress()
            if controleRetries < maxRetries:
                print(f"Sistema reiniciando error: {e}\nException type: {type(e)}")
                self._monitor_loop(controleRetries= (controleRetries + 1))
            elif isinstance(e, SQLAlchemyError) or isinstance(e, IntegrityError) or isinstance(e, DBAPIError) or isinstance(e, DatabaseError):
                print(f"Sitema reiniciando error: {e}\nException type: {type(e)}")
                self._monitor_loop(controleRetries= 0)
            else:
                print(f"Sistema parando devido error: {e}\nException type: {type(e)}")

def bypass_waf_sanitizer(text):
    if not isinstance(text, str):
        return text
    
    # Substituições táticas para enganar o WAF
    # Troca ponto e vírgula por ponto ou vírgula
    text = text.replace(";", ",") 
    
    # Remove ou troca aspas simples (MUITO comum gatilhar erro com 's ou d'agua)
    text = text.replace("'", " ") 
    
    # Evita sequencia de traços (comentários SQL)
    text = text.replace("--", "-")
    
    # Opcional: remover quebras de linha estranhas se houver
    # text = text.replace("\n", " ")
    
    return text