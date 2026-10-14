from Utils import dataRequest
from Utils import Constant as C
import time
import requests

class Authenticator:
    def __init__(self):
        self.codigo_medico_token_date: dict = { }
        self.codigo_medico_token: dict = { }
    
    # Função para buscar token de authorização do usuário
    def get_Token_for_cd_medico(self, cd_medico: str) -> str | None:
        def get_Token_from_API(self, cd_medico: str) -> str:
            # Para pegar a informação do login e senha do medico fazendo a prescricão
            query = f"""
                SELECT 
                    DS_CODIGO_CONSELHO AS crm
                FROM dbamv.prestador 
                WHERE cd_prestador = {cd_medico}
            """
            crm = ''
            users = dataRequest.get_data(queryText= query)
            if users is not None:   
                if len(users) > 0:
                    crm = str(users.iloc[0]["crm"]).strip()
            url = f"{C.API_BASE_URL}authenticate/v2?hospital_doctor_identifier={cd_medico}&crm={crm}"
            response = requests.post(url, verify= False, headers= {'hospital-key' : C.HOSPITAL_KEY})
            # transforma o body do response para json

            result = response.json()
            result = result["results"][0]
            # verificando que tivemos um retorno positivo.
            if response.status_code == 200:
                # pega o token dentro do result
                token = result["token"]
                # salva o token na cache
                self.codigo_medico_token_date[cd_medico] = time.time()
                self.codigo_medico_token[cd_medico] = token
                return token
            else:
                # não foi possivel pegar o token levana um erro para imprimir que houve falha ao buscar o token do medico junto da api
                raise Exception(f"Falha ao solicitar authenticação do medico, retorno: {result}")
        try:
            # Eu verifico primeiro se eu já busquei token para esse medico, caso contrario vou buscar o token para ele.
            if cd_medico in self.codigo_medico_token_date:
                date_token = self.codigo_medico_token_date[cd_medico]
                date_now = time.time()
                # vou validar se tem menos de 11 horas e 50 minutos que esse token foi gerado, caso contrario vou solicitar a api o novo token
                if (date_now - date_token) > 42480.0:
                    return get_Token_from_API(self= self, cd_medico= cd_medico)
                else:
                    # Como o token tem mais de 11 hrs e 50 minutos de vida, vou buscar um novo token
                    return self.codigo_medico_token[cd_medico]
            else:
                # Como nunca busquei um token para esse medico, vou busca-lo junto da api
                return get_Token_from_API(self= self, cd_medico= cd_medico)
        except Exception as e:
           print(f"Não foi possivel pegar token para medico: {cd_medico}, with error: {e}")

