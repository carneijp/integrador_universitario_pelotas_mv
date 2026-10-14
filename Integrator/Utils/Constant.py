HOSPITAL_NAME = "Unimed Centro Sul Fluminense"
HOSPITAL_KEY = "467676fcb1d22bb8873990b401b06c30" # Unimed Centro Sul Fluminense
API_BASE_URL = "https://api.portalqualis.com.br/api/"
#TODO: LANÇAR NO CLOUDFARE E ADICIONAR O LINK DA API NA VARIÁVEL ABAIXO
BOT_BASE_URL = "https://qualiswhat.carneijp.uk/api"

import sqlalchemy as sa
from urllib.parse import quote_plus

# TESTE
# username = 'dbamv'
# password = quote_plus('db!csf.248')
# ip = 'dbtst1.1308.cloudmv.com.br'
# port  = 1521
# service_name = 'tst11308.db1308.mv1308vcn.oraclevcn.com'

# PROD
username = 'qualis'
password = quote_plus(',s29TpB`7iP]')
ip = 'dbprd.1308.cloudmv.com.br'
port  = 1521
service_name = 'prd1308.db1308.mv1308vcn.oraclevcn.com'

DATABASE_SOURCE = sa.create_engine(
    f"oracle+cx_oracle://{username}:{password}@{ip}:{port}/?service_name={service_name}&encoding=UTF-8&nencoding=UTF-8",
    insertmanyvalues_page_size = 10000,
    pool_pre_ping = True, 
    pool_timeout = 3600, 
    pool_size = 0,
    #echo_pool = 'debug',
    max_overflow = 0,
    pool_recycle = 20
)

remediosignorarids = []